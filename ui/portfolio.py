"""
Portfolio tab: equity curve, detailed PnL statistics, trade history.
"""
import logging
from datetime import datetime, timezone, timedelta
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QComboBox,
    QPushButton, QGroupBox, QFormLayout
)
from PyQt5.QtCore import Qt, QTimer
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates

from ui.styles import theme

logger = logging.getLogger(__name__)

class PortfolioTab(QWidget):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QLabel("Portfolio Analytics")
        header.setFont(theme.FONTS['header'])
        layout.addWidget(header)

        # --- Equity Curve ---
        chart_group = QGroupBox("Equity Curve")
        chart_layout = QVBoxLayout(chart_group)
        self.figure = Figure(figsize=(10, 3), dpi=80)
        self.canvas = FigureCanvas(self.figure)
        chart_layout.addWidget(self.canvas)

        # PnL summary labels
        stats_layout = QHBoxLayout()
        self.lbl_daily_pnl = QLabel("Daily PnL: +0.00 USDT")
        self.lbl_weekly_pnl = QLabel("Weekly PnL: +0.00 USDT")
        self.lbl_monthly_pnl = QLabel("Monthly PnL: +0.00 USDT")
        for lbl in [self.lbl_daily_pnl, self.lbl_weekly_pnl, self.lbl_monthly_pnl]:
            lbl.setFont(theme.FONTS['small'])
        stats_layout.addWidget(self.lbl_daily_pnl)
        stats_layout.addWidget(self.lbl_weekly_pnl)
        stats_layout.addWidget(self.lbl_monthly_pnl)
        stats_layout.addStretch()
        chart_layout.addLayout(stats_layout)
        layout.addWidget(chart_group)

        # --- Trade History ---
        trades_group = QGroupBox("Trade History")
        trades_layout = QVBoxLayout(trades_group)
        self.trades_table = QTableWidget()
        self.trades_table.setColumnCount(8)
        self.trades_table.setHorizontalHeaderLabels([
            "Time", "Symbol", "Side", "Entry", "Exit", "Qty", "PnL", "Reason"
        ])
        self.trades_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.trades_table.verticalHeader().setVisible(False)
        self.trades_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        trades_layout.addWidget(self.trades_table)
        layout.addWidget(trades_group)

        # --- Refresh timer ---
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)  # обновление каждые 5 секунд

        self.apply_theme()

    def apply_theme(self):
        self.trades_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {theme.colors['bg_secondary']};
                color: {theme.colors['text_primary']};
                gridline-color: {theme.colors['border']};
                border: 1px solid {theme.colors['border']};
            }}
            QHeaderView::section {{
                background-color: {theme.colors['bg_tertiary']};
                color: {theme.colors['text_primary']};
                padding: 4px;
                border: 1px solid {theme.colors['border']};
            }}
        """)

    def refresh(self):
        try:
            # График эквити
            equity_data = self.engine.portfolio.get_equity_curve(days=30)
            if equity_data:
                times = [datetime.fromisoformat(e['time']) for e in equity_data]
                values = [e['equity'] for e in equity_data]

                self.figure.clear()
                ax = self.figure.add_subplot(111)
                ax.plot(times, values, color='#34d399', linewidth=1)
                ax.fill_between(times, values, alpha=0.2, color='#34d399')
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
                ax.set_title("Equity (30 days)")
                self.canvas.draw()

            # Расчёт PnL за разные периоды
            now = datetime.now(timezone.utc)
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = day_start - timedelta(days=now.weekday())
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            daily = self._calc_pnl_since(day_start)
            weekly = self._calc_pnl_since(week_start)
            monthly = self._calc_pnl_since(month_start)

            self.lbl_daily_pnl.setText(f"Daily PnL: {daily:+.2f} USDT")
            self.lbl_weekly_pnl.setText(f"Weekly PnL: {weekly:+.2f} USDT")
            self.lbl_monthly_pnl.setText(f"Monthly PnL: {monthly:+.2f} USDT")

            # Обновление таблицы сделок (последние 100)
            trades = self.engine.portfolio.trades[-100:]
            self.trades_table.setRowCount(len(trades))
            for row, t in enumerate(trades):
                self.trades_table.setItem(row, 0, QTableWidgetItem(t.close_time[:19]))
                self.trades_table.setItem(row, 1, QTableWidgetItem(t.symbol))
                self.trades_table.setItem(row, 2, QTableWidgetItem(t.side))
                self.trades_table.setItem(row, 3, QTableWidgetItem(f"{t.entry_price:.6f}"))
                self.trades_table.setItem(row, 4, QTableWidgetItem(f"{t.exit_price:.6f}"))
                self.trades_table.setItem(row, 5, QTableWidgetItem(f"{t.quantity:.6f}"))
                self.trades_table.setItem(row, 6, QTableWidgetItem(f"{t.pnl:+.4f}"))
                self.trades_table.setItem(row, 7, QTableWidgetItem(t.close_reason[:15]))
        except Exception as e:
            logger.debug(f"Portfolio refresh error: {e}")

    def _calc_pnl_since(self, since_dt: datetime) -> float:
        """Суммирует PnL завершённых сделок, начиная с указанной даты."""
        total = 0.0
        for t in self.engine.portfolio.trades:
            try:
                close_dt = datetime.fromisoformat(t.close_time)
                if close_dt >= since_dt:
                    total += t.pnl
            except Exception:
                pass
        return total
