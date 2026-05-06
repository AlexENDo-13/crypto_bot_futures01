from strategies.base import BaseStrategy, Signal
from indicators.base import BollingerBands, ATR

class SqueezeStrategy(BaseStrategy):
    NAME = "Squeeze"
    PARAMS = {'enabled': True, 'weight': 0.8, 'timeframes': ['1h']}
    
    def __init__(self, params=None):
        super().__init__(params)
        self.bb = BollingerBands({'period': 20, 'std_dev': 2.0})
        self.atr = ATR({'period': 14})
    
    def evaluate(self, symbol, timeframe, candles):
        if len(candles) < 20:
            return None
        bb = self.bb.calculate(candles)
        atr_val = self.atr.calculate(candles).iloc[-1]
        bb_width = bb['upper'].iloc[-1] - bb['lower'].iloc[-1]
        # Сжатие: ширина полос < 1.5 * ATR
        if bb_width < 1.5 * atr_val:
            # Ожидаем расширение и вход в направлении тренда
            if candles['close'].iloc[-1] > bb['middle'].iloc[-1]:
                return Signal(symbol=symbol, action='BUY', confidence=0.65,
                             meta={'reason': 'Bollinger squeeze, breakout up'})
            else:
                return Signal(symbol=symbol, action='SELL', confidence=0.65,
                             meta={'reason': 'Bollinger squeeze, breakout down'})
        return None
