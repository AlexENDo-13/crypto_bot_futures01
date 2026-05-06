"""
Risk Controller: daily loss/profit limits, liquidity, spread, VaR, on-chain,
and auto-rebalance when free margin is low.
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
        # Параметры (можно переопределить через конфиг)
        self.daily_loss_limit_pct = 5.0       # 5% депозита
        self.daily_profit_limit_pct = 0.0     # 0 = без ограничения
        self.spread_max_pct = 1.0             # макс. спред для входа
        self.min_volume_ratio = 0.7           # ликвидность (быстрая проверка, не фильтр)
        self.auto_pause_loss = True
        self.auto_pause_profit = False        # прибыль не ограничиваем
        self.connection_check_interval = 30.0
        self._last_connection_ok = True
        self.daily_pnl = 0.0
        self.last_day = datetime.now(timezone.utc).day

        # Автоосвобождение маржи
        self.auto_rebalance = True             # включить автоматическое закрытие части позиций при нехватке маржи
        self.rebalance_target_free_pct = 10.0  # после ребаланса свободная маржа должна составлять 10% от баланса

        # === FIX 10: Session loss limit ===
        self.session_loss_limit_pct = 2.0      # 2% за сессию (4 часа)
        self.session_pause_hours = 2.0         # пауза 2 часа
        self._session_start_time = time.time()
        self._session_pnl = 0.0
        self._paused_until = None

    # ------------------------------------------------------------------
    # Ежедневный сброс
    # ------------------------------------------------------------------
    def reset_daily(self):
        now = datetime.now(timezone.utc)
        if now.day != self.last_day:
            self.daily_pnl = 0.0
            self.last_day = now.day
            self._session_pnl = 0.0
            self._session_start_time = time.time()
            self._paused_until = None
            self.engine._paused = False
            logger.info("Daily PnL reset")

    # ------------------------------------------------------------------
    # Проверка дневных лимитов
    # ------------------------------------------------------------------
    def check_daily_limits(self):
        """Если лимит достигнут, приостанавливает торговлю."""
        # Проверяем сессионный лимит
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

        # === FIX: Session loss limit check ===
        session_loss_ratio = abs(self._session_pnl) / balance
        if self.session_loss_limit_pct > 0 and session_loss_ratio >= self.session_loss_limit_pct / 100.0:
            if not self.engine._paused:
                self.engine._paused = True
                self._paused_until = time.time() + self.session_pause_hours * 3600
                logger.warning(f"Session loss limit reached ({self.session_loss_limit_pct}%), "
                              f"pausing for {self.session_pause_hours}h until {datetime.fromtimestamp(self._paused_until)}")

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
    # Предторговая проверка (спред, ликвидность, VaR, маржа)
    # ------------------------------------------------------------------
    def pre_trade_check(self, symbol: str, signal, all_candles: dict, quantity: float, price: float):
        """
        Возвращает (разрешено: bool, причина: str)
        """
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

        # Проверка ликвидности (быстрая)
        if self.min_volume_ratio > 0:
            try:
                vol_ratio = self._check_liquidity(symbol, all_candles)
                if vol_ratio is not None and vol_ratio < self.min_volume_ratio:
                    logger.info(f"Low liquidity for {symbol}, skipping")
                    return False, "low liquidity"
            except Exception:
                pass

        # VaR
        try:
            var_amount = self._calculate_var(symbol, quantity, price)
            free_margin = self.engine.portfolio.available_margin or self._get_free_margin()
            if var_amount > free_margin * 0.05:
                logger.info(f"VaR too high ({var_amount:.2f}), skipping")
                return False, "VaR limit"
        except Exception:
            pass

        # Проверка доступной маржи и авто-ребаланс
        if self.auto_rebalance:
            free_margin = self.engine.portfolio.available_margin or self._get_free_margin()
            required_margin = (quantity * price) / 2   # примерная оценка с плечом 2
            if free_margin < required_margin:
                # Пытаемся высвободить часть маржи, закрывая наименее перспективные позиции
                if not self._free_up_margin(required_margin):
                    logger.info(f"Not enough free margin ({free_margin:.2f}) and cannot free up, skipping")
                    return False, "insufficient margin"

        return True, "ok"

    # ------------------------------------------------------------------
    # Ончейн-фильтр (заглушка, реальный вызов будет из signal_processor)
    # ------------------------------------------------------------------
    def check_onchain(self, symbol: str) -> bool:
        try:
            from filters.onchain_filter import OnChainFilter
            return True
        except ImportError:
            return True

    # ------------------------------------------------------------------
    # Мониторинг соединения
    # ------------------------------------------------------------------
    def connection_monitor(self):
        """Фоновый поток: переподключение при обрыве."""
        while self.engine._running:
            try:
                self.engine.api.ping()
                if not self._last_connection_ok:
                    logger.info("Connection restored, resuming")
                    self._last_connection_ok = True
                    self.engine._paused = False
                    self.engine.sync_manager.full_sync()
            except Exception:
                if self._last_connection_ok:
                    logger.warning("Connection lost, pausing...")
                    self._last_connection_ok = False
                    self.engine._paused = True
                    self.engine._save_state()

            if not self._last_connection_ok:
                # Пытаемся восстановить соединение каждые 5 сек
                for _ in range(int(self.connection_check_interval / 5)):
                    time.sleep(5)
                    try:
                        self.engine.api.ping()
                        logger.info("Connection restored after retry, resuming")
                        self._last_connection_ok = True
                        self.engine._paused = False
                        self.engine.sync_manager.full_sync()
                        break
                    except Exception:
                        pass
            else:
                time.sleep(self.connection_check_interval)

    # ------------------------------------------------------------------
    # Вспомогательные
    # ------------------------------------------------------------------
    def _get_free_margin(self):
        try:
            bal = self.engine.api.get_balance().get('data', {}).get('balance', {})
            return float(bal.get('availableMargin', 0))
        except Exception:
            return 0.0

    def _check_liquidity(self, symbol, candles_dict):
        if '1h' not in candles_dict:
            return None
        df = candles_dict['1h']
        if len(df) < 20:
            return None
        recent_vol = df['volume'].iloc[-5:].mean()
        avg_vol = df['volume'].iloc[-20:].mean()
        return recent_vol / avg_vol if avg_vol > 0 else 1.0

    def _calculate_var(self, symbol, quantity, price):
        atr = self.engine._get_current_atr(symbol)
        return quantity * price * (atr / price) * 1.645  # 95% VaR

    def _free_up_margin(self, required_margin: float) -> bool:
        """Автоматически закрывает часть позиции, чтобы освободить маржу."""
        positions = self.engine.portfolio.get_positions()
        if not positions:
            return False

        # Сортируем позиции по PnL (от худшей к лучшей) – закрываем часть самой убыточной или наименее прибыльной
        positions.sort(key=lambda p: p.unrealized_pnl)
        freed = 0.0
        for pos in positions:
            if freed >= required_margin:
                break
            # Закрываем 50% позиции
            try:
                close_qty = pos.quantity * 0.5
                if close_qty <= 0:
                    continue
                logger.info(f"Auto-rebalance: closing 50% of {pos.symbol} {pos.side} to free margin")
                self.engine.api.close_position(pos.symbol, pos.side, close_qty)
                # Обновляем локальный объект позиции
                pos.quantity -= close_qty
                if pos.quantity <= 0:
                    self.engine.portfolio.remove_position(pos.symbol, pos.side)
                freed += (close_qty * pos.entry_price) / pos.leverage  # примерный возврат маржи
                time.sleep(0.5)  # небольшая задержка, чтобы не заспамить API
            except Exception as e:
                logger.error(f"Auto-rebalance failed for {pos.symbol}: {e}")

        # Проверяем, достаточно ли теперь свободной маржи
        free_margin = self.engine.portfolio.available_margin or self._get_free_margin()
        return free_margin >= required_margin
