"""
Orders tab: displays open TP/SL and limit orders with cancel ability.
"""
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QHeaderView, QAbstractItemView
)
from PyQt5.QtCore import Qt
from ui.styles import theme

logger = logging.getLogger(__name__)

class OrdersTab(QWidget):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QLabel("Open Orders (TP/SL)")
        header.setFont(theme.FONTS['header'])
        layout.addWidget(header)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Symbol", "Side", "Type", "Stop Price", "Qty", "Order ID", "Cancel"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.apply_theme()
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self._refresh)
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def apply_theme(self):
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {theme.colors['bg_secondary']};
                color: {theme.colors['text_primary']};
                gridline-color: {theme.colors['border']};
                border: 1px solid {theme.colors['border']};
            }}
            QHeaderView::section {{
                background-color: {theme.colors['bg_primary']};
                color: {theme.colors['text_primary']};
                padding: 4px;
                border: 1px solid {theme.colors['border']};
            }}
            QPushButton {{
                background-color: {theme.colors['accent']};
                color: white; border: none; border-radius: 3px; padding: 2px 8px;
            }}
            QPushButton:hover {{ background-color: {theme.colors['accent_hover']}; }}
        """)

    def _refresh(self):
        try:
            orders = self.engine.api.get_open_orders()
            self._populate_table(orders)
        except Exception as e:
            logger.error(f"Failed to fetch orders: {e}")

    def _populate_table(self, orders):
        self.table.setRowCount(len(orders))
        for row, order in enumerate(orders):
            symbol = order.get('symbol', '')
            side = order.get('side', '')
            order_type = order.get('type', '')
            stop_price = order.get('stopPrice', '')
            qty = order.get('origQty', order.get('quantity', ''))
            order_id = str(order.get('orderId', ''))

            self.table.setItem(row, 0, QTableWidgetItem(symbol))
            self.table.setItem(row, 1, QTableWidgetItem(side))
            self.table.setItem(row, 2, QTableWidgetItem(order_type))
            self.table.setItem(row, 3, QTableWidgetItem(str(stop_price)))
            self.table.setItem(row, 4, QTableWidgetItem(str(qty)))
            self.table.setItem(row, 5, QTableWidgetItem(order_id))

            btn = QPushButton("Cancel")
            btn.clicked.connect(lambda checked, s=symbol, oid=order_id: self._cancel_order(s, oid))
            self.table.setCellWidget(row, 6, btn)

    def _cancel_order(self, symbol, order_id):
        try:
            self.engine.api.cancel_order(symbol, order_id)
            logger.info(f"Order {order_id} cancelled")
            self._refresh()
        except Exception as e:
            logger.error(f"Cancel order failed: {e}")

    def update_data(self):
        # вызывается периодически из main_window
        self._refresh()
