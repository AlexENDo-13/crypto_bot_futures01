"""
Adaptive Trailing Stop – динамический трейлинг-стоп на основе ATR.
Подтягивает стоп-лосс при движении цены в сторону прибыли, сохраняя
минимальный отступ (ATR * multiplier) от текущего максимума (для LONG)
или минимума (для SHORT).
"""
import logging
from core.portfolio import Position

logger = logging.getLogger(__name__)

class AdaptiveTrailingStop:
    """
    Управляет трейлингом стопа по ATR.
    Параметры:
        atr_multiplier – отступ от пика в единицах ATR
        activation_pct – процент прибыли от стопа до входа для активации трейлинга
    """

    def __init__(self, engine, atr_multiplier: float = 1.5, activation_pct: float = 0.5):
        self.engine = engine
        self.atr_multiplier = atr_multiplier
        self.activation_pct = activation_pct
        # храним пиковое значение цены для каждой позиции {key: extreme_price}
        self._extreme_prices = {}

    def update(self, pos: Position, current_price: float) -> bool:
        """
        Проверяет необходимость подтяжки стопа и, если нужно,
        обновляет pos.sl_price. Возвращает True, если стоп был изменён.
        """
        if pos.sl_price is None or pos.sl_price <= 0:
            return False

        atr = self.engine._get_current_atr(pos.symbol)
        if atr <= 0:
            return False

        key = f"{pos.symbol}_{pos.side}"
        extreme = self._extreme_prices.get(key)

        # Инициализируем экстремум, если его нет
        if extreme is None:
            self._extreme_prices[key] = current_price
            return False

        # Расстояние стоп-лосса от входа (в процентах)
        sl_distance = abs(pos.entry_price - pos.sl_price) / pos.entry_price if pos.entry_price else 0.0
        activation = sl_distance * self.activation_pct

        if pos.side == "LONG":
            # Обновляем максимум, если цена выросла
            if current_price > extreme:
                self._extreme_prices[key] = current_price
            # Предполагаемый новый стоп: от текущего пика минус ATR * мультипликатор
            new_sl = self._extreme_prices[key] - atr * self.atr_multiplier
            # Активируем трейлинг только если цена прошла порог активации от входа
            if current_price >= pos.entry_price * (1 + activation):
                if new_sl > pos.sl_price and new_sl > pos.entry_price:  # стоп только выше точки входа
                    old_sl = pos.sl_price
                    pos.sl_price = new_sl
                    logger.info(f"Adaptive trailing SL for {pos.symbol} LONG: {old_sl:.6f} -> {new_sl:.6f}")
                    return True
        else:  # SHORT
            if current_price < extreme:
                self._extreme_prices[key] = current_price
            new_sl = self._extreme_prices[key] + atr * self.atr_multiplier
            if current_price <= pos.entry_price * (1 - activation):
                if new_sl < pos.sl_price and new_sl < pos.entry_price:
                    old_sl = pos.sl_price
                    pos.sl_price = new_sl
                    logger.info(f"Adaptive trailing SL for {pos.symbol} SHORT: {old_sl:.6f} -> {new_sl:.6f}")
                    return True

        return False

    def reset(self, symbol: str, side: str):
        """Сбросить экстремум для позиции (после закрытия)."""
        key = f"{symbol}_{side}"
        self._extreme_prices.pop(key, None)
