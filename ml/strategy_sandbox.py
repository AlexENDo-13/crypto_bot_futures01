"""
Strategy Sandbox – безопасное тестирование стратегий на исторических данных.
Загружает .py файл с классом стратегии, прогоняет на выбранном символе и таймфрейме,
возвращает метрики (PnL, Sharpe, Winrate).
"""
import logging
import importlib.util
import sys
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class StrategySandbox:
    """Песочница для проверки стратегий."""

    def __init__(self, engine):
        self.engine = engine

    def load_strategy_from_file(self, filepath: str):
        """Загружает класс стратегии из .py файла (ожидается класс с NAME и evaluate)."""
        spec = importlib.util.spec_from_file_location("sandbox_strategy", filepath)
        if not spec or not spec.loader:
            raise ImportError(f"Не удалось загрузить модуль из {filepath}")
        module = importlib.util.module_from_spec(spec)
        sys.modules['sandbox_strategy'] = module
        spec.loader.exec_module(module)
        # Ищем первый класс, наследующий от BaseStrategy (или просто имеющий метод evaluate)
        from strategies.base import BaseStrategy
        for name, obj in module.__dict__.items():
            if isinstance(obj, type) and issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
                return obj()
        raise ValueError("В файле не найден класс стратегии (наследник BaseStrategy)")

    def test(self, strategy, symbol: str = 'BTC-USDT', timeframe: str = '1h',
             days: int = 7, initial_balance: float = 1000.0) -> Dict[str, Any]:
        """
        Прогоняет стратегию на исторических данных за указанное количество дней.
        Возвращает словарь с метриками.
        """
        # Получение исторических данных
        try:
            end_time = int(datetime.now(timezone.utc).timestamp() * 1000)
            start_time = end_time - days * 86400 * 1000
            klines = self.engine.api.get_klines(symbol, timeframe, start_time=start_time, end_time=end_time, limit=1000)
            if not klines:
                return {'error': 'Нет данных'}
            df = pd.DataFrame(klines)
            # Приводим к стандартному формату
            column_map = {'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close', 'volume': 'volume', 'time': 'timestamp'}
            for old, new in column_map.items():
                if old in df.columns and new not in df.columns:
                    df.rename(columns={old: new}, inplace=True)
            for col in ['open','high','low','close','volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
                df.set_index('timestamp', inplace=True)
            df.sort_index(inplace=True)
        except Exception as e:
            return {'error': f'Ошибка получения данных: {e}'}

        if df.empty or len(df) < 50:
            return {'error': 'Недостаточно данных'}

        # Симуляция торговли
        balance = initial_balance
        position = 0.0
        entry_price = 0.0
        trades = []
        for i in range(50, len(df)):
            chunk = df.iloc[:i+1]
            signal = None
            try:
                signal = strategy.evaluate(symbol, timeframe, chunk)
            except Exception:
                continue
            if signal and signal.action in ('BUY', 'SELL') and position == 0:
                # Вход в позицию
                entry_price = chunk['close'].iloc[-1]
                position = balance / entry_price
                balance = 0.0
            elif position > 0 and signal and signal.action == 'HOLD':
                # Простейший выход по противоположному сигналу (можно доработать)
                pass
            # Принудительный выход по концу периода
        if position > 0:
            exit_price = df['close'].iloc[-1]
            pnl = (exit_price - entry_price) * position
            trades.append(pnl)
            balance = position * exit_price
            position = 0.0
        else:
            if trades:
                balance += sum(trades)
            else:
                balance = initial_balance  # если не было сделок

        # Вычисление метрик
        if not trades:
            return {'error': 'Нет совершённых сделок'}
        trades_arr = np.array(trades)
        profit = np.sum(trades_arr)
        winrate = np.sum(trades_arr > 0) / len(trades_arr) if len(trades_arr) > 0 else 0
        avg_pnl = np.mean(trades_arr)
        std_pnl = np.std(trades_arr) or 1e-9
        sharpe = avg_pnl / std_pnl * np.sqrt(len(trades_arr))

        return {
            'initial_balance': initial_balance,
            'final_balance': round(balance, 2),
            'total_pnl': round(profit, 4),
            'num_trades': len(trades),
            'winrate': round(winrate * 100, 2),
            'sharpe': round(sharpe, 2),
            'avg_pnl': round(avg_pnl, 4),
            'max_drawdown': None,  # упрощённо
        }
