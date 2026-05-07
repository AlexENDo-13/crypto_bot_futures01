"""
Sliding backtest: continuously evaluates current strategy set on recent data.
Fixed: computes relative PnL, uses realistic scaling, no longer crashes weights.
"""
import logging
import threading
import time
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
        while self._running:
            try:
                self._run_backtest()
            except Exception as e:
                logger.error(f"Backtest error: {e}")
            time.sleep(300)

    def _run_backtest(self):
        symbol = 'BTC-USDT'
        try:
            df = self.engine.api.get_klines_dataframe(symbol, '1h', limit=200)
        except Exception as e:
            logger.warning(f"Cannot fetch backtest data: {e}")
            return

        if df is None or df.empty or len(df) < 100:
            logger.debug("Skipping backtest: insufficient data")
            return

        total_score = 0.0
        for name, strategy in self.engine.strategies.items():
            if strategy.is_disabled():
                continue
            score = self._test_strategy(strategy, df)
            self._results[name] = score
            total_score += score

        logger.info(f"Sliding backtest completed: total score={total_score:.4f}")
        self._update_weights()

    def _test_strategy(self, strategy, df):
        pnl_pct = 0.0
        signals = 0
        for i in range(50, len(df)-1):
            chunk = df.iloc[:i+1]
            try:
                signal = strategy.evaluate('TEST', '1h', chunk)
                if signal:
                    entry = chunk['close'].iloc[-1]
                    next_close = df['close'].iloc[i+1]
                    if signal.action == 'BUY':
                        pnl_abs = next_close - entry
                    else:
                        pnl_abs = entry - next_close
                    if entry > 0:
                        pnl_pct += (pnl_abs / entry)
                    signals += 1
            except Exception:
                pass

        if signals == 0:
            return 0.0
        avg_pnl_pct = pnl_pct / signals
        return avg_pnl_pct * 100.0

    def _update_weights(self):
        for name, score in self._results.items():
            if name in self.engine.strategies:
                old_weight = getattr(self.engine.strategies[name], 'weight', 1.0)
                adjustment = np.clip(score * 0.1, -0.5, 1.0)
                new_weight = old_weight + adjustment
                new_weight = max(0.1, min(3.0, new_weight))
                self.engine.strategies[name].weight = new_weight
                logger.debug(f"Backtest weight adjusted for {name}: {old_weight:.2f} -> {new_weight:.2f} (score={score:.2f})")

    def get_results(self):
        return self._results.copy()
