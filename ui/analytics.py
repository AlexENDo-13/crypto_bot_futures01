"""
Advanced Analytics tab: equity curve, drawdown chart, daily PnL, Sharpe ratio,
trade calendar (heatmap of daily PnL).
"""
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict

import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QFormLayout, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import QTimer
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates
from matplotlib.colors import LinearSegmentedColormap

from ui.styles import theme

logger = logging.getLogger(__name__)


class AnalyticsTab(QWidget):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._setup_ui()
        self._timer = QTimer()
        self._timer.timeout.connect(self.refresh)
        self._timer.start(10000)  # обновление каждые 10 секунд

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Advanced Analytics")
        title.setFont(theme.FONTS['header'])
        layout.addWidget(title)

        # Блок метрик
        metrics_group = QGroupBox("Performance Metrics")
        metrics_layout = QFormLayout(metrics_group)
        self.lbl_sharpe = QLabel("Sharpe Ratio: --")
        self.lbl_sortino = QLabel("Sortino Ratio: --")
        self.lbl_max_dd = QLabel("Max Drawdown: --")
        self.lbl_avg_daily = QLabel("Avg Daily PnL: --")
        self.lbl_win_days = QLabel("Win Days: --")
        for lbl in [self.lbl_sharpe, self.lbl_sortino, self.lbl_max_dd, self.lbl_avg_daily, self.lbl_win_days]:
            lbl.setFont(theme.FONTS['small'])
        metrics_layout.addRow("Sharpe Ratio:", self.lbl_sharpe)
        metrics_layout.addRow("Sortino Ratio:", self.lbl_sortino)
        metrics_layout.addRow("Max Drawdown:", self.lbl_max_dd)
        metrics_layout.addRow("Avg Daily PnL:", self.lbl_avg_daily)
        metrics_layout.addRow("Win Days:", self.lbl_win_days)
        layout.addWidget(metrics_group)

        # График эквити и просадки (два subplot)
        chart_group = QGroupBox("Equity & Drawdown")
        chart_layout = QVBoxLayout(chart_group)
        self.figure = Figure(figsize=(10, 5), dpi=80)
        self.canvas = FigureCanvas(self.figure)
        chart_layout.addWidget(self.canvas)
        layout.addWidget(chart_group)

        # График дневной доходности
        daily_group = QGroupBox("Daily PnL")
        daily_layout = QVBoxLayout(daily_group)
        self.figure_daily = Figure(figsize=(10, 2), dpi=80)
        self.canvas_daily = FigureCanvas(self.figure_daily)
        daily_layout.addWidget(self.canvas_daily)
        layout.addWidget(daily_group)

        # Календарь сделок (таблица PnL по дням)
        cal_group = QGroupBox("Trade Calendar (PnL per Day)")
        cal_layout = QVBoxLayout(cal_group)
        self.calendar_table = QTableWidget()
        self.calendar_table.setColumnCount(3)
        self.calendar_table.setHorizontalHeaderLabels(["Date", "PnL (USDT)", "Trades"])
        self.calendar_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.calendar_table.verticalHeader().setVisible(False)
        cal_layout.addWidget(self.calendar_table)
        layout.addWidget(cal_group)

        self.apply_theme()

    def apply_theme(self):
        self.calendar_table.setStyleSheet(f"""
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
            trades = self.engine.portfolio.trades
            if not trades:
                return

            # Группируем завершённые сделки по дням
            daily_pnl = defaultdict(float)
            daily_counts = defaultdict(int)
            for t in trades:
                try:
                    day = datetime.fromisoformat(t.close_time).strftime('%Y-%m-%d')
                    daily_pnl[day] += t.pnl
                    daily_counts[day] += 1
                except Exception:
                    pass

            if not daily_pnl:
                return

            sorted_days = sorted(daily_pnl.keys())
            pnl_array = np.array([daily_pnl[d] for d in sorted_days])

            # Метрики
            if len(pnl_array) >= 2:
                daily_returns = pnl_array / (self.engine.portfolio._balance or 1)
                mean_ret = np.mean(daily_returns)
                std_ret = np.std(daily_returns)
                downside = daily_returns[daily_returns < 0]
                downside_std = np.std(downside) if len(downside) > 1 else 1e-9
                sharpe = (mean_ret / std_ret * np.sqrt(365)) if std_ret > 0 else 0
                sortino = (mean_ret / downside_std * np.sqrt(365)) if downside_std > 0 else 0
            else:
                sharpe = 0
                sortino = 0
                mean_ret = np.mean(pnl_array) if len(pnl_array) else 0

            # Max Drawdown
            equity_curve = self.engine.portfolio.get_equity_curve(90)
            max_dd = 0.0
            if equity_curve:
                values = np.array([e['equity'] for e in equity_curve])
                if len(values) > 1:
                    peak = np.maximum.accumulate(values)
                    drawdowns = (peak - values) / peak * 100.0
                    max_dd = np.max(drawdowns)
            else:
                max_dd = 0.0

            win_days = np.sum(pnl_array > 0)
            total_days = len(pnl_array)

            self.lbl_sharpe.setText(f"Sharpe Ratio: {sharpe:.2f}")
            self.lbl_sortino.setText(f"Sortino Ratio: {sortino:.2f}")
            self.lbl_max_dd.setText(f"Max Drawdown: {max_dd:.1f}%")
            self.lbl_avg_daily.setText(f"Avg Daily PnL: {mean_ret:.4f} USDT")
            self.lbl_win_days.setText(f"Win Days: {win_days}/{total_days} ({win_days/total_days*100:.0f}%)")

            # График Equity & Drawdown
            self.figure.clear()
            if equity_curve:
                times = [datetime.fromisoformat(e['time']) for e in equity_curve]
                eq = [e['equity'] for e in equity_curve]
                ax1 = self.figure.add_subplot(211)
                ax1.plot(times, eq, color='#34d399')
                ax1.fill_between(times, eq, alpha=0.2, color='#34d399')
                ax1.set_ylabel('Equity')
                ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

                ax2 = self.figure.add_subplot(212, sharex=ax1)
                peak = np.maximum.accumulate(eq)
                dd = (peak - eq) / peak * 100.0
                ax2.fill_between(times, 0, dd, color='#f87171', alpha=0.5)
                ax2.set_ylabel('Drawdown %')
                ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
            self.canvas.draw()

            # График дневной доходности
            self.figure_daily.clear()
            ax3 = self.figure_daily.add_subplot(111)
            dates = [datetime.strptime(d, '%Y-%m-%d') for d in sorted_days]
            colors = ['#34d399' if v >= 0 else '#f87171' for v in pnl_array]
            ax3.bar(dates, pnl_array, color=colors)
            ax3.axhline(0, color='gray', linewidth=0.5)
            ax3.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
            ax3.set_ylabel('PnL (USDT)')
            self.canvas_daily.draw()

            # Таблица календаря
            self.calendar_table.setRowCount(len(sorted_days))
            for i, day in enumerate(sorted_days):
                self.calendar_table.setItem(i, 0, QTableWidgetItem(day))
                self.calendar_table.setItem(i, 1, QTableWidgetItem(f"{daily_pnl[day]:+.4f}"))
                self.calendar_table.setItem(i, 2, QTableWidgetItem(str(daily_counts[day])))

        except Exception as e:
            logger.debug(f"Analytics refresh error: {e}")
