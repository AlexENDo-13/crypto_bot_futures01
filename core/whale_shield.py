"""
Whale Shield – автоматическая защита от крупных манипуляций.
Обнаруживает аномальные объёмы в стакане и ленте сделок,
закрывает или переводит позицию в безубыток.
Исправлено: расчёт max_order_btc через реальную цену BTC, а не фиксированные 50000.
Добавлен более точный порог для больших ордеров относительно среднего объёма стакана.
"""
import logging
import time
import threading
from configparser import ConfigParser
from datetime import datetime, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Значения по умолчанию, переопределяются из [WHALE] в config.ini
DEPTH_THRESHOLD_MULT = 3.0
BIG_SINGLE_ORDER_BTC = 5.0           # снижено для чувствительности на малых парах
TRADE_VOLUME_SPIKE_MULT = 20
FULL_CLOSE_THRESHOLD_BTC = 100
CHECK_INTERVAL_SECONDS = 10
ALERT_COOLDOWN_MINUTES = 5
WARMUP_BARS = 10                     # первые 10 наблюдений только накапливаем

# Пороги шкалы угроз (0-10)
THREAT_EMERGENCY = 8
THREAT_PARTIAL = 5
THREAT_BREAKEVEN = 3

class WhaleShield:
    """Обнаруживает вход крупных игроков и немедленно защищает позиции."""

    def __init__(self, engine):
        self.engine = engine
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._avg_depth_volumes: Dict[str, float] = {}
        self._avg_trade_volumes: Dict[str, float] = {}
        self._last_alert_time: Dict[str, float] = {}
        self._depth_history: Dict[str, list] = {}
        self._trade_history: Dict[str, list] = {}
        self._load_config()

    def _load_config(self):
        """Читает параметры из config.ini, если файл существует."""
        try:
            cfg = ConfigParser()
            cfg.read('config.ini')
            if cfg.has_section('WHALE'):
                global DEPTH_THRESHOLD_MULT, BIG_SINGLE_ORDER_BTC, TRADE_VOLUME_SPIKE_MULT
                global FULL_CLOSE_THRESHOLD_BTC, CHECK_INTERVAL_SECONDS, ALERT_COOLDOWN_MINUTES
                DEPTH_THRESHOLD_MULT = cfg.getfloat('WHALE', 'depth_threshold_mult', fallback=DEPTH_THRESHOLD_MULT)
                BIG_SINGLE_ORDER_BTC = cfg.getfloat('WHALE', 'big_single_order_btc', fallback=BIG_SINGLE_ORDER_BTC)
                TRADE_VOLUME_SPIKE_MULT = cfg.getfloat('WHALE', 'trade_volume_spike_mult', fallback=TRADE_VOLUME_SPIKE_MULT)
                FULL_CLOSE_THRESHOLD_BTC = cfg.getfloat('WHALE', 'full_close_threshold_btc', fallback=FULL_CLOSE_THRESHOLD_BTC)
                CHECK_INTERVAL_SECONDS = cfg.getint('WHALE', 'scan_interval', fallback=CHECK_INTERVAL_SECONDS)
                ALERT_COOLDOWN_MINUTES = cfg.getint('WHALE', 'alert_cooldown_min', fallback=ALERT_COOLDOWN_MINUTES)
                logger.info("WhaleShield config loaded from config.ini")
        except Exception as e:
            logger.warning(f"Could not load WhaleShield config: {e}")

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="WhaleShield")
        self._thread.start()
        logger.info("WhaleShield started (check every %ds)", CHECK_INTERVAL_SECONDS)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self):
        while self._running:
            try:
                self._check_open_positions()
            except Exception as e:
                logger.error(f"WhaleShield error: {e}")
            time.sleep(CHECK_INTERVAL_SECONDS)

    def _check_open_positions(self):
        if self.engine.auth.demo_mode:
            return
        positions = self.engine.portfolio.get_positions()
        if not positions:
            return

        for pos in positions:
            try:
                self._protect_position(pos)
            except Exception as e:
                logger.debug(f"WhaleShield check failed for {pos.symbol}: {e}")

    def _protect_position(self, pos):
        symbol = pos.symbol
        now = time.time()

        # Сбор данных через API движка
        try:
            depth = self.engine.api.get_depth(symbol, limit=20)
            ticker = self.engine.api.get_ticker(symbol)
        except Exception as e:
            logger.debug(f"WhaleShield cannot fetch data for {symbol}: {e}")
            return

        # Расчёт объёмов стакана
        asks_vol = sum(float(a[1]) for a in depth.get('data', {}).get('asks', []))
        bids_vol = sum(float(b[1]) for b in depth.get('data', {}).get('bids', []))
        total_depth_vol = asks_vol + bids_vol

        # Инициализация истории
        if symbol not in self._depth_history:
            self._depth_history[symbol] = []
        self._depth_history[symbol].append(total_depth_vol)
        if len(self._depth_history[symbol]) > 30:
            self._depth_history[symbol].pop(0)

        if symbol not in self._trade_history:
            self._trade_history[symbol] = []
        last_qty = float(ticker.get('data', {}).get('volume', 0))
        self._trade_history[symbol].append(last_qty)
        if len(self._trade_history[symbol]) > 30:
            self._trade_history[symbol].pop(0)

        # Warm‑up: нужно не менее WARMUP_BARS наблюдений для каждого типа
        if len(self._depth_history[symbol]) < WARMUP_BARS or len(self._trade_history[symbol]) < WARMUP_BARS:
            return

        # Средние значения за последние 10 наблюдений
        self._avg_depth_volumes[symbol] = sum(self._depth_history[symbol][-10:]) / 10
        self._avg_trade_volumes[symbol] = sum(self._trade_history[symbol][-10:]) / 10

        # --- Оценка аномалии (единая шкала 0-10) ---
        threat_score = 0

        # 1. Аномальный объём стакана
        avg_depth = self._avg_depth_volumes.get(symbol, 1)
        if avg_depth > 0 and total_depth_vol > avg_depth * DEPTH_THRESHOLD_MULT:
            threat_score += 2
            logger.info(f"WhaleShield: depth spike on {symbol} ({total_depth_vol:.1f} vs avg {avg_depth:.1f})")

        # 2. Крупный одиночный ордер в стакане
        max_bid_qty = max((float(b[1]) for b in depth.get('data', {}).get('bids', [])), default=0)
        max_ask_qty = max((float(a[1]) for a in depth.get('data', {}).get('asks', [])), default=0)
        price = self.engine._get_current_price(symbol) or 1
        # Получаем реальную цену BTC для конвертации в BTC-эквивалент
        btc_price = self.engine._get_current_price('BTC-USDT') or 50000
        if btc_price <= 0:
            btc_price = 50000
        max_order_btc = (max(max_bid_qty, max_ask_qty) * price) / btc_price
        if max_order_btc > BIG_SINGLE_ORDER_BTC:
            threat_score += 3
            logger.warning(f"WhaleShield: single giant order on {symbol} ({max_order_btc:.1f} BTC eq.)")

        # 3. Всплеск объёма сделок
        avg_trade = self._avg_trade_volumes.get(symbol, 1)
        if avg_trade > 0 and last_qty > avg_trade * TRADE_VOLUME_SPIKE_MULT:
            threat_score += 1
            logger.info(f"WhaleShield: trade volume spike on {symbol} ({last_qty} vs avg {avg_trade})")

        # 4. Критический уровень – полное закрытие при гигантском ордере
        if max_order_btc > FULL_CLOSE_THRESHOLD_BTC:
            threat_score = 10

        if threat_score == 0:
            return

        # Проверка кулдауна на спам алертами
        last_alert = self._last_alert_time.get(symbol, 0)
        if now - last_alert < ALERT_COOLDOWN_MINUTES * 60 and threat_score < THREAT_EMERGENCY:
            return

        self._last_alert_time[symbol] = now

        # --- Реакция ---
        if threat_score >= THREAT_EMERGENCY:
            logger.critical(f"WhaleShield: EMERGENCY CLOSE {pos.symbol} {pos.side} (score={threat_score})")
            try:
                self.engine.api.close_position(pos.symbol, pos.side)
                self.engine.portfolio.remove_position(pos.symbol, pos.side)
                if hasattr(self.engine, 'telegram'):
                    self.engine.telegram.send_message(f"🚨 WhaleShield экстренно закрыл {symbol} {pos.side}")
            except Exception as e:
                logger.error(f"WhaleShield emergency close failed: {e}")
        elif threat_score >= THREAT_PARTIAL:
            try:
                close_qty = pos.quantity * 0.5
                self.engine.api.close_position(pos.symbol, pos.side, close_qty)
                pos.quantity -= close_qty
                if pos.quantity > 0:
                    self.engine.executor._place_tpsl_orders(pos.symbol, pos.side, pos.quantity,
                                                            pos.tp_price, pos.sl_price)
                logger.warning(f"WhaleShield: 50% close on {symbol} (score={threat_score})")
                if hasattr(self.engine, 'telegram'):
                    self.engine.telegram.send_message(f"⚠️ WhaleShield закрыл 50% {symbol} {pos.side}")
            except Exception as e:
                logger.error(f"WhaleShield partial close failed: {e}")
        elif threat_score >= THREAT_BREAKEVEN:
            if pos.side == 'LONG':
                new_sl = pos.entry_price * 1.001
            else:
                new_sl = pos.entry_price * 0.999
            pos.sl_price = new_sl
            self.engine.executor._place_tpsl_orders(pos.symbol, pos.side, pos.quantity,
                                                    pos.tp_price, new_sl)
            logger.info(f"WhaleShield: moved SL to breakeven on {symbol}")
            if hasattr(self.engine, 'telegram'):
                self.engine.telegram.send_message(f"🔒 WhaleShield перевёл SL в БУ по {symbol}")
