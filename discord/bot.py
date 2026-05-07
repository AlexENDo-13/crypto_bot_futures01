"""
Discord bot for remote monitoring and control of BingX Trading Bot.
Requires: pip install discord.py
"""
import logging
import threading
import asyncio
import discord
from discord.ext import commands
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DISCORD_AVAILABLE = True  # предполагаем, что discord.py установлен

class DiscordBot:
    def __init__(self, token: str, channel_id: int, engine):
        self.token = token
        self.channel_id = channel_id
        self.engine = engine
        self.bot = commands.Bot(command_prefix='/', intents=discord.Intents.default())
        self._register_commands()
        self._thread = None

    def _register_commands(self):
        @self.bot.event
        async def on_ready():
            logger.info(f"Discord bot logged in as {self.bot.user}")

        @self.bot.command(name='status', help='Показать статус бота')
        async def status(ctx):
            s = self.engine.get_status()
            msg = (
                f"**Баланс:** {s['balance']:.2f} USDT\n"
                f"**Эквити:** {s['equity']:.2f} USDT\n"
                f"**Сегодня:** {s['daily_pnl']:.2f} USDT\n"
                f"**Позиций:** {s['open_positions']}\n"
                f"**Связь:** {'🟢' if s['connected'] else '🔴'}\n"
                f"**Режим:** {'LIVE' if not s['demo_mode'] else 'DEMO'}\n"
                f"**Рынок:** {s.get('market_regime','?')}"
            )
            await ctx.send(msg)

        @self.bot.command(name='positions', help='Открытые позиции')
        async def positions(ctx):
            positions = self.engine.portfolio.get_positions()
            if not positions:
                await ctx.send("Нет открытых позиций")
                return
            for pos in positions:
                await ctx.send(
                    f"{pos.symbol} {pos.side} | Вход: {pos.entry_price:.6f} | "
                    f"PnL: {pos.unrealized_pnl:.4f} ({pos.pnl_pct:.1f}%)"
                )

        @self.bot.command(name='close', help='Закрыть позицию: /close SYMBOL LONG|SHORT')
        async def close(ctx, symbol: str, side: str):
            try:
                self.engine.close_position_manual(symbol.upper(), side.upper())
                await ctx.send(f"✅ Закрываю {symbol.upper()} {side.upper()}")
            except Exception as e:
                await ctx.send(f"❌ Ошибка: {e}")

        @self.bot.command(name='pause', help='Приостановить торговлю')
        async def pause(ctx):
            self.engine.pause()
            await ctx.send("⏸ Бот приостановлен")

        @self.bot.command(name='resume', help='Возобновить торговлю')
        async def resume(ctx):
            self.engine.resume()
            await ctx.send("▶ Бот возобновлён")

        @self.bot.command(name='stop', help='Экстренный стоп: закрыть все позиции и заблокировать')
        async def stop(ctx):
            for pos in self.engine.portfolio.get_positions():
                try:
                    self.engine.close_position_manual(pos.symbol, pos.side)
                except Exception as e:
                    logger.error(f"Emergency close failed for {pos.symbol}: {e}")
            self.engine.portfolio.clear()
            self.engine.risk_controller._emergency_lock = True
            self.engine.pause()
            await ctx.send("🚨 ЭКСТРЕННЫЙ СТОП. Все позиции закрыты. Бот заблокирован.")

        @self.bot.command(name='risk', help='Сменить профиль риска: /risk Conservative|Balanced|Aggressive|Adaptive')
        async def risk(ctx, profile: str):
            try:
                self.engine.risk_manager.set_profile(profile.capitalize())
                await ctx.send(f"✅ Профиль риска изменён на {profile.capitalize()}")
            except Exception as e:
                await ctx.send(f"❌ Ошибка: {e}")

        @self.bot.command(name='report', help='Ежедневный отчёт')
        async def report(ctx):
            s = self.engine.get_status()
            msg = (
                f"📅 **Ежедневный отчёт**\n"
                f"PnL за день: {s['daily_pnl']:+.2f} USDT\n"
                f"Всего сделок: {s.get('total_trades', 0)}\n"
                f"Винрейт: {s.get('win_rate', 0):.1f}%\n"
                f"Открыто позиций: {s['open_positions']}\n"
                f"Баланс: {s['balance']:.2f}\n"
                f"Эквити: {s['equity']:.2f}"
            )
            await ctx.send(msg)

    def start(self):
        if not self.token:
            logger.warning("Discord token not configured")
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Discord bot started")

    def _run(self):
        asyncio.run(self.bot.start(self.token))

    def stop(self):
        # корректное завершение не требуется, т.к. поток daemon
        pass
