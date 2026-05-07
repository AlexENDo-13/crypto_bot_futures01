"""
Sound Manager – flexible audio notifications with profiles and volume control.
"""
import logging
import os
from typing import Dict, Optional

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

PROFILES = {
    'trader': ['trade_open', 'profit', 'loss', 'error', 'milestone'],
    'critical_only': ['loss', 'error'],
    'silent': [],
}


class SoundManager:
    """Централизованное управление звуками с профилями и громкостью."""

    def __init__(self, profile: str = 'trader', volume: float = 1.0):
        self._profile = profile
        self._volume = max(0.0, min(1.0, volume))
        self._sounds: Dict[str, str] = {}
        self._load_defaults()
        self._active_events = set(PROFILES.get(profile, []))

    def _load_defaults(self):
        for event, path in DEFAULT_SOUNDS.items():
            if os.path.exists(path):
                self._sounds[event] = path
            else:
                self._sounds[event] = ''

    def set_profile(self, profile: str):
        if profile in PROFILES:
            self._profile = profile
            self._active_events = set(PROFILES[profile])
            logger.info(f"Sound profile set to '{profile}'")

    def set_volume(self, volume: float):
        self._volume = max(0.0, min(1.0, volume))
        logger.info(f"Sound volume set to {self._volume:.0%}")

    def set_sound_file(self, event: str, filepath: str):
        if event in self._sounds:
            self._sounds[event] = filepath

    def enable_event(self, event: str):
        self._active_events.add(event)

    def disable_event(self, event: str):
        self._active_events.discard(event)

    def play(self, event: str):
        """Воспроизводит звук события, если он разрешён в текущем профиле."""
        if not SOUND_AVAILABLE:
            return
        if event not in self._active_events:
            return
        path = self._sounds.get(event)
        if not path or not os.path.exists(path):
            return
        try:
            # winsound не поддерживает громкость напрямую, используем SND_ASYNC
            winsound.PlaySound(path, winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception:
            logger.debug(f"Failed to play sound: {path}")

    def get_profile(self) -> str:
        return self._profile

    def get_volume(self) -> float:
        return self._volume
