"""
Correlation Filter – blocks signals if too many correlated positions are already open.
"""
import logging
from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

class CorrelationFilter(BaseFilter):
    NAME = "CorrelationFilter"
    DESCRIPTION = "Reduce exposure on correlated pairs"
    PRIORITY = 20
    PARAMS = {
        'enabled': True,
        'correlation_threshold': 0.8,   # коэффициент Пирсона
        'max_correlated': 2             # максимум позиций с корреляцией выше порога
    }

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        open_positions = data.get('open_positions', [])
        correlations = data.get('correlations', {})
        threshold = self.config['correlation_threshold']
        max_corr = self.config['max_correlated']

        correlated_count = 0
        for pos in open_positions:
            corr_key = f"{signal.symbol}_{pos['symbol']}"
            corr_value = correlations.get(corr_key, 0.0)
            if abs(corr_value) >= threshold:
                correlated_count += 1

        if correlated_count >= max_corr:
            logger.info(f"CorrelationFilter blocked {signal.symbol}: {correlated_count} correlated positions")
            return 0.0
        elif correlated_count > 0:
            # Снижаем уверенность пропорционально количеству коррелированных позиций
            return signal.confidence * (1 - (correlated_count / max_corr) * 0.5)

        return signal.confidence
