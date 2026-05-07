"""
Sound Manager – flexible audio notifications with profiles and volume control.
Now uses text‑to‑speech (pyttsx3) for all events if available.
"""
import logging
import os
from typing import Dict, Optional

try:
    import pyttsx3
    TTS_AVAILABLE = True
except ImportError:
    TTS_AVAILABLE = False

try:
    import winsound
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False

logger = logging.getLogger(__name__)

DEFAULT_SOUNDS = {
    'trade_open': 'sounds/trade.wav',
    'profit': 'sounds/profit.wav',
    'loss': 'sounds/loss.wav',
    'error': 'sounds/error.wav',
    'milestone': 'sounds/milestone.wav',
}

# Русские фразы для TTS
PHRASES = {
    'trade_open': 'Открыта сделка',
    'profit': 'Прибыль',
    'loss': 'Убыток',
    'error': 'Ошибка',
    'milestone': 'Достигнут рубеж',
}

PROFILES = {
    'trader': ['trade_open', 'profit', 'loss', 'error', 'milestone'],
    'critical_only': ['loss', 'error'],
    'silent': [],
}


class SoundManager:
    """Централизованное управление звуками с профилями и голосом."""

    def __init__(self, profile: str = 'trader', volume: float = 1.0):
        self._profile = profile
        self._volume = max(0.0, min(1.0, volume))
        self._sounds: Dict[str, str] = {}
        self._load_defaults()
        self._active_events = set(PROFILES.get(profile, []))
        self._tts_engine = None

        if TTS_AVAILABLE:
            try:
                self._tts_engine = pyttsx3.init()
                self._tts_engine.setProperty('rate', 180)   # скорость речи
                self._tts_engine.setProperty('volume', self._volume)
                # Попробуем установить русский голос
                voices = self._tts_engine.getProperty('voices')
                for voice in voices:
                    if 'russian' in voice.name.lower() or 'ru' in voice.id:
                        self._tts_engine.setProperty('voice', voice.id)
                        break
                logger.info("TTS engine initialised for SoundManager")
            except Exception as e:
                logger.warning(f"TTS init failed: {e}")

    def _load_defaults(self):
        for event, path in DEFAULT_SOUNDS.items():
            self._sounds[event] = path if os.path.exists(path) else ''

    def set_profile(self, profile: str):
        if profile in PROFILES:
            self._profile = profile
            self._active_events = set(PROFILES[profile])
            logger.info(f"Sound profile set to '{profile}'")

    def set_volume(self, volume: float):
        self._volume = max(0.0, min(1.0, volume))
        if self._tts_engine:
            self._tts_engine.setProperty('volume', self._volume)
        logger.info(f"Sound volume set to {self._volume:.0%}")

    def set_sound_file(self, event: str, filepath: str):
        if event in self._sounds:
            self._sounds[event] = filepath

    def enable_event(self, event: str):
        self._active_events.add(event)

    def disable_event(self, event: str):
        self._active_events.discard(event)

    def play(self, event: str):
        """Воспроизводит звук/речь для события, если оно разрешено в текущем профиле."""
        if event not in self._active_events:
            return

        # Приоритет – голосовой синтез
        if self._tts_engine:
            try:
                phrase = PHRASES.get(event, event)
                self._tts_engine.say(phrase)
                self._tts_engine.runAndWait()
                logger.debug(f"TTS spoken: {phrase}")
                return
            except Exception as e:
                logger.debug(f"TTS failed, falling back to WAV: {e}")

        # Fallback – WAV‑файл
        if not SOUND_AVAILABLE:
            return
        path = self._sounds.get(event)
        if path and os.path.exists(path):
            try:
                winsound.PlaySound(path, winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            except Exception:
                logger.debug(f"Failed to play sound: {path}")

    def get_profile(self) -> str:
        return self._profile

    def get_volume(self) -> float:
        return self._volume
