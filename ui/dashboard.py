"""Dashboard tab: account overview, equity chart, system status, quick actions."""
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QFrame, QPushButton,
    QMessageBox, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates
from datetime import datetime, timezone

from ui.styles import theme

logger = logging.getLogger(__name__)


class DashboardTab(QWidget):
    # Сигналы для быстрых действий
    close_all_requested = pyqtSignal()
    close_longs_requested = pyqtSignal()
    close_shorts_requested = pyqtSignal()
    close_50_requested = pyqtSignal()

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._equity_data = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Заголовок
        header = QLabel("Dashboard")
        header.setFont(theme.FONTS['header'])
        layout.addWidget(header)

        # Светофор здоровья
        health_layout = QHBoxLayout()
        self.health_light = QLabel("●")
        self.health_light.setFont(theme.FONTS['large'])
        self.health_label = QLabel("Bot Status")
        self.health_label.setFont(theme.FONTS['header'])
        health_layout.addWidget(self.health_light)
        health_layout.addWidget(self.health_label)
        health_layout.addStretch()
        layout.addLayout(health_layout)

        # Сетка показателей
        grid = QGridLayout()
        grid.setSpacing(10)

        self.lbl_balance = QLabel("0.00 USDT")
        self.lbl_balance.setFont(theme.FONTS['large'])
        self.lbl_equity = QLabel("0.00 USDT")
        self.lbl_equity.setFont(theme.FONTS['large'])
        self.lbl_daily_pnl = QLabel("+0.00 USDT")
        self.lbl_daily_pnl.setFont(theme.FONTS['large'])
        self.lbl_unreal = QLabel("0.00 USDT")
        self.lbl_positions = QLabel("0")
        self.lbl_winrate = QLabel("0%")
        self.lbl_connection = QLabel("⚫")
        self.lbl_session = QLabel("Unknown")
        self.lbl_regime = QLabel("unknown")

        grid.addWidget(QLabel("Баланс"), 0, 0)
        grid.addWidget(self.lbl_balance, 0, 1)
        grid.addWidget(QLabel("Эквити"), 1, 0)
        grid.addWidget(self.lbl_equity, 1, 1)
        grid.addWidget(QLabel("Сегодня"), 2, 0)
        grid.addWidget(self.lbl_daily_pnl, 2, 1)
        grid.addWidget(QLabel("Нереализованный PnL"), 3, 0)
        grid.addWidget(self.lbl_unreal, 3, 1)
        grid.addWidget(QLabel("Открыто позиций"), 4, 0)
        grid.addWidget(self.lbl_positions, 4, 1)
        grid.addWidget(QLabel("Win Rate"), 5, 0)
        grid.addWidget(self.lbl_winrate, 5, 1)
        grid.addWidget(QLabel("Связь"), 6, 0)
        grid.addWidget(self.lbl_connection, 6, 1)
        grid.addWidget(QLabel("Сессия"), 7, 0)
        grid.addWidget(self.lbl_session, 7, 1)
        grid.addWidget(QLabel("Режим рынка"), 8, 0)
        grid.addWidget(self.lbl_regime, 8, 1)

        layout.addLayout(grid)

        # Быстрые действия
        actions_layout = QHBoxLayout()
        self.btn_close_all = QPushButton("Закрыть ВСЁ")
        self.btn_close_all.setObjectName("danger")
        self.btn_close_all.clicked.connect(self._on_close_all)
        actions_layout.addWidget(self.btn_close_all)

        self.btn_close_longs = QPushButton("Закрыть LONG")
        self.btn_close_longs.clicked.connect(self._on_close_longs)
        actions_layout.addWidget(self.btn_close_longs)

        self.btn_close_shorts = QPushButton("Закрыть SHORT")
        self.btn_close_shorts.clicked.connect(self._on_close_shorts)
        actions_layout.addWidget(self.btn_close_shorts)

        self.btn_close_50 = QPushButton("Закрыть 50% всех")
        self.btn_close_50.clicked.connect(self._on_close_50)
        actions_layout.addWidget(self.btn_close_50)

        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        # График эквити
        self.figure = Figure(figsize=(10, 3), dpi=80)
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        layout.addStretch()

    def update_data(self, status: dict):
        try:
            self.lbl_balance.setText(f"{status.get('balance', 0):.2f} USDT")
            self.lbl_equity.setText(f"{status.get('equity', 0):.2f} USDT")
            daily = status.get('daily_pnl', 0)
            self.lbl_daily_pnl.setText(f"{daily:+.2f} USDT")
            self.lbl_daily_pnl.setStyleSheet(
                f"color: {'#34d399' if daily >= 0 else '#f87171'};"
            )
            self.lbl_unreal.setText(f"{status.get('unrealized_pnl', 0):.2f} USDT")
            self.lbl_positions.setText(str(status.get('open_positions', 0)))
            self.lbl_winrate.setText(f"{status.get('win_rate', 0):.1f}%")
            self.lbl_connection.setText("🟢" if status.get('connected') else "🔴")
            self.lbl_session.setText(status.get('session', 'Unknown'))
            self.lbl_regime.setText(status.get('market_regime', 'unknown'))
            self._update_health(status)
        except Exception as e:
            logger.debug(f"Dashboard update error: {e}")

    def _update_health(self, status: dict):
        """Обновляет светофор здоровья."""
        if not status.get('running'):
            color, text = 'gray', 'Остановлен'
        elif status.get('paused'):
            color, text = '#fbbf24', 'Приостановлен'
        elif not status.get('connected'):
            color, text = '#f87171', 'Нет связи'
        elif status.get('demo_mode'):
            color, text = '#60a5fa', 'Демо'
        elif status.get('night_mode'):
            color, text = '#818cf8', 'Ночной режим'
        else:
            color, text = '#34d399', 'Активен'

        self.health_light.setStyleSheet(f"color: {color};")
        self.health_label.setText(text)

    def update_equity_chart(self, equity_data):
        self._equity_data = equity_data
        if not equity_data:
            return
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        times = [datetime.fromisoformat(e['time']) for e in equity_data]
        values = [e['equity'] for e in equity_data]
        ax.plot(times, values, color='#34d399')
        ax.fill_between(times, values, alpha=0.2, color='#34d399')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.set_title("Equity Curve")
        self.canvas.draw()

    def update_stats(self, stats: dict):
        if 'balance' in stats:
            self.lbl_balance.setText(f"{stats['balance']:.2f} USDT")
        if 'equity' in stats:
            self.lbl_equity.setText(f"{stats['equity']:.2f} USDT")

    def apply_theme(self):
        pass

    # ---------- Быстрые действия ----------
    def _on_close_all(self):
        reply = QMessageBox.question(self, "Подтверждение", "Закрыть ВСЕ позиции?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.close_all_requested.emit()

    def _on_close_longs(self):
        reply = QMessageBox.question(self, "Подтверждение", "Закрыть все LONG?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.close_longs_requested.emit()

    def _on_close_shorts(self):
        reply = QMessageBox.question(self, "Подтверждение", "Закрыть все SHORT?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.close_shorts_requested.emit()

    def _on_close_50(self):
        reply = QMessageBox.question(self, "Подтверждение", "Закрыть 50% всех позиций?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.close_50_requested.emit()
