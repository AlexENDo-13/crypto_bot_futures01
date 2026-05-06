"""Dashboard tab: account overview, equity chart, system status."""
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout, QFrame, QProgressBar
)
from PyQt5.QtCore import Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates
from datetime import datetime, timezone

from ui.styles import theme

logger = logging.getLogger(__name__)

class DashboardTab(QWidget):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._setup_ui()
        self._equity_data = []

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Заголовок
        header = QLabel("Dashboard")
        header.setFont(theme.FONTS['header'])
        layout.addWidget(header)

        # Сетка показателей
        grid = QGridLayout()
        grid.setSpacing(10)

        self.lbl_balance = QLabel("0.00 USDT")
        self.lbl_balance.setFont(theme.FONTS['large'])
        self.lbl_equity = QLabel("0.00 USDT")
        self.lbl_equity.setFont(theme.FONTS['large'])
        self.lbl_unreal = QLabel("0.00 USDT")
        self.lbl_daily = QLabel("0.00 USDT")
        self.lbl_positions = QLabel("0")
        self.lbl_winrate = QLabel("0%")
        self.lbl_connection = QLabel("⚫")
        self.lbl_signals = QLabel("0")
        self.lbl_regime = QLabel("unknown")

        grid.addWidget(QLabel("Баланс"), 0, 0)
        grid.addWidget(self.lbl_balance, 0, 1)
        grid.addWidget(QLabel("Эквити"), 1, 0)
        grid.addWidget(self.lbl_equity, 1, 1)
        grid.addWidget(QLabel("Нереализованный PnL"), 2, 0)
        grid.addWidget(self.lbl_unreal, 2, 1)
        grid.addWidget(QLabel("Дневной PnL"), 3, 0)
        grid.addWidget(self.lbl_daily, 3, 1)
        grid.addWidget(QLabel("Открытых позиций"), 4, 0)
        grid.addWidget(self.lbl_positions, 4, 1)
        grid.addWidget(QLabel("Win Rate"), 5, 0)
        grid.addWidget(self.lbl_winrate, 5, 1)
        grid.addWidget(QLabel("Связь"), 6, 0)
        grid.addWidget(self.lbl_connection, 6, 1)
        grid.addWidget(QLabel("Сигналов за сессию"), 7, 0)
        grid.addWidget(self.lbl_signals, 7, 1)
        grid.addWidget(QLabel("Режим рынка"), 8, 0)
        grid.addWidget(self.lbl_regime, 8, 1)

        layout.addLayout(grid)

        # График эквити
        self.figure = Figure(figsize=(10, 3), dpi=80)
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        layout.addStretch()

    def update_data(self, status: dict):
        try:
            self.lbl_balance.setText(f"{status.get('balance', 0):.2f} USDT")
            self.lbl_equity.setText(f"{status.get('equity', 0):.2f} USDT")
            self.lbl_unreal.setText(f"{status.get('unrealized_pnl', 0):.2f} USDT")
            self.lbl_daily.setText(f"{status.get('daily_pnl', 0):.2f} USDT")
            self.lbl_positions.setText(str(status.get('open_positions', 0)))
            self.lbl_winrate.setText(f"{status.get('win_rate', 0):.1f}%")
            self.lbl_signals.setText(str(len(status.get('recent_signals', []))))
            self.lbl_regime.setText(status.get('market_regime', 'unknown'))
            self.lbl_connection.setText("🟢" if status.get('connected') else "🔴")
        except Exception as e:
            logger.debug(f"Dashboard update error: {e}")

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
