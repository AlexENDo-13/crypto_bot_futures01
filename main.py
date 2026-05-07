"""BingX Trading Bot v2.0 – Main Entry Point (ALL MODULES ACTIVE)."""
import os, sys, time, logging, argparse
from pathlib import Path
from datetime import datetime, timezone

project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from PyQt5.QtWidgets import QApplication
from ui.styles import theme

__version__ = "2.0.0"

def setup_logging():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"bot_{datetime.now(timezone.utc).strftime('%Y%m%d')}.log"
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s')
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG); fh.setFormatter(formatter)
    ch = logging.StreamHandler(); ch.setLevel(logging.INFO); ch.setFormatter(formatter)
    root = logging.getLogger(); root.setLevel(logging.DEBUG); root.addHandler(fh); root.addHandler(ch)
    return log_file

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--console', action='store_true')
    args = parser.parse_args()

    setup_logging()
    logging.info(f"BingX Trading Bot v{__version__}")

    from core.auth import AuthManager
    from core.engine import TradingEngine

    auth = AuthManager()
    engine = TradingEngine(auth)
    engine.load_all_modules()

    try:
        from core.order_guard import OrderGuard
        engine.order_guard = OrderGuard(engine)
        if not auth.demo_mode:
            engine.order_guard.start()
            logging.info("OrderGuard started")
    except Exception as e:
        logging.warning(f"OrderGuard not started: {e}")

    try:
        from configparser import ConfigParser
        cfg = ConfigParser()
        cfg.read('config.ini')
        tg_token = cfg.get('TELEGRAM', 'bot_token', fallback='')
        tg_chat = cfg.get('TELEGRAM', 'chat_id', fallback='')
        tg_enabled = cfg.getboolean('TELEGRAM', 'enabled', fallback=False)

        if tg_enabled and tg_token and tg_chat:
            from telegram.bot import TelegramBot
            engine.telegram = TelegramBot(tg_token, tg_chat, engine)
            engine.telegram.start()
            logging.info("Telegram bot started")
    except Exception as e:
        logging.warning(f"Telegram bot not started: {e}")

    try:
        dc_token = cfg.get('DISCORD', 'bot_token', fallback='')
        dc_channel = cfg.getint('DISCORD', 'channel_id', fallback=0)
        dc_enabled = cfg.getboolean('DISCORD', 'enabled', fallback=False)
        if dc_enabled and dc_token and dc_channel:
            from discord_bot import DiscordBot
            engine.discord = DiscordBot(dc_token, dc_channel, engine)
            engine.discord.start()
            logging.info("Discord bot started")
    except Exception as e:
        logging.warning(f"Discord bot not started: {e}")

    try:
        from web.tradingview_webhook import TradingViewWebhook
        webhook = TradingViewWebhook(engine, port=8080)
        webhook.start()
    except Exception as e:
        logging.warning(f"TradingView webhook not started: {e}")

    try:
        from web.server import WebServer
        engine.web_server = WebServer(engine, host="0.0.0.0", port=5000)
        engine.web_server.start()
        logging.info("Web dashboard started on http://0.0.0.0:5000")
    except ImportError:
        logging.warning("Flask not installed – web dashboard disabled. pip install flask flask-cors")
    except Exception as e:
        logging.warning(f"Web dashboard not started: {e}")

    try:
        from ml.sliding_backtest import SlidingBacktest
        engine.backtest = SlidingBacktest(engine)
        if not auth.demo_mode:
            engine.backtest.start()
    except Exception as e:
        logging.warning(f"Sliding backtest not started: {e}")

    try:
        from ml.bayesian_optimizer import BayesianOptimizer
        engine.bayes_opt = BayesianOptimizer(engine)
        if not auth.demo_mode:
            engine.bayes_opt.start()
            logging.info("Bayesian optimizer started")
    except Exception as e:
        logging.warning(f"Bayesian optimizer not started: {e}")

    try:
        from ml.capital_allocator import CapitalAllocator
        engine.capital_alloc = CapitalAllocator(engine)
        engine.capital_alloc.start()
        logging.info("CapitalAllocator started")
    except Exception as e:
        logging.warning(f"CapitalAllocator not started: {e}")

    try:
        from core.tf_selector import TimeframeSelector
        engine.tf_selector = TimeframeSelector(engine)
        engine.tf_selector.start()
        logging.info("TimeframeSelector started")
    except Exception as e:
        logging.warning(f"TimeframeSelector not started: {e}")

    try:
        onchain_enabled = cfg.getboolean('ONCHAIN', 'enabled', fallback=False)
        if onchain_enabled:
            glassnode_key = cfg.get('ONCHAIN', 'glassnode_key', fallback='')
            cryptoquant_key = cfg.get('ONCHAIN', 'cryptoquant_key', fallback='')
            from ml.onchain_metrics import OnChainMetrics
            engine.onchain = OnChainMetrics(glassnode_key, cryptoquant_key)
            engine.onchain.start()
            logging.info("OnChainMetrics started")
    except Exception as e:
        logging.warning(f"OnChainMetrics not started: {e}")

    try:
        from core.alert_manager import AlertManager
        engine.alert_mgr = AlertManager(engine)
        engine.alert_mgr.start()
        logging.info("AlertManager started")
    except Exception as e:
        logging.warning(f"AlertManager not started: {e}")

    try:
        if tg_enabled:
            from core.backup_manager import BackupManager
            engine.backup_mgr = BackupManager(engine)
            engine.backup_mgr.start()
            logging.info("BackupManager started")
    except Exception as e:
        logging.warning(f"BackupManager not started: {e}")

    try:
        from core.github_backup import GitHubBackup
        engine.github_backup = GitHubBackup()
        engine.github_backup.start()
        logging.info("GitHubBackup started")
    except Exception as e:
        logging.warning(f"GitHubBackup not started: {e}")

    # ---------- Moonshot с параметрами из конфига ----------
    try:
        from core.moonshot import MoonshotTrader
        moonshot_capital_pct = cfg.getfloat('MOONSHOT', 'capital_pct', fallback=10.0)
        moonshot_max_risk = cfg.getfloat('MOONSHOT', 'max_risk_pct', fallback=1.0)
        moonshot_scan = cfg.getint('MOONSHOT', 'scan_interval', fallback=300)
        engine.moonshot = MoonshotTrader(engine, capital_pct=moonshot_capital_pct,
                                         max_risk_pct=moonshot_max_risk,
                                         scan_interval=moonshot_scan)
        engine.moonshot.start()
        logging.info(f"MoonshotTrader started (capital %.1f%%, max_risk %.1f%%, scan %ds)",
                     moonshot_capital_pct, moonshot_max_risk, moonshot_scan)
    except Exception as e:
        logging.warning(f"MoonshotTrader not started: {e}")

    try:
        from ml.portfolio_stress_test import StressTestRunner
        engine.stress_test = StressTestRunner(engine)
        engine.stress_test.start()
        logging.info("StressTestRunner started")
    except Exception as e:
        logging.warning(f"StressTestRunner not started: {e}")

    try:
        from core.voice_alerts import VoiceAlerter
        engine.voice = VoiceAlerter(engine)
        engine.voice.start()
        logging.info("VoiceAlerter started")
    except Exception as e:
        logging.warning(f"VoiceAlerter not started: {e}")

    if args.console:
        engine.start()
        logging.info("Bot running (console). Ctrl+C to stop.")
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            engine.stop()
    else:
        app = QApplication(sys.argv)
        app.setStyleSheet(theme.get_stylesheet())
        from ui.main_window import MainWindow
        window = MainWindow(engine)
        window.show()
        engine.start()
        sys.exit(app.exec_())

if __name__ == "__main__":
    main()
