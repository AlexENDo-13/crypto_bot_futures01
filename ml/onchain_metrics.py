"""
On‑chain metrics aggregator (Glassnode, CryptoQuant, Whale Alert).
Feeds signals to OnChainFilter and provides market bias.
"""
import logging
import time
import requests
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Бесплатные/условно‑бесплатные API (требуют минимальной регистрации)
GLASSNODE_API = "https://api.glassnode.com/v1/metrics/indicators/"
CRYPTOQUANT_API = "https://api.cryptoquant.com/v1/"

class OnChainMetrics:
    """Собирает ключевые ончейн‑метрики и вычисляет бычий/медвежий индекс."""

    def __init__(self, glassnode_key: str = "", cryptoquant_key: str = ""):
        self.glassnode_key = glassnode_key
        self.cryptoquant_key = cryptoquant_key
        self._cache: Dict[str, float] = {}
        self._last_update = 0.0
        self._cache_ttl = 600  # 10 минут

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._bullish_score = 0.5  # 0 = медвежий, 1 = бычий

    def start(self):
        if not self.glassnode_key and not self.cryptoquant_key:
            logger.info("OnChainMetrics disabled – no API keys")
            return
        self._running = True
        self._thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._thread.start()
        logger.info("OnChainMetrics started")

    def stop(self):
        self._running = False

    def _refresh_loop(self):
        while self._running:
            try:
                self._fetch_metrics()
            except Exception as e:
                logger.error(f"OnChainMetrics error: {e}")
            time.sleep(self._cache_ttl)

    def _fetch_metrics(self):
        now = time.time()
        if now - self._last_update < self._cache_ttl:
            return
        metrics = {}
        if self.glassnode_key:
            metrics.update(self._fetch_glassnode())
        if self.cryptoquant_key:
            metrics.update(self._fetch_cryptoquant())
        self._cache = metrics
        self._last_update = now
        self._compute_bullish_score(metrics)

    def _fetch_glassnode(self) -> Dict[str, float]:
        try:
            # Пример: Net Unrealized Profit/Loss (NUPL)
            url = f"{GLASSNODE_API}nupl?a=BTC&api_key={self.glassnode_key}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                last_value = data[-1]['v'] if data else None
                return {'nupl': last_value} if last_value else {}
        except Exception as e:
            logger.warning(f"Glassnode fetch failed: {e}")
        return {}

    def _fetch_cryptoquant(self) -> Dict[str, float]:
        try:
            # Пример: Exchange Netflow
            url = f"{CRYPTOQUANT_API}btc/exchange-netflow?api_key={self.cryptoquant_key}"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # Допустим, есть поле 'netflow'
                netflow = data.get('netflow', 0)
                return {'exchange_netflow': netflow}
        except Exception as e:
            logger.warning(f"CryptoQuant fetch failed: {e}")
        return {}

    def _compute_bullish_score(self, metrics: Dict[str, float]):
        """Очень упрощённая эвристика для демонстрации."""
        score = 0.5
        if 'nupl' in metrics:
            nupl = metrics['nupl']
            if nupl > 0.75:
                score -= 0.2  # перекуплен
            elif nupl < 0.25:
                score += 0.2  # перепродан
        if 'exchange_netflow' in metrics:
            netflow = metrics['exchange_netflow']
            if netflow < -100:  # отток с бирж
                score += 0.1
            elif netflow > 100:  # приток на биржи
                score -= 0.1
        self._bullish_score = max(0.0, min(1.0, score))
        logger.debug(f"OnChain bullish score: {self._bullish_score:.2f}")

    def get_bullish_score(self) -> float:
        return self._bullish_score

    def get_metrics(self) -> Dict[str, float]:
        return self._cache.copy()
