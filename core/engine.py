"""
Trading Engine – coordinator.
"""
import os, sys, time, json, logging, threading, pkgutil, importlib, inspect, shutil
from collections import deque
from configparser import ConfigParser
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

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

logger = logging.getLogger(__name__)

CONFIG_FILE = 'config.ini'
CONFIG_BACKUP = 'config.ini.bak'

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

        self._load_config()
        self._init_components()
        self._load_blacklist()
        self._load_state()

    def _load_config(self):
        cfg = ConfigParser()
        if os.path.exists(CONFIG_FILE):
            cfg.read(CONFIG_FILE)
            if cfg.has_section('ENGINE'):
                self.scan_interval = cfg.getint('ENGINE', 'scan_interval', fallback=60)
                self.signal_threshold = cfg.getfloat('ENGINE', 'signal_threshold', fallback=0.5)
                self.max_positions = cfg.getint('ENGINE', 'max_positions', fallback=8)
                self.timeframes = cfg.get('ENGINE', 'timeframes', fallback='15m,1h,4h').split(',')
                self.top_n_symbols = cfg.getint('ENGINE', 'top_symbols', fallback=50)
            if cfg.has_section('RISK'):
                self.risk_manager.risk_per_trade_pct = cfg.getfloat('RISK', 'risk_per_trade', fallback=2.0)
                self.risk_manager.max_leverage = cfg.getint('RISK', 'max_leverage', fallback=3)
                self.risk_manager.set_profile(cfg.get('RISK', 'profile', fallback='Adaptive'))
                if cfg.has_option('RISK', 'use_day_profile'):
                    self.risk_manager.use_day_profile = cfg.getboolean('RISK', 'use_day_profile')
                if cfg.has_option('RISK', 'kelly_enabled'):
                    self.risk_manager._kelly_enabled = cfg.getboolean('RISK', 'kelly_enabled')
                if cfg.has_option('RISK', 'kelly_winrate'):
                    self.risk_manager._kelly_winrate = cfg.getfloat('RISK', 'kelly_winrate')
                if cfg.has_option('RISK', 'kelly_avg_win_loss'):
                    self.risk_manager._kelly_avg_win_loss_ratio = cfg.getfloat('RISK', 'kelly_avg_win_loss')
            if cfg.has_section('TRADING'):
                self.trailing_sl_enabled = cfg.getboolean('TRADING', 'trailing_sl', fallback=True)
                self.trailing_distance_pct = cfg.getfloat('TRADING', 'trailing_distance_pct', fallback=0.5)
                self.partial_close_enabled = cfg.getboolean('TRADING', 'partial_close', fallback=True)
                self.partial_close_pct = cfg.getfloat('TRADING', 'partial_close_pct', fallback=50.0)
                self.breakeven_enabled = cfg.getboolean('TRADING', 'breakeven', fallback=True)
                self.breakeven_atr_mult = cfg.getfloat('TRADING', 'breakeven_atr_mult', fallback=1.0)
                self.slippage_timeout_sec = cfg.getfloat('TRADING', 'slippage_timeout', fallback=10.0)
                self.reinvest_profits = cfg.getboolean('TRADING', 'reinvest_profits', fallback=True)

    def _save_config(self):
        if os.path.exists(CONFIG_FILE):
            try: shutil.copy2(CONFIG_FILE, CONFIG_BACKUP)
            except: pass
        cfg = ConfigParser()
        if os.path.exists(CONFIG_FILE): cfg.read(CONFIG_FILE)
        if not cfg.has_section('ENGINE'): cfg.add_section('ENGINE')
        cfg.set('ENGINE', 'scan_interval', str(self.scan_interval))
        cfg.set('ENGINE', 'signal_threshold', str(self.signal_threshold))
        cfg.set('ENGINE', 'max_positions', str(self.max_positions))
        cfg.set('ENGINE', 'timeframes', ','.join(self.timeframes))
        cfg.set('ENGINE', 'top_symbols', str(self.top_n_symbols))
        if not cfg.has_section('RISK'): cfg.add_section('RISK')
        cfg.set('RISK', 'risk_per_trade', str(self.risk_manager.risk_per_trade_pct))
        cfg.set('RISK', 'max_leverage', str(self.risk_manager.max_leverage))
        cfg.set('RISK', 'profile', self.risk_manager._current_profile)
        cfg.set('RISK', 'use_day_profile', str(self.risk_manager.use_day_profile))
        cfg.set('RISK', 'kelly_enabled', str(self.risk_manager._kelly_enabled))
        cfg.set('RISK', 'kelly_winrate', str(self.risk_manager._kelly_winrate))
        cfg.set('RISK', 'kelly_avg_win_loss', str(self.risk_manager._kelly_avg_win_loss_ratio))
        if not cfg.has_section('TRADING'): cfg.add_section('TRADING')
        cfg.set('TRADING', 'trailing_sl', str(self.trailing_sl_enabled))
        cfg.set('TRADING', 'trailing_distance_pct', str(self.trailing_distance_pct))
        cfg.set('TRADING', 'partial_close', str(self.partial_close_enabled))
        cfg.set('TRADING', 'partial_close_pct', str(self.partial_close_pct))
        cfg.set('TRADING', 'breakeven', str(self.breakeven_enabled))
        cfg.set('TRADING', 'breakeven_atr_mult', str(self.breakeven_atr_mult))
        cfg.set('TRADING', 'slippage_timeout', str(self.slippage_timeout_sec))
        cfg.set('TRADING', 'reinvest_profits', str(self.reinvest_profits))
        with open(CONFIG_FILE, 'w') as f: cfg.write(f)

    def _save_state(self):
        data = {
            'daily_pnl': self.risk_controller.daily_pnl,
            'last_day': self.risk_controller.last_day,
            'strategies_disabled': self._strategies_disabled_until,
            'updated': datetime.now(timezone.utc).isoformat()
        }
        try:
            with open(self.STATE_FILE, 'w') as f: json.dump(data, f, indent=2)
        except Exception as e: logger.error(f"Save state failed: {e}")

    def _load_state(self):
        if not os.path.exists(self.STATE_FILE): return
        try:
            with open(self.STATE_FILE, 'r') as f: data = json.load(f)
            self.risk_controller.daily_pnl = data.get('daily_pnl', 0.0)
            self.risk_controller.last_day = data.get('last_day', datetime.now(timezone.utc).day)
            self._strategies_disabled_until = data.get('strategies_disabled', {})
        except Exception as e: logger.error(f"Load state failed: {e}")

    def _init_components(self):
        self.scheduler.register_callback('night_mode_on', self._on_night_mode_on)
        self.scheduler.register_callback('night_mode_off', self._on_night_mode_off)
        self.scheduler.register_callback('session_change', self._on_session_change)
        self.scheduler.register_callback('new_day', self._on_new_day)
        self.scheduler.register_task('market_scan', self.scan_interval, self._market_scan_task, enabled=True)
        self.scheduler.register_task('weight_update', 3600, self._update_weights_task, enabled=True)
        self.scheduler.register_task('equity_update', 60, self._equity_update_task, enabled=True)
        self.scheduler.register_task('position_sync', 30, self._sync_positions_task, enabled=True)
        self.scheduler.register_task('watchdog_heartbeat', 10, self._heartbeat_task, enabled=True)

    def load_all_modules(self):
        logger.info("Loading modules...")
        self.strategies = self._load_from_package('strategies', BaseStrategy)
        self.indicators = self._load_from_package('indicators', BaseIndicator)
        self.filters = self._load_from_package('filters', BaseFilter)
        for name, strategy in self.strategies.items():
            self.voting.register_strategy(name, getattr(strategy, 'weight', 1))
        logger.info(f"Loaded: {len(self.strategies)} strategies, {len(self.indicators)} indicators, {len(self.filters)} filters")

    def _load_from_package(self, package_name, base_class):
        modules = {}
        try:
            package = importlib.import_module(package_name)
            package_path = package.__path__
        except Exception as e:
            logger.error(f"Failed to import package {package_name}: {e}")
            return modules
        for _, module_name, _ in pkgutil.iter_modules(package_path):
            if module_name == 'base' or module_name.startswith('_'): continue
            full_name = f"{package_name}.{module_name}"
            try:
                mod = importlib.import_module(full_name)
            except Exception as e:
                logger.error(f"Failed to import {full_name}: {e}")
                continue
            for name, obj in inspect.getmembers(mod, inspect.isclass):
                if not issubclass(obj, base_class) or obj is base_class: continue
                if name.startswith('Base'): continue
                try:
                    instance = obj()
                    modules[getattr(instance, 'NAME', name)] = instance
                    logger.info(f"  Loaded {base_class.__name__}: {getattr(instance, 'NAME', name)}")
                except Exception as e:
                    logger.warning(f"  Failed to instantiate {name}: {e}")
        return modules

    def start(self):
        if self._running: return
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
        try:
            self._discover_symbols()
            self._load_contracts_info()
        except Exception as e:
            logger.error(f"Initial symbol discovery failed: {e}")
        # Установка пика эквити после первого обновления
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

    def pause(self): self._paused = True; logger.info("Trading paused")
    def resume(self): self._paused = False; logger.info("Trading resumed")
    def is_paused(self) -> bool: return self._paused

    def reload_modules(self):
        self.load_all_modules()
        logger.info("Modules reloaded")

    def update_settings(self, settings: dict):
        old_max = self.max_positions
        if 'max_positions' in settings: self.max_positions = int(settings['max_positions'])
        if 'scan_interval' in settings: self.scan_interval = int(settings['scan_interval'])
        if 'signal_threshold' in settings: self.signal_threshold = float(settings['signal_threshold'])
        if 'risk_per_trade' in settings: self.risk_manager.risk_per_trade_pct = float(settings['risk_per_trade'])
        if 'max_leverage' in settings: self.risk_manager.max_leverage = int(settings['max_leverage'])
        if 'risk_profile' in settings: self.risk_manager.set_profile(settings['risk_profile'])
        self._save_config()
        if 'max_positions' in settings and self.max_positions < old_max:
            self.sync_manager._enforce_limit()

    def _market_scan_task(self):
        if self._paused or not self._running: return
        self.watchdog.heartbeat()
        if self.antidetect.should_skip_update(): return
        if not self._top_symbols:
            self._discover_symbols()
            self._load_contracts_info()
        symbols = self.antidetect.shuffle_scan_order(self._top_symbols)
        last_hb = time.time()
        for symbol in symbols:
            if not self._running or self._paused: break
            if time.time() - last_hb > 30:
                self.watchdog.heartbeat()
                last_hb = time.time()
            try:
                self._process_symbol(symbol)
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
        self._last_scan_time = time.time()

    def _process_symbol(self, symbol: str):
        if symbol in self._blacklist: return
        all_candles = {}
        for tf in self.timeframes:
            try:
                self.antidetect.pre_request_delay()
                df = self.api.get_klines_dataframe(symbol, tf, limit=200)
                if not df.empty:
                    all_candles[tf] = df
                    if symbol not in self._candle_data: self._candle_data[symbol] = {}
                    self._candle_data[symbol][tf] = df
            except Exception as e:
                logger.debug(f"Failed to fetch {symbol} {tf}: {e}")
        if not all_candles: return
        regime = MarketRegime.UNKNOWN
        if '1h' in all_candles: regime = self.regime_detector.detect(all_candles['1h'])
        signals = []
        for name, strategy in self.strategies.items():
            if strategy.is_disabled(): continue
            try:
                for tf in strategy.config.get('timeframes', self.timeframes):
                    if tf not in all_candles: continue
                    signal = strategy.evaluate(symbol, tf, all_candles[tf])
                    if signal and signal.action in ('BUY', 'SELL'):
                        signal.meta['strategy'] = name
                        signal.meta['timeframe'] = tf
                        signal.meta['regime'] = regime.value
                        signals.append(signal)
                        self._recent_signals.append({
                            'time': datetime.now().strftime('%H:%M:%S'),
                            'symbol': symbol, 'action': signal.action,
                            'confidence': signal.confidence,
                            'price': self._get_current_price(symbol),
                            'strategy': name, 'regime': regime.value,
                        })
                        break
            except Exception as e:
                logger.warning(f"Strategy {name} error on {symbol}: {e}")
                strategy.record_error()
        if signals:
            combined = self.voting.evaluate_signals(signals)
            if combined and combined.confidence >= self.signal_threshold:
                self._process_signal(combined, all_candles)

    def _process_signal(self, signal: Signal, all_candles: dict):
        self.signal_processor.process(signal, all_candles)

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
                # Обновление защиты от просадки и дневных лимитов
                self.risk_controller.update_drawdown(self.portfolio._equity)
                self.risk_controller.check_daily_limits()
        except Exception as e: logger.debug(f"Equity update error: {e}")

    def _sync_positions_task(self): self.sync_manager.background_sync()
    def _heartbeat_task(self): self.watchdog.heartbeat()
    def _update_weights_task(self):
        try: self.voting.update_weights()
        except Exception as e: logger.error(f"Weight update error: {e}")

    def _on_watchdog_restart(self):
        logger.warning("Watchdog restart triggered")
        try:
            self._discover_symbols()
            self._sync_positions_task()
        except Exception as e: logger.error(f"Watchdog restart error: {e}")

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

    def _load_contracts_info(self):
        if self.auth.demo_mode:
            self._contracts_info = {s: {'minQty': 0.001, 'stepSize': 0.001} for s in self._top_symbols}
            logger.debug("Demo mode: using default contracts info")
            return
        try:
            contracts = self.api.get_contracts()
            for c in contracts:
                sym = c.get('symbol', '')
                if sym.endswith('USDT'):
                    self._contracts_info[sym] = {
                        'minQty': float(c.get('tradeMinQuantity', 0)),
                        'stepSize': float(c.get('stepSize', 0.001))
                    }
            logger.info(f"Loaded contract info for {len(self._contracts_info)} symbols")
        except Exception as e:
            logger.error(f"Failed to load contracts info: {e}")

    def _get_current_price(self, symbol):
        try:
            ticker = self.api.get_ticker(symbol)
            return float(ticker.get('data', {}).get('lastPrice', 0))
        except:
            if symbol in self._candle_data and '1h' in self._candle_data[symbol]:
                return self._candle_data[symbol]['1h']['close'].iloc[-1]
            return 0.0

    def _get_current_atr(self, symbol, candles_dict=None):
        try:
            from indicators.base import ATR
            atr_ind = ATR({'period': 14})
            data = candles_dict or self._candle_data.get(symbol, {})
            if '1h' in data:
                atr_series = atr_ind.calculate(data['1h'])
                return float(atr_series.iloc[-1]) if len(atr_series) > 0 else 0.02
        except Exception as e:
            logger.debug(f"ATR calc failed for {symbol}: {e}")
        return 0.02

    def _discover_symbols(self):
        try:
            contracts = self.api.get_contracts()
            usdt_pairs = [c for c in contracts if c.get('symbol', '').endswith('USDT')]
            usdt_pairs.sort(key=lambda x: float(x.get('volume', 0) or 0), reverse=True)
            self._top_symbols = [p['symbol'] for p in usdt_pairs[:self.top_n_symbols]
                                 if p['symbol'] not in self._blacklist]
            logger.info(f"Discovered {len(self._top_symbols)} symbols")
        except:
            self._top_symbols = ['BTC-USDT','ETH-USDT','SOL-USDT','XRP-USDT',
                                 'DOGE-USDT','ADA-USDT','AVAX-USDT','DOT-USDT']

    def add_to_blacklist(self, symbol, reason="manual"):
        if symbol not in self._blacklist:
            self._blacklist.append(symbol); self._save_blacklist()
    def remove_from_blacklist(self, symbol):
        if symbol in self._blacklist:
            self._blacklist.remove(symbol); self._save_blacklist()
    def get_blacklist(self): return self._blacklist.copy()
    def _load_blacklist(self):
        try:
            if os.path.exists(self.BLACKLIST_FILE):
                with open(self.BLACKLIST_FILE) as f:
                    self._blacklist = json.load(f).get('symbols', [])
        except: pass
    def _save_blacklist(self):
        with open(self.BLACKLIST_FILE, 'w') as f:
            json.dump({'symbols': self._blacklist, 'updated': datetime.now().isoformat()}, f, indent=2)

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
            if percent: self.api.close_position_percent(symbol, side, percent)
            else: self.api.close_position(symbol, side)
            self.portfolio.remove_position(symbol, side)
        except Exception as e: logger.error(f"Manual close failed: {e}")

    def sync_positions(self):
        self.sync_manager.full_sync()

    def get_status(self):
        balance = self.portfolio._balance or 0.0
        equity = self.portfolio._equity or balance
        unrealized = sum(p.unrealized_pnl for p in self.portfolio.get_positions())
        positions = self.portfolio.get_positions()
        return {
            'running': self._running, 'paused': self._paused,
            'demo_mode': self.auth.demo_mode, 'connected': self.api.is_connected,
            'ping_ms': self.api.last_ping_ms, 'symbols_tracked': len(self._top_symbols),
            'strategies_loaded': len(self.strategies), 'night_mode': self.scheduler.night_mode,
            'session': self.scheduler.current_session,
            'market_regime': self.regime_detector.get_current_regime().value,
            'last_scan': self._last_scan_time, 'balance': balance, 'equity': equity,
            'unrealized_pnl': unrealized, 'open_positions': len(positions),
            'daily_pnl': self.portfolio.get_daily_pnl(), 'win_rate': self.portfolio.get_win_rate(),
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
