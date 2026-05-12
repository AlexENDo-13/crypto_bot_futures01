"""
Trade executor: places MARKET orders, handles TP/SL, trailing stop, breakeven, partial close.
Fixed: respects rate limits, handles 110406/110407 errors, auto-closes after timeout in micro-mode.
Added: fatal error codes (101204, 110424, etc.) prevent position creation.
Added: forced sync after auto-close.
"""
import time
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Optional

try:
    import winsound
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False

from core.portfolio import Position

logger = logging.getLogger(__name__)


def _round_to_precision(value: float, precision: int) -> float:
    if precision <= 0:
        return round(value, 1)
    return round(value, precision)


class TradeExecutor:
    def __init__(self, engine):
        self.engine = engine
        self._last_trade_time = 0
        self._min_trade_interval = 90

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

    def _ensure_min_trade_interval(self):
        now = time.time()
        if now - self._last_trade_time < self._min_trade_interval:
            wait = self._min_trade_interval - (now - self._last_trade_time)
            logger.info(f"Trade cooldown: waiting {wait:.1f}s before next trade")
            time.sleep(wait)
        self._last_trade_time = time.time()

    def execute(self, signal, entry_price, quantity, leverage, tp_price, sl_price):
        side = signal.action
        pos_side = "LONG" if side == "BUY" else "SHORT"
        logger.info(f"Executing {side} {signal.symbol} @ {entry_price}, qty={quantity}, lev={leverage}")

        self._ensure_min_trade_interval()

        if self.engine.auth.demo_mode:
            self._simulate(signal, entry_price, quantity, leverage, tp_price, sl_price)
            return

        contract_info = self.engine._contracts_info.get(signal.symbol, {})
        price_precision = contract_info.get('pricePrecision', 1)
        min_qty = contract_info.get('minQty', 0)
        step_size = contract_info.get('stepSize', 0.001)
        entry_price = _round_to_precision(entry_price, price_precision)

        # Установка плеча
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                resp = self.engine.api.set_leverage(signal.symbol, leverage, pos_side)
                if resp.get('code') != 0:
                    logger.error(f"Set leverage failed: {resp}")
                    return
                break
            except Exception as e:
                logger.error(f"Leverage attempt {attempt+1} failed: {e}")
                if attempt == max_attempts-1:
                    return
                time.sleep(1)

        # Рыночный ордер
        for attempt in range(max_attempts):
            try:
                order = self.engine.api.place_order(
                    symbol=signal.symbol, side=side, position_side=pos_side,
                    order_type='MARKET', quantity=quantity
                )
                code = order.get('code', 0)
                if code != 0:
                    # Фатальные ошибки, после которых не нужно создавать позицию
                    fatal_codes = {101204, 110424, 110422, 101400, 101419, 101202}
                    if code in fatal_codes:
                        logger.error(f"Market order failed with fatal error {code}: {order.get('msg')}")
                        return
                    if code == 101400 and min_qty > 0:
                        quantity = quantity + step_size
                        if quantity < min_qty:
                            quantity = min_qty
                        logger.info(f"Increasing quantity to {quantity} due to min order amount")
                        continue
                    if attempt < max_attempts - 1:
                        logger.warning(f"Market order error {code}, retrying in 1s")
                        time.sleep(1)
                        continue
                    else:
                        logger.error(f"Market order failed after {max_attempts} attempts: {order}")
                        return
                else:
                    break
            except Exception as e:
                logger.error(f"Order attempt {attempt+1} failed: {e}")
                if attempt == max_attempts-1:
                    return
                time.sleep(1)

        time.sleep(1)

        # Фактическая цена входа
        actual_entry = entry_price
        try:
            positions = self.engine.api.get_positions(signal.symbol)
            for p in positions:
                if p.get('symbol') == signal.symbol and p.get('positionSide') == pos_side:
                    actual_entry = float(p.get('avgPrice', p.get('entryPrice', entry_price)))
                    break
        except Exception as e:
            logger.warning(f"Could not fetch actual entry price, using original: {e}")

        logger.info(f"Actual entry price for {signal.symbol}: {actual_entry} (requested: {entry_price})")

        # TP/SL
        if signal.suggested_tp is not None and signal.suggested_sl is not None:
            final_tp = signal.suggested_tp
            final_sl = signal.suggested_sl
            logger.info(f"Using signal-suggested TP={final_tp:.6f}, SL={final_sl:.6f}")
        else:
            atr = self.engine._get_current_atr(signal.symbol)
            sl_tp = self.engine.risk_manager.get_sl_tp_levels(actual_entry, side, atr, signal.symbol)
            final_tp = sl_tp['tp2']
            final_sl = sl_tp['sl']

        final_tp = _round_to_precision(final_tp, price_precision)
        final_sl = _round_to_precision(final_sl, price_precision)

        # Корректировка
        if pos_side == 'LONG':
            if final_sl >= actual_entry:
                final_sl = actual_entry * 0.99
            if final_tp <= actual_entry:
                final_tp = actual_entry * 1.01
            if final_sl >= final_tp:
                final_sl = final_tp * 0.99
        else:
            if final_sl <= actual_entry:
                final_sl = actual_entry * 1.01
            if final_tp >= actual_entry:
                final_tp = actual_entry * 0.99
            if final_sl <= final_tp:
                final_sl = final_tp * 1.01

        if final_sl <= 0 or final_tp <= 0:
            logger.error(f"Invalid SL/TP after corrections for {signal.symbol}: SL={final_sl}, TP={final_tp}. Aborting.")
            return

        self._place_tpsl_orders(signal.symbol, pos_side, quantity, final_tp, final_sl)

        position = Position(
            symbol=signal.symbol, side=pos_side, entry_price=actual_entry,
            quantity=quantity, leverage=leverage,
            margin=(quantity * actual_entry) / leverage,
            tp_price=final_tp, sl_price=final_sl,
            open_time=datetime.now(timezone.utc).isoformat(),
            trailing=False
        )
        self.engine.portfolio.add_position(position)

        strategy_name = signal.meta.get('strategy', 'Unknown')
        self.engine.voting.record_trade(strategy_name, 0.0)

        self._play_sound('trade_open')
        logger.info(f"Trade executed: {signal.symbol} {side} @ {actual_entry}, TP={final_tp}, SL={final_sl}")

        # Авто-закрытие для микро-режима
        if self.engine.risk_manager._current_profile == 'Micro':
            timeout = 90
            logger.info(f"Starting auto-close timer for {signal.symbol} {pos_side} after {timeout}s")
            threading.Thread(target=self._auto_close_after_timeout,
                             args=(signal.symbol, pos_side, quantity, timeout),
                             daemon=True).start()

    def _auto_close_after_timeout(self, symbol: str, pos_side: str, quantity: float, timeout_seconds: int):
        logger.info(f"Auto-close timer started for {symbol} {pos_side}, will close after {timeout_seconds}s")
        time.sleep(timeout_seconds)
        try:
            positions = self.engine.api.get_positions(symbol)
            pos = next((p for p in positions if p.get('positionSide') == pos_side and abs(float(p.get('positionAmt', 0))) > 0), None)
            if pos:
                logger.warning(f"Auto-closing {symbol} {pos_side} after {timeout_seconds}s timeout (TP/SL not hit)")
                self.engine.api.close_position(symbol, pos_side, quantity)
                # Принудительная синхронизация, чтобы локальный портфель обновился
                self.engine.sync_manager.background_sync()
            else:
                logger.info(f"Auto-close: position {symbol} {pos_side} already closed")
        except Exception as e:
            logger.error(f"Auto-close failed for {symbol}: {e}")

    # ------------------------------------------------------------------
    def apply_trailing_stop(self, pos, current_price: float):
        atr = self.engine._get_current_atr(pos.symbol)
        price = current_price or pos.entry_price
        atr_based_pct = (atr / price * 100 * 1.5) if price > 0 else 0.4
        min_pct = getattr(self.engine, 'trailing_distance_pct', 0.4)
        dist_pct = max(min_pct, atr_based_pct) / 100.0
        trail_dist = current_price * dist_pct
        if pos.side == 'LONG':
            new_sl = current_price - trail_dist
            if new_sl > pos.sl_price and new_sl > pos.entry_price:
                pos.sl_price = new_sl
                pos.trailing = True
                logger.info(f"Trailing SL updated for {pos.symbol} LONG: {new_sl:.6f} (dist={dist_pct*100:.2f}%)")
                return True
        else:
            new_sl = current_price + trail_dist
            if new_sl < pos.sl_price and new_sl < pos.entry_price:
                pos.sl_price = new_sl
                pos.trailing = True
                logger.info(f"Trailing SL updated for {pos.symbol} SHORT: {new_sl:.6f} (dist={dist_pct*100:.2f}%)")
                return True
        return False

    def apply_breakeven(self, pos, current_price: float, atr_val: float):
        mult = self.engine.breakeven_atr_mult * 0.2
        be_price = pos.entry_price + (atr_val * mult) if pos.side == 'LONG' else pos.entry_price - (atr_val * mult)
        if pos.side == 'LONG' and current_price > be_price and pos.sl_price < pos.entry_price:
            pos.sl_price = pos.entry_price * 1.001
            logger.info(f"Breakeven applied for {pos.symbol} LONG")
            return True
        elif pos.side == 'SHORT' and current_price < be_price and pos.sl_price > pos.entry_price:
            pos.sl_price = pos.entry_price * 0.999
            logger.info(f"Breakeven applied for {pos.symbol} SHORT")
            return True
        return False

    def apply_partial_close(self, pos, current_price: float):
        if getattr(pos, 'partial_done', False):
            return False
        if (pos.side == 'LONG' and current_price >= pos.tp_price) or (pos.side == 'SHORT' and current_price <= pos.tp_price):
            close_qty = pos.quantity * (self.engine.partial_close_pct / 100.0)
            try:
                self.engine.api.close_position(pos.symbol, pos.side, close_qty)
                pos.quantity -= close_qty
                pos.partial_done = True
                logger.info(f"Partial close {self.engine.partial_close_pct}% for {pos.symbol}")

                if pos.quantity > 0:
                    self._place_tpsl_orders(pos.symbol, pos.side, pos.quantity, pos.tp_price, pos.sl_price)

                self._play_sound('profit')
                return True
            except Exception as e:
                logger.error(f"Partial close failed for {pos.symbol}: {e}")
        return False

    def _place_tpsl_orders(self, symbol, pos_side, quantity, tp_price, sl_price):
        close_side = 'SELL' if pos_side == 'LONG' else 'BUY'

        try:
            open_orders = self.engine.api.get_open_orders(symbol)
        except Exception as e:
            logger.warning(f"Could not fetch open orders for {symbol}: {e}")
            open_orders = []

        for o in open_orders:
            if o.get('positionSide') != pos_side:
                continue
            o_type = o.get('type', '')
            stop_price = o.get('stopPrice')
            if stop_price is None:
                continue
            if o_type == 'TAKE_PROFIT_MARKET' and tp_price is not None:
                if abs(float(stop_price) - tp_price) < 1e-8:
                    continue
            if o_type == 'STOP_MARKET' and sl_price is not None:
                if abs(float(stop_price) - sl_price) < 1e-8:
                    continue
            try:
                self.engine.api.cancel_order(symbol, o['orderId'])
                time.sleep(0.2)
            except Exception as e:
                logger.warning(f"Failed to cancel order {o['orderId']}: {e}")

        if tp_price is not None:
            try:
                self.engine.api.place_order(
                    symbol=symbol, side=close_side, position_side=pos_side,
                    order_type='TAKE_PROFIT_MARKET', quantity=quantity, stop_price=tp_price
                )
            except Exception as e:
                if self._is_tpsl_already_exists_error(e):
                    logger.debug(f"TP already exists for {symbol} {pos_side}, skipping")
                else:
                    logger.error(f"Failed to place TP for {symbol}: {e}")

        if sl_price is not None:
            if pos_side == 'LONG' and sl_price >= tp_price:
                logger.warning(f"Invalid SL for LONG: {sl_price} >= TP {tp_price}, skipping SL order")
                return
            if pos_side == 'SHORT' and sl_price <= tp_price:
                logger.warning(f"Invalid SL for SHORT: {sl_price} <= TP {tp_price}, skipping SL order")
                return
            try:
                self.engine.api.place_order(
                    symbol=symbol, side=close_side, position_side=pos_side,
                    order_type='STOP_MARKET', quantity=quantity, stop_price=sl_price
                )
            except Exception as e:
                if self._is_tpsl_already_exists_error(e):
                    logger.debug(f"SL already exists for {symbol} {pos_side}, skipping")
                else:
                    logger.error(f"Failed to place SL for {symbol}: {e}")

    def _simulate(self, signal, entry_price, quantity, leverage, tp_price, sl_price):
        pos_side = "LONG" if signal.action == "BUY" else "SHORT"
        position = Position(
            symbol=signal.symbol, side=pos_side, entry_price=entry_price,
            quantity=quantity, leverage=leverage,
            margin=(quantity * entry_price) / leverage,
            tp_price=tp_price, sl_price=sl_price,
            open_time=datetime.now(timezone.utc).isoformat(),
            trailing=False
        )
        self.engine.portfolio.add_position(position)
        logger.info(f"[DEMO] Simulated {signal.action} {signal.symbol}")

    def _play_sound(self, event: str):
        if not SOUND_AVAILABLE:
            return
        try:
            sound_map = {
                'profit': 'sounds/profit.wav',
                'loss': 'sounds/loss.wav',
                'error': 'sounds/error.wav',
                'trade_open': 'sounds/trade.wav'
            }
            path = sound_map.get(event)
            if path:
                winsound.PlaySound(path, winsound.SND_ASYNC)
        except Exception:
            pass
