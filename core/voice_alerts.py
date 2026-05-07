"""
Voice Alert System – text‑to‑speech notifications for important events.
Uses pyttsx3 (offline) or system 'say' command as fallback.
"""
import logging
import threading
import time
from typing import Optional

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

logger = logging.getLogger(__name__)

class VoiceAlerter:
    """Генерирует голосовые сообщения при срабатывании алертов."""

    def __init__(self, engine):
        self.engine = engine
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_spoken = {}
        self._cooldown = 300  # секунд, чтобы не повторяться часто
        self._tts_engine = None

        if TTS_AVAILABLE:
            try:
                self._tts_engine = pyttsx3.init()
                self._tts_engine.setProperty('rate', 150)
            except Exception as e:
                logger.warning(f"VoiceAlerter init error: {e}")

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("VoiceAlerter started")

    def stop(self):
        self._running = False

    def _monitor_loop(self):
        while self._running:
            try:
                status = self.engine.get_status()
                self._check_alerts(status)
            except Exception as e:
                logger.error(f"VoiceAlerter error: {e}")
            time.sleep(10)

    def _check_alerts(self, status: dict):
        now = time.time()
        # Примеры критических ситуаций
        alerts = []

        # Баланс ниже 50 USDT
        if status.get('balance', 0) < 50:
            alerts.append("Внимание! Баланс ниже 50 долларов!")

        # Просадка более 15%
        if (status.get('unrealized_pnl', 0) / max(1, status.get('balance', 1))) < -0.15:
            alerts.append("Критическая просадка! Нереализованный убыток превысил 15 процентов.")

        # Экстренный локдаун
        if hasattr(self.engine.risk_controller, '_emergency_lock') and self.engine.risk_controller._emergency_lock:
            alerts.append("Экстренный стоп активирован. Все позиции закрыты, торговля остановлена.")

        for msg in alerts:
            last = self._last_spoken.get(msg, 0)
            if now - last >= self._cooldown:
                self._speak(msg)
                self._last_spoken[msg] = now

    def _speak(self, text: str):
        logger.info(f"Voice alert: {text}")
        if self._tts_engine:
            try:
                self._tts_engine.say(text)
                self._tts_engine.runAndWait()
            except Exception:
                self._fallback_speak(text)
        else:
            self._fallback_speak(text)

    def _fallback_speak(self, text: str):
        """Использует системные средства."""
        import subprocess, platform
        system = platform.system()
        try:
            if system == 'Darwin':
                subprocess.run(['say', text])
            elif system == 'Windows':
                import winsound
                winsound.Beep(1000, 500)  # короткий сигнал, если нет TTS
        except Exception:
            pass
