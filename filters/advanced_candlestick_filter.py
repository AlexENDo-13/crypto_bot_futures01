"""
Advanced Candlestick Pattern Filter – анализирует 21+ свечную модель,
используя библиотеку pandas-ta (TA-Lib patterns).
Поддерживает подтверждение сигналов и частичную блокировку.
Если библиотека отсутствует, фильтр самовыключается.
"""
import logging
from typing import Dict, Any
from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

class AdvancedCandlestickFilter(BaseFilter):
    NAME = "AdvancedCandlestick"
    DESCRIPTION = "Фильтр по 21+ свечным паттернам (pandas-ta/TA-Lib)"
    PRIORITY = 12
    PARAMS = {
        'enabled': True,
        'timeframe': '1h',                  # таймфрейм для анализа
        'bullish_weight': 1.15,             # усиление при бычьем паттерне
        'bearish_weight': 1.15,             # усиление при медвежьем
        'neutral_penalty': 0.8,             # снижение уверенности при доджи/нейтральном
        'require_confirmation': True,       # требовать совпадения хотя бы 2 паттернов
        'min_patterns': 2,                  # минимальное число паттернов для подтверждения
    }

    def __init__(self, params=None):
        super().__init__(params)
        self._pandas_ta_available = False
        self._cdl_functions = {}
        self._init_pandas_ta()

    def _init_pandas_ta(self):
        """Загружаем pandas-ta и получаем словарь свечных моделей."""
        try:
            import pandas_ta as ta
            # Получаем список всех функций CDL (candlestick)
            self._cdl_functions = {
                name: getattr(ta, name)
                for name in dir(ta)
                if name.startswith('cdl_')
            }
            if self._cdl_functions:
                self._pandas_ta_available = True
                logger.info(f"AdvancedCandlestick loaded {len(self._cdl_functions)} patterns via pandas-ta")
            else:
                logger.warning("pandas-ta found but no CDL patterns available")
        except ImportError:
            logger.warning("pandas-ta not installed. AdvancedCandlestick disabled. Install: pip install pandas-ta")
            self._pandas_ta_available = False
        except Exception as e:
            logger.error(f"Failed to init pandas-ta: {e}")
            self._pandas_ta_available = False

    def assess(self, signal: Signal, data: Dict[str, Any]) -> float:
        # Если библиотеки нет – пропускаем сигнал без изменений
        if not self.enabled or not self._pandas_ta_available:
            return signal.confidence

        candle_data = data.get('candle_data')
        if not candle_data:
            return signal.confidence

        tf = self.config['timeframe']
        df = candle_data.get(tf)
        if df is None or len(df) < 3:
            return signal.confidence

        # Приводим DataFrame к ожидаемым названиям колонок: Open,High,Low,Close,Volume
        try:
            df = df.rename(columns={
                'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'
            })
        except Exception:
            return signal.confidence

        # Подсчитываем бычьи и медвежьи сигналы от всех паттернов
        bullish_count = 0
        bearish_count = 0
        neutral_count = 0

        for name, func in self._cdl_functions.items():
            try:
                result = func(open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])
                if result is not None and not result.empty:
                    last_val = result.iloc[-1]
                    if last_val > 0:
                        bullish_count += 1
                    elif last_val < 0:
                        bearish_count += 1
                    else:
                        neutral_count += 1
            except Exception:
                continue

        total_detected = bullish_count + bearish_count + neutral_count
        if total_detected == 0:
            return signal.confidence  # нет распознанных паттернов – пропускаем

        # Логика фильтрации
        action = signal.action
        confidence = signal.confidence

        # Если требуется подтверждение, проверяем количество паттернов
        if self.config['require_confirmation'] and (bullish_count + bearish_count) < self.config['min_patterns']:
            logger.debug(f"Not enough patterns for {signal.symbol}: bull={bullish_count}, bear={bearish_count}")
            return confidence * 0.9  # небольшой штраф при слабых сигналах

        if action == 'BUY':
            if bearish_count > bullish_count and bearish_count >= 2:
                logger.info(f"AdvancedCandlestick blocked BUY {signal.symbol}: {bearish_count} bearish vs {bullish_count} bullish")
                return 0.0
            if bullish_count >= 2:
                boost = self.config['bullish_weight'] ** min(bullish_count, 3)
                confidence = min(1.0, confidence * boost)
            elif neutral_count >= 3:
                confidence *= self.config['neutral_penalty']
        elif action == 'SELL':
            if bullish_count > bearish_count and bullish_count >= 2:
                logger.info(f"AdvancedCandlestick blocked SELL {signal.symbol}: {bullish_count} bullish vs {bearish_count} bearish")
                return 0.0
            if bearish_count >= 2:
                boost = self.config['bearish_weight'] ** min(bearish_count, 3)
                confidence = min(1.0, confidence * boost)
            elif neutral_count >= 3:
                confidence *= self.config['neutral_penalty']

        return confidence
