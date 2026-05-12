"""
Trading Engine – coordinator.
Исправлено: баланс v3 — массив объектов, ищем USDT.
Добавлено: диагностика сканирования, синхронный manual_scan, проверка _candle_data.
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

from core.engine_config import load_config, save_config
from core.engine_state import load_state, save_state, load_blacklist, save_blacklist
from core.engine_data import (
    discover_symbols, load_contracts_info,
    get_current_price, get_current_atr
)
from core.engine_scan import market_scan_task
from core.engine_components import init_components as engine_init_components, load_all_modules as engine_load_all_modules

logger = logging.getLogger(__name__)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


class TradingEngine:
    CANDLES_DB = 'data/candles.db'
    BLACKLIST_FILE = 'data/blacklist.json'
    STATE_FILE = 'data/engine_state.json'

    def __init__(self, auth: AuthManager):
        self.auth = auth
        self.api = BingXAPI(auth)
        self.risk_manager = RiskManager(engine=self)
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

        self.adaptive_threshold = None
        self.micro_lot_filter = None

        load_config(self)
        self._init_components()
        self._load_blacklist()
        self._load_state()

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

        balance = self.portfolio._balance or 0
        self.risk_manager.check_low_balance(balance)

        try:
            self._discover_symbols()
            self._load_contracts_info()
        except Exception as e:
            logger.error(f"Initial symbol discovery failed: {e}")
        if not self.auth.demo_mode:
            self.risk_controller.peak_equity = self.portfolio._equity

        # --- Native BingX Trailing Stop ---
        if not self.auth.demo_mode:
            try:
                from core.trailing_stop_order import NativeBingXTrailingStop
                self.native_trailing_stop = NativeBingXTrailingStop(self)
                logger.info("NativeBingXTrailingStop initialized")
            except Exception as e:
                logger.warning(f"NativeBingXTrailingStop not initialized: {e}")

        logger.info("Trading engine started")
        if not self.auth.demo_mode:
            threading.Thread(target=self.risk_controller.connection_monitor, daemon=True).start()
        threading.Thread(target=self._state_autosave, daemon=True).start()

        # После старта принудительно запускаем одно сканирование для заполнения _candle_data
        logger.info("Starting initial market scan...")
        self._market_scan_task()
        logger.info(f"Initial scan completed. _candle_data has {len(self._candle_data)} symbols")

    def stop(self):
        self._running = False
        self._paused = False
        self.scheduler.stop()
        self.watchdog.stop()
        self._save_state()

        for attr in ['adaptive_threshold', 'moonshot', 'order_guard', 'whale_shield',
                     'backup_mgr', 'github_backup', 'voice', 'stress_test',
                     'capital_alloc', 'tf_selector', 'alert_mgr',
                     'telegram', 'discord', 'web_server', 'webhook',
                     'bayes_opt', 'backtest', 'human_emulator', 'onchain',
                     'native_trailing_stop']:
            obj = getattr(self, attr, None)
            if obj is not None and hasattr(obj, 'stop'):
                try:
                    obj.stop()
                    logger.info(f"Stopped {attr}")
                except Exception as e:
                    logger.error(f"Failed to stop {attr}: {e}")

        logger.info("Trading engine stopped")

    def pause(self):
        self._paused = True
        logger.info("Trading paused")

    def resume(self):
        self._paused = False
        logger.info("Trading resumed")

    def is_paused(self) -> bool:
        return self._paused

    # ---------- обновления по расписанию ----------
    def _market_scan_task(self):
        """Вызывается планировщиком или вручную."""
        logger.info("market_scan_task called, engine._running=%s, engine._paused=%s", self._running, self._paused)
        # Не используем отдельную функцию из engine_scan, чтобы иметь прямой контроль
        # Вызываем встроенную логику, но с логами
        self._perform_scan()

    def _perform_scan(self):
        """Реальная логика сканирования, чтобы можно было вызвать синхронно."""
        if self._paused or not self._running:
            logger.debug("Scan skipped: paused or not running")
            return
        self.watchdog.heartbeat()

        if self.antidetect.should_skip_update():
            logger.debug("Scan skipped: antidetect skip")
            return

        if not self._top_symbols:
            logger.warning("No top symbols, discovering...")
            self._discover_symbols()
            self._load_contracts_info()
            if not self._top_symbols:
                logger.error("Still no symbols, aborting scan")
                return

        symbols = self.antidetect.shuffle_scan_order(self._top_symbols)
        logger.info(f"Market scan: processing {len(symbols)} symbols")

        last_hb = time.time()
        for idx, symbol in enumerate(symbols):
            if not self._running or self._paused:
                break
            if time.time() - last_hb > 30:
                self.watchdog.heartbeat()
                last_hb = time.time()
            if idx % 10 == 0:
                logger.debug(f"Scanning {idx+1}/{len(symbols)}: {symbol}")
            try:
                self._process_symbol(symbol)
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}", exc_info=True)

        self._last_scan_time = time.time()
        logger.info(f"Market scan finished, last_scan_time={self._last_scan_time}, _candle_data symbols={len(self._candle_data)}")

    def _process_symbol(self, symbol: str):
        """Обработка одного символа — перенесено из engine_scan для наглядности."""
        if symbol in self._blacklist:
            logger.debug(f"Symbol {symbol} in blacklist, skipping")
            return

        all_candles = {}
        for tf in self.timeframes:
            try:
                self.antidetect.pre_request_delay()
                df = self.api.get_klines_dataframe(symbol, tf, limit=200)
                if not df.empty:
                    all_candles[tf] = df
                    self._candle_data.setdefault(symbol, {})[tf] = df
                else:
                    logger.warning(f"Empty DataFrame for {symbol} {tf}")
            except Exception as e:
                logger.debug(f"Failed to fetch {symbol} {tf}: {e}")

        if not all_candles:
            logger.warning(f"No candle data for {symbol}, skipping")
            return

        # Определение режима
        regime = MarketRegime.UNKNOWN
        if '1h' in all_candles:
            regime = self.regime_detector.detect(all_candles['1h'])
        elif '15m' in all_candles:
            regime = self.regime_detector.detect(all_candles['15m'])
        logger.debug(f"Regime for {symbol}: {regime.value}")

        signals = []
        for name, strategy in self.strategies.items():
            if not strategy.enabled:
                continue
            # Микро-режим: оставляем только MultiTFConsensus и MicroScalper
            if self.risk_manager._current_profile == 'Micro':
                if name not in ('MultiTFConsensus', 'MicroScalper'):
                    continue
            try:
                tf_list = strategy.config.get('timeframes', self.timeframes)
                for tf in tf_list:
                    if tf not in all_candles:
                        continue
                    signal = strategy.evaluate(symbol, tf, all_candles[tf])
                    if signal and signal.action in ('BUY', 'SELL'):
                        signal.meta['strategy'] = name
                        signal.meta['timeframe'] = tf
                        signal.meta['regime'] = regime.value
                        signals.append(signal)
                        self._recent_signals.append({
                            'time': time.strftime('%H:%M:%S'),
                            'symbol': symbol,
                            'action': signal.action,
                            'confidence': signal.confidence,
                            'price': self._get_current_price(symbol),
                            'strategy': name,
                            'regime': regime.value,
                        })
                        logger.info(f"Signal from {name} on {symbol} {tf}: {signal.action} conf={signal.confidence:.2f}")
                        break
            except Exception as e:
                logger.warning(f"Strategy {name} error on {symbol}: {e}")
                strategy.record_error()

        if signals:
            combined = self.voting.evaluate_signals(signals)
            if combined and combined.confidence >= self.signal_threshold:
                logger.info(f"Combined signal: {combined.symbol} {combined.action} conf={combined.confidence:.2f}")
                self.signal_processor.process(combined, all_candles)
            else:
                logger.debug(f"Combined confidence {combined.confidence if combined else 0:.2f} < threshold {self.signal_threshold}")
        else:
            logger.debug(f"No signals for {symbol}")

    # ---------- остальные методы (без изменений) ----------
    def _equity_update_task(self):
        try:
            if self.auth.demo_mode:
                self.portfolio.update_equity(1000.0, 0.0)
                self.portfolio.available_margin = 1000.0
            else:
                response = self.api.get_balance()
                data_list = response.get('data', [])
                if not data_list or not isinstance(data_list, list):
                    logger.warning("Balance data is empty or not a list")
                    return
                usdt_info = None
                for item in data_list:
                    if item.get('asset') == 'USDT':
                        usdt_info = item
                        break
                if usdt_info is None and data_list:
                    usdt_info = data_list[0]
                if usdt_info is None:
                    return
                balance = _safe_float(usdt_info.get('balance', 0))
                available = _safe_float(usdt_info.get('availableMargin', balance))
                unrealized = _safe_float(usdt_info.get('unrealizedProfit', 0))
                self.portfolio.update_equity(balance, unrealized)
                self.portfolio.available_margin = available
                self.risk_controller.update_drawdown(self.portfolio._equity)
                self.risk_controller.check_daily_limits()
                self.risk_manager.adapt_to_market(self)
                if balance < 15.0 and not self._paused:
                    logger.critical(f"Balance critically low ({balance:.2f} USDT) – pausing trading")
                    self._paused = True
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

    def _grid_renew_task(self):
        if hasattr(self, 'strategies'):
            grid_strat = self.strategies.get('GridStrategy')
            if grid_strat and hasattr(grid_strat, 'check_grids'):
                grid_strat.check_grids()

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

    def _discover_symbols(self):
        discover_symbols(self)

    def _load_contracts_info(self):
        load_contracts_info(self)

    def _get_current_price(self, symbol):
        return get_current_price(self, symbol)

    def _get_current_atr(self, symbol, candles_dict=None):
        return get_current_atr(self, symbol, candles_dict)

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

    def manual_scan(self):
        if not self._running:
            logger.warning("Engine is not running – cannot scan")
            return

        logger.info("Manual scan started (synchronous for debugging)")
        try:
            self._perform_scan()  # прямой вызов, не в потоке
            logger.info(f"Manual scan completed. _candle_data contains {len(self._candle_data)} symbols")
            # Вывод первых символов и их таймфреймов для диагностики
            for sym in list(self._candle_data.keys())[:5]:
                logger.info(f"  {sym} timeframes: {list(self._candle_data[sym].keys())}")
        except Exception as e:
            logger.error(f"Manual scan error: {e}", exc_info=True)

    def close_position_manual(self, symbol, side, percent=None):
        try:
            if percent:
                self.api.close_position_percent(symbol, side, percent)
                positions = self.api.get_positions(symbol)
                pos = next((p for p in positions if p.get('positionSide') == side), None)
                if pos:
                    new_qty = abs(_safe_float(pos.get('positionAmt', 0)))
                    local_pos = next((p for p in self.portfolio.get_positions()
                                      if p.symbol == symbol and p.side == side), None)
                    if local_pos:
                        local_pos.quantity = new_qty
                        logger.info(f"Position {symbol} {side} partially closed, new qty: {new_qty}")
                        if local_pos.tp_price is not None and local_pos.sl_price is not None:
                            self.executor._place_tpsl_orders(symbol, side, new_qty,
                                                             local_pos.tp_price, local_pos.sl_price)
                    else:
                        logger.warning(f"Partial close: local position not found for {symbol} {side}")
                else:
                    self.portfolio.remove_position(symbol, side)
            else:
                self.api.close_position(symbol, side)
                self.portfolio.remove_position(symbol, side)
        except Exception as e:
            logger.error(f"Manual close failed: {e}")

    def sync_positions(self):
        self.sync_manager.full_sync()

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

    def optimize_strategies(self):
        if not self._candle_data:
            logger.warning("No candle data for optimization")
            return
        for name, strat in self.strategies.items():
            if strat.is_disabled():
                continue
            try:
                best_params = self.optimizer.optimize(strat, self._candle_data)
                if best_params:
                    strat.config.update(best_params)
                    logger.info(f"Optimized {name}: {best_params}")
            except Exception as e:
                logger.error(f"Optimization failed for {name}: {e}")
