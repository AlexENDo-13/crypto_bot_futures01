"""
On-chain filter: monitors large BTC transactions (Whale Alert)
and exchange net flows (Blockchain.com). Blocks signals when
unusual activity is detected.
"""
import logging
import time
import requests
from typing import Optional, Dict, Any

from filters.base import BaseFilter
from strategies.base import Signal

logger = logging.getLogger(__name__)

class OnChainFilter(BaseFilter):
    NAME = "OnChainFilter"
    DESCRIPTION = "Block signals during large on-chain movements"
    PRIORITY = 8
    PARAMS = {
        'enabled': False,                     # отключено
        'min_btc_amount': 500,
        'max_tx_per_hour': 3,
        'use_whale_alert': True,
        'use_blockchain_com': True,
        'cache_seconds': 600,
        'api_timeout': 3,
        'max_errors': 3,
        'disable_minutes': 10
    }

    def __init__(self, params=None):
        super().__init__(params)
        self._last_check = 0
        self._cached_score = 0
        self._error_count = 0
        self._disabled_until = 0

    def assess(self, signal: Signal, data: Dict[str, Any]) -> float:
        if not self.enabled:
            return signal.confidence
        # ... остальное без изменений
