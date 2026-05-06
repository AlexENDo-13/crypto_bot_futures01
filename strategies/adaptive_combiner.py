from strategies.base import BaseStrategy, Signal
from ml.voting import VotingSystem

class AdaptiveCombinerStrategy(BaseStrategy):
    NAME = "AdaptiveCombiner"
    DESCRIPTION = "Automatically combines signals from other strategies using dynamic weights"
    PARAMS = {'enabled': True, 'weight': 1.0, 'timeframes': ['1h']}
    
    def evaluate(self, symbol, timeframe, candles):
        # Эта стратегия не генерит сигналы сама, но используется движком для комбинации.
        return None
