"""
Order Flow Imbalance Filter – анализирует дельту объёма по свечам.
"""
import logging
from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

class OrderFlowImbalanceFilter(BaseFilter):
    NAME = "OrderFlowImbalance"
    DESCRIPTION = "Фильтр по дельте объёма – подтверждает направление через дисбаланс закрытий"
    PRIORITY = 15
    PARAMS = {
        'enabled': True,
        'timeframe': '1h',
        'lookback_bars': 10,         # за сколько свечей считать дельту
        'min_delta_ratio': 0.6,      # минимальная доля свечей в нужную сторону
        'strong_delta_ratio': 0.8,   # порог для усиления сигнала
    }

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        candle_data = data.get('candle_data')
        if not candle_data:
            return signal.confidence

        tf = self.config['timeframe']
        df = candle_data.get(tf)
        if df is None or len(df) < self.config['lookback_bars']:
            return signal.confidence

        lookback = self.config['lookback_bars']
        recent = df.iloc[-lookback:]

        # Считаем количество «бычьих» свечей (close > open)
        bull_candles = sum(1 for i in range(len(recent)) if recent['close'].iloc[i] > recent['open'].iloc[i])
        delta_ratio = bull_candles / len(recent) if len(recent) > 0 else 0

        if signal.action == 'BUY':
            if delta_ratio < self.config['min_delta_ratio']:
                logger.info(f"OrderFlowImbalance blocked BUY {signal.symbol}: delta {delta_ratio:.2f}")
                return 0.0
            if delta_ratio >= self.config['strong_delta_ratio']:
                return min(1.0, signal.confidence * 1.1)
        elif signal.action == 'SELL':
            # Для продажи ожидаем мало бычьих свечей (медвежья дельта)
            if delta_ratio > (1 - self.config['min_delta_ratio']):
                logger.info(f"OrderFlowImbalance blocked SELL {signal.symbol}: delta {delta_ratio:.2f}")
                return 0.0
            if delta_ratio <= (1 - self.config['strong_delta_ratio']):
                return min(1.0, signal.confidence * 1.1)

        return signal.confidence
