from indicators.base import BaseIndicator
import pandas as pd

class MFI(BaseIndicator):
    NAME = "MFI"
    DESCRIPTION = "Money Flow Index"
    PARAMS = {'period': 14}

    def calculate(self, candles: pd.DataFrame) -> pd.Series:
        typical_price = (candles['high'] + candles['low'] + candles['close']) / 3
        money_flow = typical_price * candles['volume']
        positive_flow = money_flow.where(typical_price > typical_price.shift(), 0)
        negative_flow = money_flow.where(typical_price < typical_price.shift(), 0)
        positive_sum = positive_flow.rolling(self.config['period']).sum()
        negative_sum = negative_flow.rolling(self.config['period']).sum()
        mfi = 100 - (100 / (1 + positive_sum / negative_sum))
        return mfi
