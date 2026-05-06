from indicators.base import BaseIndicator
import pandas as pd
import numpy as np

class ADX(BaseIndicator):
    NAME = "ADX"
    DESCRIPTION = "Average Directional Index"
    PARAMS = {'period': 14}

    def calculate(self, candles: pd.DataFrame) -> pd.Series:
        period = self.config['period']
        high, low, close = candles['high'], candles['low'], candles['close']
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        up = high - high.shift()
        down = low.shift() - low
        plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=candles.index)
        minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=candles.index)
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(period).mean()
        return adx
