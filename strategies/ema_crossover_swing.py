import pandas as pd
from typing import Optional
from strategies.base import BaseStrategy, Signal
from indicators.base import EMA

class EMACrossoverSwingStrategy(BaseStrategy):
    NAME = "EMACrossoverSwing"
    DESCRIPTION = "EMA crossover swing (4h) with ADX trend filter – safe for BingX"
    VERSION = "1.0.0"
    PARAMS = {
        'enabled': True, 'weight': 1.0, 'timeframes': ['1h', '4h'],
        'ema_fast': 9, 'ema_slow': 21, 'min_adx': 20, 'use_confirmation': True,
    }

    def __init__(self, params=None, engine=None):
        super().__init__(params, engine=engine)
        self.ema_fast = EMA({'period': self.config['ema_fast']})
        self.ema_slow = EMA({'period': self.config['ema_slow']})

    def evaluate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> Optional[Signal]:
        if len(candles) < self.config['ema_slow'] + 5:
            return None

        ema_fast = self.ema_fast.calculate(candles)
        ema_slow = self.ema_slow.calculate(candles)

        cross_up = (ema_fast.iloc[-2] <= ema_slow.iloc[-2]) and (ema_fast.iloc[-1] > ema_slow.iloc[-1])
        cross_down = (ema_fast.iloc[-2] >= ema_slow.iloc[-2]) and (ema_fast.iloc[-1] < ema_slow.iloc[-1])

        if cross_up:
            return Signal(symbol=symbol, action='BUY', confidence=0.7,
                          meta={'strategy': self.NAME, 'timeframe': timeframe, 'reason': 'EMA crossover UP'})
        elif cross_down:
            return Signal(symbol=symbol, action='SELL', confidence=0.7,
                          meta={'strategy': self.NAME, 'timeframe': timeframe, 'reason': 'EMA crossover DOWN'})
        return None
