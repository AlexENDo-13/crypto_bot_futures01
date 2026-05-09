"""
Candlestick pattern filter – анализирует свечные модели и подтверждает/отклоняет сигналы.
Поддерживаемые паттерны: Поглощение, Молот / Падающая звезда, Доджи.
"""
import logging
from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

class CandlestickPatternFilter(BaseFilter):
    NAME = "CandlestickPattern"
    DESCRIPTION = "Фильтр по свечным паттернам (Поглощение, Молот, Доджи и др.)"
    PRIORITY = 13
    PARAMS = {
        'enabled': True,
        'timeframe': '1h',
        'use_engulfing': True,      # Поглощение (бычье / медвежье)
        'use_hammer': True,         # Молот (бычий разворот) / Падающая звезда
        'use_doji': True,           # Доджи (неопределённость – может снижать уверенность)
        'min_body_ratio': 0.3,      # Минимальное отношение тела свечи к диапазону для Поглощения
        'hammer_wick_ratio': 2.0,   # Отношение нижней тени к телу для Молота
    }

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        candle_data = data.get('candle_data')
        if not candle_data:
            return signal.confidence

        tf = self.config['timeframe']
        df = candle_data.get(tf)
        if df is None or len(df) < 2:
            return signal.confidence

        # Последние две свечи
        prev = df.iloc[-2]
        curr = df.iloc[-1]

        bullish = False
        bearish = False
        neutral = False   # Доджи – сигнал неопределённости

        # --- Поглощение ---
        if self.config['use_engulfing']:
            body_prev = abs(prev['close'] - prev['open'])
            body_curr = abs(curr['close'] - curr['open'])
            range_prev = prev['high'] - prev['low']
            range_curr = curr['high'] - curr['low']
            if range_prev > 0 and range_curr > 0:
                body_ratio_prev = body_prev / range_prev
                body_ratio_curr = body_curr / range_curr
                min_ratio = self.config['min_body_ratio']

                # Бычье поглощение
                if (prev['close'] < prev['open'] and curr['close'] > curr['open'] and
                    body_ratio_prev >= min_ratio and body_ratio_curr >= min_ratio and
                    curr['open'] <= prev['close'] and curr['close'] >= prev['open']):
                    bullish = True
                    logger.debug(f"Bullish Engulfing on {signal.symbol} {tf}")

                # Медвежье поглощение
                if (prev['close'] > prev['open'] and curr['close'] < curr['open'] and
                    body_ratio_prev >= min_ratio and body_ratio_curr >= min_ratio and
                    curr['open'] >= prev['close'] and curr['close'] <= prev['open']):
                    bearish = True
                    logger.debug(f"Bearish Engulfing on {signal.symbol} {tf}")

        # --- Молот / Падающая звезда ---
        if self.config['use_hammer']:
            body = abs(curr['close'] - curr['open'])
            lower_wick = min(curr['open'], curr['close']) - curr['low']
            upper_wick = curr['high'] - max(curr['open'], curr['close'])
            wick_ratio = self.config['hammer_wick_ratio']
            total_range = curr['high'] - curr['low']

            if total_range > 0 and body > 0:
                # Молот (бычий разворот): длинная нижняя тень, маленькое тело внизу
                if (lower_wick >= wick_ratio * body and upper_wick <= 0.5 * body and
                    curr['close'] > curr['open']):
                    bullish = True
                    logger.debug(f"Hammer on {signal.symbol} {tf}")

                # Падающая звезда (медвежий разворот): длинная верхняя тень, маленькое тело вверху
                if (upper_wick >= wick_ratio * body and lower_wick <= 0.5 * body and
                    curr['close'] < curr['open']):
                    bearish = True
                    logger.debug(f"Shooting Star on {signal.symbol} {tf}")

        # --- Доджи ---
        if self.config['use_doji']:
            body = abs(curr['close'] - curr['open'])
            total_range = curr['high'] - curr['low']
            if total_range > 0 and body / total_range < 0.1:
                neutral = True
                logger.debug(f"Doji on {signal.symbol} {tf}")

        # Принятие решения
        if signal.action == 'BUY':
            if bearish:
                logger.info(f"CandlestickPattern blocked BUY {signal.symbol}: bearish pattern")
                return 0.0
            if neutral:
                # Доджи снижает уверенность
                return signal.confidence * 0.7
            if bullish:
                return min(1.0, signal.confidence * 1.15)
        elif signal.action == 'SELL':
            if bullish:
                logger.info(f"CandlestickPattern blocked SELL {signal.symbol}: bullish pattern")
                return 0.0
            if neutral:
                return signal.confidence * 0.7
            if bearish:
                return min(1.0, signal.confidence * 1.15)

        # Нет явного паттерна – небольшой штраф
        return signal.confidence * 0.9
