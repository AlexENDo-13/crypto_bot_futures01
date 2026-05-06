from indicators.base import BaseIndicator
import pandas as pd

class OBV(BaseIndicator):
    NAME = "OBV"
    DESCRIPTION = "On-Balance Volume"
    PARAMS = {}

    def calculate(self, candles: pd.DataFrame) -> pd.Series:
        close = candles['close']
        volume = candles['volume']
        obv = [0]
        for i in range(1, len(close)):
            if close.iloc[i] > close.iloc[i-1]:
                obv.append(obv[-1] + volume.iloc[i])
            elif close.iloc[i] < close.iloc[i-1]:
                obv.append(obv[-1] - volume.iloc[i])
            else:
                obv.append(obv[-1])
        return pd.Series(obv, index=candles.index)
