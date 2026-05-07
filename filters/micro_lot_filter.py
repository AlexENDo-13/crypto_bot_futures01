"""
Micro-lot filter: blocks signals where calculated quantity is below exchange minimum.
"""
import logging
from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

class MicroLotFilter(BaseFilter):
    NAME = "MicroLotFilter"
    DESCRIPTION = "Blocks symbols with insufficient balance for minimum order"
    PRIORITY = 1

    PARAMS = {'enabled': True}

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        engine = self._get_engine()
        if engine is None:
            return signal.confidence

        symbol = signal.symbol
        price = data.get('current_price', 0)
        if price <= 0:
            return signal.confidence

        contract_info = engine._contracts_info.get(symbol, {})
        min_qty = contract_info.get('minQty', 0)
        if min_qty <= 0:
            return signal.confidence

        min_order_value = min_qty * price
        free_margin = data.get('available_margin', 0) or engine.portfolio.available_margin or 0
        max_leverage = engine.risk_manager.max_leverage
        required_margin = min_order_value / max_leverage

        if free_margin < required_margin:
            logger.info(f"MicroLotFilter blocked {symbol}: min lot cost {min_order_value:.2f} > margin {free_margin:.2f}")
            return 0.0

        return signal.confidence

    def _get_engine(self):
        import gc
        from core.engine import TradingEngine
        for obj in gc.get_objects():
            if isinstance(obj, TradingEngine):
                return obj
        return None
