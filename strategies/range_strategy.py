"""
Range Strategy – for sideways markets.
Uses RSI + support/resistance levels.
No scalping – 1h/4h timeframes.
"""
import pandas as pd
import numpy as np
from typing import Optional
from strategies.base import BaseStrategy, Signal
from indicators.base import RSI, ATR, EMA

class RangeStrategy(BaseStrategy):
    NAME = "Range"
    DESCRIPTION = "RSI mean reversion in ranging markets"
    VERSION = "1.0.0"
    PARAMS = {
        'enabled': True, 'weight': 1.0, 'timeframes': ['1h', '4h'],
        'rsi_period': 14, 'rsi_overbought': 72, 'rsi_oversold': 28,
        'atr_period': 14, 'lookback': 50, 'min_bars': 20,
    }
    def __init__(self, params=None):
        super().__init__(params)
        self.rsi = RSI({'period': self.config['rsi_period']})
        self.atr = ATR({'period': self.config['atr_period']})
        self.ema = EMA({'period': 50})
    def evaluate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> Optional[Signal]:
        if len(candles) < self.config['lookback'] + 10:
            return None
        rsi_vals = self.rsi.calculate(candles)
        atr = self.atr.calculate(candles)
        ema = self.ema.calculate(candles)
        current_price = candles['close'].iloc[-1]
        current_rsi = rsi_vals.iloc[-1]
        atr_val = atr.iloc[-1]
        ema_val = ema.iloc[-1]
        recent_high = candles['high'].iloc[-self.config['lookback']:].max()
        recent_low = candles['low'].iloc[-self.config['lookback']:].min()
        range_height = recent_high - recent_low
        if range_height == 0 or atr_val == 0:
            return None
        price_vs_ema = abs(current_price - ema_val) / ema_val if ema_val > 0 else 0
        if price_vs_ema > 0.03:
            return None
        position_in_range = (current_price - recent_low) / range_height
        if position_in_range < 0.15 and current_rsi < self.config['rsi_oversold']:
            confidence = 0.55 + min(0.35, (self.config['rsi_oversold'] - current_rsi) / 50)
            return Signal(symbol=symbol, action='BUY', confidence=min(0.9, confidence),
                          meta={'strategy': self.NAME, 'timeframe': timeframe, 'reason': f'Range bottom, RSI={current_rsi:.1f}'})
        if position_in_range > 0.85 and current_rsi > self.config['rsi_overbought']:
            confidence = 0.55 + min(0.35, (current_rsi - self.config['rsi_overbought']) / 50)
            return Signal(symbol=symbol, action='SELL', confidence=min(0.9, confidence),
                          meta={'strategy': self.NAME, 'timeframe': timeframe, 'reason': f'Range top, RSI={current_rsi:.1f}'})
        return None
