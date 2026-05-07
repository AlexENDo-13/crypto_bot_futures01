"""
Moonshot mode – allocates a small portion of capital to high‑volatility coins
with tight risk controls for potential explosive gains.
"""
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

class MoonshotTrader:
    """Управляет агрессивным микро‑портфелем."""

    def __init__(self, engine, capital_pct: float = 10.0, max_risk_pct: float = 1.0,
                 scan_interval: int = 300):
        self.engine = engine
        self.capital_pct = capital_pct          # доля от баланса на moonshot
        self.max_risk_pct = max_risk_pct        # риск на одну сделку внутри moonshot капитала
        self.scan_interval = scan_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("MoonshotTrader started (capital %.1f%%, scan every %ds)", self.capital_pct, self.scan_interval)

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                self._scan()
            except Exception as e:
                logger.error(f"Moonshot scan error: {e}")
            time.sleep(self.scan_interval)

    def _scan(self):
        # Получаем топ‑10 самых волатильных монет за последние 24 часа
        try:
            contracts = self.engine.api.get_contracts()
        except Exception:
            return
        # Сортируем по изменению цены за 24ч (если есть поле priceChangePercent)
        candidates = []
        for c in contracts:
            symbol = c.get('symbol', '')
            if not symbol.endswith('USDT'):
                continue
            change = float(c.get('priceChangePercent', 0) or 0)
            if abs(change) > 10:  # только монеты с сильным движением
                candidates.append((symbol, change))
        if not candidates:
            return

        # Выбираем топ‑3 по модулю изменения
        candidates.sort(key=lambda x: abs(x[1]), reverse=True)
        top_moons = candidates[:3]

        # Определяем капитал moonshot
        balance = self.engine.portfolio._balance or 0.0
        if balance <= 0:
            return
        moonshot_capital = balance * (self.capital_pct / 100.0)
        # Не больше 5% от баланса на одну монету
        max_per_coin = moonshot_capital / len(top_moons)

        for symbol, change in top_moons:
            # Не входим, если уже есть позиция по этому символу (любая)
            if any(p.symbol == symbol for p in self.engine.portfolio.get_positions()):
                continue
            price = self.engine._get_current_price(symbol)
            if price <= 0:
                continue
            atr = self.engine._get_current_atr(symbol)
            if atr == 0:
                continue

            # Определяем направление: если цена выросла >10% – шортим, если упала – лонгуем (контр-тренд)
            if change > 10:
                action = 'SELL'
                sl = price + atr * 1.0
                tp = price - atr * 2.0
            else:
                action = 'BUY'
                sl = price - atr * 1.0
                tp = price + atr * 2.0

            # Размер позиции: риск 1% от moonshot_capital на сделку
            risk_amount = moonshot_capital * (self.max_risk_pct / 100.0)
            quantity = risk_amount / atr if atr != 0 else 0
            # Проверяем мин. количество
            min_qty = self.engine._contracts_info.get(symbol, {}).get('minQty', 0.001)
            if quantity < min_qty:
                quantity = min_qty
            # Проверяем, чтобы стоимость позиции не превышала max_per_coin
            while (quantity * price) > max_per_coin and quantity > min_qty:
                quantity -= min_qty

            if quantity <= 0:
                continue

            # Исполняем через стандартный executor (симуляция, если демо)
            from strategies.base import Signal
            signal = Signal(symbol=symbol, action=action, confidence=0.9,
                            meta={'strategy': 'Moonshot', 'timeframe': '1h'})
            try:
                self.engine.executor.execute(signal, price, quantity, leverage=2,
                                             tp_price=tp, sl_price=sl)
                logger.info(f"Moonshot trade: {symbol} {action} qty={quantity} @ {price}")
            except Exception as e:
                logger.error(f"Moonshot execution failed for {symbol}: {e}")
