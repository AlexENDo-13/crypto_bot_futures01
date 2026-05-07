"""
Sound Manager – now uses text‑to‑speech (pyttsx3) for all events if available.
Falls back to WAV files, or beep if nothing else works.
"""
import logging
import os
from typing import Dict

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
    def __init__(self, profile: str = 'trader', volume: float = 1.0):
        self._profile = profile
        self._volume = max(0.0, min(1.0, volume))
        self._sounds: Dict[str, str] = {}
        self._active_events = set(PROFILES.get(profile, []))
        self._tts_engine = None

        if TTS_AVAILABLE:
            try:
                self._tts_engine = pyttsx3.init()
                self._tts_engine.setProperty('rate', 180)
                self._tts_engine.setProperty('volume', self._volume)
                voices = self._tts_engine.getProperty('voices')
                for voice in voices:
                    if 'russian' in voice.name.lower() or 'ru' in voice.id:
                        self._tts_engine.setProperty('voice', voice.id)
                        break
                logger.info("TTS engine initialised for SoundManager")
            except Exception as e:
                logger.warning(f"TTS init failed: {e}")

        for event, path in DEFAULT_SOUNDS.items():
            self._sounds[event] = path if os.path.exists(path) else ''

    def play(self, event: str):
        if event not in self._active_events:
            return

        # 1. TTS
        if self._tts_engine:
            try:
                phrase = PHRASES.get(event, event)
                self._tts_engine.say(phrase)
                self._tts_engine.runAndWait()
                return
            except Exception as e:
                logger.debug(f"TTS failed: {e}")

        # 2. WAV file
        if SOUND_AVAILABLE:
            path = self._sounds.get(event)
            if path and os.path.exists(path):
                try:
                    winsound.PlaySound(path, winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                    return
                except Exception:
                    pass

        # 3. System beep
        if SOUND_AVAILABLE:
            try:
                winsound.Beep(800, 200)
            except Exception:
                pass
