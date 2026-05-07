"""
Trading Engine – coordinator.
"""
import os, sys, time, json, logging, threading
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.api import BingXAPI
from core.auth import AuthManager
from core.risk_manager import RiskManager
from core.portfolio import PortfolioManager, Position, TradeRecord
from core.scheduler import Scheduler
from core.antidetect import AntiDetect
from core.watchdog import Watchdog
from strategies.base import BaseStrategy, Signal
from indicators.base import BaseIndicator
from filters.base import BaseFilter
from ml.voting import VotingSystem
from ml.optimizer import StrategyOptimizer
from ml.market_regime import MarketRegimeDetector, MarketRegime
from core.executor import TradeExecutor
from core.sync_manager import PositionSyncManager
from core.risk_controller import RiskController
from core.signal_processor import SignalProcessor
from core.trailing_tp import TrailingTakeProfit
from core.sound_manager import SoundManager

# Новые модули рефакторинга
from core.engine_config import load_config, save_config
from core.engine_state import load_state, save_state, load_blacklist, save_blacklist
from core.engine_data import (
    discover_symbols, load_contracts_info,
    get_current_price, get_current_atr
)
from core.engine_scan import market_scan_task
from core.engine_components import init_components as engine_init_components, load_all_modules as engine_load_all_modules

logger = logging.getLogger(__name__)


