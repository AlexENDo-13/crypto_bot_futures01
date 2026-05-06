from indicators.base import BaseIndicator
import pandas as pd
import numpy as np

class Ichimoku(BaseIndicator):
    NAME = "Ichimoku"
    DESCRIPTION = "Ichimoku Cloud"
    PARAMS = {'tenkan': 9, 'kijun': 26, 'senkou_b': 52}

    def calculate(self, candles: pd.DataFrame) -> pd.DataFrame:
        high, low, close = candles['high'], candles['low'], candles['close']
        tenkan = (high.rolling(self.config['tenkan']).max() + low.rolling(self.config['tenkan']).min()) / 2
        kijun = (high.rolling(self.config['kijun']).max() + low.rolling(self.config['kijun']).min()) / 2
        senkou_a = ((tenkan + kijun) / 2).shift(self.config['kijun'])
        senkou_b = ((high.rolling(self.config['senkou_b']).max() + low.rolling(self.config['senkou_b']).min()) / 2).shift(self.config['kijun'])
        return pd.DataFrame({'tenkan': tenkan, 'kijun': kijun, 'senkou_a': senkou_a, 'senkou_b': senkou_b}, index=candles.index)
