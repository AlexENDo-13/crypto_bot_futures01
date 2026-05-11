"""
Order Guard – periodic check and repair of TP/SL orders on the exchange.
Fixed: no longer tries to set TP/SL on positions that don't exist on exchange.
"""
import logging
import time
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 120

class OrderGuard:
    def __init__(self, engine):
        self.engine = engine
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_repair_attempt: Dict[str, float] = {}
        self._min_repeat_interval = 300

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="OrderGuard")
        self._thread.start()
        logger.info("OrderGuard started (check every %ds)", CHECK_INTERVAL_SECONDS)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while self._running:
            try:
                self._check_all_positions()
            except Exception:
                logger.exception("OrderGuard check failed")
            time.sleep(CHECK_INTERVAL_SECONDS)

    def _check_all_positions(self):
        if self.engine.auth.demo_mode:
            return
        # Получаем реальные позиции с биржи
        try:
            api_positions = self.engine.api.get_positions()
        except Exception as e:
            logger.warning(f"OrderGuard cannot fetch positions: {e}")
            return

        if not api_positions:
            # Если биржа не вернула позиций, значит ничего не открыто — чистим локально
            for pos in list(self.engine.portfolio.get_positions()):
                self.engine.portfolio.remove_position(pos.symbol, pos.side)
            return

        # Строим мапу реальных позиций: (symbol, positionSide) -> api_data
        real_positions = {}
        for p in api_positions:
            sym = p.get('symbol', '')
            side = p.get('positionSide', 'LONG')
            qty = abs(float(p.get('positionAmt', 0)))
            if qty > 0:   # игнорируем позиции с нулевым объёмом (не открыты)
                real_positions[(sym, side)] = p

        # Удаляем локальные позиции, которых нет в реальных
        for pos in list(self.engine.portfolio.get_positions()):
            key = (pos.symbol, pos.side)
            if key not in real_positions:
                logger.info(f"OrderGuard: Position {pos.symbol} {pos.side} no longer exists on exchange, removing")
                self.engine.portfolio.remove_position(pos.symbol, pos.side)

        # Для каждой реальной позиции проверяем и чиним TP/SL
        for (symbol, pos_side), api_pos in real_positions.items():
            try:
                self._check_and_repair(symbol, pos_side, abs(float(api_pos.get('positionAmt', 0))))
            except Exception as e:
                logger.error(f"OrderGuard error for {symbol} {pos_side}: {e}")

    def _check_and_repair(self, symbol, pos_side, quantity):
        # Получаем локальную позицию (если есть)
        local_pos = None
        for pos in self.engine.portfolio.get_positions():
            if pos.symbol == symbol and pos.side == pos_side:
                local_pos = pos
                break
        if local_pos is None:
            # Локальной позиции нет – создаём на основе биржевых данных (чтобы не потерять трейлинг)
            # Но здесь можем просто пропустить, т.к. синхронизация добавит её в следующем цикле
            return

        expected_tp = local_pos.tp_price
        expected_sl = local_pos.sl_price
        if expected_tp is None and expected_sl is None:
            return

        repair_key = f"{symbol}_{pos_side}"
        now = time.time()
        if now - self._last_repair_attempt.get(repair_key, 0) < self._min_repeat_interval:
            return

        try:
            orders = self.engine.api.get_open_orders(symbol)
        except Exception as e:
            logger.warning(f"OrderGuard cannot fetch orders for {symbol}: {e}")
            return

        tp_found = False
        sl_found = False

        for o in orders:
            if o.get('positionSide') != pos_side:
                continue
            order_type = o.get('type', '')
            stop_price = o.get('stopPrice')
            if stop_price is None:
                continue
            try:
                stop_price_float = float(stop_price)
            except (TypeError, ValueError):
                continue

            order_qty = float(o.get('origQty', 0))
            if order_qty <= 0:
                continue

            if order_type == 'TAKE_PROFIT_MARKET' and expected_tp is not None:
                tolerance = max(1e-8, abs(expected_tp) * 1e-3)
                if abs(stop_price_float - expected_tp) <= tolerance and abs(quantity - order_qty) < 1e-8:
                    tp_found = True
            elif order_type == 'STOP_MARKET' and expected_sl is not None:
                tolerance = max(1e-8, abs(expected_sl) * 1e-3)
                if abs(stop_price_float - expected_sl) <= tolerance and abs(quantity - order_qty) < 1e-8:
                    sl_found = True

        if not tp_found and expected_tp is not None:
            logger.warning(f"OrderGuard: TP missing for {symbol} {pos_side}, recreating TP={expected_tp}")
            try:
                close_side = 'SELL' if pos_side == 'LONG' else 'BUY'
                self.engine.api.place_order(
                    symbol=symbol, side=close_side, position_side=pos_side,
                    order_type='TAKE_PROFIT_MARKET', quantity=quantity,
                    stop_price=expected_tp
                )
                self._last_repair_attempt[repair_key] = now
            except Exception as e:
                logger.error(f"OrderGuard failed to recreate TP for {symbol}: {e}")

        if not sl_found and expected_sl is not None:
            logger.warning(f"OrderGuard: SL missing for {symbol} {pos_side}, recreating SL={expected_sl}")
            try:
                close_side = 'SELL' if pos_side == 'LONG' else 'BUY'
                self.engine.api.place_order(
                    symbol=symbol, side=close_side, position_side=pos_side,
                    order_type='STOP_MARKET', quantity=quantity,
                    stop_price=expected_sl
                )
                self._last_repair_attempt[repair_key] = now
            except Exception as e:
                logger.error(f"OrderGuard failed to recreate SL for {symbol}: {e}")
