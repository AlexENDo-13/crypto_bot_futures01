"""
BingX Perpetual Futures (Swap v2) API client.
Handles authentication, rate limiting, and request management.
"""
import hmac
import hashlib
import time
import json
import logging
from urllib.parse import urlencode
from typing import Optional, Dict, List, Any
import requests

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, requests_per_second: float = 10.0):
        self.min_interval = 1.0 / requests_per_second
        self.last_request_time = 0.0
        self.consecutive_errors = 0
        self.base_delay = 0.2
        self.max_delay = 30.0

    def wait(self):
        now = time.time()
        elapsed = now - self.last_request_time
        current_delay = min(
            self.base_delay * (2 ** self.consecutive_errors),
            self.max_delay
        )
        wait_time = max(self.min_interval, current_delay) - elapsed
        if wait_time > 0:
            time.sleep(wait_time)
        self.last_request_time = time.time()

    def record_success(self):
        self.consecutive_errors = max(0, self.consecutive_errors - 1)

    def record_error(self, status_code: int):
        if status_code in (429, 418):
            self.consecutive_errors += 1


class BingXAPI:
    BASE_URL = "https://open-api.bingx.com"

    BALANCE = "/openApi/swap/v2/user/balance"
    POSITIONS = "/openApi/swap/v2/user/positions"
    ORDER = "/openApi/swap/v2/trade/order"
    LEVERAGE = "/openApi/swap/v2/trade/leverage"
    CONTRACTS = "/openApi/swap/v2/quote/contracts"
    KLINES = "/openApi/swap/v2/quote/klines"
    TICKER = "/openApi/swap/v2/quote/ticker"
    DEPTH = "/openApi/swap/v2/quote/depth"

    def __init__(self, auth_manager):
        self.auth = auth_manager
        self.session = requests.Session()
        self.rate_limiter = RateLimiter(requests_per_second=8.0)
        self._connected = False
        self._last_ping_ms: Optional[float] = None

    def _sign_params(self, params: Dict[str, Any]) -> str:
        sorted_keys = sorted(params.keys())
        query_string = "&".join([f"{k}={params[k]}" for k in sorted_keys])
        signature = hmac.new(
            self.auth.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None,
                 max_retries: int = 3) -> Dict:
        if self.auth.demo_mode:
            raise RuntimeError("API keys not configured")

        for attempt in range(max_retries):
            try:
                self.rate_limiter.wait()

                if method.upper() == 'GET':
                    params = params or {}
                    params['timestamp'] = int(time.time() * 1000)
                    signature = self._sign_params(params)
                    params['signature'] = signature
                    url = f"{self.BASE_URL}{endpoint}?{urlencode(params)}"
                    headers = {"X-BX-APIKEY": self.auth.api_key}
                    response = self.session.get(url, headers=headers, timeout=15)
                else:
                    body = dict(params) if params else {}
                    body['timestamp'] = int(time.time() * 1000)
                    signature = self._sign_params(body)
                    body['signature'] = signature
                    url = f"{self.BASE_URL}{endpoint}"
                    headers = {
                        "X-BX-APIKEY": self.auth.api_key,
                        "Content-Type": "application/json"
                    }
                    if method.upper() == 'POST':
                        response = self.session.post(url, headers=headers, json=body, timeout=15)
                    elif method.upper() == 'DELETE':
                        response = self.session.delete(url, headers=headers, json=body, timeout=15)
                    else:
                        response = self.session.get(url, headers=headers, timeout=15)

                status_code = response.status_code
                if status_code == 200:
                    self.rate_limiter.record_success()
                    self._connected = True
                    return response.json()
                elif status_code in (429, 418):
                    self.rate_limiter.record_error(status_code)
                    wait_time = min(2 ** attempt, 30)
                    logger.warning(f"Rate limited (HTTP {status_code}), waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                elif status_code >= 500:
                    logger.warning(f"Server error {status_code}, retrying...")
                    time.sleep(2 ** attempt)
                    continue
                else:
                    logger.error(f"API error {status_code}: {response.text}")
                    raise RuntimeError(f"API returned {status_code}: {response.text}")

            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout, attempt {attempt + 1}/{max_retries}")
                time.sleep(2 ** attempt)
            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error, attempt {attempt + 1}/{max_retries}")
                self._connected = False
                time.sleep(5)
            except Exception as e:
                logger.error(f"Request error: {e}")
                raise

        raise RuntimeError(f"Failed after {max_retries} attempts")

    def ping(self) -> Optional[float]:
        try:
            start = time.time()
            url = f"{self.BASE_URL}{self.TICKER}"
            self.session.get(url, timeout=5)
            elapsed = (time.time() - start) * 1000
            self._last_ping_ms = elapsed
            self._connected = True
            return elapsed
        except Exception:
            self._connected = False
            return None

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_ping_ms(self) -> Optional[float]:
        return self._last_ping_ms

    # Account
    def get_balance(self) -> Dict:
        return self._request('GET', self.BALANCE)

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        params = {}
        if symbol:
            params['symbol'] = symbol
        response = self._request('GET', self.POSITIONS, params)
        return response.get('data', [])

    # Trading
    def set_leverage(self, symbol: str, leverage: int, position_side: str = "LONG") -> Dict:
        params = {
            'symbol': symbol,
            'leverage': leverage,
            'side': position_side,
            'positionSide': position_side
        }
        return self._request('POST', self.LEVERAGE, params)

    def place_order(self, symbol: str, side: str, position_side: str,
                    order_type: str, quantity: float,
                    price: Optional[float] = None,
                    stop_price: Optional[float] = None,
                    client_order_id: Optional[str] = None) -> Dict:
        params = {
            'symbol': symbol,
            'side': side,
            'positionSide': position_side,
            'type': order_type,
            'quantity': quantity,
        }
        if price is not None:
            params['price'] = price
        if stop_price is not None:
            params['stopPrice'] = stop_price
        if client_order_id:
            params['clientOrderID'] = client_order_id
        return self._request('POST', self.ORDER, params)

    def close_position(self, symbol: str, position_side: str,
                       quantity: Optional[float] = None) -> Dict:
        if quantity is None:
            positions = self.get_positions(symbol)
            pos = next((p for p in positions if p.get('positionSide') == position_side), None)
            if not pos:
                raise ValueError(f"No {position_side} position found for {symbol}")
            quantity = abs(float(pos.get('positionAmt', 0)))
            if quantity == 0:
                raise ValueError("Position amount is zero")
        
        close_side = "SELL" if position_side == "LONG" else "BUY"
        params = {
            'symbol': symbol,
            'side': close_side,
            'positionSide': position_side,
            'type': 'MARKET',
            'quantity': quantity,
        }
        return self._request('POST', self.ORDER, params)

    def close_position_percent(self, symbol: str, position_side: str,
                                percent: float) -> Dict:
        positions = self.get_positions(symbol)
        pos = next((p for p in positions if p.get('positionSide') == position_side), None)
        if not pos:
            raise ValueError(f"No {position_side} position found for {symbol}")
        total_qty = abs(float(pos.get('positionAmt', 0)))
        close_qty = round(total_qty * (percent / 100), 8)
        if close_qty <= 0:
            raise ValueError("Close quantity is zero")
        return self.close_position(symbol, position_side, close_qty)

    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        params = {'symbol': symbol, 'orderId': order_id}
        return self._request('DELETE', self.ORDER, params)

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        params = {}
        if symbol:
            params['symbol'] = symbol
        response = self._request('GET', self.ORDER, params)
        return response.get('data', [])

    # Market Data
    def get_contracts(self) -> List[Dict]:
        response = self._request('GET', self.CONTRACTS)
        return response.get('data', [])

    def get_ticker(self, symbol: Optional[str] = None) -> Dict:
        params = {}
        if symbol:
            params['symbol'] = symbol
        return self._request('GET', self.TICKER, params)

    def get_depth(self, symbol: str, limit: int = 20) -> Dict:
        """Возвращает полный ответ глубины стакана."""
        params = {'symbol': symbol, 'limit': limit}
        return self._request('GET', self.DEPTH, params)

    def get_klines(self, symbol: str, interval: str,
                   start_time: Optional[int] = None,
                   end_time: Optional[int] = None,
                   limit: int = 500) -> List[Dict]:
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': min(limit, 1000)
        }
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        response = self._request('GET', self.KLINES, params)
        return response.get('data', [])

    def get_klines_dataframe(self, symbol: str, interval: str,
                              limit: int = 500) -> Any:
        import pandas as pd
        data = self.get_klines(symbol, interval, limit=limit)
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        column_map = {
            'open': 'open', 'high': 'high', 'low': 'low',
            'close': 'close', 'volume': 'volume',
            'time': 'timestamp', 'openTime': 'timestamp',
        }
        for old, new in column_map.items():
            if old in df.columns and new not in df.columns:
                df.rename(columns={old: new}, inplace=True)
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
            df.set_index('timestamp', inplace=True)
        return df.sort_index()
