"""
Backup Manager – periodically sends config and state files to Telegram.
"""
import logging
import time
import threading
import io
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BACKUP_FILES = [
    'config.ini',
    'data/strategy_weights.json',
    'data/engine_state.json',
    'data/risk_state.json',
    'data/blacklist.json'
]

class BackupManager:
    """Каждые N часов отправляет бэкап в Telegram."""

    def __init__(self, engine, interval_hours: int = 24):
        self.engine = engine
        self.interval = interval_hours * 3600
        self._running = False
        self._thread = None

    def start(self):
        if not getattr(self.engine, 'telegram', None) or not self.engine.telegram.enabled:
            logger.info("BackupManager disabled – Telegram not configured")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("BackupManager started (interval %d hours)", self.interval // 3600)

    def stop(self):
        self._running = False

    def _loop(self):
        time.sleep(10)  # дать боту инициализироваться
        while self._running:
            try:
                self._send_backup()
            except Exception as e:
                logger.error(f"BackupManager failed: {e}")
            time.sleep(self.interval)

    def _send_backup(self):
        tg = self.engine.telegram
        if not tg or not tg.enabled:
            return
        # Собрать все файлы в zip-архив в памяти
        import zipfile, os
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for fname in BACKUP_FILES:
                if os.path.exists(fname):
                    zf.write(fname)
        buf.seek(0)
        # Отправить как документ
        now = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')
        try:
            import requests
            url = f"https://api.telegram.org/bot{tg.token}/sendDocument"
            files = {'document': (f'backup_{now}.zip', buf, 'application/zip')}
            data = {'chat_id': tg.chat_id, 'caption': f'Автоматический бэкап {now}'}
            resp = requests.post(url, files=files, data=data, timeout=30)
            if resp.status_code == 200:
                logger.info("Backup sent to Telegram")
            else:
                logger.warning(f"Backup send failed: {resp.text}")
        except Exception as e:
            logger.error(f"Backup send error: {e}")
