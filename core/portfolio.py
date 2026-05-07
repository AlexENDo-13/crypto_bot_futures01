"""
Portfolio management: position tracking, trade history, equity curve.
"""
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import csv
import time

logger = logging.getLogger(__name__)


class Position:
    """Represents an open position."""
    def __init__(self, symbol: str, side: str, entry_price: float,
                 quantity: float, leverage: float, margin: float,
                 tp_price: Optional[float] = None,
                 sl_price: Optional[float] = None,
                 open_time: str = "",
                 order_id: str = "",
                 trailing: bool = False):
        self.symbol = symbol
        self.side = side
        self.entry_price = entry_price
        self.quantity = quantity
        self.leverage = leverage
        self.margin = margin
        self.tp_price = tp_price
        self.sl_price = sl_price
        self.open_time = open_time or datetime.now(timezone.utc).isoformat()
        self.order_id = order_id
        self.unrealized_pnl = 0.0
        self.pnl_pct = 0.0
        self.trailing = trailing
        self.creation_time = time.time()  # для защиты от частого усреднения

    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'side': self.side,
            'entry_price': self.entry_price,
            'quantity': self.quantity,
            'leverage': self.leverage,
            'margin': self.margin,
            'unrealized_pnl': self.unrealized_pnl,
            'pnl_pct': self.pnl_pct,
            'tp_price': self.tp_price,
            'sl_price': self.sl_price,
            'open_time': self.open_time,
            'order_id': self.order_id,
            'trailing': self.trailing,
        }


class TradeRecord:
    def __init__(self, symbol, side, action, entry_price, exit_price,
                 quantity, leverage, pnl, close_reason="", open_time="", close_time=""):
        self.symbol = symbol
        self.side = side
        self.action = action
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.quantity = quantity
        self.leverage = leverage
        self.pnl = pnl
        self.close_reason = close_reason
        self.open_time = open_time
        self.close_time = close_time or datetime.now(timezone.utc).isoformat()


class PortfolioManager:
    def __init__(self):
        self._positions: Dict[str, Position] = {}
        self._trades: List[TradeRecord] = []
        self._equity_curve: List[Dict] = []
        self._daily_pnl = 0.0
        self._balance = 0.0
        self._equity = 0.0
        self.available_margin = 0.0
        self.MIN_AVERAGING_INTERVAL = 30  # секунд, защита от дублирования

    def add_position(self, position: Position):
        key = f"{position.symbol}_{position.side}"
        if key in self._positions:
            existing = self._positions[key]
            # Защита от слишком частого усреднения
            if time.time() - existing.creation_time < self.MIN_AVERAGING_INTERVAL:
                logger.info(f"Averaging too soon for {key}, ignoring new signal")
                return
            # Усредняем количество и цену
            total_qty = existing.quantity + position.quantity
            avg_price = (existing.entry_price * existing.quantity + position.entry_price * position.quantity) / total_qty
            existing.quantity = total_qty
            existing.entry_price = avg_price
            existing.margin += position.margin
            # Обновляем TP/SL на новые (последний сигнал) и статус трейлинга
            existing.tp_price = position.tp_price
            existing.sl_price = position.sl_price
            existing.trailing = position.trailing
            existing.creation_time = time.time()
        else:
            self._positions[key] = position

    def remove_position(self, symbol: str, side: str):
        key = f"{symbol}_{side}"
        if key in self._positions:
            del self._positions[key]

    def clear(self):
        self._positions.clear()

    def update_position_pnl(self, symbol, side, pnl, pnl_pct=0.0):
        key = f"{symbol}_{side}"
        if key in self._positions:
            self._positions[key].unrealized_pnl = pnl
            if self._positions[key].margin > 0:
                self._positions[key].pnl_pct = (pnl / self._positions[key].margin) * 100
            else:
                self._positions[key].pnl_pct = pnl_pct

    def get_positions(self) -> List[Position]:
        return list(self._positions.values())

    def record_trade(self, trade: TradeRecord):
        self._trades.append(trade)
        self._daily_pnl += trade.pnl

    def update_equity(self, balance: float, unrealized_pnl: float = 0.0):
        self._balance = balance
        self._equity = balance + unrealized_pnl
        self._equity_curve.append({
            'time': datetime.now(timezone.utc).isoformat(),
            'equity': self._equity,
            'balance': balance,
            'unrealized': unrealized_pnl,
        })

    def get_daily_pnl(self) -> float:
        return self._daily_pnl

    def reset_daily_pnl(self):
        self._daily_pnl = 0.0

    def get_win_rate(self) -> float:
        if not self._trades:
            return 0.0
        wins = [t for t in self._trades if t.pnl > 0]
        return (len(wins) / len(self._trades)) * 100

    @property
    def trades(self) -> List[TradeRecord]:
        return self._trades

    def get_stats(self) -> dict:
        positions = self.get_positions()
        total_unrealized = sum(p.unrealized_pnl for p in positions)
        return {
            'balance': self._balance,
            'equity': self._equity,
            'unrealized_pnl': total_unrealized,
            'daily_pnl': self._daily_pnl,
            'open_positions': len(positions),
            'win_rate': self.get_win_rate(),
            'total_trades': len(self._trades),
        }

    def get_equity_curve(self, days=7) -> List[Dict]:
        cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
        return [e for e in self._equity_curve 
                if datetime.fromisoformat(e['time']).timestamp() >= cutoff]

    def export_trades_csv(self, filepath: str) -> bool:
        try:
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['symbol', 'side', 'action', 'entry_price', 'exit_price',
                                 'quantity', 'leverage', 'pnl', 'close_reason', 'open_time', 'close_time'])
                for t in self._trades:
                    writer.writerow([t.symbol, t.side, t.action, t.entry_price, t.exit_price,
                                     t.quantity, t.leverage, t.pnl, t.close_reason, t.open_time, t.close_time])
            return True
        except Exception as e:
            logger.error(f"Failed to export trades: {e}")
            return False
