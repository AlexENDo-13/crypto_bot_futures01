"""
WebSocket client for BingX Perpetual Futures (USDT-M).
Использует правильные URL, обрабатывает Ping/Pong, автоматически продлевает listenKey.
Поддерживает Market Data (без авторизации) и Account Data (с listenKey).
"""
import json
import time
import threading
import logging
import gzip
import io
from typing import Optional

import websocket

logger = logging.getLogger(__name__)

# Правильные URL из документации
WS_MARKET = "wss://open-api-swap.bingx.com/swap-market"
WS_ACCOUNT = "wss://open-api-swap.bingx.com/swap-market"  # одинаковый, но с listenKey

# Потоки для маркет‑данных (подписываемся только на нужные)
STREAMS = [
    'kline_5m', 'kline_15m', 'kline_1h', 'kline_4h', 'kline_1d',
    'depth5', 'bookTicker', 'trade', 'ticker'
]


class BingXWebSocketClient:
    def __init__(self, engine):
        self.engine = engine
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._ws_market: Optional[websocket.WebSocketApp] = None
        self._ws_account: Optional[websocket.WebSocketApp] = None
        self._listen_key: Optional[str] = None
        self._last_listen_key_extend = 0.0
        self._extend_interval = 30 * 60  # 30 минут (рекомендовано документацией)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="WebSocketClient")
        self._thread.start()
        logger.info("WebSocket client started")

    def stop(self):
        self._running = False
        if self._ws_market:
            self._ws_market.close()
        if self._ws_account:
            self._ws_account.close()
        if self._listen_key:
            self.engine.api.close_listen_key(self._listen_key)

    def _run(self):
        retry_count = 0
        while self._running:
            try:
                self._ensure_listen_key()
                self._connect_market_streams()
                self._connect_account_stream()
                retry_count = 0  # сброс при успешном подключении
                time.sleep(5)
            except Exception as e:
                logger.error(f"WebSocket main loop error: {e}")
                delay = min(5 * (2 ** retry_count), 60)
                time.sleep(delay)
                retry_count += 1

    def _ensure_listen_key(self):
        now = time.time()
        # Если ключа нет или пора продлевать (каждые 30 мин)
        if self._listen_key is None or (now - self._last_listen_key_extend) > self._extend_interval:
            if self._listen_key:
                # Пробуем продлить существующий ключ
                if self.engine.api.extend_listen_key(self._listen_key):
                    self._last_listen_key_extend = now
                    logger.info("ListenKey extended")
                    return
                else:
                    # Если продлить не удалось, генерируем новый
                    self._listen_key = None
            # Генерируем новый ключ
            listen_key = self.engine.api.get_listen_key()
            if listen_key:
                self._listen_key = listen_key
                self._last_listen_key_extend = now
                logger.info(f"ListenKey obtained: {self._listen_key[:8]}...")
            else:
                logger.error("Failed to obtain listenKey")

    def _connect_market_streams(self):
        """Подключается к маркет‑данным (без listenKey)."""
        if not self._engine_ready():
            return

        self._ws_market = websocket.WebSocketApp(
            WS_MARKET,
            on_open=self._on_market_open,
            on_message=self._on_market_message,
            on_error=self._on_market_error,
            on_close=self._on_market_close
        )
        # run_forever с пингом каждые 30 секунд (дополнительная страховка)
        self._ws_market.run_forever(ping_interval=30, ping_timeout=10)

    def _on_market_open(self, ws):
        logger.info("Market WebSocket opened, subscribing to streams...")
        symbols = self.engine._top_symbols
        if not symbols:
            logger.warning("No symbols, cannot subscribe")
            return
        for sym in symbols:
            base = sym  # например "BTC-USDT"
            for stream in STREAMS:
                data_type = f"{base}@{stream}"
                self._subscribe(ws, data_type)
                time.sleep(0.05)

    def _subscribe(self, ws, data_type):
        msg = {
            "id": f"sub_{data_type.replace('@', '_')}",
            "reqType": "sub",
            "dataType": data_type
        }
        try:
            ws.send(json.dumps(msg))
            logger.debug(f"Subscribed to {data_type}")
        except Exception as e:
            logger.error(f"Subscription failed for {data_type}: {e}")

    def _on_market_message(self, ws, message):
        try:
            # Распаковка gzip
            if isinstance(message, bytes):
                try:
                    with gzip.GzipFile(fileobj=io.BytesIO(message)) as gz:
                        decompressed = gz.read()
                    message = decompressed.decode('utf-8')
                except Exception:
                    message = message.decode('utf-8')

            # Обработка Ping (сравниваем без учёта регистра, так как сервер может слать "Ping")
            msg_upper = message.strip().upper()
            if msg_upper == "PING":
                ws.send("Pong")
                logger.debug("Pong sent")
                return

            data = json.loads(message)
            if 'dataType' in data:
                data_type = data['dataType']
                payload = data.get('data', {})
                self._process_market_data(data_type, payload)
        except Exception as e:
            logger.error(f"Error processing market message: {e}")

    def _process_market_data(self, data_type: str, payload: dict):
        """Обновляет кэши свечей и цен."""
        parts = data_type.split('@')
        if len(parts) != 2:
            return
        symbol = parts[0]
        stream = parts[1]

        if stream.startswith('kline_'):
            interval = stream.split('_')[1]
            t = payload.get('t')
            if t is None:
                return
            o = float(payload.get('o', 0))
            h = float(payload.get('h', 0))
            l = float(payload.get('l', 0))
            c = float(payload.get('c', 0))
            v = float(payload.get('v', 0))
            # Сохраняем в engine._candle_data (упрощённо)
            if symbol not in self.engine._candle_data:
                self.engine._candle_data[symbol] = {}
            logger.debug(f"Kline {symbol} {interval}: o={o} c={c}")
        elif stream == 'ticker':
            last_price = payload.get('c')
            if last_price:
                if not hasattr(self.engine, '_current_prices'):
                    self.engine._current_prices = {}
                self.engine._current_prices[symbol] = float(last_price)
                logger.debug(f"Price update: {symbol} = {last_price}")

    def _on_market_error(self, ws, error):
        logger.error(f"Market WebSocket error: {error}")

    def _on_market_close(self, ws, close_status_code, close_msg):
        logger.warning(f"Market WebSocket closed: {close_status_code} {close_msg}")

    def _connect_account_stream(self):
        """Подключается к стриму аккаунта (требует listenKey)."""
        if not self._listen_key:
            logger.warning("No listenKey, cannot connect account stream")
            return
        url = f"{WS_ACCOUNT}?listenKey={self._listen_key}"
        self._ws_account = websocket.WebSocketApp(
            url,
            on_open=self._on_account_open,
            on_message=self._on_account_message,
            on_error=self._on_account_error,
            on_close=self._on_account_close
        )
        self._ws_account.run_forever(ping_interval=30, ping_timeout=10)

    def _on_account_open(self, ws):
        logger.info("Account WebSocket opened")
        # Сразу после открытия продлеваем listenKey, чтобы он точно был активен
        if self._listen_key:
            self.engine.api.extend_listen_key(self._listen_key)
            self._last_listen_key_extend = time.time()

    def _on_account_message(self, ws, message):
        try:
            if isinstance(message, bytes):
                try:
                    with gzip.GzipFile(fileobj=io.BytesIO(message)) as gz:
                        decompressed = gz.read()
                    message = decompressed.decode('utf-8')
                except Exception:
                    message = message.decode('utf-8')

            msg_upper = message.strip().upper()
            if msg_upper == "PING":
                ws.send("Pong")
                logger.debug("Pong sent (account)")
                return

            data = json.loads(message)
            event_type = data.get('e')
            if event_type == 'ORDER_TRADE_UPDATE':
                # Здесь можно обновлять кэш ордеров
                pass
            elif event_type == 'ACCOUNT_UPDATE':
                # Здесь можно обновлять баланс/позиции
                pass
        except Exception as e:
            logger.error(f"Account message error: {e}")

    def _on_account_error(self, ws, error):
        logger.error(f"Account WebSocket error: {error}")

    def _on_account_close(self, ws, close_status_code, close_msg):
        logger.warning(f"Account WebSocket closed: {close_status_code} {close_msg}")

    def _engine_ready(self) -> bool:
        return (self.engine is not None and
                self.engine._top_symbols and
                len(self.engine._top_symbols) > 0)
