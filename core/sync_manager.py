"""
Position sync manager: synchronises local portfolio with exchange,
applies trailing/breakeven, partial close, trailing take profit,
corrects TP/SL orders, enforces maximum position limit, records closed trades,
and supports smart replacement of weakest positions.
Optimised for micro-mode: reduces API calls, respects rate limits.
Fixed: only cancels/recreates TP/SL when truly needed, with tolerance.
Also fixed int/float conversion for order quantities.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Optional

from core.portfolio import Position, TradeRecord

logger = logging.getLogger(__name__)


class PositionSyncManager:
    def __init__(self, engine):
        self.engine = engine
        self._tpsl_cache = {}

    @staticmethod
    def _is_tpsl_already_exists_error(exception: Exception) -> bool:
        try:
            error_str = str(exception)
            match = re.search(r'\{.*"code":\s*(\d+).*\}', error_str)
            if match:
                code = int(match.group(1))
                return code in (110406, 110407)
        except Exception:
            pass
        return 'already exists' in str(exception).lower()

    def full_sync(self):
        if self.engine.auth.demo_mode:
            return
        # В микро-режиме не делаем полную синхронизацию слишком часто
        balance = self.engine.portfolio._balance or 0.0
        if balance < 100:
            logger.debug("Full sync skipped in micro-mode")
            return

        try:
            api_positions = self.engine.api.get_positions()
            self.engine.portfolio.clear()
            for p in api_positions:
                pos_side = p.get('positionSide', 'LONG')
                symbol = p.get('symbol', '')
                entry = float(p.get('avgPrice', p.get('entryPrice', 0)))
                qty = abs(float(p.get('positionAmt', 0)))
                lev = float(p.get('leverage', 1))
                tp_price, sl_price = self._fetch_exchange_tpsl(symbol, pos_side)
                tp_price, sl_price = self._logical_check(pos_side, entry, tp_price, sl_price)

                if tp_price is None or sl_price is None or sl_price <= 0:
                    atr = self.engine._get_current_atr(symbol)
                    trade_side = 'BUY' if pos_side == 'LONG' else 'SELL'
                    sl_tp = self.engine.risk_manager.get_sl_tp_levels(entry, trade_side, atr, symbol)
                    tp_price = tp_price or sl_tp['tp2']
                    sl_price = sl_price if (sl_price is not None and sl_price > 0) else sl_tp['sl']

                if qty > 0:
                    pos = Position(
                        symbol=symbol, side=pos_side, entry_price=entry,
                        quantity=qty, leverage=lev,
                        margin=(qty * entry) / lev,
                        tp_price=tp_price, sl_price=sl_price,
                        open_time=datetime.now(timezone.utc).isoformat()
                    )
                    self.engine.portfolio.add_position(pos)
                    self._tpsl_cache[f"{symbol}_{pos_side}"] = {
                        'tp': tp_price, 'sl': sl_price, 'qty': qty
                    }

            self._remove_duplicate_positions()
            self._enforce_limit()
        except Exception as e:
            logger.error(f"Full sync failed: {e}")

    def background_sync(self):
        if self.engine.auth.demo_mode:
            return

        try:
            api_positions = self.engine.api.get_positions()
            api_keys = {f"{p.get('symbol')}_{p.get('positionSide')}" for p in api_positions if abs(float(p.get('positionAmt', 0))) > 0}

            # Удаляем локальные позиции, которых нет на бирже
            for pos in list(self.engine.portfolio.get_positions()):
                if f"{pos.symbol}_{pos.side}" not in api_keys:
                    logger.info(f"Sync: removing position {pos.symbol} {pos.side} (no longer on exchange)")
                    self.engine.portfolio.remove_position(pos.symbol, pos.side)
                    cache_key = f"{pos.symbol}_{pos.side}"
                    if cache_key in self._tpsl_cache:
                        del self._tpsl_cache[cache_key]

            # Обрабатываем позиции, которые есть на бирже
            for p in api_positions:
                pos_side = p.get('positionSide', 'LONG')
                symbol = p.get('symbol', '')
                entry = float(p.get('avgPrice', p.get('entryPrice', 0)))
                qty = abs(float(p.get('positionAmt', 0)))
                lev = float(p.get('leverage', 1))
                current_price = float(p.get('markPrice', 0))
                unrealized = float(p.get('unrealizedProfit', 0))

                if qty == 0:
                    continue

                existing = next((pos for pos in self.engine.portfolio.get_positions()
                                 if pos.symbol == symbol and pos.side == pos_side), None)

                if existing:
                    existing.unrealized_pnl = unrealized
                    if existing.margin > 0:
                        existing.pnl_pct = (unrealized / existing.margin) * 100

                    # Трейлинг стоп
                    if current_price > 0 and existing.sl_price is not None:
                        if self.engine.trailing_sl_enabled:
                            if not hasattr(self.engine, 'adaptive_trailing_stop'):
                                from core.adaptive_trailing_stop import AdaptiveTrailingStop
                                self.engine.adaptive_trailing_stop = AdaptiveTrailingStop(self.engine)
                            updated = self.engine.adaptive_trailing_stop.update(existing, current_price)
                            if updated:
                                self._sync_tpsl_orders(
                                    symbol, pos_side, existing.quantity,
                                    existing.tp_price, existing.sl_price
                                )

                        if self.engine.breakeven_enabled:
                            atr = self.engine._get_current_atr(symbol)
                            self.engine.executor.apply_breakeven(existing, current_price, atr)

                    # Трейлинг TP
                    if hasattr(self.engine, 'trailing_tp') and self.engine.trailing_tp:
                        if existing.tp_price and existing.tp_price > 0:
                            updated = self.engine.trailing_tp.update(existing, current_price)
                            if updated:
                                self.engine.trailing_tp.sync_order(
                                    symbol, pos_side, existing.quantity, existing.tp_price
                                )

                    # Частичное закрытие
                    if self.engine.partial_close_enabled and existing.tp_price is not None:
                        self.engine.executor.apply_partial_close(existing, current_price)

                    # Синхронизация TP/SL
                    self._sync_tpsl_orders(symbol, pos_side, existing.quantity,
                                           existing.tp_price, existing.sl_price)
                else:
                    # Новая позиция – добавляем
                    atr = self.engine._get_current_atr(symbol)
                    trade_side = 'BUY' if pos_side == 'LONG' else 'SELL'
                    sl_tp = self.engine.risk_manager.get_sl_tp_levels(entry, trade_side, atr, symbol)
                    pos = Position(
                        symbol=symbol, side=pos_side, entry_price=entry,
                        quantity=qty, leverage=lev,
                        margin=(qty * entry) / lev,
                        tp_price=sl_tp['tp2'], sl_price=sl_tp['sl'],
                        open_time=datetime.now(timezone.utc).isoformat()
                    )
                    self.engine.portfolio.add_position(pos)
                    self._tpsl_cache[f"{symbol}_{pos_side}"] = {
                        'tp': sl_tp['tp2'], 'sl': sl_tp['sl'], 'qty': qty
                    }

            self._remove_duplicate_positions()
            self._enforce_limit()

        except Exception:
            logger.exception("Background sync crashed")

    def _remove_duplicate_positions(self):
        positions = self.engine.portfolio.get_positions()
        symbols_seen = set()
        for pos in list(positions):
            if pos.symbol in symbols_seen:
                logger.warning(f"Duplicate position detected for {pos.symbol}, closing {pos.side}")
                try:
                    self.engine.api.close_position(pos.symbol, pos.side)
                except Exception as e:
                    logger.error(f"Failed to close duplicate {pos.symbol} {pos.side}: {e}")
                self.engine.portfolio.remove_position(pos.symbol, pos.side)
                cache_key = f"{pos.symbol}_{pos.side}"
                if cache_key in self._tpsl_cache:
                    del self._tpsl_cache[cache_key]
            else:
                symbols_seen.add(pos.symbol)

    def _enforce_limit(self):
        positions = self.engine.portfolio.get_positions()
        max_pos = self.engine.max_positions
        if len(positions) <= max_pos:
            return
        positions.sort(key=lambda p: p.unrealized_pnl)
        to_close = positions[:-max_pos]
        for pos in to_close:
            try:
                logger.info(f"Enforcing limit: closing {pos.symbol} {pos.side} (PnL={pos.unrealized_pnl:.4f})")
                self.engine.api.close_position(pos.symbol, pos.side)
                self.engine.portfolio.remove_position(pos.symbol, pos.side)
            except Exception as e:
                logger.error(f"Failed to close {pos.symbol} during limit enforcement: {e}")

    def try_replace_weakest(self, new_signal_confidence: float, new_signal_symbol: str) -> bool:
        positions = self.engine.portfolio.get_positions()
        max_pos = self.engine.max_positions
        if len(positions) < max_pos:
            return True

        now = datetime.now(timezone.utc)
        for pos in positions:
            try:
                open_t = datetime.fromisoformat(pos.open_time)
                if (now - open_t).total_seconds() < 60:
                    return False
            except:
                pass

        scored = []
        for pos in positions:
            try:
                open_t = datetime.fromisoformat(pos.open_time)
                hours_held = (now - open_t).total_seconds() / 3600.0
            except Exception:
                hours_held = 99.0
            if pos.tp_price and pos.entry_price:
                if pos.side == 'LONG' and pos.tp_price != pos.entry_price:
                    progress = (pos.sl_price - pos.entry_price) / (pos.tp_price - pos.entry_price) if pos.tp_price != pos.entry_price else 0
                elif pos.side == 'SHORT' and pos.tp_price != pos.entry_price:
                    progress = (pos.entry_price - pos.sl_price) / (pos.entry_price - pos.tp_price) if pos.entry_price != pos.tp_price else 0
                else:
                    progress = 0.0
            else:
                progress = 0.0
            score = progress * 0.7 - hours_held * 0.02
            scored.append((pos, score))

        if not scored:
            return False
        weakest_pos, weakest_score = min(scored, key=lambda x: x[1])

        if new_signal_confidence > 0.5 and (new_signal_confidence - 0.1) > weakest_score:
            logger.info(f"Smart replace: closing {weakest_pos.symbol} {weakest_pos.side} "
                        f"(score={weakest_score:.3f}) for new signal {new_signal_symbol} "
                        f"(conf={new_signal_confidence:.2f})")
            try:
                self.engine.api.close_position(weakest_pos.symbol, weakest_pos.side)
                self.engine.portfolio.remove_position(weakest_pos.symbol, weakest_pos.side)
                return True
            except Exception as e:
                logger.error(f"Smart replace failed: {e}")
                return False
        return False

    def _fetch_exchange_tpsl(self, symbol: str, pos_side: str):
        tp_price = None
        sl_price = None
        try:
            orders = self.engine.api.get_open_orders(symbol)
            for o in orders:
                if o.get('positionSide') != pos_side:
                    continue
                order_type = o.get('type', '')
                stop_price = o.get('stopPrice')
                if stop_price is None:
                    continue
                if order_type == 'TAKE_PROFIT_MARKET':
                    tp_price = float(stop_price)
                elif order_type == 'STOP_MARKET':
                    sl_price = float(stop_price)
        except Exception as e:
            logger.debug(f"Could not fetch open orders for {symbol}: {e}")
        return tp_price, sl_price

    def _logical_check(self, pos_side, entry, tp, sl):
        if pos_side == 'LONG':
            if tp is not None and tp <= entry:
                tp = None
            if sl is not None and sl >= entry:
                sl = None
            if tp is not None and sl is not None and tp < sl:
                tp, sl = sl, tp
        else:
            if tp is not None and tp >= entry:
                tp = None
            if sl is not None and sl <= entry:
                sl = None
            if tp is not None and sl is not None and tp > sl:
                tp, sl = sl, tp
        return tp, sl

    def _sync_tpsl_orders(self, symbol, pos_side, quantity, expected_tp, expected_sl):
        cache_key = f"{symbol}_{pos_side}"
        cached = self._tpsl_cache.get(cache_key)

        if cached and abs(cached['qty'] - quantity) < 1e-8:
            tp_close = True
            sl_close = True
            if expected_tp is not None and cached['tp'] is not None:
                if abs(expected_tp - cached['tp']) / max(abs(expected_tp), 1e-8) < 0.001:
                    tp_close = False
            if expected_sl is not None and cached['sl'] is not None:
                if abs(expected_sl - cached['sl']) / max(abs(expected_sl), 1e-8) < 0.001:
                    sl_close = False
            if not tp_close and not sl_close:
                return

        try:
            orders = self.engine.api.get_open_orders(symbol)
            for o in orders:
                if o.get('positionSide') != pos_side:
                    continue
                order_type = o.get('type', '')
                if order_type in ('TAKE_PROFIT_MARKET', 'STOP_MARKET'):
                    existing_price = float(o.get('stopPrice', 0))
                    order_qty = float(o.get('origQty', 0))
                    if order_type == 'TAKE_PROFIT_MARKET' and expected_tp is not None:
                        if abs(existing_price - expected_tp) / max(abs(expected_tp), 1e-8) < 0.001 and abs(quantity - order_qty) < 1e-8:
                            continue
                    elif order_type == 'STOP_MARKET' and expected_sl is not None:
                        if abs(existing_price - expected_sl) / max(abs(expected_sl), 1e-8) < 0.001 and abs(quantity - order_qty) < 1e-8:
                            continue
                    try:
                        self.engine.api.cancel_order(symbol, o.get('orderId', ''))
                        time.sleep(0.2)
                    except Exception as e:
                        logger.warning(f"Failed to cancel order {o.get('orderId')}: {e}")

            close_side = 'SELL' if pos_side == 'LONG' else 'BUY'
            if expected_tp is not None:
                try:
                    self.engine.api.place_order(
                        symbol=symbol, side=close_side, position_side=pos_side,
                        order_type='TAKE_PROFIT_MARKET', quantity=quantity,
                        stop_price=expected_tp
                    )
                except Exception as e:
                    if self._is_tpsl_already_exists_error(e):
                        logger.debug(f"TP already exists for {symbol}, skip")
                    else:
                        logger.error(f"TP order failed for {symbol}: {e}")

            if expected_sl is not None:
                if (pos_side == 'LONG' and expected_sl >= expected_tp) or \
                   (pos_side == 'SHORT' and expected_sl <= expected_tp):
                    logger.warning(f"Invalid SL {expected_sl} relative to TP {expected_tp}, skipping SL order")
                else:
                    try:
                        self.engine.api.place_order(
                            symbol=symbol, side=close_side, position_side=pos_side,
                            order_type='STOP_MARKET', quantity=quantity,
                            stop_price=expected_sl
                        )
                    except Exception as e:
                        if self._is_tpsl_already_exists_error(e):
                            logger.debug(f"SL already exists for {symbol}, skip")
                        else:
                            logger.error(f"SL order failed for {symbol}: {e}")

            self._tpsl_cache[cache_key] = {
                'tp': expected_tp, 'sl': expected_sl, 'qty': quantity
            }
        except Exception as e:
            logger.error(f"Failed to sync TP/SL orders for {symbol}: {e}")
