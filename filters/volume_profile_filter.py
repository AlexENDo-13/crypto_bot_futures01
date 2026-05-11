"""
Volume Profile Filter – использует POC и Value Area для подтверждения сигналов.
Исправлено: price above VAH больше не блокирует BUY полностью, а снижает confidence.
"""
import logging
import numpy as np
from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

class VolumeProfileFilter(BaseFilter):
    NAME = "VolumeProfile"
    DESCRIPTION = "Фильтр по объёмному профилю (POC/VAH/VAL) – развороты и пробои"
    PRIORITY = 14
    PARAMS = {
        'enabled': True,
        'timeframe': '4h',
        'lookback_bars': 100,
        'value_area_pct': 0.70,   # 70% объёма для Value Area
        'poc_tolerance': 0.005,   # 0.5% близость к POC
        'vah_penalty': 0.9,       # ИЗМЕНЕНО: было 0.7 – теперь меньше штрафа за пробой VAH
        'poc_boost': 1.1,         # усиление при нахождении вблизи POC
    }

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        candle_data = data.get('candle_data')
        if not candle_data:
            return signal.confidence

        tf = self.config['timeframe']
        df = candle_data.get(tf)
        if df is None or len(df) < self.config['lookback_bars']:
            return signal.confidence

        # Берём последние N свечей
        recent = df.iloc[-self.config['lookback_bars']:]
        price = recent['close'].iloc[-1]
        high = recent['high']
        low = recent['low']
        close = recent['close']
        volume = recent['volume']

        # Строим профиль: разбиваем диапазон на 50 уровней
        price_min = low.min()
        price_max = high.max()
        if price_max == price_min:
            return signal.confidence

        bins = np.linspace(price_min, price_max, 50)
        vol_profile = np.zeros(len(bins) - 1)

        for i in range(len(recent)):
            candle_low = low.iloc[i]
            candle_high = high.iloc[i]
            candle_vol = volume.iloc[i]
            candle_range = candle_high - candle_low if candle_high != candle_low else 1e-9
            for j in range(len(bins) - 1):
                bin_low = bins[j]
                bin_high = bins[j + 1]
                overlap_low = max(candle_low, bin_low)
                overlap_high = min(candle_high, bin_high)
                if overlap_low < overlap_high:
                    vol_profile[j] += candle_vol * (overlap_high - overlap_low) / candle_range

        # Находим POC (уровень с максимальным объёмом)
        poc_idx = np.argmax(vol_profile)
        poc_price = (bins[poc_idx] + bins[poc_idx + 1]) / 2

        # Сортируем уровни по объёму для Value Area
        sorted_idx = np.argsort(vol_profile)[::-1]
        cumulative_vol = 0
        total_vol = vol_profile.sum()
        vah_price = poc_price
        val_price = poc_price

        for idx in sorted_idx:
            cumulative_vol += vol_profile[idx]
            level_price = (bins[idx] + bins[idx + 1]) / 2
            if level_price > vah_price:
                vah_price = level_price
            if level_price < val_price:
                val_price = level_price
            if cumulative_vol / total_vol >= self.config['value_area_pct']:
                break

        poc_tol = self.config['poc_tolerance']

        # Логика фильтрации (ИЗМЕНЕНА)
        if signal.action == 'BUY':
            # Близость к POC – усиление
            if abs(price - poc_price) / poc_price <= poc_tol:
                return min(1.0, signal.confidence * self.config['poc_boost'])
            # Цена ниже VAL – хорошая возможность для покупки
            if price < val_price:
                return min(1.0, signal.confidence * 1.05)
            # Цена выше VAH – снижаем уверенность, но не блокируем
            if price > vah_price * (1 + poc_tol):
                new_conf = signal.confidence * self.config['vah_penalty']
                logger.info(f"VolumeProfile penalty for BUY {signal.symbol}: price above VAH, conf {signal.confidence:.2f} -> {new_conf:.2f}")
                return new_conf
        elif signal.action == 'SELL':
            if abs(price - poc_price) / poc_price <= poc_tol:
                return min(1.0, signal.confidence * self.config['poc_boost'])
            if price > vah_price:
                return min(1.0, signal.confidence * 1.05)
            if price < val_price * (1 - poc_tol):
                new_conf = signal.confidence * self.config['vah_penalty']
                logger.info(f"VolumeProfile penalty for SELL {signal.symbol}: price below VAL, conf {signal.confidence:.2f} -> {new_conf:.2f}")
                return new_conf

        return signal.confidence
