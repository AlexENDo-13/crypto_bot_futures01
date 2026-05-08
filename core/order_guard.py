"""
Order Guard – periodic check and repair of TP/SL orders on the exchange.
Runs in a separate thread, ensures every open position has valid stop-loss
and take-profit orders at all times.
"""
import logging
import time
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 120  # уменьшено с 600 до 120 секунд для быстрой реакции


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
        positions = self.engine.portfolio.get_positions()
        if not positions:
            return
        logger.debug("OrderGuard: checking %d positions", len(positions))
        for pos in positions:
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

        for o in orders:
            if o.get('positionSide') != pos_side:
                continue
            order_type = o.get('type', '')
            stop_price = o.get('stopPrice')
            if order_type == 'TAKE_PROFIT_MARKET' and expected_tp is not None:
                if stop_price and abs(float(stop_price) - expected_tp) < 1e-10:
                    tp_found = True
            elif order_type == 'STOP_MARKET' and expected_sl is not None:
                if stop_price and abs(float(stop_price) - expected_sl) < 1e-10:
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
