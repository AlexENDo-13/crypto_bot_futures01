"""
Native BingX Trailing Stop Orders.
Размещает ордер TRAILING_STOP_MARKET, который автоматически подтягивается биржей.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class NativeBingXTrailingStop:
    """
    Управление родными трейлинг-стопами BingX.
    activation_price – цена, после которой трейлинг активируется.
    callback_rate – процент отката от максимума для активации стопа.
    """

    def __init__(self, engine):
        self.engine = engine
        self._active_trailing_stops = {}  # key: f"{symbol}_{side}" -> orderId

    def place_trailing_stop(self, symbol: str, side: str, quantity: float,
                            activation_price: float, callback_rate: float) -> Optional[str]:
        """
        Размещает трейлинг-стоп ордер. Возвращает orderId или None при ошибке.
        """
        if self.engine.auth.demo_mode:
            logger.info(f"Demo: trailing stop for {symbol} {side} placed (no API)")
            return "demo_trailing_id"

        pos_side = "LONG" if side.upper() in ("BUY", "LONG") else "SHORT"
        close_side = "SELL" if pos_side == "LONG" else "BUY"

        params = {
            'symbol': symbol,
            'side': close_side,
            'positionSide': pos_side,
            'type': 'TRAILING_STOP_MARKET',
            'quantity': quantity,
            'activationPrice': activation_price,
            'callbackRate': callback_rate  # 0.1 – 5.0 (%)
        }

        try:
            resp = self.engine.api._request('POST', '/openApi/swap/v2/trade/order', params)
            if resp.get('code') == 0:
                order_id = resp['data']['order']['orderId']
                key = f"{symbol}_{pos_side}"
                self._active_trailing_stops[key] = order_id
                logger.info(f"Trailing stop placed for {symbol} {pos_side}: activation={activation_price}, "
                            f"callback={callback_rate}%")
                return str(order_id)
            else:
                logger.error(f"Failed to place trailing stop: {resp}")
        except Exception as e:
            logger.error(f"Trailing stop error: {e}")

        return None

    def cancel_trailing_stop(self, symbol: str, side: str) -> bool:
        """Отменяет активный трейлинг-стоп для указанной стороны."""
        key = f"{symbol}_{side}"
        order_id = self._active_trailing_stops.pop(key, None)
        if not order_id:
            return False
        try:
            self.engine.api.cancel_order(symbol, order_id)
            logger.info(f"Trailing stop cancelled for {symbol} {side}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel trailing stop: {e}")
            return False

    def cancel_all(self):
        """Отменяет все трейлинг-стопы."""
        for key in list(self._active_trailing_stops.keys()):
            parts = key.split('_')
            if len(parts) == 2:
                self.cancel_trailing_stop(parts[0], parts[1])
