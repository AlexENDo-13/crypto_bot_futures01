"""
Bayesian Hyperparameter Optimizer for trading strategies.
Uses scikit-optimize (skopt) to find best parameters on recent historical data.
"""
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Callable
import threading
import time

logger = logging.getLogger(__name__)

# Попробуем импортировать skopt, если нет – предупредим
try:
    from skopt import gp_minimize
    from skopt.space import Real, Integer, Categorical
    from skopt.utils import use_named_args
    SKOPT_AVAILABLE = True
except ImportError:
    SKOPT_AVAILABLE = False
    logger.warning("scikit-optimize not installed. Bayesian optimization disabled. Install with: pip install scikit-optimize")


class BayesianOptimizer:
    """
    Periodically optimizes strategy parameters using Gaussian Process regression.
    Runs in a background thread.
    """

    def __init__(self, engine, max_iter: int = 30, lookback_days: int = 7):
        self.engine = engine
        self.max_iter = max_iter
        self.lookback_days = lookback_days
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if not SKOPT_AVAILABLE:
            logger.warning("BayesianOptimizer cannot start: install scikit-optimize")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="BayesOpt")
        self._thread.start()
        logger.info("BayesianOptimizer started (interval 6 hours)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self):
        while self._running:
            try:
                self._optimize_all_strategies()
            except Exception as e:
                logger.error(f"BayesianOptimizer error: {e}")
            time.sleep(6 * 3600)  # каждые 6 часов

    def _optimize_all_strategies(self):
        if self.engine.auth.demo_mode:
            return
        # Для оптимизации нужны исторические данные хотя бы одной пары (например, BTC-USDT)
        try:
            df = self.engine.api.get_klines_dataframe('BTC-USDT', '1h', limit=500)
        except Exception as e:
            logger.warning(f"Cannot fetch data for optimization: {e}")
            return
        if df.empty or len(df) < 100:
            return

        for name, strategy in self.engine.strategies.items():
            if strategy.is_disabled():
                continue
            try:
                best_params = self._optimize_strategy(strategy, df.copy())
                if best_params:
                    # Обновляем параметры стратегии
                    for k, v in best_params.items():
                        strategy.config[k] = v
                    logger.info(f"BayesianOptimizer updated {name}: {best_params}")
            except Exception as e:
                logger.error(f"Optimization failed for {name}: {e}")

    def _optimize_strategy(self, strategy, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Возвращает лучший набор параметров для стратегии."""
        # Собираем числовые параметры, которые можно оптимизировать
        space = []
        param_names = []
        for key, val in strategy.config.items():
            if key in ('enabled', 'weight', 'timeframes'):
                continue
            if isinstance(val, int):
                low = max(1, int(val * 0.5))
                high = int(val * 1.5)
                if high <= low:      # <-- ИСПРАВЛЕНИЕ: не даём high быть равным или меньше low
                    high = low + 1
                space.append(Integer(low, high, name=key))
                param_names.append(key)
            elif isinstance(val, float):
                space.append(Real(max(0.001, val * 0.5), val * 1.5, name=key))
                param_names.append(key)

        if not space:
            return None

        # Разделяем данные на обучающую (80%) и проверочную (20%) выборку по времени
        split_idx = int(len(df) * 0.8)
        train_df = df.iloc[:split_idx]
        val_df = df.iloc[split_idx:]

        @use_named_args(space)
        def objective(**params):
            # Устанавливаем параметры
            for k, v in params.items():
                strategy.config[k] = v
            # Оцениваем на валидации
            metrics = self._evaluate(strategy, val_df)
            # Чем лучше метрика, тем меньше результат (минимизация)
            return -metrics  # минимизируем отрицательный Sharpe или PnL

        try:
            result = gp_minimize(objective, space, n_calls=self.max_iter, random_state=42)
            if result.x is not None:
                best = dict(zip(param_names, result.x))
                return best
        except Exception as e:
            logger.warning(f"Bayesian opt failed: {e}")
        return None

    def _evaluate(self, strategy, df: pd.DataFrame) -> float:
        """Оценивает стратегию на данных и возвращает метрику (например, Sharpe)."""
        pnl = []
        for i in range(50, len(df)):
            chunk = df.iloc[:i+1]
            try:
                signal = strategy.evaluate('BTC-USDT', '1h', chunk)
                if signal:
                    entry = chunk['close'].iloc[-2]
                    exit_ = chunk['close'].iloc[-1]
                    if signal.action == 'BUY':
                        pnl.append(exit_ - entry)
                    else:
                        pnl.append(entry - exit_)
            except:
                pass
        if not pnl:
            return 0.0
        pnl = np.array(pnl)
        avg = np.mean(pnl)
        std = np.std(pnl) or 1e-9
        return avg / std  # Sharpe-like
