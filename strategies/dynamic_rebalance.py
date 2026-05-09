"""
Dynamic Rebalance Strategy – перераспределяет капитал между позициями.
"""
import logging
import numpy as np
from typing import Optional
from strategies.base import BaseStrategy, Signal

logger = logging.getLogger(__name__)

class DynamicRebalanceStrategy(BaseStrategy):
    NAME = "DynamicRebalance"
    DESCRIPTION = "Автоматически перераспределяет капитал между позициями по волатильности"
    VERSION = "1.0.0"
    PARAMS = {
        'enabled': True,
        'weight': 0.5,
        'timeframes': ['1h'],
        'rebalance_interval_hours': 4,
        'target_volatility': 0.02,
        'max_allocation_pct': 0.40,
    }

    def __init__(self, params=None, engine=None):
        super().__init__(params, engine=engine)

    def evaluate(self, symbol: str, timeframe: str, candles) -> Optional[Signal]:
        return None

    def calculate_weights(self, positions, candle_data):
        weights = {}
        total_vol = 0.0
        vol_map = {}
        for pos in positions:
            sym = pos.symbol
            df = candle_data.get(sym, {}).get('1h')
            if df is not None and len(df) >= 14:
                atr = self._calc_atr(df)
                price = df['close'].iloc[-1]
                if price > 0:
                    vol = atr / price
                    vol_map[sym] = vol
                    total_vol += vol
                else:
                    vol_map[sym] = 0.0
            else:
                vol_map[sym] = 0.0
        if total_vol == 0:
            for pos in positions:
                weights[pos.symbol] = 1.0 / len(positions)
            return weights
        for pos in positions:
            sym = pos.symbol
            inv_vol = 1.0 / vol_map[sym] if vol_map[sym] > 0 else 0.0
            weights[sym] = inv_vol
        total_inv = sum(weights.values())
        if total_inv == 0:
            for pos in positions:
                weights[pos.symbol] = 1.0 / len(positions)
            return weights
        for sym in weights:
            weights[sym] = min(weights[sym] / total_inv, self.config['max_allocation_pct'])
        s = sum(weights.values())
        if s > 0:
            for sym in weights:
                weights[sym] /= s
        return weights

    @staticmethod
    def _calc_atr(df, period=14):
        high, low, close = df['high'], df['low'], df['close']
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean().iloc[-1]
