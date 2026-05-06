from filters.base import BaseFilter
from strategies.base import Signal

class DrawdownLimiter(BaseFilter):
    NAME = "DrawdownLimiter"
    DESCRIPTION = "Reduces position size during drawdown"
    PRIORITY = 5
    PARAMS = {'enabled': True, 'max_dd_pct': 10.0, 'reduction_factor': 0.5}

    def assess(self, signal: Signal, data: dict) -> float:
        current_dd = data.get('current_drawdown_pct', 0.0)
        if current_dd >= self.config['max_dd_pct']:
            return 0.0  # Block all trades
        elif current_dd >= self.config['max_dd_pct'] * 0.7:
            return signal.confidence * self.config['reduction_factor']
        return signal.confidence
