"""
Trend Following Strategy - Uses EMA crossover with trend confirmation.
"""
import pandas as pd
import numpy as np
from typing import Optional

from strategies.base import BaseStrategy, Signal
from indicators.base import EMA, ATR, RSI


class TrendFollowingStrategy(BaseStrategy):
    """
    Trend following strategy using EMA crossover.
    
    Entry: Fast EMA crosses above slow EMA with RSI confirmation
    Exit: Opposite crossover or trailing stop
    """
    
    NAME = "TrendFollowing"
    DESCRIPTION = "EMA crossover trend following with RSI filter"
    VERSION = "1.0.0"
    
    PARAMS = {
        'enabled': True,
        'weight': 1.5,
        'timeframes': ['1h', '4h'],
        'fast_ema': 12,
        'slow_ema': 26,
        'rsi_period': 14,
        'rsi_overbought': 65,
        'rsi_oversold': 35,
        'min_trend_bars': 3,
    }
    
    def __init__(self, params=None):
        super().__init__(params)
        self.ema_fast = EMA({'period': self.config['fast_ema']})
        self.ema_slow = EMA({'period': self.config['slow_ema']})
        self.rsi = RSI({'period': self.config['rsi_period']})
        self.atr = ATR({'period': 14})
    
    def evaluate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> Optional[Signal]:
        """Evaluate trend following signals."""
        if len(candles) < self.config['slow_ema'] + 10:
            return None
        
        # Calculate indicators
        ema_fast_line = self.ema_fast.calculate(candles)
        ema_slow_line = self.ema_slow.calculate(candles)
        rsi_values = self.rsi.calculate(candles)
        atr_values = self.atr.calculate(candles)
        
        # Get current and previous values
        current_fast = ema_fast_line.iloc[-1]
        current_slow = ema_slow_line.iloc[-1]
        prev_fast = ema_fast_line.iloc[-2]
        prev_slow = ema_slow_line.iloc[-2]
        current_rsi = rsi_values.iloc[-1]
        current_atr = atr_values.iloc[-1]
        
        current_price = candles['close'].iloc[-1]
        
        # Check for crossover
        bullish_cross = prev_fast <= prev_slow and current_fast > current_slow
        bearish_cross = prev_fast >= prev_slow and current_fast < current_slow
        
        # Check trend alignment (multiple bars)
        fast_above_slow = (ema_fast_line.iloc[-self.config['min_trend_bars']:].values > 
                          ema_slow_line.iloc[-self.config['min_trend_bars']:].values)
        slow_above_fast = (ema_fast_line.iloc[-self.config['min_trend_bars']:].values < 
                          ema_slow_line.iloc[-self.config['min_trend_bars']:].values)
        
        # BUY signal
        if bullish_cross or (fast_above_slow.all() and current_rsi > self.config['rsi_oversold']):
            if current_rsi < self.config['rsi_overbought']:  # Not overbought
                confidence = self._calculate_confidence(
                    True, current_rsi, current_fast, current_slow, current_atr, current_price
                )
                
                sl_price = current_price - (current_atr * 2)
                tp_price = current_price + (current_atr * 3)
                
                return Signal(
                    symbol=symbol,
                    action='BUY',
                    confidence=confidence,
                    meta={
                        'strategy': self.NAME,
                        'timeframe': timeframe,
                        'rsi': round(current_rsi, 2),
                        'atr': round(current_atr, 6),
                        'ema_fast': round(current_fast, 6),
                        'ema_slow': round(current_slow, 6),
                    },
                    suggested_sl=sl_price,
                    suggested_tp=tp_price
                )
        
        # SELL signal
        if bearish_cross or (slow_above_fast.all() and current_rsi < self.config['rsi_overbought']):
            if current_rsi > self.config['rsi_oversold']:  # Not oversold
                confidence = self._calculate_confidence(
                    False, current_rsi, current_fast, current_slow, current_atr, current_price
                )
                
                sl_price = current_price + (current_atr * 2)
                tp_price = current_price - (current_atr * 3)
                
                return Signal(
                    symbol=symbol,
                    action='SELL',
                    confidence=confidence,
                    meta={
                        'strategy': self.NAME,
                        'timeframe': timeframe,
                        'rsi': round(current_rsi, 2),
                        'atr': round(current_atr, 6),
                        'ema_fast': round(current_fast, 6),
                        'ema_slow': round(current_slow, 6),
                    },
                    suggested_sl=sl_price,
                    suggested_tp=tp_price
                )
        
        return None
    
    def _calculate_confidence(self, is_bullish: bool, rsi: float, 
                              fast_ema: float, slow_ema: float, 
                              atr: float, price: float) -> float:
        """Calculate signal confidence (0.0 to 1.0)."""
        confidence = 0.5  # Base
        
        # RSI alignment
        if is_bullish:
            confidence += 0.15 * (50 - min(rsi, 50)) / 50  # Lower RSI = more room to move up
        else:
            confidence += 0.15 * (max(rsi, 50) - 50) / 50  # Higher RSI = more room to move down
        
        # EMA separation (trend strength)
        ema_diff = abs(fast_ema - slow_ema) / price
        confidence += min(0.2, ema_diff * 10)
        
        # ATR check (avoid low volatility)
        atr_pct = atr / price
        if 0.005 < atr_pct < 0.05:  # Normal volatility
            confidence += 0.1
        
        return min(1.0, max(0.1, confidence))
