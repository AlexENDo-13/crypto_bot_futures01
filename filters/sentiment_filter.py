"""
Sentiment Filter – queries public crypto sentiment from Twitter/Reddit.
Uses free, no‑key API endpoints where possible.
"""
import logging
import requests
import time
from typing import Optional, Dict, Any

from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

# Бесплатный эндпоинт для альтернативных данных (без гарантии, можно заменить)
SENTIMENT_API = "https://api.alternative.me/fng/?limit=1"  # Fear & Greed Index

class SentimentFilter(BaseFilter):
    NAME = "SentimentFilter"
    DESCRIPTION = "Adjusts confidence based on market fear/greed"
    PRIORITY = 5  # Очень рано, чтобы перебить другие фильтры
    PARAMS = {
        'enabled': True,
        'cache_seconds': 1800,  # обновлять каждые 30 минут
        'extreme_fear_threshold': 20,  # ниже = экстремальный страх → BUY boost, SELL penalty
        'extreme_greed_threshold': 80, # выше = жадность → SELL boost, BUY penalty
    }

    def __init__(self, params=None):
        super().__init__(params)
        self._cached_value = None
        self._last_update = 0

    def assess(self, signal: Signal, data: Dict[str, Any]) -> float:
        if not self.enabled:
            return signal.confidence

        now = time.time()
        if now - self._last_update < self.config['cache_seconds']:
            fng = self._cached_value
        else:
            fng = self._fetch_fear_greed()
            self._cached_value = fng
            self._last_update = now

        if fng is None:
            return signal.confidence

        # Корректировка уверенности в зависимости от настроений
        if fng <= self.config['extreme_fear_threshold']:
            # Экстремальный страх: BUY становится более привлекательным, SELL — менее
            if signal.action == 'BUY':
                return min(1.0, signal.confidence * 1.2)
            else:
                return signal.confidence * 0.7
        elif fng >= self.config['extreme_greed_threshold']:
            # Экстремальная жадность: SELL более привлекателен
            if signal.action == 'SELL':
                return min(1.0, signal.confidence * 1.2)
            else:
                return signal.confidence * 0.7
        return signal.confidence

    def _fetch_fear_greed(self) -> Optional[int]:
        try:
            resp = requests.get(SENTIMENT_API, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # Структура ответа: {"name": "...", "data": [{"value": "34", ...}]}
                value_str = data['data'][0]['value']
                return int(value_str)
        except Exception as e:
            logger.warning(f"SentimentFilter fetch failed: {e}")
        return None
