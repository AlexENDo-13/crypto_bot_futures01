"""
Simple vectorized backtest engine for evaluating strategies.
"""
import logging
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class BacktestEngine:
    def __init__(self, engine):
        self.engine = engine

    def run(self, strategy_name: str, symbol: str = 'BTC-USDT',
            timeframe: str = '1h', start_date: Optional[str] = None,
            end_date: Optional[str] = None, initial_balance: float = 1000.0) -> Dict[str, Any]:
        """
        Запускает бэктест стратегии на исторических данных.
        Возвращает словарь с метриками.
        """
        if strategy_name not in self.engine.strategies:
            return {'error': f'Strategy {strategy_name} not found'}
        strategy = self.engine.strategies[strategy_name]
        try:
            # Получаем исторические данные
            end_time = int(pd.Timestamp.now(tz='UTC').timestamp() * 1000) if not end_date else \
                       int(pd.Timestamp(end_date, tz='UTC').timestamp() * 1000)
            start_time = int(pd.Timestamp(start_date, tz='UTC').timestamp() * 1000) if start_date else \
                         end_time - 7 * 24 * 3600 * 1000  # 7 дней по умолчанию
            klines = self.engine.api.get_klines(symbol, timeframe, start_time=start_time,
                                                end_time=end_time, limit=1000)
            if not klines:
                return {'error': 'No historical data'}

            df = pd.DataFrame(klines)
            # Приводим колонки к стандартным названиям
            column_map = {'open': 'open', 'high': 'high', 'low': 'low',
                         'close': 'close', 'volume': 'volume', 'time': 'timestamp'}
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
            if df.empty or len(df) < 50:
                return {'error': 'Insufficient data after processing'}

            # Симуляция
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
                if signal is None:
                    continue
                if signal.action in ('BUY', 'SELL') and position == 0:
                    entry_price = chunk['close'].iloc[-1]
                    position = balance / entry_price
                    balance = 0.0
                elif position > 0 and signal.action == 'HOLD':
                    # Выход по обратному сигналу, для простоты считаем, что стратегия даёт сигнал на выход
                    pass
            # Закрытие в конце периода
            if position > 0:
                exit_price = df['close'].iloc[-1]
                pnl = (exit_price - entry_price) * position
                trades.append(pnl)
                balance = position * exit_price
            else:
                balance = initial_balance

            if not trades:
                return {'error': 'No trades executed'}
            trades_arr = np.array(trades)
            profit = np.sum(trades_arr)
            winrate = np.sum(trades_arr > 0) / len(trades_arr)
            avg_pnl = np.mean(trades_arr)
            std_pnl = np.std(trades_arr) or 1e-9
            sharpe = avg_pnl / std_pnl * np.sqrt(len(trades_arr))
            return {
                'initial_balance': initial_balance,
                'final_balance': balance,
                'total_pnl': round(profit, 4),
                'num_trades': len(trades),
                'winrate': winrate,
                'sharpe': round(sharpe, 2),
                'avg_pnl': round(avg_pnl, 4),
                'max_drawdown': None,
            }
        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            return {'error': str(e)}
