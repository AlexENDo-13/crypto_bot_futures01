"""
Безопасный микро‑свинг (скальпинг) с защитой от бана.
Открывает позицию при сигнале MultiTFConsensus, держит 1‑5 минут,
фиксирует 0.3% прибыли, стоп 0.12%. Не чаще 1 сделки в 5 минут.
"""
import time
import pandas as pd
from typing import Optional
from strategies.base import BaseStrategy, Signal

class MicroScalperStrategy(BaseStrategy):
    NAME = "MicroScalper"
    DESCRIPTION = "Быстрые сделки при мультитаймфреймовом согласии, TP=0.3%, SL=0.12%"
    VERSION = "1.1.0"
    PARAMS = {
        'enabled': True,
        'weight': 1.0,
        'timeframes': ['5m', '15m', '1h', '4h', '1d'],
        'tp_pct': 0.3,      # тейк‑профит в % от входа
        'sl_pct': 0.12,     # стоп‑лосс в % от входа
        'min_volume_ratio': 0.8,
        'cooldown_seconds': 300,  # минимальный интервал между сделками (5 минут)
    }

    def __init__(self, params=None, engine=None):
        super().__init__(params, engine=engine)
        self._last_trade_time = 0

    def evaluate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> Optional[Signal]:
        if self.engine is None:
            return None
        # Защита от слишком частых входов
        now = time.time()
        if now - self._last_trade_time < self.config['cooldown_seconds']:
            return None

        # Используем сигнал только от MultiTFConsensus (высокое качество)
        mcs = self.engine.strategies.get('MultiTFConsensus')
        if mcs is None or not mcs.enabled:
            return None
        signal = mcs.evaluate(symbol, timeframe, candles)
        if signal is None or signal.confidence < 0.6:
            return None

        # Дополнительная проверка объёма
        if len(candles) < 5:
            return None
        current_vol = candles['volume'].iloc[-1]
        avg_vol = candles['volume'].iloc[-5:].mean()
        if avg_vol > 0 and current_vol / avg_vol < self.config['min_volume_ratio']:
            return None

        price = candles['close'].iloc[-1]
        tp = price * (1 + self.config['tp_pct'] / 100) if signal.action == 'BUY' else price * (1 - self.config['tp_pct'] / 100)
        sl = price * (1 - self.config['sl_pct'] / 100) if signal.action == 'BUY' else price * (1 + self.config['sl_pct'] / 100)

        self._last_trade_time = now
        signal.confidence = min(0.95, signal.confidence * 1.1)
        signal.suggested_tp = tp
        signal.suggested_sl = sl
        signal.meta['strategy'] = self.NAME
        return signal
