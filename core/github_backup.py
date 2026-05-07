"""
GitHub Auto‑Backup – periodically commits and pushes changes to a remote repository.
"""
import logging
import subprocess
import time
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class GitHubBackup:
    """Автоматический git push с заданным интервалом."""

    def __init__(self, interval_hours: int = 24, remote: str = "origin", branch: str = "main"):
        self.interval = interval_hours * 3600
        self.remote = remote
        self.branch = branch
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        # Проверяем, что git доступен и мы в репозитории
        try:
            subprocess.check_call(["git", "status"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.warning("GitHubBackup disabled – git not available or not a git repository")
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("GitHubBackup started (interval %d hours, push to %s/%s)", self.interval // 3600, self.remote, self.branch)

    def stop(self):
        self._running = False

    def _loop(self):
        time.sleep(10)  # дать боту инициализироваться
        while self._running:
            try:
                self._do_backup()
            except Exception as e:
                logger.error(f"GitHubBackup failed: {e}")
            time.sleep(self.interval)

    def _do_backup(self):
        # Добавить все изменения
        subprocess.check_call(["git", "add", "-A"])
        # Закоммитить с временной меткой
        msg = f"auto-backup {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"
        try:
            subprocess.check_call(["git", "commit", "-m", msg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            # Нечего коммитить – выходим
            logger.debug("GitHubBackup: nothing to commit")
            return
        # Запушить
        subprocess.check_call(["git", "push", self.remote, self.branch])
        logger.info("GitHubBackup: committed and pushed")
