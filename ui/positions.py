"""Positions tab: open positions, close all, close long/short."""
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QPushButton, QHeaderView, QAbstractItemView
)
from PyQt5.QtCore import Qt
from ui.styles import theme

logger = logging.getLogger(__name__)

class PositionsTab(QWidget):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QLabel("Open Positions")
        header.setFont(theme.FONTS['header'])
        layout.addWidget(header)

        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels([
            "Symbol", "Side", "Entry Price", "Size", "Leverage",
            "Margin", "PnL", "PnL %", "TP / SL", "Trailing", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.apply_theme()
        layout.addWidget(self.table)

        # Кнопки
        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self._refresh)
        btn_layout.addWidget(self.btn_refresh)

        self.btn_close_long = QPushButton("Close All LONG")
        self.btn_close_long.clicked.connect(lambda: self._close_by_side('LONG'))
        btn_layout.addWidget(self.btn_close_long)

        self.btn_close_short = QPushButton("Close All SHORT")
        self.btn_close_short.clicked.connect(lambda: self._close_by_side('SHORT'))
        btn_layout.addWidget(self.btn_close_short)

        self.btn_close_half = QPushButton("Close 50% All")
        self.btn_close_half.clicked.connect(self._close_half)
        btn_layout.addWidget(self.btn_close_half)

        self.btn_close_all = QPushButton("Close All")
        self.btn_close_all.clicked.connect(self._close_all)
        btn_layout.addWidget(self.btn_close_all)
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
            QTableWidget QHeaderView::section {{
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

    def update_positions(self, positions):
        self.table.setRowCount(len(positions))
        global_trailing_on = self.engine.trailing_sl_enabled  # глобальный флаг

        for row, pos in enumerate(positions):
            self.table.setItem(row, 0, QTableWidgetItem(pos.get('symbol', '')))
            self.table.setItem(row, 1, QTableWidgetItem(pos.get('side', '')))
            self.table.setItem(row, 2, QTableWidgetItem(f"{pos.get('entry_price', 0):.6f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{pos.get('quantity', 0):.6f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{pos.get('leverage', 0):.1f}x"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{pos.get('margin', 0):.2f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{pos.get('unrealized_pnl', 0):.4f}"))
            self.table.setItem(row, 7, QTableWidgetItem(f"{pos.get('pnl_pct', 0):.2f}%"))
            tp = pos.get('tp_price')
            sl = pos.get('sl_price')
            tp_sl_str = ""
            if tp: tp_sl_str += f"TP: {tp:.4f}"
            if sl: tp_sl_str += f" / SL: {sl:.4f}"
            self.table.setItem(row, 8, QTableWidgetItem(tp_sl_str))

            # ---- Определяем статус трейлинга ----
            trailing_active = pos.get('trailing', False)   # из модели
            if global_trailing_on:
                if trailing_active:
                    status = "On"
                    color = theme.colors['success']
                    tooltip = "Trailing stop is active and updating."
                else:
                    status = "Waiting..."
                    color = theme.colors['warning']
                    tooltip = "Trailing enabled. Waiting for price to move away from entry."
            else:
                status = "Off"
                color = theme.colors['text_muted']
                tooltip = "Trailing stop is globally disabled."

            trailing_item = QTableWidgetItem(status)
            trailing_item.setForeground(Qt.green if color == theme.colors['success'] else
                                        (Qt.yellow if color == theme.colors['warning'] else Qt.gray))
            trailing_item.setToolTip(tooltip)
            self.table.setItem(row, 9, trailing_item)

            btn = QPushButton("Close")
            btn.clicked.connect(lambda checked, s=pos['symbol'], side=pos['side']: self._close_position(s, side))
            self.table.setCellWidget(row, 10, btn)

        self.apply_theme()

    def _refresh(self):
        try:
            self.engine.sync_positions()
            positions = self.engine.portfolio.get_positions()
            self.update_positions([p.to_dict() for p in positions])
            logger.info("Positions refreshed manually")
        except Exception as e:
            logger.error(f"Refresh failed: {e}")

    def _close_position(self, symbol, side):
        try:
            self.engine.close_position_manual(symbol, side)
        except Exception as e:
            logger.error(f"Close failed: {e}")

    def _close_by_side(self, side):
        for pos in self.engine.portfolio.get_positions():
            if pos.side == side:
                self._close_position(pos.symbol, pos.side)

    def _close_half(self):
        for pos in self.engine.portfolio.get_positions():
            try:
                self.engine.close_position_manual(pos.symbol, pos.side, percent=50.0)
            except Exception as e:
                logger.error(f"Half-close failed: {e}")

    def _close_all(self):
        for pos in self.engine.portfolio.get_positions():
            self._close_position(pos.symbol, pos.side)
