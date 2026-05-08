"""
Breakout Strategy – for high volatility markets.
Uses Bollinger Band squeeze + volume surge.
No scalping – 1h/4h timeframes.
"""
import pandas as pd
import numpy as np
from typing import Optional
from strategies.base import BaseStrategy, Signal
from indicators.base import BollingerBands, ATR, EMA

class BreakoutStrategy(BaseStrategy):
    NAME = "Breakout"
    DESCRIPTION = "Bollinger squeeze breakout with volume confirmation"
    VERSION = "1.0.0"
    PARAMS = {
        'enabled': True, 'weight': 1.0, 'timeframes': ['1h', '4h'],
        'bb_period': 20, 'bb_std_dev': 2.0, 'atr_period': 14,
        'squeeze_threshold': 1.5, 'volume_ma_period': 20, 'min_volume_ratio': 1.5, 'ema_period': 50,
    }
    def __init__(self, params=None):
        super().__init__(params)
        self.bb = BollingerBands({'period': self.config['bb_period'], 'std_dev': self.config['bb_std_dev']})
        self.atr = ATR({'period': self.config['atr_period']})
        self.ema = EMA({'period': self.config['ema_period']})
        self.volume_sma = EMA({'period': self.config['volume_ma_period']})
    def evaluate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> Optional[Signal]:
        if len(candles) < self.config['bb_period'] + 10:
            return None
        bb = self.bb.calculate(candles)
        atr = self.atr.calculate(candles)
        ema = self.ema.calculate(candles)
        vol_ma = self.volume_sma.calculate(candles)
        current_price = candles['close'].iloc[-1]
        prev_price = candles['close'].iloc[-2]
        current_vol = candles['volume'].iloc[-1]
        upper = bb['upper'].iloc[-1]
        lower = bb['lower'].iloc[-1]
        bb_width = upper - lower
        atr_val = atr.iloc[-1]
        if atr_val == 0:
            return None
        is_squeeze = bb_width < self.config['squeeze_threshold'] * atr_val
        if not is_squeeze:
            return None
        vol_ratio = current_vol / vol_ma.iloc[-1] if vol_ma.iloc[-1] > 0 else 1.0
        if vol_ratio < self.config['min_volume_ratio']:
            return None
        ema_val = ema.iloc[-1]
        trend_up = current_price > ema_val
        if prev_price <= upper and current_price > upper and trend_up:
            confidence = 0.6 + min(0.3, (vol_ratio - 1) * 0.15)
            return Signal(symbol=symbol, action='BUY', confidence=min(0.95, confidence),
                          meta={'strategy': self.NAME, 'timeframe': timeframe, 'reason': f'BB breakout up, vol={vol_ratio:.2f}'})
        elif prev_price >= lower and current_price < lower and not trend_up:
            confidence = 0.6 + min(0.3, (vol_ratio - 1) * 0.15)
            return Signal(symbol=symbol, action='SELL', confidence=min(0.95, confidence),
                          meta={'strategy': self.NAME, 'timeframe': timeframe, 'reason': f'BB breakout down, vol={vol_ratio:.2f}'})
        return None
