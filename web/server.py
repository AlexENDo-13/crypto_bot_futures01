"""
Lightweight web dashboard and REST API with strategy management.
"""
import json, os, logging
from flask import Flask, request, jsonify, render_template_string, redirect, url_for, flash
from flask_cors import CORS
from werkzeug.utils import secure_filename
from datetime import datetime

logger = logging.getLogger(__name__)

API_USER = os.environ.get("BOT_WEB_USER", "admin")
API_PASS = os.environ.get("BOT_WEB_PASS", "bingx2024")
UPLOAD_FOLDER = 'strategies'

class WebServer:
    def __init__(self, engine, host="0.0.0.0", port=5000):
        self.engine = engine
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        CORS(self.app)
        self._setup_routes()

    def _check_auth(self):
        auth = request.authorization
        if not auth or auth.username != API_USER or auth.password != API_PASS:
            return False
        return True

    def _setup_routes(self):
        @self.app.route('/')
        def index():
            if not self._check_auth():
                return ('Unauthorized', 401, {'WWW-Authenticate': 'Basic realm="BingX Bot"'})
            return render_template_string(INDEX_HTML, **self._get_dashboard_data())

        # API status, positions, close, emergency stop, settings – оставлены без изменений

        @self.app.route('/api/status')
        def api_status():
            if not self._check_auth():
                return jsonify({"error": "unauthorized"}), 401
            return jsonify(self.engine.get_status())

        @self.app.route('/api/positions')
        def api_positions():
            if not self._check_auth():
                return jsonify({"error": "unauthorized"}), 401
            positions = [p.to_dict() for p in self.engine.portfolio.get_positions()]
            return jsonify(positions)

        @self.app.route('/api/close', methods=['POST'])
        def api_close():
            if not self._check_auth():
                return jsonify({"error": "unauthorized"}), 401
            data = request.get_json()
            symbol = data.get('symbol')
            side = data.get('side')
            if not symbol or not side:
                return jsonify({"error": "symbol and side required"}), 400
            try:
                self.engine.close_position_manual(symbol, side)
                return jsonify({"status": "ok"})
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/emergency_stop', methods=['POST'])
        def api_emergency():
            if not self._check_auth():
                return jsonify({"error": "unauthorized"}), 401
            try:
                for pos in self.engine.portfolio.get_positions():
                    self.engine.close_position_manual(pos.symbol, pos.side)
                self.engine.risk_controller._emergency_lock = True
                self.engine.pause()
                return jsonify({"status": "emergency stop activated"})
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route('/api/settings', methods=['GET', 'POST'])
        def api_settings():
            if not self._check_auth():
                return jsonify({"error": "unauthorized"}), 401
            if request.method == 'GET':
                return jsonify({
                    "max_positions": self.engine.max_positions,
                    "signal_threshold": self.engine.signal_threshold,
                    "scan_interval": self.engine.scan_interval,
                    "risk_per_trade": self.engine.risk_manager.risk_per_trade_pct,
                    "max_leverage": self.engine.risk_manager.max_leverage,
                    "trailing_enabled": self.engine.trailing_sl_enabled,
                    "partial_close": self.engine.partial_close_enabled,
                    "breakeven": self.engine.breakeven_enabled,
                })
            else:
                data = request.get_json()
                if 'max_positions' in data: self.engine.max_positions = int(data['max_positions'])
                if 'signal_threshold' in data: self.engine.signal_threshold = float(data['signal_threshold'])
                if 'scan_interval' in data: self.engine.scan_interval = int(data['scan_interval'])
                if 'risk_per_trade' in data: self.engine.risk_manager.risk_per_trade_pct = float(data['risk_per_trade'])
                if 'max_leverage' in data: self.engine.risk_manager.max_leverage = int(data['max_leverage'])
                if 'trailing_enabled' in data: self.engine.trailing_sl_enabled = bool(data['trailing_enabled'])
                if 'partial_close' in data: self.engine.partial_close_enabled = bool(data['partial_close'])
                if 'breakeven' in data: self.engine.breakeven_enabled = bool(data['breakeven'])
                self.engine._save_config()
                return jsonify({"status": "saved"})

        # === Новые маршруты управления стратегиями ===
        @self.app.route('/strategies')
        def strategy_list():
            if not self._check_auth():
                return redirect(url_for('index'))
            strategies = []
            for name, s in self.engine.strategies.items():
                strategies.append({
                    'name': name,
                    'enabled': s.enabled,
                    'weight': s.weight,
                    'description': s.DESCRIPTION,
                })
            return render_template_string(STRATEGIES_HTML, strategies=strategies)

        @self.app.route('/api/strategies/toggle', methods=['POST'])
        def toggle_strategy():
            if not self._check_auth():
                return jsonify({"error":"unauthorized"}), 401
            data = request.get_json()
            name = data.get('name')
            enabled = data.get('enabled')
            if name not in self.engine.strategies:
                return jsonify({"error":"strategy not found"}), 404
            self.engine.strategies[name].enabled = enabled
            return jsonify({"status":"ok"})

        @self.app.route('/api/strategies/upload', methods=['POST'])
        def upload_strategy():
            if not self._check_auth():
                return jsonify({"error":"unauthorized"}), 401
            if 'file' not in request.files:
                return jsonify({"error":"no file"}), 400
            file = request.files['file']
            if file.filename == '':
                return jsonify({"error":"no filename"}), 400
            if not file.filename.endswith('.py'):
                return jsonify({"error":"only .py files allowed"}), 400
            filename = secure_filename(file.filename)
            filepath = os.path.join(self.app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            try:
                self.engine.load_all_modules()   # исправлено: раньше было reload_modules()
                return jsonify({"status":"uploaded", "reloaded": True})
            except Exception as e:
                return jsonify({"error": str(e)}), 500

    def _get_dashboard_data(self):
        s = self.engine.get_status()
        return {
            "balance": f"{s['balance']:.2f}",
            "equity": f"{s['equity']:.2f}",
            "daily_pnl": f"{s['daily_pnl']:.2f}",
            "open_positions": s['open_positions'],
            "connected": "yes" if s['connected'] else "no",
            "mode": "LIVE" if not s['demo_mode'] else "DEMO",
            "positions": [p.to_dict() for p in self.engine.portfolio.get_positions()]
        }

    def start(self):
        logger.info(f"Starting web server on {self.host}:{self.port}")
        from threading import Thread
        Thread(target=self.app.run, kwargs={"host": self.host, "port": self.port, "debug": False}, daemon=True).start()


# ---------- HTML-шаблоны ----------
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>BingX Bot</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; margin: 20px; background:#1e1e2e; color:#e0e0f0; }
        .card { background:#2a2a3e; padding:15px; margin:10px 0; border-radius:8px; }
        .btn { background:#7c3aed; color:white; border:none; padding:8px 16px; border-radius:4px; cursor:pointer; text-decoration:none; }
        .btn.danger { background:#f87171; }
        table { width:100%; border-collapse:collapse; margin-top:10px; }
        th,td { padding:8px; text-align:left; border-bottom:1px solid #404060; }
    </style>
</head>
<body>
    <h1>🤖 BingX Trading Bot</h1>
    <p><a href="/strategies" class="btn">⚙️ Управление стратегиями</a></p>
    <div class="card">
        <b>Баланс:</b> {{ balance }} USDT | <b>Эквити:</b> {{ equity }} USDT<br>
        <b>Сегодня:</b> {{ daily_pnl }} USDT | <b>Позиций открыто:</b> {{ open_positions }}<br>
        <b>Связь:</b> {{ connected }} | <b>Режим:</b> {{ mode }}
    </div>
    <div class="card">
        <button class="btn danger" onclick="emergency_stop()">🚨 ЭКСТРЕННЫЙ СТОП</button>
    </div>
    <div class="card">
        <h3>Открытые позиции</h3>
        {% if positions %}
        <table>
            <tr><th>Символ</th><th>Сторона</th><th>Цена входа</th><th>Кол-во</th><th>PnL</th><th>Действия</th></tr>
            {% for p in positions %}
            <tr>
                <td>{{ p.symbol }}</td>
                <td>{{ p.side }}</td>
                <td>{{ p.entry_price }}</td>
                <td>{{ p.quantity }}</td>
                <td style="color:{% if p.unrealized_pnl >= 0 %}#34d399{% else %}#f87171{% endif %}">
                    {{ p.unrealized_pnl }}
                </td>
                <td><button class="btn" onclick="close_position('{{ p.symbol }}','{{ p.side }}')">Закрыть</button></td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
        <p>Нет открытых позиций</p>
        {% endif %}
    </div>
    <script>
        function close_position(symbol, side) {
            if(confirm(`Закрыть ${symbol} ${side}?`)) {
                fetch('/api/close', {
                    method:'POST',
                    headers:{'Content-Type':'application/json','Authorization':'Basic '+btoa('admin:bingx2024')},
                    body:JSON.stringify({symbol:symbol, side:side})
                }).then(r=>r.json()).then(console.log);
            }
        }
        function emergency_stop() {
            if(confirm('ЭКСТРЕННЫЙ СТОП! Закрыть ВСЕ позиции?')) {
                fetch('/api/emergency_stop', {
                    method:'POST',
                    headers:{'Authorization':'Basic '+btoa('admin:bingx2024')}
                }).then(r=>r.json()).then(console.log);
            }
        }
    </script>
</body>
</html>
""".replace("admin:bingx2024", f"{API_USER}:{API_PASS}")

STRATEGIES_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Управление стратегиями</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: sans-serif; margin: 20px; background:#1e1e2e; color:#e0e0f0; }
        .card { background:#2a2a3e; padding:15px; margin:10px 0; border-radius:8px; }
        .btn { background:#7c3aed; color:white; border:none; padding:6px 12px; border-radius:4px; cursor:pointer; }
        .btn.toggle { min-width:80px; }
        .btn.danger { background:#f87171; }
        input[type="file"] { color:#e0e0f0; }
    </style>
</head>
<body>
    <h1>⚙️ Управление стратегиями</h1>
    <a href="/" class="btn">← Назад</a>
    <div class="card">
        <h3>Загрузить новую стратегию</h3>
        <input type="file" id="fileInput" accept=".py">
        <button class="btn" onclick="uploadStrategy()">Загрузить</button>
    </div>
    <div class="card">
        <h3>Активные стратегии</h3>
        <ul>
        {% for s in strategies %}
            <li style="margin:8px 0;">
                <b>{{ s.name }}</b> ({{ s.description }})<br>
                Вес: {{ s.weight }} |
                <button class="btn toggle" onclick="toggleStrategy('{{ s.name }}', {{ s.enabled|lower }})">
                    {{ 'Выключить' if s.enabled else 'Включить' }}
                </button>
            </li>
        {% endfor %}
        </ul>
    </div>
    <script>
        function toggleStrategy(name, currentEnabled) {
            fetch('/api/strategies/toggle', {
                method:'POST',
                headers:{'Content-Type':'application/json','Authorization':'Basic '+btoa('admin:bingx2024')},
                body:JSON.stringify({name:name, enabled:!currentEnabled})
            }).then(r=>r.json()).then(data=>{
                if(data.status === 'ok') location.reload();
            });
        }
        function uploadStrategy() {
            const fileInput = document.getElementById('fileInput');
            const file = fileInput.files[0];
            if(!file) return alert('Выберите файл');
            const formData = new FormData();
            formData.append('file', file);
            fetch('/api/strategies/upload', {
                method:'POST',
                headers:{'Authorization':'Basic '+btoa('admin:bingx2024')},
                body:formData
            }).then(r=>r.json()).then(data=>{
                alert(data.status);
                if(data.reloaded) location.reload();
            });
        }
    </script>
</body>
</html>
""".replace("admin:bingx2024", f"{API_USER}:{API_PASS}")
