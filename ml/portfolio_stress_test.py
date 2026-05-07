"""
Portfolio Stress Tester.
Simulates PnL impact of sudden market drops (10/20/30%) and sends report.
"""
import logging
import time
import threading
from datetime import datetime, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)

class StressTestRunner:
    """Периодически моделирует падение рынка и оценивает максимальную просадку."""

    def __init__(self, engine, interval_hours: int = 24):
        self.engine = engine
        self.interval = interval_hours * 3600
        self._running = False
        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("StressTestRunner started (interval %d hours)", self.interval // 3600)

    def stop(self):
        self._running = False

    def _loop(self):
        time.sleep(30)  # начальная задержка
        while self._running:
            try:
                report = self.run_test()
                self._send_report(report)
            except Exception as e:
                logger.error(f"StressTestRunner error: {e}")
            time.sleep(self.interval)

    def run_test(self) -> Dict[str, Any]:
        """Выполняет стресс‑тест и возвращает отчёт."""
        positions = self.engine.portfolio.get_positions()
        if not positions:
            return {'error': 'no positions'}

        total_exposure = sum(p.quantity * p.entry_price for p in positions)
        balance = self.engine.portfolio._balance or 0.0
        if balance <= 0:
            return {'error': 'zero balance'}

        report = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'balance': balance,
            'open_positions': len(positions),
            'total_exposure': total_exposure,
            'scenarios': {}
        }

        for drop_pct in [10, 20, 30]:
            # Предполагаем, что цена падает на drop_pct% для всех позиций
            loss = 0.0
            for p in positions:
                if p.side == 'LONG':
                    loss += p.quantity * p.entry_price * (drop_pct / 100.0)
                else:
                    loss -= p.quantity * p.entry_price * (drop_pct / 100.0)  # шорт зарабатывает
            new_equity = balance - loss
            drawdown = (balance - new_equity) / balance * 100.0 if balance > 0 else 0
            report['scenarios'][f'-{drop_pct}%'] = {
                'estimated_loss': round(loss, 2),
                'remaining_equity': round(new_equity, 2),
                'drawdown_pct': round(drawdown, 2)
            }

        return report

    def _send_report(self, report: Dict[str, Any]):
        if 'error' in report:
            return
        # Отправка через Telegram
        if hasattr(self.engine, 'telegram') and self.engine.telegram.enabled:
            lines = [f"📉 **Краш‑тест портфеля**"]
            for scenario, data in report['scenarios'].items():
                lines.append(f"{scenario}: убыток {data['estimated_loss']:.2f} USDT, "
                             f"эквити {data['remaining_equity']:.2f} (просадка {data['drawdown_pct']:.1f}%)")
            self.engine.telegram.send_message("\n".join(lines))
        logger.info(f"Stress test results: {report['scenarios']}")
