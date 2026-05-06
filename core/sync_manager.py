"""
Position sync manager: synchronises local portfolio with exchange,
applies trailing/breakeven, partial close, corrects TP/SL orders,
enforces maximum position limit, records closed trades, and
supports smart replacement of weakest positions.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from core.portfolio import Position, TradeRecord

logger = logging.getLogger(__name__)

class PositionSyncManager:
    def __init__(self, engine):
        self.engine = engine
        # Кэш последних известных TP/SL для предотвращения спама переустановками
        self._tpsl_cache = {}   # ключ: f"{symbol}_{side}"

    # ------------------------------------------------------------------
    # Полная синхронизация (при старте / ручном обновлении)
    # ------------------------------------------------------------------
    def full_sync(self):
        """Загружает позиции с биржи и восстанавливает портфель."""
        if self.engine.auth.demo_mode:
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

                # Логическая проверка
                tp_price, sl_price = self._logical_check(pos_side, entry, tp_price, sl_price)

                # Если не удалось получить, вычисляем через risk_manager
                if tp_price is None or sl_price is None:
                    atr = self.engine._get_current_atr(symbol)
                    trade_side = 'BUY' if pos_side == 'LONG' else 'SELL'
                    sl_tp = self.engine.risk_manager.get_sl_tp_levels(entry, trade_side, atr, symbol)
                    tp_price = tp_price or sl_tp['tp2']
                    sl_price = sl_price or sl_tp['sl']

                if qty > 0:
                    pos = Position(
                        symbol=symbol, side=pos_side, entry_price=entry,
                        quantity=qty, leverage=lev,
                        margin=(qty * entry) / lev,
                        tp_price=tp_price, sl_price=sl_price,
                        open_time=datetime.now(timezone.utc).isoformat()
                    )
                    self.engine.portfolio.add_position(pos)
                    # Обновляем кэш
                    self._tpsl_cache[f"{symbol}_{pos_side}"] = (tp_price, sl_price)
                    logger.info(f"Synced existing position: {symbol} {pos_side} qty={qty} @ {entry} "
                                f"TP={tp_price} SL={sl_price}")
            # Применяем лимит сразу после полной синхронизации
            self._enforce_limit()
        except Exception as e:
            logger.error(f"Full sync failed: {e}")

    # ------------------------------------------------------------------
    # Фоновая синхронизация (вызывается по расписанию)
    # ------------------------------------------------------------------
    def background_sync(self):
        """Периодическая синхронизация: обновление PnL, трейлинг, частичное закрытие, лимит, запись закрытых сделок."""
        if self.engine.auth.demo_mode:
            return
        try:
            api_positions = self.engine.api.get_positions()
            api_keys = {f"{p.get('symbol')}_{p.get('positionSide')}" for p in api_positions}

            # Обработка закрытых позиций
            for pos in self.engine.portfolio.get_positions():
                if f"{pos.symbol}_{pos.side}" not in api_keys:
                    # Позиция была закрыта – фиксируем сделку
                    pnl = pos.unrealized_pnl  # последний известный нереализованный PnL
                    exit_price = (pos.entry_price + (pnl / pos.quantity) if pos.side == 'LONG' 
                                  else pos.entry_price - (pnl / pos.quantity))
                    trade = TradeRecord(
                        symbol=pos.symbol, side=pos.side, action='CLOSE',
                        entry_price=pos.entry_price, exit_price=exit_price,
                        quantity=pos.quantity, leverage=pos.leverage, pnl=pnl,
                        close_reason='TP/SL' if pnl != 0 else 'Manual',
                        open_time=pos.open_time,
                        close_time=datetime.now(timezone.utc).isoformat()
                    )
                    self.engine.portfolio.record_trade(trade)
                    logger.info(f"Position closed: {pos.symbol} {pos.side} PnL={pnl:.4f}")
                    # === Адаптивный риск по серии ===
                    self.engine.risk_manager.update_adaptive_risk(pnl)
                    # Удаляем позицию
                    self.engine.portfolio.remove_position(pos.symbol, pos.side)
                    # Удаляем из кэша TP/SL
                    cache_key = f"{pos.symbol}_{pos.side}"
                    if cache_key in self._tpsl_cache:
                        del self._tpsl_cache[cache_key]

            # Обработка активных позиций
            for p in api_positions:
                pos_side = p.get('positionSide', 'LONG')
                symbol = p.get('symbol', '')
                entry = float(p.get('avgPrice', p.get('entryPrice', 0)))
                qty = abs(float(p.get('positionAmt', 0)))
                lev = float(p.get('leverage', 1))
                current_price = float(p.get('markPrice', 0))
                unrealized = float(p.get('unrealizedProfit', 0))

                existing = next((pos for pos in self.engine.portfolio.get_positions()
                                 if pos.symbol == symbol and pos.side == pos_side), None)

                if existing:
                    existing.unrealized_pnl = unrealized
                    if existing.margin > 0:
                        existing.pnl_pct = (unrealized / existing.margin) * 100

                    # Трейлинг‑стоп и безубыток
                    if current_price > 0 and existing.sl_price is not None:
                        if self.engine.trailing_sl_enabled:
                            self.engine.executor.apply_trailing_stop(existing, current_price)
                        if self.engine.breakeven_enabled:
                            atr = self.engine._get_current_atr(symbol)
                            self.engine.executor.apply_breakeven(existing, current_price, atr)

                    # Частичное закрытие
                    if self.engine.partial_close_enabled and existing.tp_price is not None:
                        self.engine.executor.apply_partial_close(existing, current_price)

                    # Синхронизация ордеров TP/SL на бирже (только если изменились)
                    self._sync_tpsl_orders(symbol, pos_side, existing.quantity,
                                           existing.tp_price, existing.sl_price)

                else:
                    # Позиция есть на бирже, но не в портфеле — добавляем
                    if len(self.engine.portfolio.get_positions()) >= self.engine.max_positions:
                        continue
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
                    # Обновляем кэш
                    self._tpsl_cache[f"{symbol}_{pos_side}"] = (sl_tp['tp2'], sl_tp['sl'])

            # Принудительное соблюдение лимита позиций
            self._enforce_limit()

        except Exception:
            logger.exception("Background sync crashed")

    # ------------------------------------------------------------------
    # Принудительное соблюдение лимита
    # ------------------------------------------------------------------
    def _enforce_limit(self):
        """Если позиций больше max_positions, закрываем часть самых слабых."""
        positions = self.engine.portfolio.get_positions()
        max_pos = self.engine.max_positions
        if len(positions) <= max_pos:
            return
        # Сортируем от худшего PnL к лучшему
        positions.sort(key=lambda p: p.unrealized_pnl)
        to_close = positions[:-max_pos]  # оставляем последние max_pos лучших
        for pos in to_close:
            try:
                logger.info(f"Enforcing limit: closing {pos.symbol} {pos.side} (PnL={pos.unrealized_pnl:.4f})")
                self.engine.api.close_position(pos.symbol, pos.side)
                self.engine.portfolio.remove_position(pos.symbol, pos.side)
            except Exception as e:
                logger.error(f"Failed to close {pos.symbol} during limit enforcement: {e}")

    # ------------------------------------------------------------------
    # Умная замена позиций (для использования в signal_processor)
    # ------------------------------------------------------------------
    def try_replace_weakest(self, new_signal_confidence: float, new_signal_symbol: str) -> bool:
        """
        Если все слоты заняты, пытается закрыть самую слабую позицию,
        чтобы освободить место для нового сигнала.
        Возвращает True, если слот освобождён или уже было место.
        """
        positions = self.engine.portfolio.get_positions()
        max_pos = self.engine.max_positions
        if len(positions) < max_pos:
            return True  # места достаточно

        # Оцениваем каждую позицию
        now = datetime.now(timezone.utc)
        scored = []
        for pos in positions:
            # Время в часах
            try:
                open_t = datetime.fromisoformat(pos.open_time)
                hours_held = (now - open_t).total_seconds() / 3600.0
            except Exception:
                hours_held = 99.0
            # Прогресс к TP (0 = только открылись, 1 = почти закрылись по TP)
            if pos.tp_price and pos.entry_price:
                if pos.side == 'LONG' and pos.tp_price != pos.entry_price:
                    progress = (pos.sl_price - pos.entry_price) / (pos.tp_price - pos.entry_price)
                elif pos.side == 'SHORT' and pos.tp_price != pos.entry_price:
                    progress = (pos.entry_price - pos.sl_price) / (pos.entry_price - pos.tp_price)
                else:
                    progress = 0.0
            else:
                progress = 0.0
            score = progress * 0.7 - hours_held * 0.02  # чем больше висит, тем хуже
            scored.append((pos, score))

        # Худшая позиция
        weakest_pos, weakest_score = min(scored, key=lambda x: x[1])

        # Порог для замены: confidence нового сигнала должна быть выше (с учётом слабости старой позиции)
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

    # ------------------------------------------------------------------
    # Вспомогательные
    # ------------------------------------------------------------------
    def _fetch_exchange_tpsl(self, symbol: str, pos_side: str):
        """Получает TP/SL из открытых ордеров."""
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
        """Корректирует логически неверные TP/SL."""
        if pos_side == 'LONG':
            if tp is not None and tp <= entry:
                tp = None
            if sl is not None and sl >= entry:
                sl = None
            if tp is not None and sl is not None and tp < sl:
                tp, sl = sl, tp
        else:  # SHORT
            if tp is not None and tp >= entry:
                tp = None
            if sl is not None and sl <= entry:
                sl = None
            if tp is not None and sl is not None and tp > sl:
                tp, sl = sl, tp
        return tp, sl

    def _sync_tpsl_orders(self, symbol, pos_side, quantity, expected_tp, expected_sl):
        """Отменяет старые и выставляет новые TP/SL ордера, только если они изменились."""
        cache_key = f"{symbol}_{pos_side}"
        cached_tp, cached_sl = self._tpsl_cache.get(cache_key, (None, None))

        # Если ничего не изменилось – выходим
        if cached_tp == expected_tp and cached_sl == expected_sl:
            return

        try:
            orders = self.engine.api.get_open_orders(symbol)
            # Отменяем существующие TP/SL ордера для этой позиции
            for o in orders:
                if o.get('positionSide') != pos_side:
                    continue
                order_type = o.get('type', '')
                if order_type in ('TAKE_PROFIT_MARKET', 'STOP_MARKET'):
                    try:
                        self.engine.api.cancel_order(symbol, o.get('orderId', ''))
                        logger.debug(f"Cancelled {order_type} for {symbol} {pos_side}")
                    except Exception as e:
                        logger.warning(f"Failed to cancel order {o.get('orderId')}: {e}")

            close_side = 'SELL' if pos_side == 'LONG' else 'BUY'
            if expected_tp is not None:
                self.engine.api.place_order(
                    symbol=symbol, side=close_side, position_side=pos_side,
                    order_type='TAKE_PROFIT_MARKET', quantity=quantity,
                    stop_price=expected_tp
                )
                logger.info(f"Set new TP for {symbol} {pos_side}: {expected_tp}")
            if expected_sl is not None:
                # Проверка валидности
                if (pos_side == 'LONG' and expected_sl >= expected_tp) or \
                   (pos_side == 'SHORT' and expected_sl <= expected_tp):
                    logger.warning(f"Invalid SL {expected_sl} relative to TP {expected_tp}, skipping SL order")
                else:
                    self.engine.api.place_order(
                        symbol=symbol, side=close_side, position_side=pos_side,
                        order_type='STOP_MARKET', quantity=quantity,
                        stop_price=expected_sl
                    )
                    logger.info(f"Set new SL for {symbol} {pos_side}: {expected_sl}")

            # Обновляем кэш
            self._tpsl_cache[cache_key] = (expected_tp, expected_sl)
        except Exception as e:
            logger.error(f"Failed to sync TP/SL orders for {symbol}: {e}")
