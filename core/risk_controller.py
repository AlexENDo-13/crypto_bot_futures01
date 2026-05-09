"""
Risk Controller: daily loss/profit limits, liquidity, spread, VaR, correlation-based protection,
multi-level drawdown protection, and auto-rebalance when free margin is low.
"""
import logging
import time
import threading
from datetime import datetime, timezone

import numpy as np

logger = logging.getLogger(__name__)

class RiskController:
    def __init__(self, engine):
        self.engine = engine
        # Дневные лимиты
        self.daily_loss_limit_pct = 5.0
        self.daily_profit_limit_pct = 0.0     # 0 = без ограничения
        self.spread_max_pct = 1.0
        self.auto_pause_loss = True
        self.auto_pause_profit = False
        self.connection_check_interval = 30.0
        self._last_connection_ok = True
        self.daily_pnl = 0.0
        self.last_day = datetime.now(timezone.utc).day

        # Сессионные лимиты
        self.session_loss_limit_pct = 2.0
        self.session_pause_hours = 2.0
        self._session_start_time = time.time()
        self._session_pnl = 0.0
        self._paused_until = None

        # Автоосвобождение маржи
        self.auto_rebalance = True
        self.rebalance_target_free_pct = 10.0

        # === Многоуровневая защита от просадки ===
        self.drawdown_enabled = True
        self.peak_equity = 0.0                # исторический максимум эквити
        self.drawdown_pct = 0.0               # текущая просадка в %
        # Уровни (адаптированы под SmartTurbo)
        self.dd_level1 = 5.0                  # снизить риск до Conservative
        self.dd_level2 = 10.0                 # закрыть все позиции + пауза 30 минут
        self.dd_level3 = 15.0                 # аварийный локдаун до нового дня
        self._emergency_lock = False
        self._dd_pause_until = 0.0

        # Корреляционный фильтр
        self.max_correlation_positions = 2     # максимум коррелирующих позиций
        self.correlation_threshold = 0.7      # порог корреляции Пирсона
        self._correlation_cache = {}

    # ------------------------------------------------------------------
    def reset_daily(self):
        now = datetime.now(timezone.utc)
        if now.day != self.last_day:
            self.daily_pnl = 0.0
            self.last_day = now.day
            self._session_pnl = 0.0
            self._session_start_time = time.time()
            self._paused_until = None
            self._emergency_lock = False
            self._dd_pause_until = 0.0
            self.engine._paused = False
            logger.info("Daily PnL reset")

    # ------------------------------------------------------------------
    def update_drawdown(self, current_equity: float):
        """Обновляет пик и текущую просадку, запускает защиту при превышении уровней."""
        if not self.drawdown_enabled:
            return

        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

        if self.peak_equity > 0:
            self.drawdown_pct = (self.peak_equity - current_equity) / self.peak_equity * 100.0
        else:
            self.drawdown_pct = 0.0

        # Уровень 3 – аварийный локдаун
        if self.drawdown_pct >= self.dd_level3 and not self._emergency_lock:
            self._emergency_lock = True
            logger.critical(f"EMERGENCY LOCKDOWN: drawdown {self.drawdown_pct:.1f}% ≥ {self.dd_level3}%")
            self._close_all_positions()
            self.engine._paused = True

        # Уровень 2 – закрыть всё и пауза
        elif self.drawdown_pct >= self.dd_level2 and not self._dd_pause_until:
            logger.warning(f"DRAWDOWN LEVEL 2: {self.drawdown_pct:.1f}%. Closing all positions, pause 30 min")
            self._close_all_positions()
            self._dd_pause_until = time.time() + 1800.0  # 30 минут
            self.engine._paused = True

        # Уровень 1 – снижение риска
        elif self.drawdown_pct >= self.dd_level1:
            if self.engine.risk_manager._current_profile != 'Conservative':
                logger.info(f"DRAWDOWN LEVEL 1: {self.drawdown_pct:.1f}%. Switching to Conservative risk")
                self.engine.risk_manager.set_profile('Conservative')

    def check_daily_limits(self):
        # Если аварийный локдаун – не разблокируем до нового дня
        if self._emergency_lock:
            if not self.engine._paused:
                self.engine._paused = True
            return

        # Проверка паузы второго уровня
        if self._dd_pause_until and time.time() < self._dd_pause_until:
            if not self.engine._paused:
                self.engine._paused = True
            return
        elif self._dd_pause_until and time.time() >= self._dd_pause_until:
            self._dd_pause_until = 0.0
            self.engine._paused = False
            logger.info("Drawdown level 2 pause ended")

        # Сессионный лимит
        if self._paused_until and time.time() < self._paused_until:
            if not self.engine._paused:
                self.engine._paused = True
            return
        elif self._paused_until and time.time() >= self._paused_until:
            self._paused_until = None
            self.engine._paused = False
            self._session_pnl = 0.0
            self._session_start_time = time.time()
            logger.info("Session pause ended, trading resumed")

        balance = self.engine.portfolio._balance or 0.0
        if balance <= 0:
            return

        loss_ratio = abs(self.daily_pnl) / balance
        if self.auto_pause_loss and self.daily_loss_limit_pct > 0 and loss_ratio >= self.daily_loss_limit_pct / 100.0:
            if not self.engine._paused:
                self.engine._paused = True
                logger.warning(f"Daily loss limit reached ({self.daily_loss_limit_pct}%), pausing until next day")

        session_loss_ratio = abs(self._session_pnl) / balance
        if self.session_loss_limit_pct > 0 and session_loss_ratio >= self.session_loss_limit_pct / 100.0:
            if not self.engine._paused:
                self.engine._paused = True
                self._paused_until = time.time() + self.session_pause_hours * 3600
                logger.warning(f"Session loss limit reached ({self.session_loss_limit_pct}%), pausing for {self.session_pause_hours}h")

        if self.auto_pause_profit and self.daily_profit_limit_pct > 0 and self.daily_pnl > 0:
            profit_ratio = self.daily_pnl / balance
            if profit_ratio >= self.daily_profit_limit_pct / 100.0:
                if not self.engine._paused:
                    self.engine._paused = True
                    logger.warning(f"Daily profit limit reached ({self.daily_profit_limit_pct}%), pausing")

    def update_daily_pnl(self, trade_pnl: float):
        self.daily_pnl += trade_pnl
        self._session_pnl += trade_pnl

    # ------------------------------------------------------------------
    def pre_trade_check(self, symbol: str, signal, all_candles: dict, quantity: float, price: float):
        """Предторговая проверка: спред, корреляция, VaR, маржа."""
        if self._emergency_lock:
            return False, "emergency lock"

        # Проверка спреда
        if self.spread_max_pct > 0:
            try:
                depth = self.engine.api.get_depth(symbol, limit=5)
                asks = depth.get('data', {}).get('asks', [])
                bids = depth.get('data', {}).get('bids', [])
                if asks and bids:
                    best_ask = float(asks[0][0])
                    best_bid = float(bids[0][0])
                    spread_pct = (best_ask - best_bid) / best_bid * 100
                    if spread_pct > self.spread_max_pct:
                        logger.info(f"Spread {spread_pct:.2f}% > {self.spread_max_pct}%, skipping {symbol}")
                        return False, "spread too wide"
            except Exception as e:
                logger.debug(f"Spread check failed: {e}")

        # Проверка корреляции с уже открытыми позициями
        positions = self.engine.portfolio.get_positions()
        if positions and self.max_correlation_positions > 0:
            correlated_count = 0
            for pos in positions:
                corr = self._get_pair_correlation(symbol, pos.symbol, all_candles)
                if abs(corr) > self.correlation_threshold:
                    correlated_count += 1
                    if correlated_count >= self.max_correlation_positions:
                        logger.info(f"Correlation filter: {symbol} blocked (too many correlated positions)")
                        return False, "correlation limit"

        # VaR
        try:
            var_amount = self._calculate_var(symbol, quantity, price)
            free_margin = self.engine.portfolio.available_margin or self._get_free_margin()
            if var_amount > free_margin * 0.05:
                logger.info(f"VaR too high ({var_amount:.2f}), skipping")
                return False, "VaR limit"
        except Exception:
            pass

        # Автоосвобождение маржи при необходимости
        if self.auto_rebalance:
            free_margin = self.engine.portfolio.available_margin or self._get_free_margin()
            required_margin = (quantity * price) / (self.engine.risk_manager.max_leverage or 1)
            if free_margin < required_margin:
                if not self._free_up_margin(required_margin):
                    logger.info(f"Not enough free margin ({free_margin:.2f}) and cannot free up, skipping")
                    return False, "insufficient margin"

        return True, "ok"

    # ------------------------------------------------------------------
    def connection_monitor(self):
        """Фоновый поток: переподключение при обрыве."""
        while self.engine._running:
            try:
                self.engine.api.ping()
                if not self._last_connection_ok:
                    logger.info("Connection restored, resuming")
                    self._last_connection_ok = True
                    if not self._emergency_lock:
                        self.engine._paused = False
                    self.engine.sync_manager.full_sync()
            except Exception:
                if self._last_connection_ok:
                    logger.warning("Connection lost, pausing...")
                    self._last_connection_ok = False
                    self.engine._paused = True
                    self.engine._save_state()

            if not self._last_connection_ok:
                for _ in range(int(self.connection_check_interval / 5)):
                    time.sleep(5)
                    try:
                        self.engine.api.ping()
                        logger.info("Connection restored after retry, resuming")
                        self._last_connection_ok = True
                        if not self._emergency_lock:
                            self.engine._paused = False
                        self.engine.sync_manager.full_sync()
                        break
                    except Exception:
                        pass
            else:
                time.sleep(self.connection_check_interval)

    # ------------------------------------------------------------------
    def _close_all_positions(self):
        """Экстренное закрытие всех позиций по рынку."""
        for pos in self.engine.portfolio.get_positions():
            try:
                self.engine.api.close_position(pos.symbol, pos.side)
                logger.warning(f"Emergency close: {pos.symbol} {pos.side}")
            except Exception as e:
                logger.error(f"Emergency close failed for {pos.symbol}: {e}")
        self.engine.portfolio.clear()

    def _get_free_margin(self):
        try:
            bal = self.engine.api.get_balance().get('data', {}).get('balance', {})
            return float(bal.get('availableMargin', 0))
        except Exception:
            return 0.0

    def _calculate_var(self, symbol, quantity, price):
        atr = self.engine._get_current_atr(symbol)
        return quantity * price * (atr / price) * 1.645

    def _free_up_margin(self, required_margin: float) -> bool:
        positions = self.engine.portfolio.get_positions()
        if not positions:
            return False
        positions.sort(key=lambda p: p.unrealized_pnl)
        freed = 0.0
        for pos in positions:
            if freed >= required_margin:
                break
            try:
                close_qty = pos.quantity * 0.5
                if close_qty <= 0:
                    continue
                logger.info(f"Auto-rebalance: closing 50% of {pos.symbol} {pos.side} to free margin")
                self.engine.api.close_position(pos.symbol, pos.side, close_qty)
                pos.quantity -= close_qty
                if pos.quantity <= 0:
                    self.engine.portfolio.remove_position(pos.symbol, pos.side)
                freed += (close_qty * pos.entry_price) / max(pos.leverage, 1)
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Auto-rebalance failed for {pos.symbol}: {e}")
        free_margin = self.engine.portfolio.available_margin or self._get_free_margin()
        return free_margin >= required_margin

    def _get_pair_correlation(self, sym1: str, sym2: str, all_candles: dict) -> float:
        """Рассчитывает корреляцию между двумя символами по 1h свечам (последние 50)."""
        if sym1 == sym2:
            return 1.0
        key = f"{sym1}-{sym2}"
        if key in self._correlation_cache:
            return self._correlation_cache[key]
        try:
            # Получаем данные из переданного словаря all_candles
            data1 = all_candles.get(sym1, {}).get('1h')
            data2 = all_candles.get(sym2, {}).get('1h')
            if data1 is None or data2 is None:
                return 0.0
            closes1 = data1['close'].values[-50:]
            closes2 = data2['close'].values[-50:]
            if len(closes1) < 2 or len(closes2) < 2:
                return 0.0
            # Выравниваем длину
            min_len = min(len(closes1), len(closes2))
            closes1 = closes1[-min_len:]
            closes2 = closes2[-min_len:]
            corr = np.corrcoef(closes1, closes2)[0, 1]
            if np.isnan(corr):
                corr = 0.0
            self._correlation_cache[key] = corr
            return corr
        except Exception as e:
            logger.debug(f"Correlation calculation failed for {sym1}/{sym2}: {e}")
            return 0.0
