"""
Strategy optimizer using grid search on historical candle data.
"""
import itertools
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class StrategyOptimizer:
    def __init__(self):
        pass

    def optimize(self, strategy, candle_data: Dict[str, Dict[str, pd.DataFrame]],
                 metric: str = 'sharpe') -> Optional[Dict[str, Any]]:
        """
        Простой сеточный поиск по параметрам стратегии.
        Возвращает лучший набор параметров или None.
        """
        params = strategy.PARAMS.copy()
        # Убираем служебные ключи
        for key in ['enabled', 'weight', 'timeframes']:
            params.pop(key, None)

        if not params:
            logger.info(f"No tunable parameters for {strategy.NAME}")
            return None

        # Генерируем пространство поиска (только числовые параметры)
        search_space = {}
        for key, default in params.items():
            if isinstance(default, (int, float)):
                # Диапазон: ±50% от значения по умолчанию, шаг примерно 10%
                step = max(1, round(default * 0.1)) if isinstance(default, int) else default * 0.1
                low = max(1, int(default * 0.5)) if isinstance(default, int) else default * 0.5
                high = max(low + 1, int(default * 1.5)) if isinstance(default, int) else default * 1.5
                if isinstance(default, int):
                    values = list(range(low, high + 1, step))
                else:
                    values = [round(low + i * step, 2) for i in range(5)]
                if default not in values:
                    values.append(default)
                search_space[key] = sorted(set(values))

        if not search_space:
            return None

        # Выбираем исторические данные для бэктеста (возьмём 1h по первой доступной паре)
        hist_data = None
        for symbol, tfs in candle_data.items():
            if '1h' in tfs:
                hist_data = tfs['1h']
                break
        if hist_data is None or len(hist_data) < 50:
            logger.warning("Not enough historical data for optimization")
            return None

        best_score = -np.inf
        best_params = None

        keys = list(search_space.keys())
        for values in itertools.product(*[search_space[k] for k in keys]):
            trial = dict(zip(keys, values))
            strategy.config.update(trial)
            signals = []
            try:
                for i in range(len(hist_data) - 30):
                    chunk = hist_data.iloc[i:i+30]
                    sig = strategy.evaluate("TEST", "1h", chunk)
                    if sig:
                        signals.append(sig)
            except Exception as e:
                logger.debug(f"Trial {trial} error: {e}")
                continue

            if not signals:
                continue

            # Простейшая метрика: количество сигналов × средняя уверенность
            score = len(signals) * np.mean([s.confidence for s in signals])
            if score > best_score:
                best_score = score
                best_params = trial

        if best_params:
            logger.info(f"Best params for {strategy.NAME}: {best_params} (score={best_score:.2f})")
        return best_params
