"""
Adaptive Timeframe Selector.
Assigns optimal timeframes for each symbol based on current volatility (ATR%).
"""
import logging
import time
import threading
import numpy as np
from typing import List, Dict

logger = logging.getLogger(__name__)

# Доступные таймфреймы, отсортированные по длительности в минутах
AVAILABLE_TIMEFRAMES = ['15m', '1h', '4h', '1d']
TF_MINUTES = {'15m': 15, '1h': 60, '4h': 240, '1d': 1440}

# Пороги волатильности в процентах (ATR/цена * 100)
HIGH_VOL_THRESHOLD = 3.0       # выше этого — высокая волатильность
LOW_VOL_THRESHOLD = 0.5        # ниже этого — низкая волатильность

class TimeframeSelector:
    """Автоматически подбирает таймфреймы для каждого символа."""

    def __init__(self, engine, update_interval_hours=12):
        self.engine = engine
        self.update_interval = update_interval_hours * 3600
        self._running = False
        self._thread: threading.Thread | None = None
        # Кэш: symbol -> список таймфреймов
        self._assignments: Dict[str, List[str]] = {}

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="TimeframeSelector")
        self._thread.start()
        logger.info("TimeframeSelector started (update every %d hours)", self.update_interval // 3600)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def get_timeframes(self, symbol: str) -> List[str]:
        """Возвращает назначенные таймфреймы для символа. Если нет — список по умолчанию."""
        return self._assignments.get(symbol, ['15m', '1h', '4h'])

    def _loop(self):
        while self._running:
            try:
                self._update_all()
            except Exception:
                logger.exception("TimeframeSelector update failed")
            time.sleep(self.update_interval)

    def _update_all(self):
        symbols = self.engine._top_symbols
        if not symbols:
            return
        new_assignments = {}
        for sym in symbols:
            try:
                atr_pct = self._calc_atr_pct(sym)
                if atr_pct is not None:
                    new_assignments[sym] = self._pick_tfs(atr_pct)
                else:
                    new_assignments[sym] = ['15m', '1h', '4h']  # fallback
            except Exception as e:
                logger.debug(f"TF select error for {sym}: {e}")
                new_assignments[sym] = ['15m', '1h', '4h']

        self._assignments = new_assignments
        logger.info("TimeframeSelector updated assignments for %d symbols", len(new_assignments))

    def _calc_atr_pct(self, symbol: str) -> float | None:
        """Рассчитывает ATR в процентах от цены на 1h."""
        try:
            df = self.engine.api.get_klines_dataframe(symbol, '1h', limit=50)
            if df.empty or len(df) < 14:
                return None
            from indicators.base import ATR
            atr_ind = ATR({'period': 14})
            atr_series = atr_ind.calculate(df)
            if atr_series.empty:
                return None
            current_atr = float(atr_series.iloc[-1])
            current_price = float(df['close'].iloc[-1])
            if current_price <= 0:
                return None
            return (current_atr / current_price) * 100.0
        except Exception as e:
            logger.debug(f"ATR% calculation failed for {symbol}: {e}")
            return None

    def _pick_tfs(self, atr_pct: float) -> List[str]:
        """По значению ATR% возвращает набор таймфреймов."""
        if atr_pct > HIGH_VOL_THRESHOLD:
            # Высокая волатильность — больше коротких ТФ
            return ['15m', '1h']
        elif atr_pct < LOW_VOL_THRESHOLD:
            # Низкая волатильность — добавляем дневной
            return ['1h', '4h', '1d']
        else:
            # Средняя — стандартный набор
            return ['15m', '1h', '4h']
