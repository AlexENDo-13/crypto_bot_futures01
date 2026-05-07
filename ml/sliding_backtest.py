"""
Sliding backtest: continuously evaluates current strategy set on recent data.
Fixed: won't run in demo mode, checks for valid data before updating weights.
"""
import logging
import threading
import numpy as np
import pandas as pd
from typing import Dict, Any

logger = logging.getLogger(__name__)

class SlidingBacktest:
    def __init__(self, engine):
        self.engine = engine
        self._running = False
        self._results: Dict[str, Any] = {}

    def start(self):
        # В демо‑режиме не запускаем, чтобы не искажать веса
        if self.engine.auth.demo_mode:
            logger.info("Sliding backtest not started (demo mode)")
            return
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()
        logger.info("Sliding backtest started")

    def stop(self):
        self._running = False

    def _loop(self):
        import time
        while self._running:
            try:
                self._run_backtest()
            except Exception as e:
                logger.error(f"Backtest error: {e}")
            time.sleep(300)  # Каждые 5 минут

    def _run_backtest(self):
        """Запускает бэктест на последних 200 свечах для BTC-USDT, если данные валидны."""
        symbol = 'BTC-USDT'
        try:
            df = self.engine.api.get_klines_dataframe(symbol, '1h', limit=200)
        except Exception as e:
            logger.warning(f"Cannot fetch backtest data: {e}")
            return

        if df is None or df.empty or len(df) < 100:
            logger.debug("Skipping backtest: insufficient data")
            return

        total_pnl = 0.0
        for name, strategy in self.engine.strategies.items():
            if strategy.is_disabled():
                continue
            pnl = self._test_strategy(strategy, df)
            self._results[name] = pnl
            total_pnl += pnl

        logger.info(f"Sliding backtest completed: total PnL={total_pnl:.4f}")
        self._update_weights()

    def _test_strategy(self, strategy, df):
        """Применяет стратегию на исторических данных и возвращает PnL."""
        pnl = 0.0
        for i in range(50, len(df)):
            chunk = df.iloc[:i+1]
            try:
                signal = strategy.evaluate('TEST', '1h', chunk)
                if signal:
                    entry = chunk['close'].iloc[-2]
                    exit_ = chunk['close'].iloc[-1]
                    if signal.action == 'BUY':
                        pnl += exit_ - entry
                    else:
                        pnl += entry - exit_
            except:
                pass
        return pnl

    def _update_weights(self):
        """Обновляет веса стратегий на основе результатов бэктеста."""
        for name, pnl in self._results.items():
            if name in self.engine.strategies:
                old_weight = getattr(self.engine.strategies[name], 'weight', 1.0)
                # Плавное изменение веса: при положительном PnL увеличиваем, при отрицательном уменьшаем
                adjustment = 1.0 + pnl * 0.001
                new_weight = max(0.1, min(3.0, old_weight * adjustment))
                self.engine.strategies[name].weight = new_weight
                logger.debug(f"Backtest weight adjusted for {name}: {old_weight:.2f} -> {new_weight:.2f}")

    def get_results(self):
        return self._results.copy()
