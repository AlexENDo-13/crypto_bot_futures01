"""
Mean Reversion Strategy - Uses Bollinger Bands for range-bound markets.
"""
import pandas as pd
import numpy as np
from typing import Optional

from strategies.base import BaseStrategy, Signal
from indicators.base import BollingerBands, RSI, SMA


class MeanReversionStrategy(BaseStrategy):
    NAME = "MeanReversion"
    DESCRIPTION = "Bollinger Bands mean reversion with RSI"
    VERSION = "1.0.0"
    
    PARAMS = {
        'enabled': True,            # отключено
        'weight': 1.0,
        'timeframes': ['15m', '1h'],
        'bb_period': 20,
        'bb_std_dev': 2.0,
        'rsi_period': 14,
        'rsi_overbought': 70,
        'rsi_oversold': 30,
    }
    
    def __init__(self, params=None):
        super().__init__(params)
        self.bb = BollingerBands({
            'period': self.config['bb_period'],
            'std_dev': self.config['bb_std_dev']
        })
        self.rsi = RSI({'period': self.config['rsi_period']})
        self.sma = SMA({'period': self.config['bb_period']})
    
    def evaluate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> Optional[Signal]:
        if len(candles) < self.config['bb_period'] + 10:
            return None
        
        bb_values = self.bb.calculate(candles)
        rsi_values = self.rsi.calculate(candles)
        
        current_price = candles['close'].iloc[-1]
        prev_price = candles['close'].iloc[-2]
        
        upper = bb_values['upper'].iloc[-1]
        middle = bb_values['middle'].iloc[-1]
        lower = bb_values['lower'].iloc[-1]
        
        current_rsi = rsi_values.iloc[-1]
        
        band_range = upper - lower
        if band_range == 0:
            return None
        
        position_in_band = (current_price - lower) / band_range
        
        if position_in_band < 0.1 and current_rsi < self.config['rsi_oversold']:
            confidence = self._calculate_confidence(True, position_in_band, current_rsi)
            return Signal(
                symbol=symbol,
                action='BUY',
                confidence=confidence,
                meta={
                    'strategy': self.NAME,
                    'timeframe': timeframe,
                    'rsi': round(current_rsi, 2),
                    'bb_position': round(position_in_band, 3),
                    'bb_lower': round(lower, 6),
                    'bb_middle': round(middle, 6),
                    'bb_upper': round(upper, 6),
                },
                suggested_sl=lower - (band_range * 0.1),
                suggested_tp=middle
            )
        
        if position_in_band > 0.9 and current_rsi > self.config['rsi_overbought']:
            confidence = self._calculate_confidence(False, position_in_band, current_rsi)
            return Signal(
                symbol=symbol,
                action='SELL',
                confidence=confidence,
                meta={
                    'strategy': self.NAME,
                    'timeframe': timeframe,
                    'rsi': round(current_rsi, 2),
                    'bb_position': round(position_in_band, 3),
                    'bb_lower': round(lower, 6),
                    'bb_middle': round(middle, 6),
                    'bb_upper': round(upper, 6),
                },
                suggested_sl=upper + (band_range * 0.1),
                suggested_tp=middle
            )
        return None
    
    def _calculate_confidence(self, is_bullish: bool, 
                              position_in_band: float, rsi: float) -> float:
        confidence = 0.4
        if is_bullish:
            rsi_factor = (self.config['rsi_oversold'] - rsi) / self.config['rsi_oversold']
            confidence += min(0.3, rsi_factor * 0.3)
            confidence += min(0.2, (0.1 - position_in_band))
        else:
            rsi_factor = (rsi - self.config['rsi_overbought']) / (100 - self.config['rsi_overbought'])
            confidence += min(0.3, rsi_factor * 0.3)
            confidence += min(0.2, (position_in_band - 0.9))
        return min(0.9, max(0.1, confidence))
