"""
Market regime detection: trend, range, volatility phases.
"""
import logging
import numpy as np
import pandas as pd
from typing import Optional, Dict, List
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime types."""
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    UNKNOWN = "unknown"


@dataclass
class RegimeFeatures:
    """Features used for regime classification."""
    adx: float  # Average Directional Index
    di_plus: float  # DI+ indicator
    di_minus: float  # DI- indicator
    atr_ratio: float  # ATR relative to price
    bb_width: float  # Bollinger Band width
    price_vs_sma: float  # Price relative to SMA
    volatility: float  # Recent volatility
    momentum: float  # Price momentum


class MarketRegimeDetector:
    """
    Detects current market regime using multiple indicators.
    Helps select appropriate strategy sets.
    """
    
    def __init__(self, lookback_period: int = 50):
        self.lookback = lookback_period
        self._current_regime: MarketRegime = MarketRegime.UNKNOWN
        self._regime_history: List[MarketRegime] = []
        self._features: Optional[RegimeFeatures] = None
        self._regime_duration: int = 0
    
    def detect(self, candles: pd.DataFrame) -> MarketRegime:
        """
        Detect market regime from candle data.
        
        Args:
            candles: DataFrame with OHLCV data
        
        Returns:
            Detected market regime
        """
        if len(candles) < self.lookback:
            return MarketRegime.UNKNOWN
        
        # Calculate features
        features = self._calculate_features(candles)
        self._features = features
        
        # Classify regime
        regime = self._classify(features)
        
        # Track regime duration
        if regime == self._current_regime:
            self._regime_duration += 1
        else:
            self._regime_duration = 0
            self._current_regime = regime
        
        self._regime_history.append(regime)
        if len(self._regime_history) > 100:
            self._regime_history = self._regime_history[-100:]
        
        return regime
    
    def _calculate_features(self, candles: pd.DataFrame) -> RegimeFeatures:
        """Calculate regime detection features."""
        close = candles['close']
        high = candles['high']
        low = candles['low']
        
        # ADX calculation
        adx, di_plus, di_minus = self._calculate_adx(high, low, close)
        
        # ATR ratio
        atr = self._calculate_atr(high, low, close)
        atr_ratio = atr / close.iloc[-1] if close.iloc[-1] > 0 else 0
        
        # Bollinger Band width
        sma = close.rolling(20).mean()
        std = close.rolling(20).std()
        bb_width = (std.iloc[-1] / sma.iloc[-1]) if sma.iloc[-1] > 0 else 0
        
        # Price vs SMA
        price_vs_sma = (close.iloc[-1] - sma.iloc[-1]) / sma.iloc[-1] if sma.iloc[-1] > 0 else 0
        
        # Volatility (recent std)
        volatility = close.iloc[-20:].pct_change().std() * np.sqrt(365)
        
        # Momentum
        momentum = (close.iloc[-1] - close.iloc[-10]) / close.iloc[-10] if close.iloc[-10] > 0 else 0
        
        return RegimeFeatures(
            adx=adx,
            di_plus=di_plus,
            di_minus=di_minus,
            atr_ratio=atr_ratio,
            bb_width=bb_width,
            price_vs_sma=price_vs_sma,
            volatility=volatility,
            momentum=momentum,
        )
    
    def _classify(self, f: RegimeFeatures) -> MarketRegime:
        """Classify regime based on features."""
        # High volatility check
        if f.atr_ratio > 0.03 or f.volatility > 1.0:
            return MarketRegime.HIGH_VOLATILITY
        
        # Low volatility check
        if f.atr_ratio < 0.005 or f.volatility < 0.3:
            return MarketRegime.LOW_VOLATILITY
        
        # Trend detection using ADX
        if f.adx > 25:
            if f.di_plus > f.di_minus:
                return MarketRegime.TREND_UP
            else:
                return MarketRegime.TREND_DOWN
        
        # Range-bound
        return MarketRegime.RANGE
    
    def _calculate_adx(self, high: pd.Series, low: pd.Series, 
                       close: pd.Series, period: int = 14) -> tuple:
        """Calculate ADX, DI+, DI-."""
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        atr = tr.rolling(window=period).mean()
        
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        plus_di = 100 * plus_dm.rolling(window=period).mean() / atr
        minus_di = 100 * minus_dm.rolling(window=period).mean() / atr
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        dx = dx.replace([np.inf, -np.inf], 0).fillna(0)
        adx = dx.rolling(window=period).mean()
        
        return adx.iloc[-1] if len(adx) > 0 else 0, \
               plus_di.iloc[-1] if len(plus_di) > 0 else 0, \
               minus_di.iloc[-1] if len(minus_di) > 0 else 0
    
    def _calculate_atr(self, high: pd.Series, low: pd.Series, 
                       close: pd.Series, period: int = 14) -> float:
        """Calculate Average True Range."""
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean().iloc[-1]
    
    def get_current_regime(self) -> MarketRegime:
        return self._current_regime
    
    def get_regime_duration(self) -> int:
        """How long current regime has persisted (in bars)."""
        return self._regime_duration
    
    def get_features(self) -> Optional[Dict]:
        """Get last calculated features."""
        if self._features is None:
            return None
        return {
            'adx': self._features.adx,
            'di_plus': self._features.di_plus,
            'di_minus': self._features.di_minus,
            'atr_ratio': self._features.atr_ratio,
            'bb_width': self._features.bb_width,
            'price_vs_sma': self._features.price_vs_sma,
            'volatility': self._features.volatility,
            'momentum': self._features.momentum,
        }
    
    def get_recommended_strategies(self) -> List[str]:
        """
        Get recommended strategy types for current regime.
        
        Returns:
            List of strategy type names
        """
        regime = self._current_regime
        
        recommendations = {
            MarketRegime.TREND_UP: ['trend_following', 'momentum'],
            MarketRegime.TREND_DOWN: ['trend_following', 'momentum'],
            MarketRegime.RANGE: ['mean_reversion', 'oscillator'],
            MarketRegime.HIGH_VOLATILITY: ['breakout', 'momentum'],
            MarketRegime.LOW_VOLATILITY: ['mean_reversion', 'range'],
            MarketRegime.UNKNOWN: ['trend_following'],
        }
        
        return recommendations.get(regime, ['trend_following'])
    
    def get_regime_distribution(self, lookback: int = 50) -> Dict[str, float]:
        """
        Get distribution of regimes over recent history.
        
        Returns:
            Dict of regime -> percentage
        """
        if not self._regime_history:
            return {}
        
        recent = self._regime_history[-lookback:]
        distribution = {}
        for regime in recent:
            name = regime.value
            distribution[name] = distribution.get(name, 0) + 1
        
        total = len(recent)
        return {k: v/total for k, v in distribution.items()}
