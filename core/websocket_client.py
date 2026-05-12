"""
WebSocket client for BingX Perpetual Futures (USDT-M).
Subscribes to real-time market data streams: kline, depth, ticker, trade.
Updates engine._candle_data and engine._current_prices in real time.
Falls back to REST if WebSocket connection fails.
Fully compliant with BingX WebSocket documentation.
"""
import json
import time
import threading
import logging
import queue
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone, timedelta

import websocket
import pandas as pd

logger = logging.getLogger(__name__)

# WebSocket endpoints
WS_MARKET = "wss://open-api-cswap-ws.bingx.com/market"
WS_ACCOUNT = "wss://open-api-cswap-ws.bingx.com/market"  # same host + listenKey
REST_LISTEN_KEY = "/openApi/swap/v1/user/listenKey"

# Stream types
STREAMS = ['kline_5m', 'kline_15m', 'kline_1h', 'kline_4h', 'kline_1d',
           'depth5', 'bookTicker', 'trade', 'ticker']

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
        self._subscribed_symbols = set()
        self._pending_pong = False
        
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
        now = time.time()
        if self._listen_key is None or (now - self._last_listen_key_update) > self._listen_key_update_interval:
            try:
                resp = self.engine.api._request('POST', REST_LISTEN_KEY, {})
                if resp.get('code') == 0:
                    self._listen_key = resp['data']['listenKey']
                    self._last_listen_key_update = now
                    logger.info(f"ListenKey obtained: {self._listen_key[:8]}...")
                else:
                    logger.error(f"Failed to get listenKey: {resp}")
            except Exception as e:
                logger.error(f"ListenKey error: {e}")
                
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
        # run_forever with ping/pong handling
        self._ws_market.run_forever(ping_interval=30, ping_timeout=10)
        
    def _on_market_open(self, ws):
        logger.info("Market WebSocket opened, subscribing to streams...")
        symbols = self.engine._top_symbols
        if not symbols:
            logger.warning("No symbols, cannot subscribe")
            return
        for sym in symbols:
            base = sym  # e.g. "BTC-USDT"
            for stream in STREAMS:
                # Подписываемся на каждый поток отдельным сообщением (как требует документация)
                data_type = f"{base}@{stream}"
                self._subscribe(ws, data_type)
                time.sleep(0.05)  # небольшая задержка, чтобы не флудить подписками
                
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
            # Обработка ping
            if message == "ping":
                ws.send("pong")
                logger.debug("Pong sent")
                return
                
            data = json.loads(message)
            if 'dataType' in data:
                data_type = data['dataType']
                payload = data.get('data', {})
                self._process_market_data(data_type, payload)
        except json.JSONDecodeError:
            logger.warning(f"Non-JSON message: {message[:100]}")
        except Exception as e:
            logger.error(f"Error processing market message: {e}")
            
    def _process_market_data(self, data_type: str, payload: dict):
        """Обновляет engine._candle_data и другие структуры."""
        parts = data_type.split('@')
        if len(parts) != 2:
            return
        symbol = parts[0]
        stream = parts[1]
        
        if stream.startswith('kline_'):
            # Парсим kline
            interval = stream.split('_')[1]  # 5m, 15m, 1h, 4h, 1d
            t = payload.get('t')  # start time (ms)
            o = float(payload.get('o', 0))
            h = float(payload.get('h', 0))
            l = float(payload.get('l', 0))
            c = float(payload.get('c', 0))
            v = float(payload.get('v', 0))
            if t is None or o == 0:
                return
            # Обновляем или добавляем свечу в engine._candle_data
            if symbol not in self.engine._candle_data:
                self.engine._candle_data[symbol] = {}
            if interval not in self.engine._candle_data[symbol]:
                # Создаём пустой DataFrame
                self.engine._candle_data[symbol][interval] = pd.DataFrame(columns=['open','high','low','close','volume','timestamp'])
                self.engine._candle_data[symbol][interval].set_index('timestamp', inplace=True)
            df = self.engine._candle_data[symbol][interval]
            # Проверяем, не существует ли уже свеча с таким t
            ts = pd.Timestamp(t, unit='ms', tz='UTC')
            if ts in df.index:
                # Обновляем последнюю свечу
                df.loc[ts, ['open','high','low','close','volume']] = [o, max(h, df.loc[ts,'high']), min(l, df.loc[ts,'low']), c, v]
            else:
                # Добавляем новую
                new_row = pd.DataFrame({'open': o, 'high': h, 'low': l, 'close': c, 'volume': v}, index=[ts])
                df = pd.concat([df, new_row])
                # Оставляем последние 200 свечей
                if len(df) > 200:
                    df = df.iloc[-200:]
                self.engine._candle_data[symbol][interval] = df
                
        elif stream == 'bookTicker':
            best_bid = float(payload.get('b', 0))
            best_ask = float(payload.get('a', 0))
            # Можно сохранить, если нужно
            if not hasattr(self.engine, '_best_bid_ask'):
                self.engine._best_bid_ask = {}
            self.engine._best_bid_ask[symbol] = (best_bid, best_ask)
            
        elif stream == 'ticker':
            last_price = payload.get('c')
            if last_price:
                if not hasattr(self.engine, '_current_prices'):
                    self.engine._current_prices = {}
                self.engine._current_prices[symbol] = float(last_price)
                
        elif stream == 'trade':
            # Не критично для свечей, можно игнорировать
            pass
            
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
        
    def _on_account_message(self, ws, message):
        if message == "ping":
            ws.send("pong")
            return
        try:
            data = json.loads(message)
            event_type = data.get('e')
            if event_type == 'ORDER_TRADE_UPDATE':
                self._process_order_update(data.get('o', {}))
            elif event_type == 'ACCOUNT_UPDATE':
                self._process_account_update(data.get('a', {}))
            elif event_type == 'ACCOUNT_CONFIG_UPDATE':
                # Можно игнорировать или обработать
                pass
        except Exception as e:
            logger.error(f"Account message error: {e}")
            
    def _process_order_update(self, order_data):
        # Можно обновлять локальный кэш ордеров, но для простоты пока пропускаем
        pass
        
    def _process_account_update(self, account_data):
        # Обновляем баланс
        balances = account_data.get('B', [])
        for b in balances:
            if b.get('a') == 'USDT':
                balance = float(b.get('wb', 0))
                self.engine.portfolio._balance = balance
                self.engine.portfolio._equity = balance
        # Позиции (P) – можно синхронизировать, но это уже делает sync_manager
        # Заметим, что мы не должны удалять позиции, которые есть на бирже, но не пришли в этом обновлении
        # Пока просто логируем
        positions = account_data.get('P', [])
        if positions:
            logger.debug(f"Account update: {len(positions)} positions")
            
    def _on_account_error(self, ws, error):
        logger.error(f"Account WebSocket error: {error}")
        
    def _on_account_close(self, ws, close_status_code, close_msg):
        logger.warning(f"Account WebSocket closed: {close_status_code} {close_msg}")
        
    def _engine_ready(self) -> bool:
        return (self.engine is not None and 
                self.engine._top_symbols and 
                len(self.engine._top_symbols) > 0)
                
    # ------------------------------------------------------------------
    # Fallback to REST when WebSocket data is missing (used by engine_scan)
    # ------------------------------------------------------------------
    def get_candles_fallback(self, symbol: str, timeframe: str, limit: int = 200):
        """Резервный метод для получения свечей через REST, если WebSocket не обновил данные."""
        logger.warning(f"Using REST fallback for {symbol} {timeframe}")
        try:
            return self.engine.api.get_klines_dataframe(symbol, timeframe, limit=limit)
        except Exception as e:
            logger.error(f"REST fallback failed: {e}")
            return None
