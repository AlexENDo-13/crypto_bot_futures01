"""
Volume Surge Filter.
Requires signal candle volume to be at least multiplier times average volume.
"""
import logging
from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

class VolumeSurgeFilter(BaseFilter):
    NAME = "VolumeSurgeFilter"
    DESCRIPTION = "Blocks signals with low relative volume (no surge)"
    PRIORITY = 12  # После базовых, до трендовых
    PARAMS = {
        'enabled': True,
        'min_volume_mult': 1.5,    # минимальное превышение среднего объёма
        'lookback_bars': 20,       # период усреднения
        'timeframe': '1h'          # с какого ТФ брать объём (обычно тот же, что у сигнала)
    }

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        candle_data = data.get('candle_data')
        if not candle_data:
            return signal.confidence

        tf = self.config.get('timeframe', '1h')
        if tf not in candle_data:
            # Пробуем первый доступный таймфрейм
            tf = next(iter(candle_data.keys()), None)
            if not tf:
                return signal.confidence

        df = candle_data[tf]
        lookback = self.config['lookback_bars']
        if len(df) < lookback + 1:
            return signal.confidence

        # Объём последней закрытой свечи
        current_volume = df['volume'].iloc[-1]
        # Средний объём за предыдущие lookback свечей
        avg_volume = df['volume'].iloc[-(lookback+1):-1].mean()

        if avg_volume <= 0:
            return signal.confidence

        ratio = current_volume / avg_volume
        threshold = self.config['min_volume_mult']

        if ratio < threshold:
            logger.info(f"VolumeSurge blocked {signal.symbol}: vol ratio {ratio:.2f} < {threshold}")
            return 0.0

        # Пропускаем, можно даже немного повысить уверенность при сильном всплеске
        if ratio > 2.0:
            logger.debug(f"Volume surge boost for {signal.symbol}: ratio {ratio:.2f}")
            return min(1.0, signal.confidence * 1.1)

        return signal.confidence
