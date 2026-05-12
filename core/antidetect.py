"""
Anti-detection measures: random delays, User-Agent rotation, human-like behavior.
Enhanced for micro-mode: longer delays, lower request frequency.
"""
import random
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

logger = logging.getLogger(__name__)


class AntiDetect:
    """
    Anti-detection system to avoid being flagged as automated trading.
    Implements human-like behavior patterns.
    """
    
    # Pool of realistic browser User-Agents
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 OPR/108.0.0.0",
    ]
    
    def __init__(self, night_mode_slowdown: float = 2.0):
        self._current_ua: str = random.choice(self.USER_AGENTS)
        self._ua_last_update: datetime = datetime.now(timezone.utc)
        self._ua_update_interval: timedelta = timedelta(hours=random.uniform(1, 2))
        self._night_mode_slowdown = night_mode_slowdown
        self._night_mode: bool = False
        self._request_count: int = 0
        self._skipped_count: int = 0
        self._trade_delay_min: float = 2.0   # увеличен до 2 минут между сделками
        self._last_trade_time: float = 0
        
    def get_user_agent(self) -> str:
        """Get current User-Agent, rotate if needed."""
        now = datetime.now(timezone.utc)
        if now - self._ua_last_update > self._ua_update_interval:
            old_ua = self._current_ua[:30] + "..."
            self._rotate_user_agent()
            logger.debug(f"User-Agent rotated: {old_ua} -> {self._current_ua[:30]}...")
        return self._current_ua
    
    def _rotate_user_agent(self):
        """Select a new random User-Agent."""
        new_ua = self._current_ua
        while new_ua == self._current_ua:
            new_ua = random.choice(self.USER_AGENTS)
        self._current_ua = new_ua
        self._ua_last_update = datetime.now(timezone.utc)
        self._ua_update_interval = timedelta(hours=random.uniform(1, 2))
    
    def pre_request_delay(self):
        """Add random delay before API request. In micro-mode, delays are longer."""
        self._request_count += 1
        
        # Base delay: 800-2000ms (увеличено с 200-800ms)
        base_delay = random.uniform(0.8, 2.0)
        
        # Night mode multiplier
        if self._night_mode:
            base_delay *= self._night_mode_slowdown
        
        time.sleep(base_delay)
    
    def should_skip_update(self) -> bool:
        """
        Randomly skip data updates (15% chance) to appear human.
        Returns True if this update should be skipped.
        """
        if random.random() < 0.15:
            self._skipped_count += 1
            return True
        return False
    
    def post_trade_delay(self):
        """Add delay after trade to simulate human reaction time."""
        delay = random.uniform(3.0, 8.0)
        if self._night_mode:
            delay *= 1.5
        time.sleep(delay)
    
    def can_trade_now(self) -> bool:
        """Check if enough time has passed since last trade."""
        now = time.time()
        min_interval = self._trade_delay_min * 60  # Convert to seconds
        
        if now - self._last_trade_time < min_interval:
            return False
        
        self._last_trade_time = now
        return True
    
    def shuffle_scan_order(self, symbols: List[str]) -> List[str]:
        """Randomize the order of symbol scanning."""
        shuffled = symbols.copy()
        random.shuffle(shuffled)
        return shuffled
    
    def set_night_mode(self, enabled: bool):
        """Update night mode status."""
        self._night_mode = enabled
    
    def get_request_headers(self) -> dict:
        """Get realistic request headers."""
        return {
            'User-Agent': self.get_user_agent(),
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
        }
    
    def get_stats(self) -> dict:
        """Get anti-detect statistics."""
        return {
            'requests_made': self._request_count,
            'updates_skipped': self._skipped_count,
            'current_ua_age_hours': (datetime.now(timezone.utc) - self._ua_last_update).total_seconds() / 3600,
            'night_mode': self._night_mode,
            'min_trade_interval_min': self._trade_delay_min,
        }
