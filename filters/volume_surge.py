"""
Volume Surge Filter.
Requires signal candle volume to be at least multiplier times average volume.
Now with adaptive threshold – relaxes if no trades were executed for a while.
Also loads min_volume_mult from config.ini under [FILTERS] section.
"""
import logging
import time
from configparser import ConfigParser
from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

class VolumeSurgeFilter(BaseFilter):
    NAME = "VolumeSurgeFilter"
    DESCRIPTION = "Blocks signals with low relative volume (no surge)"
    PRIORITY = 12
    PARAMS = {
        'enabled': True,
        'min_volume_mult': 0.15,          # было 1.5
        'lookback_bars': 20,
        'timeframe': '1h',
        'adaptive_relax': True,
        'relax_after_seconds': 180,
    }

    def __init__(self, params=None):
        super().__init__(params)
        self._load_config()
        self._last_trade_time = time.time()

    def _load_config(self):
        try:
            cfg = ConfigParser()
            cfg.read('config.ini')
            if cfg.has_option('FILTERS', 'volume_surge_min_mult'):
                val = cfg.getfloat('FILTERS', 'volume_surge_min_mult')
                self.config['min_volume_mult'] = val
        except Exception as e:
            logger.debug(f"Could not load VolumeSurge config: {e}")

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        candle_data = data.get('candle_data')
        if not candle_data:
            return signal.confidence

        tf = self.config.get('timeframe', '1h')
        if isinstance(tf, list):
            tf = tf[0] if tf else '1h'

        if tf not in candle_data:
            tf = next(iter(candle_data.keys()), None)
            if not tf:
                return signal.confidence

        df = candle_data[tf]
        lookback = self.config['lookback_bars']
        if len(df) < lookback + 1:
            return signal.confidence

        current_volume = df['volume'].iloc[-1]
        avg_volume = df['volume'].iloc[-(lookback+1):-1].mean()

        if avg_volume <= 0:
            return signal.confidence

        ratio = current_volume / avg_volume

        threshold = self.config['min_volume_mult']
        if self.config.get('adaptive_relax'):
            time_since_last_trade = time.time() - self._last_trade_time
            if time_since_last_trade > self.config.get('relax_after_seconds', 180):
                threshold = max(0.1, threshold * 0.5)

        if ratio < threshold:
            logger.info(f"VolumeSurge blocked {signal.symbol}: vol ratio {ratio:.2f} < {threshold}")
            return 0.0

        self._last_trade_time = time.time()

        if ratio > 2.0:
            return min(1.0, signal.confidence * 1.1)

        return signal.confidence
