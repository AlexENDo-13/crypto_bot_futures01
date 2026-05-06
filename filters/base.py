"""
Base Filter class for risk management filtering.
Filters assess signals and can reduce confidence or block trades.
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from strategies.base import Signal


class BaseFilter(ABC):
    """
    Abstract base class for all risk filters.
    
    Filters assess trading signals and can:
    - Reduce confidence (partial block)
    - Block the trade entirely (return 0 confidence)
    - Pass the signal unchanged
    
    To create a new filter:
    1. Create a file in filters/ folder
    2. Inherit from BaseFilter
    3. Define PARAMS dict with configurable parameters
    4. Implement assess() method
    """
    
    NAME: str = "BaseFilter"
    DESCRIPTION: str = "Base filter description"
    PRIORITY: int = 100  # Lower = evaluated first
    
    PARAMS: Dict[str, Any] = {
        'enabled': True,
    }
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        self.config = dict(self.PARAMS)
        if params:
            self.config.update(params)
        self.enabled = self.config.get('enabled', True)
        
    @abstractmethod
    def assess(self, signal: Signal, data: Dict[str, Any]) -> float:
        """
        Assess a trading signal and return adjusted confidence.
        
        Args:
            signal: The trading signal to assess
            data: Additional context data (portfolio state, market regime, etc.)
        
        Returns:
            Adjusted confidence (0.0 to 1.0), where 0.0 blocks the trade
        """
        pass
    
    def __repr__(self):
        return f"{self.NAME}(enabled={self.enabled}, priority={self.PRIORITY})"


# ============================================================
# Built-in filter implementations
# ============================================================

class MaxDrawdownFilter(BaseFilter):
    """Blocks new trades if portfolio drawdown exceeds threshold."""
    NAME = "MaxDrawdownFilter"
    DESCRIPTION = "Block trades during excessive drawdown"
    PRIORITY = 10
    PARAMS = {'enabled': True, 'max_drawdown_pct': 10.0}
    
    def assess(self, signal: Signal, data: Dict[str, Any]) -> float:
        if not self.enabled:
            return signal.confidence
        
        current_drawdown = data.get('current_drawdown_pct', 0.0)
        max_dd = self.config['max_drawdown_pct']
        
        if current_drawdown >= max_dd:
            return 0.0  # Block all trades
        elif current_drawdown >= max_dd * 0.7:
            # Reduce confidence proportionally
            reduction = (current_drawdown / max_dd) * 0.5
            return signal.confidence * (1 - reduction)
        
        return signal.confidence


class CorrelationFilter(BaseFilter):
    """Reduces position size for correlated pairs."""
    NAME = "CorrelationFilter"
    DESCRIPTION = "Reduce exposure on correlated pairs"
    PRIORITY = 20
    PARAMS = {'enabled': True, 'correlation_threshold': 0.8, 'max_correlated': 2}
    
    def assess(self, signal: Signal, data: Dict[str, Any]) -> float:
        if not self.enabled:
            return signal.confidence
        
        open_positions = data.get('open_positions', [])
        threshold = self.config['correlation_threshold']
        max_corr = self.config['max_correlated']
        
        # Count how many open positions are correlated with this signal
        correlated_count = 0
        for pos in open_positions:
            corr = data.get('correlations', {}).get(f"{signal.symbol}_{pos['symbol']}", 0.0)
            if abs(corr) >= threshold:
                correlated_count += 1
        
        if correlated_count >= max_corr:
            return 0.0  # Block - too many correlated positions
        elif correlated_count > 0:
            # Reduce confidence
            return signal.confidence * (1 - (correlated_count / max_corr) * 0.5)
        
        return signal.confidence


class VolatilityFilter(BaseFilter):
    """Blocks or reduces trades during extreme volatility."""
    NAME = "VolatilityFilter"
    DESCRIPTION = "Filter based on market volatility"
    PRIORITY = 30
    PARAMS = {'enabled': True, 'atr_multiplier_high': 3.0, 'atr_multiplier_low': 0.5}
    
    def assess(self, signal: Signal, data: Dict[str, Any]) -> float:
        if not self.enabled:
            return signal.confidence
        
        current_atr = data.get('current_atr', 0)
        avg_atr = data.get('average_atr', 1)
        
        if avg_atr == 0:
            return signal.confidence
        
        atr_ratio = current_atr / avg_atr
        high_threshold = self.config['atr_multiplier_high']
        low_threshold = self.config['atr_multiplier_low']
        
        if atr_ratio > high_threshold:
            # Too volatile - reduce confidence
            excess = atr_ratio / high_threshold
            return signal.confidence / excess
        elif atr_ratio < low_threshold:
            # Too calm - reduce confidence
            return signal.confidence * (atr_ratio / low_threshold)
        
        return signal.confidence


class TimeFilter(BaseFilter):
    """Blocks trades during certain hours/days."""
    NAME = "TimeFilter"
    DESCRIPTION = "Filter based on time of day/week"
    PRIORITY = 40
    PARAMS = {
        'enabled': True,
        'blocked_hours': [],  # e.g., [0, 1, 2] for midnight-3am UTC
        'blocked_days': [],   # 0=Monday, 6=Sunday
        'friday_close_hour': 20,  # Stop trading after this hour on Friday
    }
    
    def assess(self, signal: Signal, data: Dict[str, Any]) -> float:
        if not self.enabled:
            return signal.confidence
        
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        
        hour = now.hour
        weekday = now.weekday()
        
        if hour in self.config.get('blocked_hours', []):
            return 0.0
        if weekday in self.config.get('blocked_days', []):
            return 0.0
        if weekday == 4 and hour >= self.config.get('friday_close_hour', 20):
            return 0.0  # Friday evening
        
        return signal.confidence


class CooldownFilter(BaseFilter):
    """Enforces minimum time between trades on same symbol."""
    NAME = "CooldownFilter"
    DESCRIPTION = "Minimum interval between trades per symbol"
    PRIORITY = 15
    PARAMS = {'enabled': True, 'min_interval_minutes': 1}
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        super().__init__(params)
        self._last_trade_time: Dict[str, float] = {}
    
    def assess(self, signal: Signal, data: Dict[str, Any]) -> float:
        if not self.enabled:
            return signal.confidence
        
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).timestamp()
        symbol = signal.symbol
        
        last_time = self._last_trade_time.get(symbol, 0)
        interval_sec = self.config['min_interval_minutes'] * 60
        
        if now - last_time < interval_sec:
            return 0.0  # In cooldown
        
        # Record this trade time
        self._last_trade_time[symbol] = now
        return signal.confidence
