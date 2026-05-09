"""
Walk-Forward Optimizer: periodically refits strategy parameters on recent data.
"""
import logging
import itertools
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class WalkForwardOptimizer:
    def __init__(self, engine, update_interval_hours: int = 24):
        self.engine = engine
        self.update_interval = update_interval_hours * 3600
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="WalkForward")
        self._thread.start()
        logger.info(f"WalkForwardOptimizer started (every {self.update_interval//3600}h)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while self._running:
            try:
                self._optimize_all()
            except Exception as e:
                logger.error(f"WalkForward optimizer error: {e}")
            time.sleep(self.update_interval)

    def _optimize_all(self):
        if self.engine.auth.demo_mode:
            return
        for name, strategy in self.engine.strategies.items():
            if strategy.is_disabled():
                continue
            try:
                best_params = self._optimize_strategy(strategy)
                if best_params:
                    strategy.config.update(best_params)
                    logger.info(f"WalkForward updated {name}: {best_params}")
            except Exception as e:
                logger.error(f"WalkForward failed for {name}: {e}")

    def _optimize_strategy(self, strategy) -> Optional[Dict[str, Any]]:
        # Используем BTC-USDT 1h последние 200 свечей для быстрого поиска
        try:
            df = self.engine.api.get_klines_dataframe('BTC-USDT', '1h', limit=200)
            if df.empty:
                return None
        except Exception:
            return None

        # Собираем числовые параметры для перебора
        search_space = {}
        for key, val in strategy.config.items():
            if key in ('enabled', 'weight', 'timeframes'):
                continue
            if isinstance(val, int):
                low = max(1, int(val * 0.5))
                high = int(val * 1.5) + 1
                search_space[key] = list(range(low, high, max(1, (high - low)//3)))
            elif isinstance(val, float):
                low = val * 0.5
                high = val * 1.5
                search_space[key] = [round(low + i * (high - low) / 3, 2) for i in range(4)]

        if not search_space:
            return None

        best_score = -np.inf
        best_params = None
        keys = list(search_space.keys())
        for values in itertools.product(*[search_space[k] for k in keys]):
            trial = dict(zip(keys, values))
            strategy.config.update(trial)
            score = self._evaluate(strategy, df)
            if score > best_score:
                best_score = score
                best_params = trial

        return best_params

    def _evaluate(self, strategy, df: pd.DataFrame) -> float:
        """Простая оценка: количество сигналов × средняя уверенность."""
        signals = []
        for i in range(30, len(df)):
            chunk = df.iloc[:i+1]
            try:
                sig = strategy.evaluate('BTC-USDT', '1h', chunk)
                if sig:
                    signals.append(sig)
            except:
                pass
        if not signals:
            return 0.0
        return len(signals) * np.mean([s.confidence for s in signals])
