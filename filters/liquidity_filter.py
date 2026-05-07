"""
Liquidity filter: blocks signals when recent volume is too low relative to average.
Now with adaptive threshold – relaxes if no trades were executed for a while.
Also loads min_volume_ratio from config.ini under [FILTERS] section.
"""
import logging
import time
import pandas as pd
from configparser import ConfigParser
from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

class LiquidityFilter(BaseFilter):
    NAME = "LiquidityFilter"
    DESCRIPTION = "Blocks signals with low recent volume (adaptive)"
    PRIORITY = 15
    PARAMS = {
        'enabled': True,
        'min_volume_ratio': 0.3,
        'lookback_bars': 20,
        'recent_bars': 5,
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
            if cfg.has_option('FILTERS', 'liquidity_min_ratio'):
                val = cfg.getfloat('FILTERS', 'liquidity_min_ratio')
                self.config['min_volume_ratio'] = val
                logger.debug(f"Liquidity min_volume_ratio loaded from config: {val}")
        except Exception as e:
            logger.debug(f"Could not load Liquidity config: {e}")

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        candle_data = data.get('candle_data')
        if candle_data is None or '1h' not in candle_data:
            return signal.confidence

        df = candle_data['1h']
        min_periods = max(self.config['lookback_bars'], self.config['recent_bars'])
        if len(df) < min_periods:
            return signal.confidence

        recent_vol = df['volume'].iloc[-self.config['recent_bars']:].mean()
        avg_vol = df['volume'].iloc[-self.config['lookback_bars']:].mean()
        if avg_vol <= 0:
            return signal.confidence

        ratio = recent_vol / avg_vol

        threshold = self.config['min_volume_ratio']
        if self.config.get('adaptive_relax'):
            time_since_last_trade = time.time() - self._last_trade_time
            if time_since_last_trade > self.config.get('relax_after_seconds', 180):
                threshold = max(0.02, threshold * 0.5)
                logger.debug(f"Liquidity threshold relaxed to {threshold:.2f}")

        if ratio < threshold:
            logger.info(f"Liquidity filter blocked {signal.symbol}: volume ratio {ratio:.2f} < {threshold:.2f}")
            return 0.0

        self._last_trade_time = time.time()
        return signal.confidence
