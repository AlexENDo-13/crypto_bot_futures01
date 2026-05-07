import logging
from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

class ATRFilter(BaseFilter):
    NAME = "ATRFilter"
    DESCRIPTION = "Blocks symbols with extreme ATR/price ratio"
    PRIORITY = 8
    PARAMS = {
        'enabled': True,
        'max_atr_ratio': 0.10,
    }

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        current_price = data.get('current_price', 0)
        current_atr = data.get('current_atr', 0)

        if current_price <= 0 or current_atr <= 0:
            return signal.confidence

        ratio = current_atr / current_price
        if ratio > self.config['max_atr_ratio']:
            logger.info(f"ATRFilter blocked {signal.symbol}: ATR/Price = {ratio:.2%} > {self.config['max_atr_ratio']:.0%}")
            return 0.0

        return signal.confidence
