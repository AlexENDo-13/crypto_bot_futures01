from indicators.base import BaseIndicator
import pandas as pd

class KeltnerChannels(BaseIndicator):
    NAME = "KeltnerChannels"
    DESCRIPTION = "Keltner Channels"
    PARAMS = {'ema_period': 20, 'atr_period': 10, 'multiplier': 2.0}

    def calculate(self, candles: pd.DataFrame) -> pd.DataFrame:
        typical_price = (candles['high'] + candles['low'] + candles['close']) / 3
        ema = typical_price.ewm(span=self.config['ema_period'], adjust=False).mean()
        tr = pd.concat([candles['high'] - candles['low'],
                        abs(candles['high'] - candles['close'].shift()),
                        abs(candles['low'] - candles['close'].shift())], axis=1).max(axis=1)
        atr = tr.rolling(self.config['atr_period']).mean()
        upper = ema + self.config['multiplier'] * atr
        lower = ema - self.config['multiplier'] * atr
        return pd.DataFrame({'upper': upper, 'middle': ema, 'lower': lower}, index=candles.index)
