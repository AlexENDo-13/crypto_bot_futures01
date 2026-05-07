"""
Trailing Take Profit (TTP) module.
Updates TP order to lock in more profit when price moves favourably.
"""
import logging
from core.portfolio import Position

logger = logging.getLogger(__name__)


class TrailingTakeProfit:
    """Управляет трейлингом тейк‑профита для открытых позиций."""

    def __init__(self, engine):
        self.engine = engine
        # Кэш состояния трейлинга TP (чтобы не дёргать API без необходимости)
        self._cache = {}  # key: f"{symbol}_{side}" -> last_tp_price

    def update(self, pos: Position, current_price: float) -> bool:
        """
        Проверяет, можно ли подтянуть TP.
        Возвращает True, если TP был изменён.
        """
        if not pos.tp_price or pos.tp_price <= 0:
            return False

        # Трейлинг включается только после достижения уровня активации (например, 70% от TP)
        activation_pct = 0.7
        if pos.side == 'LONG':
            if current_price >= pos.entry_price + (pos.tp_price - pos.entry_price) * activation_pct:
                # Подтягиваем TP на расстояние, равное текущему расстоянию от входа до цены, но не ближе минимума
                distance = current_price - pos.entry_price
                new_tp = current_price + distance * 0.5  # половина движения добавляем к TP
                if new_tp > pos.tp_price:
                    old_tp = pos.tp_price
                    pos.tp_price = new_tp
                    logger.info(f"TTP updated for {pos.symbol} LONG: TP {old_tp:.6f} -> {new_tp:.6f}")
                    return True
        else:  # SHORT
            if current_price <= pos.entry_price - (pos.entry_price - pos.tp_price) * activation_pct:
                distance = pos.entry_price - current_price
                new_tp = current_price - distance * 0.5
                if new_tp < pos.tp_price:
                    old_tp = pos.tp_price
                    pos.tp_price = new_tp
                    logger.info(f"TTP updated for {pos.symbol} SHORT: TP {old_tp:.6f} -> {new_tp:.6f}")
                    return True
        return False

    def sync_order(self, symbol: str, pos_side: str, quantity: float, new_tp: float):
        """Обновляет TP‑ордер на бирже."""
        cache_key = f"{symbol}_{pos_side}"
        last_tp = self._cache.get(cache_key)
        if last_tp == new_tp:
            return
        try:
            close_side = 'SELL' if pos_side == 'LONG' else 'BUY'
            # Отменяем старый TP (если есть)
            orders = self.engine.api.get_open_orders(symbol)
            for o in orders:
                if o.get('positionSide') == pos_side and o.get('type') == 'TAKE_PROFIT_MARKET':
                    self.engine.api.cancel_order(symbol, o['orderId'])
            # Ставим новый
            self.engine.api.place_order(
                symbol=symbol, side=close_side, position_side=pos_side,
                order_type='TAKE_PROFIT_MARKET', quantity=quantity,
                stop_price=new_tp
            )
            self._cache[cache_key] = new_tp
            logger.info(f"Set new TTP order for {symbol} {pos_side}: {new_tp}")
        except Exception as e:
            logger.error(f"Failed to sync TTP order for {symbol}: {e}")
