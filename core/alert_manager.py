"""
User‑defined alerting system.
Monitors conditions (balance, drawdown, positions) and sends notifications
via Telegram (or other channels) when thresholds are breached.
"""
import logging
import time
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable

logger = logging.getLogger(__name__)

class AlertRule:
    """Одно правило алерта."""
    def __init__(self, name: str, condition: Callable[[dict], bool], message: str, cooldown_seconds: int = 3600):
        self.name = name
        self.condition = condition      # функция, принимает status_dict и возвращает bool
        self.message = message          # текст уведомления
        self.cooldown = cooldown_seconds
        self.last_triggered: float = 0.0

class AlertManager:
    """Периодически проверяет правила и отправляет уведомления."""

    def __init__(self, engine, check_interval: int = 120):
        self.engine = engine
        self.check_interval = check_interval
        self._rules: Dict[str, AlertRule] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Добавляем встроенные правила
        self._add_builtin_rules()

    def _add_builtin_rules(self):
        # Баланс ниже порога
        self.add_rule("low_balance", 
                      lambda s: s.get('balance', 0) < 100.0,
                      "⚠️ Баланс опустился ниже 100 USDT!")

        # Просадка > 10%
        self.add_rule("high_drawdown",
                      lambda s: s.get('open_positions', 0) > 0 and (s.get('unrealized_pnl', 0) / s.get('balance', 1) < -0.1),
                      "📉 Просадка по открытым позициям превысила 10%!")

        # Слишком много позиций (больше 80% лимита)
        self.add_rule("many_positions",
                      lambda s: s.get('open_positions', 0) >= self.engine.max_positions * 0.8,
                      f"ℹ️ Занято {self.engine.max_positions * 0.8:.0f}+ слотов позиций")

    def add_rule(self, name: str, condition: Callable, message: str, cooldown: int = 3600):
        self._rules[name] = AlertRule(name, condition, message, cooldown)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="AlertManager")
        self._thread.start()
        logger.info("AlertManager started")

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                status = self.engine.get_status()
                self._check_rules(status)
            except Exception as e:
                logger.error(f"AlertManager error: {e}")
            time.sleep(self.check_interval)

    def _check_rules(self, status: dict):
        now = time.time()
        for rule in self._rules.values():
            if now - rule.last_triggered < rule.cooldown:
                continue
            try:
                if rule.condition(status):
                    self._send_notification(rule.message)
                    rule.last_triggered = now
            except Exception as e:
                logger.error(f"Rule {rule.name} evaluation failed: {e}")

    def _send_notification(self, text: str):
        # Отправляем через Telegram, если доступен
        if hasattr(self.engine, 'telegram') and self.engine.telegram.enabled:
            try:
                self.engine.telegram.send_message(text)
                logger.info(f"Alert sent via Telegram: {text}")
            except Exception as e:
                logger.error(f"Telegram alert failed: {e}")
        # Отправляем через Discord, если доступен
        if hasattr(self.engine, 'discord'):
            try:
                # Discord бот может отправлять в заданный канал, если реализован
                # В нашем DiscordBot нет send_message, но можно добавить при необходимости
                pass
            except Exception as e:
                logger.error(f"Discord alert failed: {e}")
        # Всегда пишем в лог
        logger.warning(f"ALERT: {text}")
