"""
Momentum Strategy - Uses RSI and volume for momentum confirmation.
"""
import pandas as pd
import numpy as np
from typing import Optional

from strategies.base import BaseStrategy, Signal
from indicators.base import RSI, EMA, SMA


class MomentumStrategy(BaseStrategy):
    """
    Momentum strategy using RSI divergence and volume.
    
    Entry: RSI momentum with volume confirmation
    Exit: Momentum exhaustion
    """
    
    NAME = "Momentum"
    DESCRIPTION = "RSI momentum with volume confirmation"
    VERSION = "1.0.0"
    
    PARAMS = {
        'enabled': True,
        'weight': 1.2,
        'timeframes': ['15m', '1h'],
        'rsi_period': 10,
        'rsi_entry_long': 55,
        'rsi_entry_short': 45,
        'volume_ma_period': 20,
        'min_volume_ratio': 1.2,
    }
    
    def __init__(self, params=None):
        super().__init__(params)
        self.rsi = RSI({'period': self.config['rsi_period']})
        self.volume_sma = SMA({'period': self.config['volume_ma_period']})
        self.price_ema = EMA({'period': 20})
    
    def evaluate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> Optional[Signal]:
        """Evaluate momentum signals."""
        if len(candles) < self.config['volume_ma_period'] + 10:
            return None
        
        # Calculate indicators
        rsi_values = self.rsi.calculate(candles)
        volume_ma = self.volume_sma.calculate(candles)
        price_ema = self.price_ema.calculate(candles)
        
        current_price = candles['close'].iloc[-1]
        current_volume = candles['volume'].iloc[-1]
        current_rsi = rsi_values.iloc[-1]
        prev_rsi = rsi_values.iloc[-5]  # 5 bars ago
        
        current_vol_ma = volume_ma.iloc[-1]
        volume_ratio = current_volume / current_vol_ma if current_vol_ma > 0 else 1
        
        # Price vs EMA (trend direction)
        price_above_ema = current_price > price_ema.iloc[-1]
        
        # BUY: RSI rising above threshold with volume
        if (current_rsi > self.config['rsi_entry_long'] and 
            prev_rsi < current_rsi and  # Rising momentum
            volume_ratio > self.config['min_volume_ratio']):
            
            confidence = self._calculate_confidence(
                True, current_rsi, prev_rsi, volume_ratio, price_above_ema
            )
            
            return Signal(
                symbol=symbol,
                action='BUY',
                confidence=confidence,
                meta={
                    'strategy': self.NAME,
                    'timeframe': timeframe,
                    'rsi': round(current_rsi, 2),
                    'rsi_prev': round(prev_rsi, 2),
                    'volume_ratio': round(volume_ratio, 2),
                    'trend_aligned': price_above_ema,
                }
            )
        
        # SELL: RSI falling below threshold with volume
        if (current_rsi < self.config['rsi_entry_short'] and 
            prev_rsi > current_rsi and  # Falling momentum
            volume_ratio > self.config['min_volume_ratio']):
            
            confidence = self._calculate_confidence(
                False, current_rsi, prev_rsi, volume_ratio, not price_above_ema
            )
            
            return Signal(
                symbol=symbol,
                action='SELL',
                confidence=confidence,
                meta={
                    'strategy': self.NAME,
                    'timeframe': timeframe,
                    'rsi': round(current_rsi, 2),
                    'rsi_prev': round(prev_rsi, 2),
                    'volume_ratio': round(volume_ratio, 2),
                    'trend_aligned': not price_above_ema,
                }
            )
        
        return None
    
    def _calculate_confidence(self, is_bullish: bool, rsi: float, 
                              prev_rsi: float, volume_ratio: float,
                              trend_aligned: bool) -> float:
        """Calculate signal confidence."""
        confidence = 0.45  # Base
        
        # RSI momentum strength
        rsi_change = abs(rsi - prev_rsi)
        confidence += min(0.2, rsi_change / 50)
        
        # Volume confirmation
        if volume_ratio > self.config['min_volume_ratio']:
            confidence += min(0.15, (volume_ratio - 1) * 0.1)
        
        # Trend alignment bonus
        if trend_aligned:
            confidence += 0.1
        else:
            confidence -= 0.05  # Counter-trend penalty
        
        return min(1.0, max(0.1, confidence))
