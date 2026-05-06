"""
Kelly Criterion calculator based on historical trade results.
"""
import logging
import numpy as np
from typing import List

logger = logging.getLogger(__name__)

class KellyCalculator:
    def __init__(self):
        self._pnls: List[float] = []

    def add_trade(self, pnl: float):
        self._pnls.append(pnl)

    def get_optimal_fraction(self) -> float:
        """Вычисляет оптимальную долю капитала (f) по Келли."""
        if len(self._pnls) < 5:
            return 0.25  # Консервативное значение при малом количестве сделок

        wins = [p for p in self._pnls if p > 0]
        losses = [abs(p) for p in self._pnls if p <= 0]

        if not losses:
            return 0.5  # Нет убытков — позволяем половину

        win_rate = len(wins) / len(self._pnls)
        avg_win = np.mean(wins) if wins else 1
        avg_loss = np.mean(losses) if losses else 1
        if avg_loss == 0:
            return 0.5

        b = avg_win / avg_loss
        f = (win_rate * (b + 1) - 1) / b

        # Ограничиваем фракцию от 0.1 до 0.5
        return max(0.1, min(0.5, f))
