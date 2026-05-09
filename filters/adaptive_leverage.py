"""
Adaptive Leverage Filter – динамически корректирует плечо на основе ATR.
"""
import logging
from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

class AdaptiveLeverageFilter(BaseFilter):
    NAME = "AdaptiveLeverage"
    DESCRIPTION = "Автоматически регулирует плечо в зависимости от волатильности (ATR)"
    PRIORITY = 1          # самый первый фильтр, до проверки объёмов
    PARAMS = {
        'enabled': True,
        'atr_timeframe': '1h',
        'max_leverage': 10,
        'min_leverage': 2,
        'high_vol_threshold': 0.05,   # ATR/Price > 5% -> снижаем плечо
        'low_vol_threshold': 0.01,    # ATR/Price < 1% -> повышаем плечо
    }

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        current_price = data.get('current_price', 0)
        current_atr = data.get('current_atr', 0)
        if current_price <= 0 or current_atr <= 0:
            return signal.confidence

        atr_ratio = current_atr / current_price
        engine = getattr(self, 'engine', None)
        if engine is None:
            return signal.confidence

        # Вычисляем оптимальное плечо
        if atr_ratio > self.config['high_vol_threshold']:
            desired_leverage = self.config['min_leverage']
        elif atr_ratio < self.config['low_vol_threshold']:
            desired_leverage = self.config['max_leverage']
        else:
            # Линейная интерполяция между min и max
            ratio = (atr_ratio - self.config['low_vol_threshold']) / (self.config['high_vol_threshold'] - self.config['low_vol_threshold'])
            desired_leverage = self.config['max_leverage'] - ratio * (self.config['max_leverage'] - self.config['min_leverage'])

        desired_leverage = int(round(desired_leverage))
        desired_leverage = max(self.config['min_leverage'], min(self.config['max_leverage'], desired_leverage))

        if desired_leverage != engine.risk_manager.max_leverage:
            logger.info(f"AdaptiveLeverage: ATR ratio={atr_ratio:.4f}, setting leverage to {desired_leverage}x")
            engine.risk_manager.max_leverage = desired_leverage

        return signal.confidence
