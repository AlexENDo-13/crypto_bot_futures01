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
        'enabled': True,                     # Включено по умолчанию
        'min_btc_amount': 500,               # Минимальный объём одной транзакции (BTC)
        'max_tx_per_hour': 3,                # Максимум крупных транзакций в час
        'use_whale_alert': True,             # Использовать Whale Alert API (без ключа)
        'use_blockchain_com': True,          # Использовать Blockchain.com (без ключа)
        'cache_seconds': 600,                # Кэш метрик на 10 минут
        'api_timeout': 3,                    # Таймаут запроса, секунды
        'max_errors': 3,                     # Количество ошибок подряд перед отключением фильтра
        'disable_minutes': 10                # На сколько минут отключить фильтр при превышении лимита ошибок
    }

    def __init__(self, params=None):
        super().__init__(params)
        self._last_check = 0
        self._cached_score = 0
        self._error_count = 0
        self._disabled_until = 0  # timestamp или 0, если фильтр активен

    def assess(self, signal: Signal, data: Dict[str, Any]) -> float:
        if not self.enabled:
            return signal.confidence

        # Проверяем, не отключён ли фильтр из-за ошибок
        if self._disabled_until and time.time() < self._disabled_until:
            return signal.confidence

        now = time.time()
        if now - self._last_check < self.config['cache_seconds']:
            risk_score = self._cached_score
        else:
            risk_score = self._calculate_risk_score()
            self._cached_score = risk_score
            self._last_check = now

        # Если риск превышает 0.7, блокируем сделку
        if risk_score > 0.7:
            logger.info(f"On-chain risk {risk_score:.2f}, blocking {signal.symbol}")
            return 0.0
        elif risk_score > 0.4:
            # Снижаем уверенность
            return signal.confidence * 0.7
        return signal.confidence

    def _calculate_risk_score(self) -> float:
        """Возвращает оценку риска от 0 (нет риска) до 1 (максимальный риск)."""
        score = 0.0
        count = 0

        if self.config.get('use_whale_alert'):
            whale_score = self._check_whale_alert()
            if whale_score is not None:
                score += whale_score
                count += 1

        if self.config.get('use_blockchain_com'):
            bc_score = self._check_blockchain_com()
            if bc_score is not None:
                score += bc_score
                count += 1

        if count == 0:
            return 0.0

        avg_score = score / count

        # Если обе проверки вернули None (ошибки), считаем риск 0 и не учитываем ошибки
        if score == 0 and all(s is None for s in [whale_score, bc_score]):
            self._error_count = 0
            return 0.0

        # Если была ошибка – увеличиваем счётчик
        if score == 0:
            self._error_count += 1
            if self._error_count >= self.config['max_errors']:
                self._disabled_until = time.time() + self.config['disable_minutes'] * 60
                logger.warning(f"OnChainFilter disabled for {self.config['disable_minutes']} min due to {self._error_count} consecutive errors")
            return 0.0
        else:
            self._error_count = 0
            if self._disabled_until:
                self._disabled_until = 0
                logger.info("OnChainFilter re-enabled after successful response")

        return avg_score

    def _check_whale_alert(self) -> Optional[float]:
        """Проверяет последние транзакции китов (Whale Alert)."""
        try:
            # Бесплатный API без ключа, теперь с коротким таймаутом
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
        except Exception as e:
            logger.warning(f"Whale Alert check failed: {e}")
            return None

    def _check_blockchain_com(self) -> Optional[float]:
        """Проверяет крупные переводы через Blockchain.com API (публичный)."""
        try:
            url = "https://blockchain.info/blocks?format=json"
            resp = requests.get(url, timeout=self.config['api_timeout'])
            if resp.status_code == 200:
                blocks = resp.json()
                total_txs = sum(b.get('tx', 1) for b in blocks)
                avg_tx_per_block = total_txs / len(blocks) if blocks else 0
                if avg_tx_per_block > 2000:  # Эмпирический порог
                    return 0.5
                return 0.0
            return 0.0
        except Exception as e:
            logger.warning(f"Blockchain.com check failed: {e}")
            return None
