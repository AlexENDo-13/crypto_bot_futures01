"""
Smart Pyramiding Strategy – наращивает позицию в сторону тренда при подтверждении.
Заменяет скальпинг, не нарушает лимиты API.
"""
import logging
import time
import pandas as pd
from datetime import datetime, timezone
from typing import Optional

from strategies.base import BaseStrategy, Signal
from indicators.base import EMA, ATR
from indicators.adx import ADX                         # <-- ИСПРАВЛЕНО
from core.whale_shield import ALERT_COOLDOWN_MINUTES

logger = logging.getLogger(__name__)


class SmartPyramidingStrategy(BaseStrategy):
    NAME = "SmartPyramiding"
    DESCRIPTION = "Пирамидинг в сторону сильного тренда с подтверждением Whale Shield"
    VERSION = "1.0.0"

    PARAMS = {
        'enabled': True,
        'weight': 0.9,
        'timeframes': ['1h'],
        'ema_fast': 20,
        'ema_slow': 50,
        'adx_period': 14,
        'min_adx': 25,
        'atr_period': 14,
        'pyramid_max_additions': 3,
        'pyramid_profit_threshold': 0.02,
    }

    def __init__(self, params=None, engine=None):
        super().__init__(params, engine=engine)
        self.ema_fast = EMA({'period': self.config['ema_fast']})
        self.ema_slow = EMA({'period': self.config['ema_slow']})
        self.adx = ADX({'period': self.config['adx_period']})
        self.atr = ATR({'period': self.config['atr_period']})
        self._pyramid_counters = {}

    def evaluate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> Optional[Signal]:
        if len(candles) < self.config['ema_slow'] + 10:
            return None

        ema_fast_vals = self.ema_fast.calculate(candles)
        ema_slow_vals = self.ema_slow.calculate(candles)
        adx_vals = self.adx.calculate(candles)
        atr_vals = self.atr.calculate(candles)

        current_price = candles['close'].iloc[-1]
        fast_above_slow = ema_fast_vals.iloc[-1] > ema_slow_vals.iloc[-1]
        adx_value = adx_vals.iloc[-1] if not adx_vals.empty else 0

        strong_trend_up = fast_above_slow and adx_value > self.config['min_adx']
        strong_trend_down = not fast_above_slow and adx_value > self.config['min_adx']

        engine = self.engine
        if engine is None:
            logger.error("SmartPyramiding: engine not set, cannot evaluate")
            return None

        existing_positions = engine.portfolio.get_positions()
        current_pos = next((p for p in existing_positions if p.symbol == symbol), None)

        if current_pos is None:
            if strong_trend_up:
                if not self._is_whale_safe(symbol, engine):
                    return None
                confidence = self._calc_confidence(adx_value, True, atr_vals.iloc[-1], current_price)
                return Signal(
                    symbol=symbol, action='BUY', confidence=confidence,
                    meta={'reason': 'SmartPyramiding initial BUY trend'}
                )
            elif strong_trend_down:
                if not self._is_whale_safe(symbol, engine):
                    return None
                confidence = self._calc_confidence(adx_value, False, atr_vals.iloc[-1], current_price)
                return Signal(
                    symbol=symbol, action='SELL', confidence=confidence,
                    meta={'reason': 'SmartPyramiding initial SELL trend'}
                )
        else:
            key = f"{symbol}_{current_pos.side}"
            pyramid_count = self._pyramid_counters.get(key, 0)
            if pyramid_count >= self.config['pyramid_max_additions']:
                return None

            if current_pos.pnl_pct >= self.config['pyramid_profit_threshold'] * 100:
                if current_pos.side == 'LONG' and strong_trend_up:
                    if not self._is_whale_safe(symbol, engine):
                        return None
                    self._pyramid_counters[key] = pyramid_count + 1
                    confidence = self._calc_confidence(adx_value, True, atr_vals.iloc[-1], current_price) * 0.8
                    return Signal(
                        symbol=symbol, action='BUY', confidence=confidence,
                        meta={'reason': f'SmartPyramiding add #{pyramid_count+1} to LONG'}
                    )
                elif current_pos.side == 'SHORT' and strong_trend_down:
                    if not self._is_whale_safe(symbol, engine):
                        return None
                    self._pyramid_counters[key] = pyramid_count + 1
                    confidence = self._calc_confidence(adx_value, False, atr_vals.iloc[-1], current_price) * 0.8
                    return Signal(
                        symbol=symbol, action='SELL', confidence=confidence,
                        meta={'reason': f'SmartPyramiding add #{pyramid_count+1} to SHORT'}
                    )
        return None

    def _calc_confidence(self, adx: float, is_bullish: bool, atr: float, price: float) -> float:
        conf = 0.5
        conf += min(0.3, (adx - self.config['min_adx']) / 50)
        atr_pct = atr / price if price > 0 else 0
        if 0.01 < atr_pct < 0.05:
            conf += 0.1
        return min(1.0, max(0.1, conf))

    def _is_whale_safe(self, symbol: str, engine) -> bool:
        if hasattr(engine, 'whale_shield') and engine.whale_shield._running:
            last_alert = engine.whale_shield._last_alert_time.get(symbol, 0)
            if time.time() - last_alert < 60 * ALERT_COOLDOWN_MINUTES:
                logger.debug(f"SmartPyramiding blocked by Whale Shield for {symbol}")
                return False
        return True
