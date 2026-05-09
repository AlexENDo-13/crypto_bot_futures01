"""
Portfolio Correlation Filter – следит за корреляцией открытых позиций.
Блокирует сигналы, если порог корреляции превышен.
"""
import logging
import numpy as np
from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

class PortfolioCorrelationFilter(BaseFilter):
    NAME = "PortfolioCorrelation"
    DESCRIPTION = "Фильтр корреляции портфеля. Не открывает новые позиции при высокой корреляции."
    PRIORITY = 16
    PARAMS = {
        'enabled': True,
        'max_correlation': 0.7,           # максимально допустимая корреляция
        'correlation_lookback': 50,        # сколько свечей для расчёта
        'timeframe': '1h',
    }

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        open_positions = data.get('open_positions', [])
        candle_data = data.get('candle_data')
        if not open_positions or not candle_data:
            return signal.confidence

        tf = self.config['timeframe']

        # Получаем свечи для символа сигнала
        if signal.symbol not in candle_data or tf not in candle_data[signal.symbol]:
            return signal.confidence
        new_closes = candle_data[signal.symbol][tf]['close'].values[-self.config['correlation_lookback']:]

        for pos in open_positions:
            pos_symbol = pos.get('symbol', '')
            if pos_symbol not in candle_data or tf not in candle_data[pos_symbol]:
                continue
            existing_closes = candle_data[pos_symbol][tf]['close'].values[-self.config['correlation_lookback']:]
            # Выравниваем длину
            min_len = min(len(new_closes), len(existing_closes))
            if min_len < 2:
                continue
            new = new_closes[-min_len:]
            existing = existing_closes[-min_len:]
            corr = np.corrcoef(new, existing)[0, 1]

            if abs(corr) >= self.config['max_correlation']:
                logger.info(f"Correlation filter blocked {signal.symbol}: corr={corr:.2f} with {pos_symbol}")
                return 0.0

        return signal.confidence
