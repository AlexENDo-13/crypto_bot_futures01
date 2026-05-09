import pandas as pd
from typing import Optional
from strategies.base import BaseStrategy, Signal
from indicators.supertrend import SuperTrend

class SuperTrendSwingStrategy(BaseStrategy):
    NAME = "SuperTrendSwing"
    DESCRIPTION = "SuperTrend on 1h/4h for swing entries – no scalping"
    VERSION = "1.0.0"
    PARAMS = {
        'enabled': True, 'weight': 1.0, 'timeframes': ['1h', '4h'],
        'super_period': 10, 'super_mult': 3.0,
    }

    def __init__(self, params=None, engine=None):
        super().__init__(params, engine=engine)
        self.super = SuperTrend({'period': self.config['super_period'], 'multiplier': self.config['super_mult']})

    def evaluate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> Optional[Signal]:
        if len(candles) < 20:
            return None

        st = self.super.calculate(candles)
        trend = st['trend'].iloc[-1]
        prev_trend = st['trend'].iloc[-2]

        if prev_trend == -1 and trend == 1:
            return Signal(symbol=symbol, action='BUY', confidence=0.65,
                          meta={'strategy': self.NAME, 'timeframe': timeframe, 'reason': 'SuperTrend turned bullish'})
        elif prev_trend == 1 and trend == -1:
            return Signal(symbol=symbol, action='SELL', confidence=0.65,
                          meta={'strategy': self.NAME, 'timeframe': timeframe, 'reason': 'SuperTrend turned bearish'})
        return None
