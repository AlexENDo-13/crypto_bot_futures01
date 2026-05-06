"""
Base Strategy class for Lego-modular trading bot system.
All strategies must inherit from BaseStrategy and implement evaluate().
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import pandas as pd


@dataclass
class Signal:
    """Trading signal produced by a strategy."""
    symbol: str
    action: str  # 'BUY', 'SELL', or 'HOLD'
    confidence: float = 0.0  # 0.0 to 1.0
    meta: Dict[str, Any] = field(default_factory=dict)
    
    # Optional fields filled by risk manager / engine
    suggested_tp: Optional[float] = None
    suggested_sl: Optional[float] = None
    position_size: Optional[float] = None
    leverage: Optional[int] = None
    
    def __post_init__(self):
        if self.action not in ('BUY', 'SELL', 'HOLD'):
            raise ValueError(f"Invalid action: {self.action}")
        self.confidence = max(0.0, min(1.0, self.confidence))


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    To create a new strategy:
    1. Create a file in strategies/ folder
    2. Inherit from BaseStrategy
    3. Define PARAMS dict with configurable parameters
    4. Implement evaluate() method
    """
    
    # Strategy metadata - override in subclass
    NAME: str = "BaseStrategy"
    DESCRIPTION: str = "Base strategy description"
    VERSION: str = "1.0.0"
    AUTHOR: str = ""
    
    # Configurable parameters - define defaults here
    # GUI will auto-generate controls from this dict
    PARAMS: Dict[str, Any] = {
        'enabled': True,
        'weight': 1.0,  # Voting weight in ensemble
        'timeframes': ['15m', '1h', '4h'],
    }
    
    def __init__(self, params: Optional[Dict[str, Any]] = None):
        """
        Initialize strategy with parameters.
        
        Args:
            params: Override default PARAMS values
        """
        self.config = dict(self.PARAMS)
        if params:
            self.config.update(params)
        self.enabled = self.config.get('enabled', True)
        self.weight = self.config.get('weight', 1.0)
        self._error_count = 0
        self._last_error_time = None
        self._disabled_until = None
        
    @abstractmethod
    def evaluate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> Optional[Signal]:
        """
        Evaluate market data and return a trading signal.
        
        Args:
            symbol: Trading pair (e.g., 'BTC-USDT')
            timeframe: Candle timeframe (e.g., '15m', '1h')
            candles: DataFrame with columns [open, high, low, close, volume, timestamp]
        
        Returns:
            Signal object or None if no signal
        """
        pass
    
    def on_trade_completed(self, signal: Signal, pnl: float, duration_seconds: float):
        """
        Called when a trade based on this strategy's signal completes.
        Use this for strategy self-optimization / learning.
        
        Args:
            signal: The original signal
            pnl: Profit/loss in quote currency (positive = profit)
            duration_seconds: How long the position was held
        """
        pass
    
    def get_params_schema(self) -> Dict[str, Dict[str, Any]]:
        """
        Return parameter schema for GUI auto-generation.
        Override to provide type hints, ranges, descriptions.
        
        Returns:
            Dict of param_name -> {type, default, min, max, description}
        """
        schema = {}
        for key, value in self.config.items():
            param_info = {
                'value': value,
                'type': type(value).__name__,
                'description': f"Parameter {key}"
            }
            if isinstance(value, bool):
                param_info['widget'] = 'checkbox'
            elif isinstance(value, (int, float)):
                param_info['widget'] = 'slider'
                if isinstance(value, int):
                    param_info['min'] = 1
                    param_info['max'] = max(100, value * 10)
                    param_info['step'] = 1
                else:
                    param_info['min'] = 0.0
                    param_info['max'] = max(1.0, value * 5)
                    param_info['step'] = 0.01
            elif isinstance(value, str):
                param_info['widget'] = 'lineedit'
            elif isinstance(value, list):
                param_info['widget'] = 'multiselect'
            schema[key] = param_info
        return schema
    
    def is_disabled(self) -> bool:
        """Check if strategy is temporarily disabled due to errors."""
        if not self.enabled:
            return True
        if self._disabled_until is not None:
            from datetime import datetime, timezone
            if datetime.now(timezone.utc).timestamp() < self._disabled_until:
                return True
            self._disabled_until = None
        return False
    
    def disable_temporarily(self, seconds: float = 3600):
        """Temporarily disable strategy after repeated errors."""
        from datetime import datetime, timezone
        self._disabled_until = datetime.now(timezone.utc).timestamp() + seconds
        
    def record_error(self):
        """Record an error occurrence. Disable if too many errors."""
        self._error_count += 1
        if self._error_count >= 3:
            self.disable_temporarily(3600)  # 1 hour
            self._error_count = 0
    
    def reset_error_count(self):
        """Reset error counter after successful execution."""
        self._error_count = 0
        self._disabled_until = None
        
    def __repr__(self):
        return f"{self.NAME}(weight={self.weight}, enabled={self.enabled})"
