"""
Adaptive Threshold Manager.
Automatically adjusts signal threshold based on recent winrate.
"""
import logging
import threading
import time
from collections import deque

logger = logging.getLogger(__name__)

class AdaptiveThresholdManager:
    def __init__(self, engine, check_interval=300, lookback_trades=20):
        self.engine = engine
        self.check_interval = check_interval
        self.lookback = lookback_trades
        self._running = False
        self._thread = None
        self._min_threshold = 0.3
        self._max_threshold = 0.85
        self._base_threshold = engine.signal_threshold

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="AdaptiveThreshold")
        self._thread.start()
        logger.info("AdaptiveThresholdManager started")

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                self._adjust_threshold()
            except Exception as e:
                logger.error(f"AdaptiveThreshold error: {e}")
            time.sleep(self.check_interval)

    def _adjust_threshold(self):
        trades = self.engine.portfolio.trades
        if len(trades) < 5:
            return
        recent = trades[-self.lookback:]
        wins = sum(1 for t in recent if t.pnl > 0)
        total = len(recent)
        winrate = wins / total if total > 0 else 0.5

        # Если винрейт низкий – повышаем порог, чтобы отсечь слабые сигналы
        # Если высокий – немного снижаем, чтобы брать больше возможностей
        if winrate < 0.4:
            new_threshold = self.engine.signal_threshold + 0.05
        elif winrate > 0.7:
            new_threshold = self.engine.signal_threshold - 0.05
        else:
            new_threshold = self.engine.signal_threshold

        new_threshold = max(self._min_threshold, min(self._max_threshold, new_threshold))
        if new_threshold != self.engine.signal_threshold:
            self.engine.signal_threshold = new_threshold
            logger.info(f"Adaptive threshold updated: {self.engine.signal_threshold:.2f} (winrate {winrate:.1%})")
