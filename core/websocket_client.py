"""
WebSocket client for BingX Perpetual Futures (USDT-M).
Subscribes to real-time market data streams: kline, depth, ticker, trade.
Automatically decompresses gzipped messages.
Uses api.get_listen_key() for authentication.
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

# WebSocket endpoints
WS_MARKET = "wss://open-api-cswap-ws.bingx.com/market"
WS_ACCOUNT = "wss://open-api-cswap-ws.bingx.com/market"

# Stream types to subscribe
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
        self._last_listen_key_update = 0.0
        self._listen_key_update_interval = 50 * 60  # 50 минут

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

    def _run(self):
        while self._running:
            try:
                self._ensure_listen_key()
                self._connect_market_streams()
                self._connect_account_stream()
                time.sleep(5)
            except Exception as e:
                logger.error(f"WebSocket main loop error: {e}")
                time.sleep(10)

    def _ensure_listen_key(self):
        """Получает или обновляет listenKey через API (без подписи)."""
        now = time.time()
        if self._listen_key is None or (now - self._last_listen_key_update) > self._listen_key_update_interval:
            try:
                listen_key = self.engine.api.get_listen_key()
                if listen_key:
                    self._listen_key = listen_key
                    self._last_listen_key_update = now
                    logger.info(f"ListenKey updated: {self._listen_key[:8]}...")
                else:
                    logger.error("Failed to obtain listenKey")
            except Exception as e:
                logger.error(f"ListenKey error: {e}")

    def _connect_market_streams(self):
        """Подключается к публичным маркет-стримам (без авторизации)."""
        if not self._engine_ready():
            return

        self._ws_market = websocket.WebSocketApp(
            WS_MARKET,
            on_open=self._on_market_open,
            on_message=self._on_market_message,
            on_error=self._on_market_error,
            on_close=self._on_market_close
        )
        # run_forever с пингом раз в 30 секунд
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
                time.sleep(0.05)  # небольшая задержка между подписками

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
            # Распаковка gzip, если данные сжаты
            if isinstance(message, bytes):
                try:
                    # Пробуем распаковать gzip
                    with gzip.GzipFile(fileobj=io.BytesIO(message)) as gz:
                        decompressed = gz.read()
                    message = decompressed.decode('utf-8')
                except Exception:
                    # Если не gzip, просто декодируем как utf-8
                    message = message.decode('utf-8')

            # Обработка ping
            if message == "ping":
                ws.send("pong")
                return

            data = json.loads(message)
            if 'dataType' in data:
                data_type = data['dataType']
                payload = data.get('data', {})
                self._process_market_data(data_type, payload)
        except Exception as e:
            logger.error(f"Error processing market message: {e}")

    def _process_market_data(self, data_type: str, payload: dict):
        """Обновляет кэш свечей и цен на основе WebSocket данных."""
        parts = data_type.split('@')
        if len(parts) != 2:
            return
        symbol = parts[0]
        stream = parts[1]

        if stream.startswith('kline_'):
            interval = stream.split('_')[1]  # 5m, 15m, 1h, 4h, 1d
            t = payload.get('t')  # время начала свечи в ms
            if t is None:
                return
            o = float(payload.get('o', 0))
            h = float(payload.get('h', 0))
            l = float(payload.get('l', 0))
            c = float(payload.get('c', 0))
            v = float(payload.get('v', 0))

            # Сохраняем в engine._candle_data (упрощённо, для реальной работы нужна полная синхронизация)
            if symbol not in self.engine._candle_data:
                self.engine._candle_data[symbol] = {}
            # Для простоты просто обновляем последнее значение close
            if interval not in self.engine._candle_data[symbol]:
                import pandas as pd
                self.engine._candle_data[symbol][interval] = pd.DataFrame(columns=['open','high','low','close','volume'])
            # Добавляем/обновляем свечу
            logger.debug(f"Kline update: {symbol} {interval} o={o} h={h} l={l} c={c} v={v}")

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
        """Подключается к защищённому стриму аккаунта (требует listenKey)."""
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

    def _on_account_message(self, ws, message):
        # Обработка пинга и распаковка gzip
        try:
            if isinstance(message, bytes):
                try:
                    with gzip.GzipFile(fileobj=io.BytesIO(message)) as gz:
                        decompressed = gz.read()
                    message = decompressed.decode('utf-8')
                except Exception:
                    message = message.decode('utf-8')

            if message == "ping":
                ws.send("pong")
                return

            data = json.loads(message)
            event_type = data.get('e')
            if event_type == 'ORDER_TRADE_UPDATE':
                # Можно обновлять кэш ордеров (опционально)
                pass
            elif event_type == 'ACCOUNT_UPDATE':
                # Обновлять баланс и позиции (опционально)
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
