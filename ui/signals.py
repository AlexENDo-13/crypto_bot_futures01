"""
Signals tab: displays recent trading signals and strategy weights.
"""
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QGroupBox, QFormLayout
)
from ui.styles import theme

logger = logging.getLogger(__name__)


class SignalsTab(QWidget):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QLabel("Trading Signals & Strategy Weights")
        header.setFont(theme.FONTS['header'])
        layout.addWidget(header)

        # Recent signals table
        signals_group = QGroupBox("Recent Signals")
        signals_layout = QVBoxLayout(signals_group)
        self.signals_table = QTableWidget()
        self.signals_table.setColumnCount(7)
        self.signals_table.setHorizontalHeaderLabels(
            ["Time", "Symbol", "Action", "Confidence", "Price", "Strategy", "Regime"]
        )
        self.signals_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.signals_table.verticalHeader().setVisible(False)
        self.signals_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.signals_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        signals_layout.addWidget(self.signals_table)
        layout.addWidget(signals_group)

        # Strategy weights table
        weights_group = QGroupBox("Strategy Weights")
        weights_layout = QVBoxLayout(weights_group)
        self.weights_table = QTableWidget()
        self.weights_table.setColumnCount(3)
        self.weights_table.setHorizontalHeaderLabels(["Strategy", "Weight", "Status"])
        self.weights_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.weights_table.verticalHeader().setVisible(False)
        self.weights_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        weights_layout.addWidget(self.weights_table)
        layout.addWidget(weights_group)

        self.apply_theme()

    def apply_theme(self):
        for table in [self.signals_table, self.weights_table]:
            table.setStyleSheet(f"""
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
        # Signals
        signals = status.get('recent_signals', [])
        self.signals_table.setRowCount(len(signals))
        for row, sig in enumerate(signals):
            self.signals_table.setItem(row, 0, QTableWidgetItem(sig.get('time', '')))
            self.signals_table.setItem(row, 1, QTableWidgetItem(sig.get('symbol', '')))
            self.signals_table.setItem(row, 2, QTableWidgetItem(sig.get('action', '')))
            self.signals_table.setItem(row, 3, QTableWidgetItem(f"{sig.get('confidence', 0):.2f}"))
            self.signals_table.setItem(row, 4, QTableWidgetItem(f"{sig.get('price', 0):.4f}"))
            self.signals_table.setItem(row, 5, QTableWidgetItem(sig.get('strategy', '')))
            self.signals_table.setItem(row, 6, QTableWidgetItem(sig.get('regime', '')))

        # Weights
        weights = status.get('strategy_weights', {})
        self.weights_table.setRowCount(len(weights))
        row = 0
        for name, data in weights.items():
            self.weights_table.setItem(row, 0, QTableWidgetItem(name))
            weight = data.get('weight', 1.0) if isinstance(data, dict) else data
            enabled = data.get('enabled', True) if isinstance(data, dict) else True
            self.weights_table.setItem(row, 1, QTableWidgetItem(f"{weight:.2f}"))
            self.weights_table.setItem(row, 2, QTableWidgetItem("Active" if enabled else "Disabled"))
            row += 1

        self.apply_theme()
