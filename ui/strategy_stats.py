"""
Strategy statistics tab: shows performance metrics per strategy.
"""
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from ui.styles import theme

logger = logging.getLogger(__name__)


class StrategyStatsTab(QWidget):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QLabel("Strategy Statistics")
        header.setFont(theme.FONTS['header'])
        layout.addWidget(header)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Strategy", "Trades", "Win Rate %", "Total PnL", "Avg PnL", "Last 3 PnL"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.apply_theme()
        layout.addWidget(self.table)

    def apply_theme(self):
        self.table.setStyleSheet(f"""
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

    def update_data(self, status: dict):
        stats = status.get('strategy_stats', {})
        self.table.setRowCount(len(stats))
        row = 0
        for name, data in stats.items():
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(str(data.get('trades', 0))))
            self.table.setItem(row, 2, QTableWidgetItem(f"{data.get('win_rate', 0):.1f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{data.get('total_pnl', 0):.4f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{data.get('avg_pnl', 0):.4f}"))
            last_3 = data.get('last_3', [])
            self.table.setItem(row, 5, QTableWidgetItem(", ".join(f"{p:.4f}" for p in last_3)))
            row += 1
        self.apply_theme()
