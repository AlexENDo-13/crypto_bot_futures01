"""
Multi-Timeframe Confluence Filter.
Confirms that the signal aligns with the long-term trend (4h 200 EMA).
"""
import logging
from filters.base import BaseFilter
from strategies.base import Signal
from indicators.base import EMA

logger = logging.getLogger(__name__)

class MultiTFConfluenceFilter(BaseFilter):
    NAME = "MultiTFConfluenceFilter"
    DESCRIPTION = "Blocks signals against the long-term trend (4h 200 EMA)"
    PRIORITY = 18  # После ликвидности и объёма, до корреляций
    PARAMS = {
        'enabled': True,
        'ema_period': 200,
        'trend_timeframe': '4h',  # ТФ для определения глобального тренда
        'signal_timeframe': '1h'  # сюда будем подставлять фактический ТФ сигнала
    }

    def __init__(self, params=None):
        super().__init__(params)
        self.ema = EMA({'period': self.config['ema_period']})

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        candle_data = data.get('candle_data')
        if not candle_data:
            return signal.confidence

        trend_tf = self.config['trend_timeframe']
        if trend_tf not in candle_data:
            # Если нужного ТФ нет — пропускаем (не блокируем)
            return signal.confidence

        df = candle_data[trend_tf]
        min_bars = self.config['ema_period'] + 5
        if len(df) < min_bars:
            return signal.confidence

        try:
            ema_series = self.ema.calculate(df)
            if ema_series.empty:
                return signal.confidence
            ema_value = ema_series.iloc[-1]
            current_price = df['close'].iloc[-1]
        except Exception as e:
            logger.debug(f"MultiTFConfluence error: {e}")
            return signal.confidence

        if signal.action == 'BUY' and current_price < ema_value:
            logger.info(f"MultiTF blocked BUY {signal.symbol}: price {current_price} < 200EMA {ema_value:.2f}")
            return 0.0
        elif signal.action == 'SELL' and current_price > ema_value:
            logger.info(f"MultiTF blocked SELL {signal.symbol}: price {current_price} > 200EMA {ema_value:.2f}")
            return 0.0

        # Небольшой буст уверенности, если сигнал строго по тренду и расстояние велико
        if signal.action == 'BUY' and current_price > ema_value * 1.02:
            return min(1.0, signal.confidence * 1.05)
        if signal.action == 'SELL' and current_price < ema_value * 0.98:
            return min(1.0, signal.confidence * 1.05)

        return signal.confidence
