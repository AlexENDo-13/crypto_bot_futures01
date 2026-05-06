"""
Base Indicator class for Lego-modular trading bot system.
Indicators can be used by strategies for technical analysis.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Union
import pandas as pd
import numpy as np


class BaseIndicator(ABC):
    """
    Abstract base class for all technical indicators.
    
    To create a new indicator:
    1. Create a file in indicators/ folder
    2. Inherit from BaseIndicator
    3. Define PARAMS dict with configurable parameters
    4. Implement calculate() method
    """
    
    NAME: str = "BaseIndicator"
    DESCRIPTION: str = "Base indicator description"
    
    PARAMS: Dict[str, Any] = {
        'period': 14,
    }
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        self.config = dict(self.PARAMS)
        if params:
            self.config.update(params)
        self._cache: Dict[str, Any] = {}
        
    @abstractmethod
    def calculate(self, candles: pd.DataFrame) -> Union[pd.Series, pd.DataFrame, float]:
        """
        Calculate indicator values from candle data.
        
        Args:
            candles: DataFrame with columns [open, high, low, close, volume]
        
        Returns:
            Indicator values (Series, DataFrame, or scalar)
        """
        pass
    
    def get_last_value(self, candles: pd.DataFrame) -> Optional[float]:
        """Get the most recent indicator value."""
        result = self.calculate(candles)
        if isinstance(result, (pd.Series, pd.DataFrame)):
            return result.iloc[-1] if len(result) > 0 else None
        return result
    
    def validate_data(self, candles: pd.DataFrame, min_periods: Optional[int] = None) -> bool:
        """Validate that candle data has sufficient rows for calculation."""
        if candles is None or candles.empty:
            return False
        min_req = min_periods or self.config.get('period', 1)
        return len(candles) >= min_req
    
    def clear_cache(self):
        """Clear internal cache."""
        self._cache.clear()


# ============================================================
# Built-in indicator implementations
# ============================================================

class SMA(BaseIndicator):
    """Simple Moving Average."""
    NAME = "SMA"
    DESCRIPTION = "Simple Moving Average"
    PARAMS = {'period': 20}
    
    def calculate(self, candles: pd.DataFrame) -> pd.Series:
        period = self.config['period']
        return candles['close'].rolling(window=period).mean()


class EMA(BaseIndicator):
    """Exponential Moving Average."""
    NAME = "EMA"
    DESCRIPTION = "Exponential Moving Average"
    PARAMS = {'period': 20}
    
    def calculate(self, candles: pd.DataFrame) -> pd.Series:
        period = self.config['period']
        return candles['close'].ewm(span=period, adjust=False).mean()


class RSI(BaseIndicator):
    """Relative Strength Index."""
    NAME = "RSI"
    DESCRIPTION = "Relative Strength Index"
    PARAMS = {'period': 14}
    
    def calculate(self, candles: pd.DataFrame) -> pd.Series:
        period = self.config['period']
        delta = candles['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))


class MACD(BaseIndicator):
    """Moving Average Convergence Divergence."""
    NAME = "MACD"
    DESCRIPTION = "MACD with signal line"
    PARAMS = {'fast': 12, 'slow': 26, 'signal': 9}
    
    def calculate(self, candles: pd.DataFrame) -> pd.DataFrame:
        fast = self.config['fast']
        slow = self.config['slow']
        signal = self.config['signal']
        ema_fast = candles['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = candles['close'].ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        histogram = macd - signal_line
        return pd.DataFrame({
            'macd': macd,
            'signal': signal_line,
            'histogram': histogram
        })


class ATR(BaseIndicator):
    """Average True Range."""
    NAME = "ATR"
    DESCRIPTION = "Average True Range - volatility measure"
    PARAMS = {'period': 14}
    
    def calculate(self, candles: pd.DataFrame) -> pd.Series:
        period = self.config['period']
        high_low = candles['high'] - candles['low']
        high_close = np.abs(candles['high'] - candles['close'].shift())
        low_close = np.abs(candles['low'] - candles['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()


class BollingerBands(BaseIndicator):
    """Bollinger Bands."""
    NAME = "BollingerBands"
    DESCRIPTION = "Bollinger Bands"
    PARAMS = {'period': 20, 'std_dev': 2.0}
    
    def calculate(self, candles: pd.DataFrame) -> pd.DataFrame:
        period = self.config['period']
        std_dev = self.config['std_dev']
        sma = candles['close'].rolling(window=period).mean()
        std = candles['close'].rolling(window=period).std()
        return pd.DataFrame({
            'upper': sma + (std * std_dev),
            'middle': sma,
            'lower': sma - (std * std_dev)
        })


class VWAP(BaseIndicator):
    """Volume Weighted Average Price."""
    NAME = "VWAP"
    DESCRIPTION = "Volume Weighted Average Price"
    PARAMS = {'period': 20}
    
    def calculate(self, candles: pd.DataFrame) -> pd.Series:
        period = self.config['period']
        typical_price = (candles['high'] + candles['low'] + candles['close']) / 3
        vwap = (typical_price * candles['volume']).rolling(window=period).sum() / \
               candles['volume'].rolling(window=period).sum()
        return vwap


class Stochastic(BaseIndicator):
    """Stochastic Oscillator."""
    NAME = "Stochastic"
    DESCRIPTION = "Stochastic Oscillator (%K and %D)"
    PARAMS = {'k_period': 14, 'd_period': 3, 'smooth_k': 3}
    
    def calculate(self, candles: pd.DataFrame) -> pd.DataFrame:
        k_period = self.config['k_period']
        d_period = self.config['d_period']
        smooth_k = self.config['smooth_k']
        
        lowest_low = candles['low'].rolling(window=k_period).min()
        highest_high = candles['high'].rolling(window=k_period).max()
        
        k = 100 * ((candles['close'] - lowest_low) / (highest_high - lowest_low))
        k = k.rolling(window=smooth_k).mean()
        d = k.rolling(window=d_period).mean()
        
        return pd.DataFrame({'k': k, 'd': d})
