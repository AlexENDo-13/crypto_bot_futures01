from indicators.base import BaseIndicator
import pandas as pd
import numpy as np

class VolumeProfile(BaseIndicator):
    NAME = "VolumeProfile"
    DESCRIPTION = "Volume Profile"
    PARAMS = {'bins': 50}

    def calculate(self, candles: pd.DataFrame) -> dict:
        high, low, close, volume = candles['high'], candles['low'], candles['close'], candles['volume']
        price_min = low.min()
        price_max = high.max()
        price_range = price_max - price_min
        if price_range == 0:
            return {'poc': price_min, 'profile': {}}

        bin_size = price_range / self.config['bins']
        bins = np.arange(price_min, price_max + bin_size, bin_size)
        vol_profile = {b: 0 for b in bins[:-1]}

        for i in range(len(candles)):
            candle_low = low.iloc[i]
            candle_high = high.iloc[i]
            candle_vol = volume.iloc[i]
            candle_range = candle_high - candle_low
            if candle_range == 0:
                candle_range = 1e-9  # защита от деления на ноль

            for j in range(len(bins) - 1):
                bin_low = bins[j]
                bin_high = bins[j + 1]

                # === FIX: Корректная проверка пересечения свечи и бина ===
                # Свеча пересекает бин если: max(нижние границы) < min(верхние границы)
                overlap_low = max(candle_low, bin_low)
                overlap_high = min(candle_high, bin_high)

                if overlap_low < overlap_high:
                    overlap = overlap_high - overlap_low
                    vol_profile[bin_low] += candle_vol * (overlap / candle_range)

        if vol_profile:
            max_vol_bin = max(vol_profile, key=vol_profile.get)
        else:
            max_vol_bin = price_min

        return {'poc': max_vol_bin, 'profile': vol_profile}
