"""
WebSocket client for BingX Perpetual Futures (USDT-M).
Исправлена ошибка при получении списка вместо словаря.
"""
import json
import time
import threading
import logging
import gzip
import io
from typing import Optional, Union, List, Dict

import websocket

logger = logging.getLogger(__name__)

# Правильные URL из документации
WS_MARKET = "wss://open-api-swap.bingx.com/swap-market"
WS_ACCOUNT = "wss://open-api-swap.bingx.com/swap-market"

# Потоки для маркет‑данных
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
        self._extend_interval = 30 * 60  # 30 минут

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
                retry_count = 0
                time.sleep(5)
            except Exception as e:
                logger.error(f"WebSocket main loop error: {e}")
                delay = min(5 * (2 ** retry_count), 60)
                time.sleep(delay)
                retry_count += 1

    def _ensure_listen_key(self):
        now = time.time()
        if self._listen_key is None or (now - self._last_listen_key_extend) > self._extend_interval:
            if self._listen_key:
                if self.engine.api.extend_listen_key(self._listen_key):
                    self._last_listen_key_extend = now
                    logger.info("ListenKey extended")
                    return
                else:
                    self._listen_key = None
            listen_key = self.engine.api.get_listen_key()
            if listen_key:
                self._listen_key = listen_key
                self._last_listen_key_extend = now
                logger.info(f"ListenKey obtained: {self._listen_key[:8]}...")
            else:
                logger.error("Failed to obtain listenKey")

    def _connect_market_streams(self):
        if not self._engine_ready():
            return
        self._ws_market = websocket.WebSocketApp(
            WS_MARKET,
            on_open=self._on_market_open,
            on_message=self._on_market_message,
            on_error=self._on_market_error,
            on_close=self._on_market_close
        )
        self._ws_market.run_forever(ping_interval=30, ping_timeout=10)

    def _on_market_open(self, ws):
        logger.info("Market WebSocket opened, subscribing to streams...")
        symbols = self.engine._top_symbols
        if not symbols:
            logger.warning("No symbols, cannot subscribe")
            return
        for sym in symbols:
            for stream in STREAMS:
                data_type = f"{sym}@{stream}"
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

            msg_upper = message.strip().upper()
            if msg_upper == "PING":
                ws.send("Pong")
                logger.debug("Pong sent")
                return

            data = json.loads(message)
            # Проверяем, что data является словарём
            if not isinstance(data, dict):
                logger.warning(f"Received non-dict message: {type(data)} -> {str(data)[:200]}")
                return

            # Поиск dataType: может быть в корне или в поле 'dataType'
            data_type = data.get('dataType')
            if not data_type:
                # Возможно, это подтверждение подписки или другое служебное сообщение
                if 'code' in data:
                    logger.debug(f"Subscription confirmation: {data.get('msg')}")
                return

            payload = data.get('data')
            # Если payload — список, это может быть массив ордеров или сделок. Игнорируем или обрабатываем особым образом
            if isinstance(payload, list):
                logger.debug(f"Ignoring list payload for {data_type} (size {len(payload)})")
                return
            if not isinstance(payload, dict):
                logger.debug(f"Unexpected payload type for {data_type}: {type(payload)}")
                return

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
            # Можно обновить свечные данные, но для микро-режима это не критично
            logger.debug(f"Kline {symbol} {interval}: o={payload.get('o')} c={payload.get('c')}")
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
            if not isinstance(data, dict):
                return

            event_type = data.get('e')
            if event_type == 'ORDER_TRADE_UPDATE':
                # Обновление ордера – можно обновлять кэш, но не обязательно
                pass
            elif event_type == 'ACCOUNT_UPDATE':
                # Обновление баланса/позиций – можно синхронизировать, но для простоты игнорируем
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
