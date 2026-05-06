"""BingX Trading Bot v2.0 – Main Entry Point."""
import os, sys, time, logging, argparse, traceback
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

    # Запуск дополнительных сервисов
    try:
        from web.tradingview_webhook import TradingViewWebhook
        webhook = TradingViewWebhook(engine, port=8080)
        webhook.start()
    except Exception as e:
        logging.warning(f"TradingView webhook not started: {e}")

    try:
        from ml.sliding_backtest import SlidingBacktest
        backtest = SlidingBacktest(engine)
        backtest.start()
    except Exception as e:
        logging.warning(f"Sliding backtest not started: {e}")

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
