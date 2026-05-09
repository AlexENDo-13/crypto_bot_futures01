"""
Grid Strategy – сетка лимитных ордеров.
Размещает серию отложенных заявок на покупку/продажу с фиксированным шагом,
позволяя зарабатывать на колебаниях цены.
Параметры:
  grid_levels      – количество уровней в одну сторону
  grid_step_atr    – шаг сетки в единицах ATR
  atr_period       – период ATR для шага
  order_qty_pct    – доля от размера позиции на один ордер
  max_grid_orders  – максимальное количество одновременных ордеров (общее)
"""
import logging
import time
import pandas as pd
from typing import Optional, List, Dict
from strategies.base import BaseStrategy, Signal
from indicators.base import ATR

logger = logging.getLogger(__name__)

class GridStrategy(BaseStrategy):
    NAME = "GridStrategy"
    DESCRIPTION = "Сетка лимитных ордеров с шагом ATR"
    VERSION = "1.0.0"
    PARAMS = {
        'enabled': True,
        'weight': 0.8,
        'timeframes': ['15m', '1h'],
        'grid_levels': 4,                # уровней в каждую сторону
        'grid_step_atr': 0.5,            # шаг относительно ATR
        'atr_period': 14,
        'order_qty_pct': 20.0,           # % от позиции на один ордер
        'max_grid_orders': 8,            # лимит ордеров всего
        'renew_interval_minutes': 60,    # как часто обновлять сетку
    }

    def __init__(self, params=None, engine=None):
        super().__init__(params, engine=engine)
        self.atr = ATR({'period': self.config['atr_period']})
        self._active_grids: Dict[str, dict] = {}  # symbol -> {orders, last_renew}
        self._grid_positions: Dict[str, dict] = {} # symbol -> {side, base_qty, base_price, ...}

    def evaluate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> Optional[Signal]:
        # Логика активации сетки: при отсутствии позиции и благоприятном режиме (например, RANGE)
        # но для простоты будем запускать сетку по сигналу извне (пока команда /grid_start)
        # evaluate можно оставить пустым, а управление через Telegram или AutoStrategySelector
        return None

    # -----------------------------------------------------------------
    # Методы управления сеткой (вызываются извне, например, через Telegram)
    # -----------------------------------------------------------------
    def start_grid(self, symbol: str, side: str, quantity: float, price: float) -> bool:
        """Запустить сетку ордеров вокруг текущей цены."""
        if self.engine is None:
            logger.error("GridStrategy: engine not set")
            return False

        # Проверка на уже существующую сетку
        if symbol in self._active_grids:
            logger.warning(f"Сетка для {symbol} уже активна")
            return False

        # Получаем ATR для шага
        try:
            df = self.engine.api.get_klines_dataframe(symbol, '1h', limit=50)
            atr_val = self.atr.calculate(df).iloc[-1] if not df.empty else price * 0.01
        except Exception:
            atr_val = price * 0.01

        step = atr_val * self.config['grid_step_atr']
        levels = self.config['grid_levels']
        qty_per_order = quantity * (self.config['order_qty_pct'] / 100.0)

        # Убедимся, что количество не ниже минимального
        contract_info = self.engine._contracts_info.get(symbol, {})
        min_qty = contract_info.get('minQty', 0.001)
        qty_per_order = max(qty_per_order, min_qty)

        # Формируем сетку ордеров
        orders = []
        pos_side = "LONG" if side.upper() == "BUY" else "SHORT"
        close_side = "SELL" if pos_side == "LONG" else "BUY"

        # Ордера в одну сторону (покупка/продажа) и противоположную (тейк-профит)
        try:
            for i in range(1, levels + 1):
                # Ордер на покупку (ниже рынка) для LONG или продажу (выше рынка) для SHORT
                if pos_side == "LONG":
                    order_price = price - step * i
                else:
                    order_price = price + step * i
                # Размещаем лимитный ордер
                resp = self.engine.api.place_order(
                    symbol=symbol,
                    side=side,
                    position_side=pos_side,
                    order_type='LIMIT',
                    quantity=qty_per_order,
                    price=order_price
                )
                orders.append(resp)
                logger.info(f"Grid order placed: {symbol} {side} @ {order_price}")

            # Тейк-профит ордера на противоположной стороне
            tp_side = "SELL" if pos_side == "LONG" else "BUY"
            for i in range(1, levels + 1):
                if pos_side == "LONG":
                    tp_price = price + step * i
                else:
                    tp_price = price - step * i
                resp = self.engine.api.place_order(
                    symbol=symbol,
                    side=tp_side,
                    position_side=pos_side,
                    order_type='LIMIT',
                    quantity=qty_per_order,
                    price=tp_price,
                    stop_price=tp_price   # это будет TAKE_PROFIT_LIMIT? упростим пока LIMIT для закрытия
                )
                orders.append(resp)

            self._active_grids[symbol] = {
                'side': pos_side,
                'orders': orders,
                'last_renew': time.time(),
                'base_price': price,
                'qty_per_order': qty_per_order,
                'levels': levels
            }
            return True

        except Exception as e:
            logger.error(f"Не удалось разместить сетку для {symbol}: {e}")
            return False

    def cancel_grid(self, symbol: str) -> bool:
        """Отменить все ордера сетки."""
        if symbol not in self._active_grids:
            logger.warning(f"Нет активной сетки для {symbol}")
            return False
        grid = self._active_grids[symbol]
        try:
            # Отменяем все ордера сетки
            open_orders = self.engine.api.get_open_orders(symbol)
            for o in open_orders:
                order_id = o.get('orderId')
                if order_id and any(str(o2.get('orderId')) == str(order_id) for o2 in grid['orders']):
                    self.engine.api.cancel_order(symbol, order_id)
            del self._active_grids[symbol]
            logger.info(f"Сетка для {symbol} отменена")
            return True
        except Exception as e:
            logger.error(f"Ошибка отмены сетки {symbol}: {e}")
            return False

    def renew_grid(self, symbol: str) -> bool:
        """Пересоздать сетку на новых уровнях."""
        if symbol not in self._active_grids:
            return False
        grid = self._active_grids[symbol]
        # Отменяем старую
        if not self.cancel_grid(symbol):
            return False
        # Получаем текущую цену
        try:
            ticker = self.engine.api.get_ticker(symbol)
            price = float(ticker.get('data', {}).get('lastPrice', 0))
        except Exception:
            price = grid['base_price']
        if price <= 0:
            return False
        # Позиция должна существовать
        positions = self.engine.portfolio.get_positions()
        pos = next((p for p in positions if p.symbol == symbol), None)
        if not pos:
            logger.warning(f"Нет позиции для {symbol}, сетка не обновляется")
            return False
        # Запускаем новую сетку с тем же направлением и текущим количеством
        return self.start_grid(symbol, 'BUY' if pos.side == 'LONG' else 'SELL', pos.quantity, price)

    def check_grids(self):
        """Периодическая проверка и обновление сеток (вызывать из основного цикла)."""
        now = time.time()
        for symbol in list(self._active_grids.keys()):
            grid = self._active_grids[symbol]
            if now - grid['last_renew'] > self.config['renew_interval_minutes'] * 60:
                self.renew_grid(symbol)
