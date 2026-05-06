"""
TradingView webhook receiver. Listens for JSON alerts and injects signals into the engine.
"""
import logging
import threading
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone

from strategies.base import Signal

logger = logging.getLogger(__name__)

class TradingViewWebhook:
    def __init__(self, engine, port: int = 8080):
        self.engine = engine
        self.port = port
        self._server: HTTPServer = None

    def start(self):
        if self._server:
            return
        handler = self._make_handler()
        self._server = HTTPServer(('0.0.0.0', self.port), handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        logger.info(f"TradingView webhook listening on port {self.port}")

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None

    def _make_handler(self):
        engine = self.engine
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                try:
                    content_length = int(self.headers.get('Content-Length', 0))
                    body = self.rfile.read(content_length)
                    data = json.loads(body)
                    self._process_alert(data)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'OK')
                except Exception as e:
                    logger.error(f"Webhook error: {e}")
                    self.send_response(400)
                    self.end_headers()

            def _process_alert(self, data):
                symbol = data.get('symbol', '').upper()
                action = data.get('action', 'HOLD').upper()
                confidence = float(data.get('confidence', 0.7))
                if symbol and action in ('BUY', 'SELL'):
                    signal = Signal(
                        symbol=symbol,
                        action=action,
                        confidence=min(1.0, confidence),
                        meta={'source': 'tradingview', 'boost': 0.2}
                    )
                    engine._recent_signals.append({
                        'time': datetime.now().strftime('%H:%M:%S'),
                        'symbol': signal.symbol,
                        'action': signal.action,
                        'confidence': signal.confidence,
                        'price': engine._get_current_price(symbol),
                        'strategy': 'TradingView',
                    })
                    # Добавляем в очередь (будет подхвачено при следующем скане)
                    signal.meta['webhook'] = True
                    engine._process_signal(signal, {})  # Вызываем напрямую с пустыми свечами
            def log_message(self, format, *args):
                pass
        return Handler
