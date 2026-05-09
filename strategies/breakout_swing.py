import pandas as pd
from typing import Optional
from strategies.base import BaseStrategy, Signal
from indicators.base import EMA, ATR

class BreakoutSwingStrategy(BaseStrategy):
    NAME = "BreakoutSwing"
    DESCRIPTION = "Breakout strategy on 1h/4h with ATR stop – no scalping"
    VERSION = "1.0.0"
    PARAMS = {
        'enabled': True, 'weight': 1.0, 'timeframes': ['1h', '4h'],
        'ema_period': 200, 'atr_period': 14, 'lookback': 20,
    }

    def __init__(self, params=None, engine=None):
        super().__init__(params, engine=engine)
        self.ema = EMA({'period': self.config['ema_period']})
        self.atr = ATR({'period': self.config['atr_period']})

    def evaluate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> Optional[Signal]:
        if len(candles) < self.config['ema_period'] + self.config['lookback']:
            return None

        ema_val = self.ema.calculate(candles).iloc[-1]
        atr_val = self.atr.calculate(candles).iloc[-1]
        price = candles['close'].iloc[-1]
        recent_high = candles['high'].iloc[-self.config['lookback']:-1].max()
        recent_low = candles['low'].iloc[-self.config['lookback']:-1].min()

        if price > ema_val and price > recent_high:
            return Signal(symbol=symbol, action='BUY', confidence=0.65,
                          suggested_sl=price - atr_val * 2.0,
                          suggested_tp=price + atr_val * 4.0,
                          meta={'strategy': self.NAME, 'timeframe': timeframe, 'reason': 'Swing breakout UP'})
        elif price < ema_val and price < recent_low:
            return Signal(symbol=symbol, action='SELL', confidence=0.65,
                          suggested_sl=price + atr_val * 2.0,
                          suggested_tp=price - atr_val * 4.0,
                          meta={'strategy': self.NAME, 'timeframe': timeframe, 'reason': 'Swing breakout DOWN'})
        return None
