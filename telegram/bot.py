"""
Enhanced Telegram bot for remote control and monitoring.
Supports commands: /start, /status, /positions, /close, /pause, /resume,
/stop, /risk, /report, /performance, /switch_profile, /enable_strat,
/disable_strat, /strategies, /filter_toggle, /filters.
"""
import logging
import threading
import time
import requests
from datetime import datetime, timezone
from typing import Optional, Callable

logger = logging.getLogger(__name__)

TELEGRAM_AVAILABLE = True

class TelegramBot:
    API_BASE = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, token: str = "", chat_id: str = "", engine=None):
        self.token = token
        self.chat_id = chat_id
        self.engine = engine
        self.enabled = bool(token and chat_id)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_update_id = 0
        self._command_handlers = {}
        self._register_default_handlers()

    def configure(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.enabled = bool(token and chat_id)

    def _register_default_handlers(self):
        self._command_handlers = {
            '/start': self._cmd_start,
            '/status': self._cmd_status,
            '/positions': self._cmd_positions,
            '/close': self._cmd_close,
            '/pause': self._cmd_pause,
            '/resume': self._cmd_resume,
            '/stop': self._cmd_emergency_stop,
            '/risk': self._cmd_risk,
            '/report': self._cmd_daily_report,
            '/performance': self._cmd_performance,
            '/switch_profile': self._cmd_switch_profile,
            '/enable_strat': self._cmd_enable_strategy,
            '/disable_strat': self._cmd_disable_strategy,
            '/strategies': self._cmd_list_strategies,
            '/filter_toggle': self._cmd_filter_toggle,
            '/filters': self._cmd_list_filters,
        }

    def start(self):
        if not self.enabled:
            logger.info("Telegram bot not configured, skipping")
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="TelegramBot")
        self._thread.start()
        self.send_message("✅ BingX Trading Bot started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def send_message(self, text: str, parse_mode: str = 'HTML', reply_markup: dict = None) -> bool:
        if not self.enabled:
            return False
        try:
            url = self.API_BASE.format(token=self.token, method='sendMessage')
            data = {
                'chat_id': self.chat_id,
                'text': text[:4096],
                'parse_mode': parse_mode,
                'disable_web_page_preview': True,
            }
            if reply_markup:
                data['reply_markup'] = reply_markup
            resp = requests.post(url, json=data, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    # ------------------------------------------------------------------
    def _poll_loop(self):
        while self._running:
            try:
                self._check_updates()
            except Exception:
                logger.exception("Telegram poll error")
            time.sleep(2)

    def _check_updates(self):
        url = self.API_BASE.format(token=self.token, method='getUpdates')
        params = {'offset': self._last_update_id + 1, 'timeout': 5, 'allowed_updates': ['message']}
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return
        updates = resp.json().get('result', [])
        for upd in updates:
            self._last_update_id = upd['update_id']
            msg = upd.get('message', {})
            text = msg.get('text', '')
            if text.startswith('/'):
                parts = text.split()
                cmd = parts[0].lower()
                handler = self._command_handlers.get(cmd)
                if handler:
                    handler(msg, parts[1:])

    # ---------- Стандартные команды ----------
    def _cmd_start(self, msg, args):
        keyboard = {
            'keyboard': [
                ['/status', '/positions'],
                ['/pause', '/resume'],
                ['/stop', '/risk'],
                ['/report', '/performance'],
                ['/strategies', '/filters'],
                ['/enable_strat', '/disable_strat'],
                ['/switch_profile', '/filter_toggle']
            ],
            'resize_keyboard': True,
            'one_time_keyboard': False
        }
        self.send_message("🤖 Доступные команды:", reply_markup=keyboard)

    def _cmd_status(self, msg, args):
        if not self.engine:
            return
        s = self.engine.get_status()
        text = f"""
📊 **Статус бота**
Баланс: {s['balance']:.2f} USDT
Эквити: {s['equity']:.2f} USDT
Дневной PnL: {s['daily_pnl']:.2f} USDT
Открытых позиций: {s['open_positions']}
Связь: {'🟢' if s['connected'] else '🔴'}
Режим: {'LIVE' if not s['demo_mode'] else 'DEMO'}
Сессия: {s.get('session','?')}
Режим рынка: {s.get('market_regime','?')}
        """
        self.send_message(text.strip())

    def _cmd_positions(self, msg, args):
        if not self.engine:
            return
        positions = self.engine.portfolio.get_positions()
        if not positions:
            self.send_message("📭 Нет открытых позиций")
            return
        for pos in positions:
            self.send_message(
                f"{pos.symbol} {pos.side}\n"
                f"Вход: {pos.entry_price:.6f} | PnL: {pos.unrealized_pnl:.4f} ({pos.pnl_pct:.1f}%)"
            )

    def _cmd_close(self, msg, args):
        if not self.engine or len(args) < 2:
            self.send_message("Используйте: /close SYMBOL LONG|SHORT")
            return
        symbol = args[0].upper()
        side = args[1].upper()
        try:
            self.engine.api.close_position(symbol, side)
            self.send_message(f"✅ Закрываю {symbol} {side}")
        except Exception as e:
            self.send_message(f"❌ Ошибка: {e}")

    def _cmd_pause(self, msg, args):
        if self.engine:
            self.engine.pause()
            self.send_message("⏸ Бот приостановлен")

    def _cmd_resume(self, msg, args):
        if self.engine:
            self.engine.resume()
            self.send_message("▶ Бот возобновлён")

    def _cmd_emergency_stop(self, msg, args):
        if not self.engine:
            return
        logger.critical("EMERGENCY STOP via Telegram")
        for pos in self.engine.portfolio.get_positions():
            try:
                self.engine.api.close_position(pos.symbol, pos.side)
            except Exception as e:
                logger.error(f"Emergency close failed for {pos.symbol}: {e}")
        self.engine.portfolio.clear()
        self.engine.risk_controller._emergency_lock = True
        self.engine.pause()
        self.send_message("🚨 ЭКСТРЕННЫЙ СТОП. Все позиции закрыты. Бот заблокирован до ручного снятия.")

    def _cmd_risk(self, msg, args):
        if not self.engine or not args:
            self.send_message("Используйте: /risk Conservative|Balanced|Aggressive|Adaptive")
            return
        profile = args[0].capitalize()
        try:
            self.engine.risk_manager.set_profile(profile)
            self.send_message(f"✅ Профиль риска изменён на {profile}")
        except Exception as e:
            self.send_message(f"❌ Ошибка: {e}")

    def _cmd_daily_report(self, msg, args):
        if not self.engine:
            return
        s = self.engine.get_status()
        text = f"""
📅 **Ежедневный отчёт**
PnL за день: {s['daily_pnl']:+.2f} USDT
Всего сделок: {s.get('total_trades', 0)}
Винрейт: {s.get('win_rate', 0):.1f}%
Открыто позиций: {s['open_positions']}
Баланс: {s['balance']:.2f}
Эквити: {s['equity']:.2f}
        """
        self.send_message(text.strip())

    # ---------- НОВЫЕ КОМАНДЫ ----------
    def _cmd_performance(self, msg, args):
        if not self.engine:
            return
        stats = self.engine.portfolio.get_stats()
        s = self.engine.get_status()
        text = f"""
📈 **Производительность**
Баланс: {stats['balance']:.2f} USDT
Эквити: {stats['equity']:.2f} USDT
Нереализованный PnL: {stats['unrealized_pnl']:.2f} USDT
Дневной PnL: {stats['daily_pnl']:.2f} USDT
Всего сделок: {stats['total_trades']}
Винрейт: {stats['win_rate']:.1f}%
Текущая просадка: {stats.get('current_drawdown_pct', 0):.2f}%
Активных стратегий: {s.get('strategies_loaded', 0)}
        """
        self.send_message(text.strip())

    def _cmd_switch_profile(self, msg, args):
        if not self.engine or not args:
            profiles = ", ".join(self.engine.risk_manager._profiles.keys())
            self.send_message(f"Доступные профили: {profiles}\nИспользуйте: /switch_profile ProfileName")
            return
        profile = args[0].capitalize()
        try:
            self.engine.risk_manager.set_profile(profile)
            self.send_message(f"✅ Профиль риска изменён на {profile}")
        except Exception as e:
            self.send_message(f"❌ Ошибка: {e}")

    def _cmd_list_strategies(self, msg, args):
        if not self.engine:
            return
        lines = ["🧠 **Стратегии**:"]
        for name, s in self.engine.strategies.items():
            status = "✅" if s.enabled else "❌"
            lines.append(f"{status} {name} (weight={s.weight:.2f})")
        self.send_message("\n".join(lines))

    def _cmd_enable_strategy(self, msg, args):
        if not self.engine or not args:
            self.send_message("Используйте: /enable_strat StrategyName")
            return
        name = args[0]
        if name in self.engine.strategies:
            self.engine.strategies[name].enabled = True
            if name in self.engine.voting._weights:
                self.engine.voting._weights[name]['disabled'] = False
                self.engine.voting._weights[name]['disabled_reason'] = None
                self.engine.voting._weights[name]['weight'] = 1.0
                self.engine.voting._save_weights()
            self.send_message(f"✅ Стратегия {name} включена")
        else:
            self.send_message(f"❌ Стратегия {name} не найдена")

    def _cmd_disable_strategy(self, msg, args):
        if not self.engine or not args:
            self.send_message("Используйте: /disable_strat StrategyName")
            return
        name = args[0]
        if name in self.engine.strategies:
            self.engine.strategies[name].enabled = False
            if name in self.engine.voting._weights:
                self.engine.voting._weights[name]['disabled'] = True
                self.engine.voting._weights[name]['disabled_reason'] = 'manual_telegram'
                self.engine.voting._weights[name]['weight'] = 0.0
                self.engine.voting._save_weights()
            self.send_message(f"⛔ Стратегия {name} отключена")
        else:
            self.send_message(f"❌ Стратегия {name} не найдена")

    def _cmd_list_filters(self, msg, args):
        if not self.engine:
            return
        lines = ["🔍 **Фильтры**:"]
        for name, f in self.engine.filters.items():
            status = "✅" if f.enabled else "❌"
            lines.append(f"{status} {name}")
        self.send_message("\n".join(lines))

    def _cmd_filter_toggle(self, msg, args):
        if not self.engine or not args:
            self.send_message("Используйте: /filter_toggle FilterName")
            return
        name = args[0]
        if name in self.engine.filters:
            flt = self.engine.filters[name]
            flt.enabled = not flt.enabled
            state = "включен" if flt.enabled else "отключен"
            self.send_message(f"🔁 Фильтр {name} {state}")
        else:
            self.send_message(f"❌ Фильтр {name} не найден")
