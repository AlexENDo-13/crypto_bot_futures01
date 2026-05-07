"""
Adaptive Capital Allocator.
Periodically adjusts strategy weights in the VotingSystem based on recent performance.
"""
import logging
import time
import threading
import numpy as np
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class CapitalAllocator:
    def __init__(self, engine, update_interval_minutes=60, lookback_trades=20):
        self.engine = engine
        self.update_interval = update_interval_minutes * 60
        self.lookback_trades = lookback_trades  # количество последних сделок для оценки
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="CapitalAllocator")
        self._thread.start()
        logger.info("CapitalAllocator started (interval %d min)", self.update_interval//60)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while self._running:
            try:
                self._update_allocations()
            except Exception as e:
                logger.error(f"CapitalAllocator error: {e}")
            time.sleep(self.update_interval)

    def _update_allocations(self):
        voting = self.engine.voting
        # Получаем полную статистику, а не только веса
        all_stats = voting.get_strategy_stats()
        if not all_stats:
            return

        # Рассчитываем показатели для каждой стратегии
        scores = {}
        for name, stats in all_stats.items():
            trades = stats.get('trades', 0)
            if trades < 3:  # недостаточно данных – оставляем текущий вес
                scores[name] = stats.get('weight', 1.0)
                continue

            avg_pnl = stats.get('avg_pnl', 0)
            winrate = stats.get('winrate', 0) / 100.0
            # Простая оценка: winrate * avg_pnl (нормализовано)
            if avg_pnl <= 0:
                score = 0.1  # минимальный вес
            else:
                score = winrate * avg_pnl
            scores[name] = score

        # Нормализуем в веса от 0.1 до 3.0 (максимальный вес)
        total = sum(scores.values())
        if total == 0:
            return
        for name in scores:
            normalized = scores[name] / total * len(scores)  # масштабируем, чтобы средний = 1
            normalized = max(0.1, min(3.0, normalized))
            # Обновляем вес в статистике VotingSystem
            if name in voting._weights:
                voting._weights[name]['weight'] = normalized
                logger.debug(f"Capital allocation: {name} → {normalized:.2f} (raw score {scores[name]:.4f})")

        logger.info("Capital allocation updated for %d strategies", len(scores))
