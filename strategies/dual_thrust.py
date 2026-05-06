from strategies.base import BaseStrategy, Signal
import pandas as pd

class DualThrustStrategy(BaseStrategy):
    NAME = "DualThrust"
    PARAMS = {'enabled': True, 'weight': 0.7, 'timeframes': ['15m'], 'lookback': 20, 'k': 0.7}
    
    def evaluate(self, symbol, timeframe, candles):
        if len(candles) < self.config['lookback']:
            return None
        high, low, close = candles['high'], candles['low'], candles['close']
        n = self.config['lookback']
        hh = high[:-1].max()
        ll = low[:-1].min()
        range_val = hh - ll
        upper = close.iloc[-2] + self.config['k'] * range_val
        lower = close.iloc[-2] - self.config['k'] * range_val
        current = close.iloc[-1]
        if current > upper:
            return Signal(symbol=symbol, action='BUY', confidence=0.65,
                         meta={'reason': f'Dual Thrust breakout above {upper:.6f}'})
        elif current < lower:
            return Signal(symbol=symbol, action='SELL', confidence=0.65,
                         meta={'reason': f'Dual Thrust breakdown below {lower:.6f}'})
        return None
