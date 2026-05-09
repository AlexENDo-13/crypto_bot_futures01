"""
Smart Money Filter – использует 200 EMA и ATR для фильтрации сигналов.
Если цена далеко от EMA200 и волатильность низкая – возможна манипуляция,
блокируем. Если цена вблизи EMA200 – тренд подтверждён, пропускаем.
"""
import logging
from filters.base import BaseFilter
from strategies.base import Signal
from indicators.base import EMA, ATR

logger = logging.getLogger(__name__)

class SmartMoneyFilter(BaseFilter):
    NAME = "SmartMoneyFilter"
    DESCRIPTION = "Фильтр по EMA200 и ATR – выявляет манипуляции и подтверждает тренд"
    PRIORITY = 11
    PARAMS = {
        'enabled': True,
        'ema_period': 200,
        'atr_period': 14,
        'low_vol_threshold': 0.003,          # ATR/Price < 0.3% – низкая волатильность
        'deviation_threshold': 0.05,         # отклонение > 5% от EMA200
        'confirm_zone': 0.01,               # зона +-1% от EMA200 – подтверждение
        'trend_timeframe': '1h',            # базовый ТФ для расчёта EMA/ATR
    }

    def __init__(self, params=None):
        super().__init__(params)
        self.ema = EMA({'period': self.config['ema_period']})
        self.atr = ATR({'period': self.config['atr_period']})

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        candle_data = data.get('candle_data')
        if not candle_data:
            return signal.confidence

        tf = self.config['trend_timeframe']
        df = candle_data.get(tf)
        if df is None or len(df) < self.config['ema_period'] + 1:
            return signal.confidence

        # Рассчитываем индикаторы
        ema_series = self.ema.calculate(df)
        atr_series = self.atr.calculate(df)

        current_price = df['close'].iloc[-1]
        ema_val = ema_series.iloc[-1]
        atr_val = atr_series.iloc[-1]

        if ema_val <= 0 or current_price <= 0:
            return signal.confidence

        # Относительные показатели
        price_deviation = (current_price - ema_val) / ema_val
        atr_ratio = atr_val / current_price if current_price > 0 else 0

        # Проверка на манипуляцию: далеко от EMA200 и низкая волатильность
        if abs(price_deviation) > self.config['deviation_threshold'] and atr_ratio < self.config['low_vol_threshold']:
            logger.info(f"SmartMoneyFilter blocked {signal.symbol}: deviation={price_deviation:.3f}, atr_ratio={atr_ratio:.4f}")
            return 0.0

        # Подтверждение тренда: цена вблизи EMA200
        if abs(price_deviation) < self.config['confirm_zone']:
            if signal.action == 'BUY' and price_deviation > 0:
                boost = 1.1
            elif signal.action == 'SELL' and price_deviation < 0:
                boost = 1.1
            else:
                boost = 1.0
            return min(1.0, signal.confidence * boost)

        # Во всех остальных случаях небольшая скидка
        return signal.confidence * 0.95
