"""
Main application window with tabbed interface.
"""
import sys, os, logging
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QLabel, QPushButton, QStatusBar,
    QMessageBox, QApplication, QFrame
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject

from ui.styles import theme
from ui.dashboard import DashboardTab
from ui.signals import SignalsTab
from ui.positions import PositionsTab
from ui.settings import SettingsTab
from ui.logs import LogsTab
from ui.backtest import BacktestTab
from ui.blacklist import BlacklistTab
from ui.system import SystemTab
from ui.chart import ChartTab
from ui.strategy_stats import StrategyStatsTab

logger = logging.getLogger(__name__)


class SignalBridge(QObject):
    status_update = pyqtSignal(dict)
    log_message = pyqtSignal(str, str)
    position_update = pyqtSignal(list)
    equity_update = pyqtSignal(list)


class MainWindow(QMainWindow):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.bridge = SignalBridge()

        self.setWindowTitle("BingX Trading Bot")
        self.setMinimumSize(1400, 900)

        self._setup_ui()
        self._setup_timer()
        self._connect_signals()
        self.apply_theme()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = self._create_top_bar()
        layout.addWidget(top_bar)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.tab_dashboard = DashboardTab(self.engine)
        self.tab_signals = SignalsTab(self.engine)
        self.tab_positions = PositionsTab(self.engine)
        self.tab_settings = SettingsTab(self.engine)
        self.tab_logs = LogsTab(self.engine)
        self.tab_backtest = BacktestTab(self.engine)
        self.tab_blacklist = BlacklistTab(self.engine)
        self.tab_system = SystemTab(self.engine)
        self.tab_chart = ChartTab(self.engine)
        self.tab_strategy_stats = StrategyStatsTab(self.engine)

        self.tabs.addTab(self.tab_dashboard, "Dashboard")
        self.tabs.addTab(self.tab_signals, "Signals")
        self.tabs.addTab(self.tab_positions, "Positions")
        self.tabs.addTab(self.tab_settings, "Settings")
        self.tabs.addTab(self.tab_logs, "Logs")
        self.tabs.addTab(self.tab_backtest, "Backtest")
        self.tabs.addTab(self.tab_blacklist, "Blacklist")
        self.tabs.addTab(self.tab_system, "System")
        self.tabs.addTab(self.tab_chart, "Chart")
        self.tabs.addTab(self.tab_strategy_stats, "Strategy Stats")

        layout.addWidget(self.tabs)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_connection = QLabel("Disconnected")
        self.status_mode = QLabel("DEMO")
        self.status_bot = QLabel("Stopped")
        self.status_positions = QLabel("Positions: 0")
        self.status_ping = QLabel("Ping: --")

        self.status_bar.addWidget(self.status_connection)
        self.status_bar.addWidget(self.status_mode)
        self.status_bar.addWidget(self.status_bot)
        self.status_bar.addWidget(self.status_positions)
        self.status_bar.addPermanentWidget(self.status_ping)

    def _create_top_bar(self):
        bar = QFrame()
        bar.setObjectName("topBar")
        bar.setMaximumHeight(50)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(15, 5, 15, 5)

        title = QLabel("BingX Trading Bot")
        title.setFont(theme.FONTS['header'])
        title.setStyleSheet(f"color: {theme.colors['accent']};")
        layout.addWidget(title)

        layout.addStretch()

        self.btn_start = QPushButton("Start")
        self.btn_start.setObjectName("success")
        self.btn_start.setFixedWidth(80)
        self.btn_start.clicked.connect(self._on_start)
        layout.addWidget(self.btn_start)

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setObjectName("warning")
        self.btn_pause.setFixedWidth(80)
        self.btn_pause.clicked.connect(self._on_pause)
        self.btn_pause.setEnabled(False)
        layout.addWidget(self.btn_pause)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.setFixedWidth(80)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setEnabled(False)
        layout.addWidget(self.btn_stop)

        layout.addSpacing(20)

        self.btn_theme = QPushButton("Theme")
        self.btn_theme.setFixedWidth(70)
        self.btn_theme.clicked.connect(self._toggle_theme)
        layout.addWidget(self.btn_theme)

        return bar

    def _setup_timer(self):
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_ui)
        self.update_timer.start(2000)

    def _connect_signals(self):
        self.bridge.status_update.connect(self._handle_status_update)
        self.bridge.log_message.connect(self._handle_log_message)
        self.bridge.position_update.connect(self._handle_position_update)

    def _update_ui(self):
        try:
            status = self.engine.get_status()
            self.bridge.status_update.emit(status)

            self.tab_dashboard.update_data(status)
            self.tab_signals.update_data(status)

            positions = self.engine.portfolio.get_positions()
            pos_data = [p.to_dict() for p in positions]
            self.tab_positions.update_positions(pos_data)
            self.status_positions.setText(f"Positions: {len(positions)}")

            self.tab_strategy_stats.update_data(status)

            equity = self.engine.portfolio.get_equity_curve(days=7)
            if equity:
                self.tab_dashboard.update_equity_chart(equity)

            stats = self.engine.portfolio.get_stats()
            self.tab_dashboard.update_stats(stats)

        except Exception as e:
            logger.debug(f"UI update error: {e}")

    def _handle_status_update(self, status: dict):
        try:
            if status.get('connected'):
                self.status_connection.setText("Connected")
                self.status_connection.setStyleSheet(f"color: {theme.colors['success']};")
            else:
                self.status_connection.setText("Disconnected")
                self.status_connection.setStyleSheet(f"color: {theme.colors['danger']};")

            if status.get('demo_mode'):
                self.status_mode.setText("DEMO")
                self.status_mode.setStyleSheet(f"color: {theme.colors['warning']};")
            else:
                self.status_mode.setText("LIVE")
                self.status_mode.setStyleSheet(f"color: {theme.colors['danger']};")

            if status.get('running'):
                if status.get('paused'):
                    self.status_bot.setText("Paused")
                    self.status_bot.setStyleSheet(f"color: {theme.colors['warning']};")
                else:
                    self.status_bot.setText("Running")
                    self.status_bot.setStyleSheet(f"color: {theme.colors['success']};")
            else:
                self.status_bot.setText("Stopped")
                self.status_bot.setStyleSheet(f"color: {theme.colors['text_muted']};")

            ping = status.get('ping_ms')
            if ping:
                self.status_ping.setText(f"Ping: {ping:.0f}ms")
            else:
                self.status_ping.setText("Ping: --")
        except Exception as e:
            logger.debug(f"Status update error: {e}")

    def _handle_log_message(self, message: str, level: str):
        try:
            self.tab_logs.append_log(message, level)
        except Exception as e:
            logger.debug(f"Log message error: {e}")

    def _handle_position_update(self, positions: list):
        try:
            self.tab_positions.update_positions(positions)
        except Exception as e:
            logger.debug(f"Position update error: {e}")

    def _on_start(self):
        try:
            self.engine.start()
            self.btn_start.setEnabled(False)
            self.btn_pause.setEnabled(True)
            self.btn_stop.setEnabled(True)
            logger.info("Bot started from GUI")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to start: {e}")

    def _on_pause(self):
        if self.engine.is_paused():
            self.engine.resume()
            self.btn_pause.setText("Pause")
        else:
            self.engine.pause()
            self.btn_pause.setText("Resume")

    def _on_stop(self):
        reply = QMessageBox.question(
            self, "Confirm Stop",
            "Stop the trading bot?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.engine.stop()
            self.btn_start.setEnabled(True)
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.btn_pause.setText("Pause")
            logger.info("Bot stopped from GUI")

    def _toggle_theme(self):
        theme.toggle()
        self.apply_theme()

    def apply_theme(self):
        stylesheet = theme.get_stylesheet()
        QApplication.instance().setStyleSheet(stylesheet)
        for tab_attr in ['tab_dashboard', 'tab_signals', 'tab_positions', 'tab_settings',
                         'tab_logs', 'tab_backtest', 'tab_blacklist', 'tab_system',
                         'tab_chart', 'tab_strategy_stats']:
            tab = getattr(self, tab_attr, None)
            if tab and hasattr(tab, 'apply_theme'):
                tab.apply_theme()

    def closeEvent(self, event):
        reply = QMessageBox.question(
            self, "Confirm Exit",
            "Exit the application? The bot will be stopped.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.engine.stop()
            event.accept()
        else:
            event.ignore()
