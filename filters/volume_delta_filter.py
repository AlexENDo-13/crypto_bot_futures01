"""
Volume Delta Filter – анализирует дельту объёма (покупки минус продажи) для подтверждения тренда.
"""
import logging
from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

class VolumeDeltaFilter(BaseFilter):
    NAME = "VolumeDelta"
    DESCRIPTION = "Фильтр по дельте объёма – подтверждает направление сигнала"
    PRIORITY = 15
    PARAMS = {
        'enabled': True,
        'timeframe': '1h',
        'delta_period': 10,          # за сколько свечей считать дельту
        'min_delta_ratio': 0.6,      # минимальная доля свечей с положительной дельтой
        'strong_delta_ratio': 0.8,   # сильный сигнал
    }

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        candle_data = data.get('candle_data')
        if not candle_data:
            return signal.confidence

        tf = self.config['timeframe']
        df = candle_data.get(tf)
        if df is None or len(df) < self.config['delta_period'] + 2:
            return signal.confidence

        period = self.config['delta_period']
        recent = df.iloc[-period:]

        # Дельта: если close > open -> объём считаем покупкой, иначе продажей
        positive_delta = 0
        total = 0
        for i in range(len(recent)):
            if recent['close'].iloc[i] > recent['open'].iloc[i]:
                positive_delta += 1
            total += 1

        if total == 0:
            return signal.confidence

        delta_ratio = positive_delta / total

        if signal.action == 'BUY':
            if delta_ratio < self.config['min_delta_ratio']:
                logger.info(f"VolumeDelta blocked BUY {signal.symbol}: delta ratio {delta_ratio:.2f} < {self.config['min_delta_ratio']}")
                return 0.0
            if delta_ratio >= self.config['strong_delta_ratio']:
                return min(1.0, signal.confidence * 1.1)
        elif signal.action == 'SELL':
            # Для продажи нужна отрицательная дельта (мало покупок)
            if delta_ratio > (1 - self.config['min_delta_ratio']):
                logger.info(f"VolumeDelta blocked SELL {signal.symbol}: delta ratio {delta_ratio:.2f} > {1 - self.config['min_delta_ratio']}")
                return 0.0
            if delta_ratio <= (1 - self.config['strong_delta_ratio']):
                return min(1.0, signal.confidence * 1.1)

        return signal.confidence
