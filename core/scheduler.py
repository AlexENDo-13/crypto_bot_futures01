"""
Task scheduler with robust exception handling and console traceback.
"""
import logging
import time
import threading
import traceback
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, List

logger = logging.getLogger(__name__)


class Task:
    def __init__(self, name: str, interval_seconds: float,
                 callback: Callable, enabled: bool = True,
                 run_on_start: bool = False):
        self.name = name
        self.interval = interval_seconds
        self.callback = callback
        self.enabled = enabled
        self.last_run: Optional[float] = None
        self.run_count = 0
        self.error_count = 0
        self.run_on_start = run_on_start


class Scheduler:
    SESSIONS = {
        'Asian': (0, 8),
        'European': (8, 16),
        'American': (16, 24),
    }

    def __init__(self):
        self._tasks: Dict[str, Task] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._night_mode = False
        self._current_session = 'Unknown'
        self._callbacks: Dict[str, List[Callable]] = {
            'night_mode_on': [],
            'night_mode_off': [],
            'session_change': [],
            'new_day': [],
            'new_week': [],
            'new_month': [],
        }

    def register_task(self, name, interval, callback, enabled=True, run_on_start=False):
        self._tasks[name] = Task(name, interval, callback, enabled, run_on_start)
        logger.info(f"Registered task '{name}' (interval: {interval}s)")

    def enable_task(self, name):
        if name in self._tasks:
            self._tasks[name].enabled = True

    def disable_task(self, name):
        if name in self._tasks:
            self._tasks[name].enabled = False

    def set_task_interval(self, name, interval):
        if name in self._tasks:
            self._tasks[name].interval = interval

    def register_callback(self, event, callback):
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _trigger_event(self, event, *args, **kwargs):
        for cb in self._callbacks.get(event, []):
            try:
                cb(*args, **kwargs)
            except Exception:
                logger.exception(f"Callback error for {event}")

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="Scheduler")
        self._thread.start()
        logger.info("Scheduler started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Scheduler stopped")

    def _loop(self):
        # Run startup tasks
        for task in self._tasks.values():
            if task.run_on_start and task.enabled:
                self._execute_task(task)

        last_session_check = 0
        last_day = datetime.now(timezone.utc).day
        last_week = datetime.now(timezone.utc).isocalendar()[1]
        last_month = datetime.now(timezone.utc).month

        while self._running:
            try:
                now = time.time()
                now_dt = datetime.now(timezone.utc)

                # Проверка сессии и ночного режима
                if now - last_session_check >= 300:
                    self._check_session(now_dt)
                    self._check_night_mode(now_dt)
                    last_session_check = now

                # Проверка границ дня/недели/месяца
                if now_dt.day != last_day:
                    self._trigger_event('new_day')
                if now_dt.isocalendar()[1] != last_week:
                    self._trigger_event('new_week')
                if now_dt.month != last_month:
                    self._trigger_event('new_month')
                last_day, last_week, last_month = now_dt.day, now_dt.isocalendar()[1], now_dt.month

                # Запуск задач по расписанию
                for task in self._tasks.values():
                    if not task.enabled:
                        continue
                    if task.last_run is None or (now - task.last_run) >= task.interval:
                        # Ночной режим для market_scan
                        if self._night_mode and task.name == 'market_scan':
                            if task.last_run and (now - task.last_run) < task.interval * 2:
                                continue
                        self._execute_task(task)
            except Exception:
                print("*** SCHEDULER LOOP CRASHED ***")
                traceback.print_exc()
                logger.exception("Scheduler loop crashed")
            time.sleep(0.5)

    def _execute_task(self, task: Task):
        try:
            task.callback()
            task.last_run = time.time()
            task.run_count += 1
        except Exception:
            task.error_count += 1
            print(f"*** Task '{task.name}' crashed ***")
            traceback.print_exc()
            logger.exception(f"Task '{task.name}' crashed")

    def _check_session(self, now):
        hour = now.hour
        for session, (start, end) in self.SESSIONS.items():
            if start <= hour < end:
                if self._current_session != session:
                    old = self._current_session
                    self._current_session = session
                    self._trigger_event('session_change', old, session)
                break

    def _check_night_mode(self, now):
        hour = now.hour
        is_night = hour >= 19 or hour < 5
        if is_night and not self._night_mode:
            self._night_mode = True
            self._trigger_event('night_mode_on')
            logger.info("Night mode activated")
        elif not is_night and self._night_mode:
            self._night_mode = False
            self._trigger_event('night_mode_off')
            logger.info("Night mode deactivated")

    @property
    def night_mode(self):
        return self._night_mode

    @property
    def current_session(self):
        return self._current_session

    def get_task_stats(self):
        return {
            name: {
                'enabled': t.enabled,
                'run_count': t.run_count,
                'error_count': t.error_count,
                'last_run': t.last_run,
                'interval': t.interval,
            }
            for name, t in self._tasks.items()
        }
