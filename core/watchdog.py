"""
Watchdog: monitors bot health and restarts if hanging.
"""
import logging
import time
import threading
import traceback
from datetime import datetime, timezone
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class Watchdog:
    """
    Monitors the main bot thread and restarts it if it becomes unresponsive.
    """
    
    def __init__(self, timeout_seconds: float = 120.0, 
                 check_interval: float = 10.0,
                 restart_callback: Optional[Callable] = None):
        self.timeout = timeout_seconds
        self.check_interval = check_interval
        self.restart_callback = restart_callback
        self._last_heartbeat: float = time.time()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._main_thread_running = False
        self._restart_count = 0
        self._last_restart_time: Optional[float] = None
        self._on_restart_callbacks: list = []
    
    def register_restart_callback(self, callback: Callable):
        """Register a callback to run on restart."""
        self._on_restart_callbacks.append(callback)
    
    def heartbeat(self):
        """Call this regularly from the main thread to show it's alive."""
        self._last_heartbeat = time.time()
        self._main_thread_running = True
    
    def start(self):
        """Start the watchdog monitoring thread."""
        self._running = True
        self._thread = threading.Thread(target=self._monitor, daemon=True, name="Watchdog")
        self._thread.start()
        logger.info(f"Watchdog started (timeout: {self.timeout}s)")
    
    def stop(self):
        """Stop the watchdog."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Watchdog stopped")
    
    def _monitor(self):
        """Main watchdog monitoring loop."""
        while self._running:
            time.sleep(self.check_interval)
            
            if not self._main_thread_running:
                # Bot hasn't started yet
                continue
            
            elapsed = time.time() - self._last_heartbeat
            
            if elapsed > self.timeout:
                logger.error(f"Watchdog: Main thread unresponsive for {elapsed:.0f}s! Restarting...")
                self._perform_restart()
    
    def _perform_restart(self):
        """Perform bot restart."""
        self._restart_count += 1
        self._last_restart_time = time.time()
        
        logger.info(f"Watchdog restart #{self._restart_count} initiated")
        
        # Run restart callbacks
        for callback in self._on_restart_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Restart callback error: {e}")
        
        # Call main restart callback if provided
        if self.restart_callback:
            try:
                self.restart_callback()
            except Exception as e:
                logger.error(f"Main restart callback error: {e}")
                traceback.print_exc()
        
        # Reset heartbeat
        self._last_heartbeat = time.time()
        logger.info("Watchdog restart completed")
    
    def get_stats(self) -> dict:
        """Get watchdog statistics."""
        elapsed = time.time() - self._last_heartbeat
        return {
            'running': self._running,
            'timeout_seconds': self.timeout,
            'time_since_heartbeat': elapsed,
            'is_healthy': elapsed < self.timeout,
            'restart_count': self._restart_count,
            'last_restart': datetime.fromtimestamp(self._last_restart_time, timezone.utc).isoformat() 
                            if self._last_restart_time else None,
        }
