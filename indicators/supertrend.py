import pandas as pd
import numpy as np
from indicators.base import BaseIndicator

class SuperTrend(BaseIndicator):
    NAME = "SuperTrend"
    DESCRIPTION = "SuperTrend indicator for trend direction and stop-loss placement"
    PARAMS = {'period': 10, 'multiplier': 3.0}

    def calculate(self, candles: pd.DataFrame) -> pd.DataFrame:
        period = self.config['period']
        multiplier = self.config['multiplier']

        high = candles['high']
        low = candles['low']
        close = candles['close']

        atr = self._calc_atr(high, low, close, period)

        hl2 = (high + low) / 2
        upper_band = hl2 + multiplier * atr
        lower_band = hl2 - multiplier * atr

        trend = pd.Series(1.0, index=candles.index)
        supertrend = pd.Series(0.0, index=candles.index)

        for i in range(1, len(candles)):
            if close.iloc[i] > upper_band.iloc[i-1]:
                trend.iloc[i] = 1
            elif close.iloc[i] < lower_band.iloc[i-1]:
                trend.iloc[i] = -1
            else:
                trend.iloc[i] = trend.iloc[i-1]
                if trend.iloc[i] == 1 and lower_band.iloc[i] < lower_band.iloc[i-1]:
                    lower_band.iloc[i] = lower_band.iloc[i-1]
                if trend.iloc[i] == -1 and upper_band.iloc[i] > upper_band.iloc[i-1]:
                    upper_band.iloc[i] = upper_band.iloc[i-1]

            if trend.iloc[i] == 1:
                supertrend.iloc[i] = lower_band.iloc[i]
            else:
                supertrend.iloc[i] = upper_band.iloc[i]

        return pd.DataFrame({
            'supertrend': supertrend,
            'trend': trend
        }, index=candles.index)

    @staticmethod
    def _calc_atr(high, low, close, period):
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
