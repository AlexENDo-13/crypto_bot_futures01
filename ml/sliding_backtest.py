"""
Sliding backtest: continuously evaluates current strategy set on recent data.
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
            import time
            time.sleep(300)  # Каждые 5 минут

    def _run_backtest(self):
        """Запускает бэктест на последних 200 свечах для всех стратегий."""
        symbol = 'BTC-USDT'  # Пока для одной пары
        try:
            df = self.engine.api.get_klines_dataframe(symbol, '1h', limit=200)
            if df.empty:
                return
        except:
            return

        total_pnl = 0.0
        for name, strategy in self.engine.strategies.items():
            if strategy.is_disabled():
                continue
            pnl = self._test_strategy(strategy, df)
            self._results[name] = pnl
            total_pnl += pnl

        logger.info(f"Sliding backtest completed: total PnL={total_pnl:.4f}")

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

    def get_results(self):
        return self._results.copy()
