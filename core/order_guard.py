"""
Order Guard – periodic check and repair of TP/SL orders on the exchange.
Runs in a separate thread, ensures every open position has valid stop-loss
and take-profit orders at all times. Now also detects closed positions and
removes them instead of trying to recreate orders.
Fixed: price comparison with tolerance, rate limiting, and logging improvements.
"""
import logging
import time
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 300  # уменьшено с 600 до 120 секунд для быстрой реакции (оставляем как было 300? Исправим на 120 для быстрой реакции, как в исходнике? В исходнике CHECK_INTERVAL_SECONDS = 300, но в комменте сказано "уменьшено с 600 до 120 секунд". Оставим 300?)
# В исходном файле было 300, потом в комменте упоминалось 120. Оставим 120 для более быстрого обнаружения пропавших ордеров, но добавим кулдаун.
CHECK_INTERVAL_SECONDS = 120

class OrderGuard:
    def __init__(self, engine):
        self.engine = engine
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_repair_attempt: Dict[str, float] = {}
        self._min_repeat_interval = 300  # минимальный интервал между попытками восстановления одного ордера

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
        positions = self.engine.portfolio.get_positions()
        if not positions:
            return
        logger.debug("OrderGuard: checking %d positions", len(positions))
        # Сначала проверим, какие позиции реально существуют на бирже
        api_positions = []
        try:
            api_positions = self.engine.api.get_positions()
        except Exception as e:
            logger.warning(f"OrderGuard cannot fetch positions: {e}")
            return

        api_keys = {f"{p.get('symbol')}_{p.get('positionSide')}" for p in api_positions}

        for pos in list(positions):  # копируем список, чтобы безопасно удалять
            key = f"{pos.symbol}_{pos.side}"
            if key not in api_keys:
                # Позиции больше нет на бирже – удаляем её локально
                logger.info(f"OrderGuard: Position {pos.symbol} {pos.side} no longer exists on exchange, removing")
                self.engine.portfolio.remove_position(pos.symbol, pos.side)
                continue

            try:
                self._check_and_repair(pos)
            except Exception as e:
                logger.error(f"OrderGuard error for {pos.symbol} {pos.side}: {e}")

    def _check_and_repair(self, pos):
        symbol = pos.symbol
        pos_side = pos.side
        quantity = pos.quantity
        expected_tp = pos.tp_price
        expected_sl = pos.sl_price

        if expected_tp is None and expected_sl is None:
            return

        repair_key = f"{symbol}_{pos_side}"

        try:
            orders = self.engine.api.get_open_orders(symbol)
        except Exception as e:
            logger.warning(f"OrderGuard cannot fetch orders for {symbol}: {e}")
            return

        tp_found = False
        sl_found = False

        # Сравниваем с допуском 0.1% от ожидаемой цены
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

            if order_type == 'TAKE_PROFIT_MARKET' and expected_tp is not None:
                # Допуск: 0.1% от TP, но не менее 1e-8
                tolerance = max(1e-8, abs(expected_tp) * 1e-3)
                if abs(stop_price_float - expected_tp) <= tolerance:
                    tp_found = True
            elif order_type == 'STOP_MARKET' and expected_sl is not None:
                tolerance = max(1e-8, abs(expected_sl) * 1e-3)
                if abs(stop_price_float - expected_sl) <= tolerance:
                    sl_found = True

        now = time.time()
        last_attempt = self._last_repair_attempt.get(repair_key, 0)
        if now - last_attempt < self._min_repeat_interval:
            return

        close_side = 'SELL' if pos_side == 'LONG' else 'BUY'

        if not tp_found and expected_tp is not None:
            logger.warning(f"OrderGuard: TP missing for {symbol} {pos_side}, recreating TP={expected_tp}")
            try:
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
                self.engine.api.place_order(
                    symbol=symbol, side=close_side, position_side=pos_side,
                    order_type='STOP_MARKET', quantity=quantity,
                    stop_price=expected_sl
                )
                self._last_repair_attempt[repair_key] = now
            except Exception as e:
                logger.error(f"OrderGuard failed to recreate SL for {symbol}: {e}")
