"""
Turtle Trading Strategy – классический пробой 20-периодного канала.
Покупаем при пробое максимума, продаём при пробое минимума.
Тренд-фильтр: 50-EMA, только в направлении тренда.
Стоп: 2 ATR, Тейк: 4 ATR.
"""
import pandas as pd
from typing import Optional
from strategies.base import BaseStrategy, Signal
from indicators.base import EMA, ATR

class TurtleTradingStrategy(BaseStrategy):
    NAME = "TurtleTrading"
    DESCRIPTION = "Пробой 20-дневного экстремума с тренд-фильтром (50 EMA) и ATR стопом"
    VERSION = "1.0.0"
    PARAMS = {
        'enabled': True,
        'weight': 1.0,
        'timeframes': ['1h', '4h'],
        'channel_period': 20,       # период канала (классические 20)
        'ema_period': 50,           # период EMA для тренд-фильтра
        'atr_period': 14,           # период ATR
        'atr_mult_sl': 2.0,         # множитель ATR для стоп-лосса
        'atr_mult_tp': 4.0,         # множитель ATR для тейк-профита
    }

    def __init__(self, params=None, engine=None):
        super().__init__(params, engine=engine)
        self.ema = EMA({'period': self.config['ema_period']})
        self.atr = ATR({'period': self.config['atr_period']})

    def evaluate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> Optional[Signal]:
        if len(candles) < max(self.config['channel_period'], self.config['ema_period'], self.config['atr_period']) + 5:
            return None

        # Расчёт индикаторов
        ema_series = self.ema.calculate(candles)
        atr_series = self.atr.calculate(candles)

        # Текущие значения
        current_price = candles['close'].iloc[-1]
        ema_val = ema_series.iloc[-1]
        atr_val = atr_series.iloc[-1]

        # Канал пробоя: берём максимум/минимум за последние channel_period свечей (исключая текущую)
        channel_high = candles['high'].iloc[-(self.config['channel_period']+1):-1].max()
        channel_low = candles['low'].iloc[-(self.config['channel_period']+1):-1].min()

        # Проверка пробоя и тренда
        if current_price > channel_high and current_price > ema_val:
            # Пробой вверх, тренд восходящий
            stop_loss = current_price - atr_val * self.config['atr_mult_sl']
            take_profit = current_price + atr_val * self.config['atr_mult_tp']
            confidence = self._calc_confidence(current_price, channel_high, atr_val, ema_val, 'BUY')
            return Signal(
                symbol=symbol,
                action='BUY',
                confidence=confidence,
                meta={
                    'strategy': self.NAME,
                    'timeframe': timeframe,
                    'reason': f'Turtle breakout UP, channel H={channel_high:.6f}',
                },
                suggested_sl=stop_loss,
                suggested_tp=take_profit,
            )

        if current_price < channel_low and current_price < ema_val:
            # Пробой вниз, тренд нисходящий
            stop_loss = current_price + atr_val * self.config['atr_mult_sl']
            take_profit = current_price - atr_val * self.config['atr_mult_tp']
            confidence = self._calc_confidence(current_price, channel_low, atr_val, ema_val, 'SELL')
            return Signal(
                symbol=symbol,
                action='SELL',
                confidence=confidence,
                meta={
                    'strategy': self.NAME,
                    'timeframe': timeframe,
                    'reason': f'Turtle breakout DOWN, channel L={channel_low:.6f}',
                },
                suggested_sl=stop_loss,
                suggested_tp=take_profit,
            )

        return None

    def _calc_confidence(self, price, level, atr_val, ema_val, direction) -> float:
        # Базовая уверенность
        confidence = 0.5

        # Сила пробоя (на сколько % цена ушла за уровень)
        breakout_pct = abs(price - level) / level if level > 0 else 0.0
        confidence += min(0.2, breakout_pct * 10)

        # Чем сильнее тренд (расстояние до EMA), тем выше уверенность
        ema_distance = abs(price - ema_val) / ema_val if ema_val > 0 else 0.0
        confidence += min(0.15, ema_distance * 5)

        # Волатильность: при нормальной ATR/Price добавляем бонус
        if price > 0 and atr_val > 0:
            atr_ratio = atr_val / price
            if 0.005 < atr_ratio < 0.03:
                confidence += 0.05

        return min(0.95, max(0.3, confidence))
