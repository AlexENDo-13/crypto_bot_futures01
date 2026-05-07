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
        'enabled': False,                     # по умолчанию выключен, включите при необходимости
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
        """Возвращает уверенность сигнала (0‑1), блокируя при высоком риске."""
        if not self.enabled:
            return signal.confidence

        # Отключён из‑за ошибок?
        if self._disabled_until and time.time() < self._disabled_until:
            return signal.confidence

        try:
            now = time.time()
            if now - self._last_check < self.config['cache_seconds']:
                risk_score = self._cached_score
            else:
                risk_score = self._calculate_risk_score()
                self._cached_score = risk_score
                self._last_check = now
        except Exception:
            logger.exception("OnChain filter failed, allowing signal")
            return signal.confidence

        if risk_score > 0.7:
            logger.info(f"On-chain risk {risk_score:.2f}, blocking {signal.symbol}")
            return 0.0
        elif risk_score > 0.4:
            return signal.confidence * 0.7

        return signal.confidence

    def _calculate_risk_score(self) -> float:
        score = 0.0
        count = 0

        if self.config.get('use_whale_alert'):
            try:
                whale_score = self._check_whale_alert()
                if whale_score is not None:
                    score += whale_score
                    count += 1
            except Exception:
                logger.debug("Whale alert check failed")

        if self.config.get('use_blockchain_com'):
            try:
                bc_score = self._check_blockchain_com()
                if bc_score is not None:
                    score += bc_score
                    count += 1
            except Exception:
                logger.debug("Blockchain.com check failed")

        if count == 0:
            self._error_count += 1
            if self._error_count >= self.config['max_errors']:
                self._disabled_until = time.time() + self.config['disable_minutes'] * 60
                logger.warning(f"OnChainFilter disabled for {self.config['disable_minutes']} min "
                               f"due to {self._error_count} consecutive errors")
            return 0.0
        else:
            self._error_count = 0
            if self._disabled_until:
                self._disabled_until = 0
                logger.info("OnChainFilter re-enabled after successful response")

        avg_score = score / count
        return avg_score

    def _check_whale_alert(self) -> Optional[float]:
        try:
            url = "https://api.whale-alert.io/v1/transactions?limit=50&min_value=50000000"
            resp = requests.get(url, timeout=self.config['api_timeout'])
            if resp.status_code == 200:
                data = resp.json()
                txs = data.get('transactions', [])
                large_txs = [tx for tx in txs if tx.get('symbol') == 'BTC' and
                             tx.get('amount_usd', 0) > 1_000_000]
                if len(large_txs) > self.config['max_tx_per_hour']:
                    return 0.8
                elif large_txs:
                    return 0.3
            return 0.0
        except Exception:
            return None

    def _check_blockchain_com(self) -> Optional[float]:
        try:
            url = "https://blockchain.info/blocks?format=json"
            resp = requests.get(url, timeout=self.config['api_timeout'])
            if resp.status_code == 200:
                blocks = resp.json()
                total_txs = sum(b.get('tx', 1) for b in blocks)
                avg_tx_per_block = total_txs / len(blocks) if blocks else 0
                if avg_tx_per_block > 2000:
                    return 0.5
                return 0.0
            return 0.0
        except Exception:
            return None
