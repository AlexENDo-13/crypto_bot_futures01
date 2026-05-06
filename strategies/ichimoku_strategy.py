from strategies.base import BaseStrategy, Signal
from indicators.ichimoku import Ichimoku
import pandas as pd

class IchimokuStrategy(BaseStrategy):
    NAME = "Ichimoku"
    PARAMS = {'enabled': True, 'weight': 1.0, 'timeframes': ['4h']}
    
    def __init__(self, params=None):
        super().__init__(params)
        self.ichi = Ichimoku()
    
    def evaluate(self, symbol, timeframe, candles):
        if len(candles) < 52:
            return None
        data = self.ichi.calculate(candles)
        last = data.iloc[-1]
        prev = data.iloc[-2]
        price = candles['close'].iloc[-1]
        
        # Пробой облака вверх
        if prev['senkou_a'] < prev['senkou_b'] and last['senkou_a'] > last['senkou_b'] and price > last['senkou_a']:
            return Signal(symbol=symbol, action='BUY', confidence=0.7,
                         meta={'reason': 'Ichimoku cloud breakout up'})
        # Пробой облака вниз
        elif prev['senkou_a'] > prev['senkou_b'] and last['senkou_a'] < last['senkou_b'] and price < last['senkou_a']:
            return Signal(symbol=symbol, action='SELL', confidence=0.7,
                         meta={'reason': 'Ichimoku cloud breakout down'})
        return None