class TradingEngine:
    CANDLES_DB = 'data/candles.db'
    BLACKLIST_FILE = 'data/blacklist.json'
    STATE_FILE = 'data/engine_state.json'

    def __init__(self, auth: AuthManager):
        self.auth = auth
        self.api = BingXAPI(auth)
        self.risk_manager = RiskManager()
        self.portfolio = PortfolioManager()
        self.scheduler = Scheduler()
        self.antidetect = AntiDetect()
        self.watchdog = Watchdog(restart_callback=self._on_watchdog_restart)
        self.voting = VotingSystem()
        self.optimizer = StrategyOptimizer()
        self.regime_detector = MarketRegimeDetector()

        self.sound_manager = SoundManager(profile='trader')
        self.executor = TradeExecutor(self)
        self.sync_manager = PositionSyncManager(self)
        self.risk_controller = RiskController(self)
        self.signal_processor = SignalProcessor(self)
        self.trailing_tp = TrailingTakeProfit(self)

        self.strategies: Dict[str, BaseStrategy] = {}
        self.indicators: Dict[str, BaseIndicator] = {}
        self.filters: Dict[str, BaseFilter] = {}

        self._running = False
        self._paused = False
        self._top_symbols = []
        self._blacklist = []
        self._candle_data = {}
        self._last_scan_time = 0
        self._contracts_info = {}
        self._lock = threading.Lock()
        self._recent_signals = deque(maxlen=50)
        self._strategy_pnl: Dict[str, List[float]] = {}
        self._start_time: Optional[datetime] = None

        # Параметры по умолчанию
        self.scan_interval = 60
        self.signal_threshold = 0.5
        self.max_positions = 8
        self.timeframes = ['15m', '1h', '4h']
        self.top_n_symbols = 50

        self.trailing_sl_enabled = True
        self.trailing_distance_pct = 0.5
        self.partial_close_enabled = True
        self.partial_close_pct = 50.0
        self.breakeven_enabled = True
        self.breakeven_atr_mult = 1.0
        self.slippage_timeout_sec = 10.0
        self.reinvest_profits = True

        # Внешние модули
        self.adaptive_threshold = None
        self.micro_lot_filter = None

        load_config(self)
        self._init_components()
        self._load_blacklist()
        self._load_state()

    # ---------- инициализация и конфигурация ----------
    def _init_components(self):
        engine_init_components(self)

    def load_all_modules(self):
        engine_load_all_modules(self)

    def _load_blacklist(self):
        load_blacklist(self)

    def _save_blacklist(self):
        save_blacklist(self)

    def _load_state(self):
        load_state(self)

    def _save_state(self):
        save_state(self)

    def _load_config(self):
        load_config(self)

    def _save_config(self):
        save_config(self)

    # ---------- управление ----------
    def start(self):
        if self._running:
            return
        if self.auth.demo_mode:
            logger.warning("Running in DEMO mode - no real trades")
        self._running = True
        self._paused = False
        self._start_time = datetime.now(timezone.utc)
        if not self.auth.demo_mode:
            self.sync_manager.full_sync()
        self._equity_update_task()
        self.scheduler.start()
        self.watchdog.start()
        self.risk_manager.apply_day_profile()

        # Защита депозита
        balance = self.portfolio._balance or 0
        self.risk_manager.check_low_balance(balance)

        try:
            self._discover_symbols()
            self._load_contracts_info()
        except Exception as e:
            logger.error(f"Initial symbol discovery failed: {e}")
        if not self.auth.demo_mode:
            self.risk_controller.peak_equity = self.portfolio._equity
        logger.info("Trading engine started")
        if not self.auth.demo_mode:
            threading.Thread(target=self.risk_controller.connection_monitor, daemon=True).start()
        threading.Thread(target=self._state_autosave, daemon=True).start()

    def stop(self):
        self._running = False
        self._paused = False
        self.scheduler.stop()
        self.watchdog.stop()
        self._save_state()
        logger.info("Trading engine stopped")

    def pause(self):
        self._paused = True; logger.info("Trading paused")

    def resume(self):
        self._paused = False; logger.info("Trading resumed")

    def is_paused(self) -> bool:
        return self._paused

    # ---------- обновления по расписанию ----------
    def _market_scan_task(self):
        market_scan_task(self)

    def _equity_update_task(self):
        try:
            if self.auth.demo_mode:
                self.portfolio.update_equity(1000.0, 0.0)
                self.portfolio.available_margin = 1000.0
            else:
                bal = self.api.get_balance().get('data', {}).get('balance', {})
                balance = float(bal.get('balance', 0))
                available = float(bal.get('availableMargin', balance))
                unrealized = float(bal.get('unrealizedProfit', 0))
                self.portfolio.update_equity(balance, unrealized)
                self.portfolio.available_margin = available
                self.risk_controller.update_drawdown(self.portfolio._equity)
                self.risk_controller.check_daily_limits()
        except Exception as e:
            logger.debug(f"Equity update error: {e}")

    def _sync_positions_task(self):
        self.sync_manager.background_sync()

    def _heartbeat_task(self):
        self.watchdog.heartbeat()

    def _update_weights_task(self):
        try:
            self.voting.update_weights()
        except Exception as e:
            logger.error(f"Weight update error: {e}")

    # ---------- колбэки ----------
    def _on_watchdog_restart(self):
        logger.warning("Watchdog restart triggered")
        try:
            self._discover_symbols()
            self._sync_positions_task()
        except Exception as e:
            logger.error(f"Watchdog restart error: {e}")

    def _on_night_mode_on(self):
        self.risk_manager.set_night_mode(True)
        self.antidetect.set_night_mode(True)

    def _on_night_mode_off(self):
        self.risk_manager.set_night_mode(False)
        self.antidetect.set_night_mode(False)

    def _on_session_change(self, old, new):
        logger.info(f"Session changed: {old} -> {new}")

    def _on_new_day(self):
        self.portfolio.reset_daily_pnl()
        self.risk_controller.reset_daily()

    def _state_autosave(self):
        while self._running:
            self._save_state()
            time.sleep(60)

    # ---------- данные рынка ----------
    def _discover_symbols(self):
        discover_symbols(self)

    def _load_contracts_info(self):
        load_contracts_info(self)

    def _get_current_price(self, symbol):
        return get_current_price(self, symbol)

    def _get_current_atr(self, symbol, candles_dict=None):
        return get_current_atr(self, symbol, candles_dict)

    # ---------- чёрный список ----------
    def add_to_blacklist(self, symbol, reason="manual"):
        if symbol not in self._blacklist:
            self._blacklist.append(symbol)
            self._save_blacklist()

    def remove_from_blacklist(self, symbol):
        if symbol in self._blacklist:
            self._blacklist.remove(symbol)
            self._save_blacklist()

    def get_blacklist(self):
        return self._blacklist.copy()

    # ---------- ручное управление ----------
    def manual_scan(self):
        if not self._running:
            logger.warning("Engine is not running – cannot scan")
            return
        def _scan():
            try:
                self._market_scan_task()
            except Exception as e:
                logger.error(f"Manual scan error: {e}")
        threading.Thread(target=_scan, daemon=True, name="ManualScan").start()
        logger.info("Manual scan started (async)")

    def close_position_manual(self, symbol, side, percent=None):
        try:
            if percent:
                self.api.close_position_percent(symbol, side, percent)
            else:
                self.api.close_position(symbol, side)
            self.portfolio.remove_position(symbol, side)
        except Exception as e:
            logger.error(f"Manual close failed: {e}")

    def sync_positions(self):
        self.sync_manager.full_sync()

    # ---------- обновление настроек ----------
    def update_settings(self, settings: dict):
        old_max = self.max_positions
        if 'max_positions' in settings:
            self.max_positions = int(settings['max_positions'])
        if 'scan_interval' in settings:
            self.scan_interval = int(settings['scan_interval'])
        if 'signal_threshold' in settings:
            self.signal_threshold = float(settings['signal_threshold'])
        if 'risk_per_trade' in settings:
            self.risk_manager.risk_per_trade_pct = float(settings['risk_per_trade'])
        if 'max_leverage' in settings:
            self.risk_manager.max_leverage = int(settings['max_leverage'])
        if 'risk_profile' in settings:
            self.risk_manager.set_profile(settings['risk_profile'])
        self._save_config()
        if 'max_positions' in settings and self.max_positions < old_max:
            self.sync_manager._enforce_limit()

    # ---------- статус ----------
    def get_status(self):
        balance = self.portfolio._balance or 0.0
        equity = self.portfolio._equity or balance
        unrealized = sum(p.unrealized_pnl for p in self.portfolio.get_positions())
        positions = self.portfolio.get_positions()
        return {
            'running': self._running,
            'paused': self._paused,
            'demo_mode': self.auth.demo_mode,
            'connected': self.api.is_connected,
            'ping_ms': self.api.last_ping_ms,
            'symbols_tracked': len(self._top_symbols),
            'strategies_loaded': len(self.strategies),
            'night_mode': self.scheduler.night_mode,
            'session': self.scheduler.current_session,
            'market_regime': self.regime_detector.get_current_regime().value,
            'last_scan': self._last_scan_time,
            'balance': balance,
            'equity': equity,
            'unrealized_pnl': unrealized,
            'open_positions': len(positions),
            'daily_pnl': self.portfolio.get_daily_pnl(),
            'win_rate': self.portfolio.get_win_rate(),
            'recent_signals': list(self._recent_signals),
            'strategy_weights': self.voting.get_weights(),
            'strategy_stats': self._get_strategy_stats(),
        }

    def _get_strategy_stats(self):
        stats = {}
        for name, pnl_list in self._strategy_pnl.items():
            if pnl_list:
                wins = sum(1 for p in pnl_list if p > 0)
                total = len(pnl_list)
                stats[name] = {
                    'trades': total,
                    'win_rate': (wins/total)*100 if total else 0,
                    'total_pnl': sum(pnl_list),
                    'avg_pnl': sum(pnl_list)/total if total else 0,
                    'last_3': pnl_list[-3:] if len(pnl_list)>=3 else pnl_list
                }
        return stats
