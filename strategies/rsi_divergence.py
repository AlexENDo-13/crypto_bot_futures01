from strategies.base import BaseStrategy, Signal
from indicators.base import RSI

class RSIDivergenceStrategy(BaseStrategy):
    NAME = "RSIDivergence"
    PARAMS = {'enabled': True, 'weight': 0.9, 'timeframes': ['1h']}
    
    def __init__(self, params=None):
        super().__init__(params)
        self.rsi = RSI({'period': 14})
    
    def evaluate(self, symbol, timeframe, candles):
        if len(candles) < 30:
            return None
        rsi_vals = self.rsi.calculate(candles)
        price = candles['close']
        # Упрощённый поиск дивергенции: сравниваем последние два экстремума
        # Ищем локальный минимум/максимум за последние 10 баров
        last_high = price[-10:].idxmax()
        prev_high = price[:-10].idxmax()
        if price[last_high] > price[prev_high] and rsi_vals[last_high] < rsi_vals[prev_high]:
            return Signal(symbol=symbol, action='SELL', confidence=0.7,
                         meta={'reason': 'Bearish RSI divergence'})
        last_low = price[-10:].idxmin()
        prev_low = price[:-10].idxmin()
        if price[last_low] < price[prev_low] and rsi_vals[last_low] > rsi_vals[prev_low]:
            return Signal(symbol=symbol, action='BUY', confidence=0.7,
                         meta={'reason': 'Bullish RSI divergence'})
        return None
