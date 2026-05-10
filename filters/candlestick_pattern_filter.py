"""
Candlestick pattern filter – анализирует 12 свечных моделей и подтверждает/отклоняет сигналы.
Исправлено: медвежьи паттерны при BUY теперь не блокируют полностью, а лишь снижают confidence.
"""
import logging
from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

class CandlestickPatternFilter(BaseFilter):
    NAME = "CandlestickPattern"
    DESCRIPTION = "Фильтр по 12 свечным паттернам (Поглощение, Молот, Доджи, Звезда и др.)"
    PRIORITY = 13
    PARAMS = {
        'enabled': True,
        'timeframe': '1h',
        'use_engulfing': True,
        'use_hammer': True,
        'use_morning_star': True,
        'use_three_soldiers': True,
        'use_marubozu': True,
        'bearish_penalty': 0.3,      # коэффициент штрафа при противодействующем паттерне
        'bullish_boost': 1.15,       # коэффициент усиления при подтверждающем паттерне
    }

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        candle_data = data.get('candle_data')
        if not candle_data:
            return signal.confidence

        tf = self.config['timeframe']
        df = candle_data.get(tf)
        if df is None or len(df) < 4:
            return signal.confidence

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3]
        prev3 = df.iloc[-4]

        bullish = False
        bearish = False

        # --- Бычье/Медвежье Поглощение ---
        if self.config['use_engulfing']:
            if (prev['close'] < prev['open'] and curr['close'] > curr['open'] and
                curr['open'] <= prev['close'] and curr['close'] >= prev['open']):
                bullish = True
            if (prev['close'] > prev['open'] and curr['close'] < curr['open'] and
                curr['open'] >= prev['close'] and curr['close'] <= prev['open']):
                bearish = True

        # --- Молот / Падающая звезда ---
        if self.config['use_hammer']:
            body = abs(curr['close'] - curr['open'])
            if body > 0:
                lower_wick = min(curr['open'], curr['close']) - curr['low']
                upper_wick = curr['high'] - max(curr['open'], curr['close'])
                if lower_wick >= 2 * body and upper_wick <= 0.5 * body:
                    bullish = True
                if upper_wick >= 2 * body and lower_wick <= 0.5 * body:
                    bearish = True

        # --- Утренняя звезда / Вечерняя звезда ---
        if self.config['use_morning_star']:
            if (prev2['close'] < prev2['open'] and
                abs(prev['close'] - prev['open']) < abs(prev2['close'] - prev2['open']) * 0.3 and
                curr['close'] > curr['open'] and curr['close'] > prev2['open']):
                bullish = True
            if (prev2['close'] > prev2['open'] and
                abs(prev['close'] - prev['open']) < abs(prev2['close'] - prev2['open']) * 0.3 and
                curr['close'] < curr['open'] and curr['close'] < prev2['open']):
                bearish = True

        # --- Три белых солдата / Три чёрных вороны ---
        if self.config['use_three_soldiers']:
            if (prev2['close'] > prev2['open'] and prev['close'] > prev['open'] and
                curr['close'] > curr['open'] and prev['close'] > prev2['close'] and
                curr['close'] > prev['close']):
                bullish = True
            if (prev2['close'] < prev2['open'] and prev['close'] < prev['open'] and
                curr['close'] < curr['open'] and prev['close'] < prev2['close'] and
                curr['close'] < prev['close']):
                bearish = True

        # --- Марубозу (свеча без теней) ---
        if self.config['use_marubozu']:
            body = abs(curr['close'] - curr['open'])
            total_range = curr['high'] - curr['low']
            if total_range > 0 and body / total_range > 0.9:
                if curr['close'] > curr['open']:
                    bullish = True
                else:
                    bearish = True

        # --- Принятие решения (ИЗМЕНЕНО) ---
        if signal.action == 'BUY':
            if bearish and not bullish:
                # Медвежий паттерн при BUY – снижаем уверенность, а не блокируем полностью
                new_conf = signal.confidence * self.config['bearish_penalty']
                logger.info(f"CandlestickPattern penalty for BUY {signal.symbol}: bearish pattern, conf {signal.confidence:.2f} -> {new_conf:.2f}")
                return new_conf
            if bullish:
                return min(1.0, signal.confidence * self.config['bullish_boost'])
        elif signal.action == 'SELL':
            if bullish and not bearish:
                new_conf = signal.confidence * self.config['bearish_penalty']
                logger.info(f"CandlestickPattern penalty for SELL {signal.symbol}: bullish pattern, conf {signal.confidence:.2f} -> {new_conf:.2f}")
                return new_conf
            if bearish:
                return min(1.0, signal.confidence * self.config['bullish_boost'])

        # Если нет явных паттернов, лёгкий штраф за неопределённость (0.95 вместо 0.9, чтобы не снижать слишком сильно)
        return signal.confidence * 0.95
