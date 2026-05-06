"""
ATR multiplier auto-tuner for individual symbols.
Analyses recent candles to find optimal SL/TP multipliers.
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

class ATRTuner:
    def __init__(self, engine):
        self.engine = engine

    def tune_all(self):
        """Запускает тюнинг для всех отслеживаемых символов."""
        symbols = self.engine._top_symbols[:20]  # Ограничим 20 парами для скорости
        for symbol in symbols:
            try:
                self.tune_symbol(symbol)
            except Exception as e:
                logger.debug(f"ATR tuning failed for {symbol}: {e}")

    def tune_symbol(self, symbol: str):
        """Подбирает множители для конкретного символа."""
        # Получаем исторические данные
        try:
            df = self.engine.api.get_klines_dataframe(symbol, '1h', limit=200)
            if df.empty:
                return
        except Exception:
            return

        atr = self._calc_atr(df, 14)

        # Генетический поиск (простой перебор)
        best_sl, best_tp, best_score = 1.5, 2.0, -np.inf
        for sl_mult in np.arange(1.0, 3.0, 0.25):
            for tp_mult in np.arange(1.5, 4.0, 0.25):
                score = self._backtest(df, atr, sl_mult, tp_mult)
                if score > best_score:
                    best_score = score
                    best_sl = sl_mult
                    best_tp = tp_mult

        logger.info(f"ATR tuned for {symbol}: SL={best_sl:.2f}, TP={best_tp:.2f}, score={best_score:.2f}")
        self.engine.risk_manager.set_atr_multipliers(symbol, best_sl, best_tp)

    def _calc_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        high, low, close = df['high'], df['low'], df['close']
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def _backtest(self, df: pd.DataFrame, atr: pd.Series, sl_mult: float, tp_mult: float) -> float:
        """Простой бэктест на истории: возвращает средний PnL."""
        close = df['close']
        pnls = []
        for i in range(14, len(df)-1):
            entry = close.iloc[i]
            sl = entry - atr.iloc[i] * sl_mult
            tp = entry + atr.iloc[i] * tp_mult
            exit_price = entry
            for j in range(i+1, len(df)):
                if df['low'].iloc[j] <= sl:
                    exit_price = sl
                    break
                if df['high'].iloc[j] >= tp:
                    exit_price = tp
                    break
                exit_price = close.iloc[j]
            pnls.append(exit_price - entry)
        if not pnls:
            return 0.0
        # Используем Sharpe-подобную метрику
        avg = np.mean(pnls)
        std = np.std(pnls) or 1
        return avg / std
