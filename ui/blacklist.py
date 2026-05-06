"""
Blacklist tab: manage blacklisted trading pairs.
"""
import logging
from datetime import datetime, timezone
from typing import List
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLineEdit, QMessageBox, QMenu
)
from PyQt5.QtCore import Qt

from ui.styles import theme

logger = logging.getLogger(__name__)


class BlacklistTab(QWidget):
    """Tab for managing blacklisted symbols."""
    
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._setup_ui()
        self._refresh_list()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QHBoxLayout()
        
        title = QLabel("Blacklisted Pairs")
        title.setFont(theme.FONTS['header'])
        header.addWidget(title)
        
        header.addStretch()
        
        # Add symbol
        self.add_input = QLineEdit()
        self.add_input.setPlaceholderText("BTC-USDT")
        self.add_input.setFixedWidth(150)
        header.addWidget(self.add_input)
        
        self.btn_add = QPushButton("Add")
        self.btn_add.clicked.connect(self._add_symbol)
        header.addWidget(self.btn_add)
        
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self._refresh_list)
        header.addWidget(self.btn_refresh)
        
        layout.addLayout(header)
        
        # Info label
        info = QLabel("Blacklisted pairs are excluded from trading. Auto-removed after 3 days.")
        info.setFont(theme.FONTS['small'])
        info.setStyleSheet(f"color: {theme.colors['text_muted']};")
        layout.addWidget(info)
        
        # Blacklist table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Symbol", "Added", "Reason", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.setMinimumHeight(300)
        
        layout.addWidget(self.table)
        
        # Auto-blacklist info
        auto_group = QWidget()
        auto_layout = QVBoxLayout(auto_group)
        auto_layout.setContentsMargins(0, 10, 0, 0)
        
        auto_title = QLabel("Auto-Blacklist Rules")
        auto_title.setFont(theme.FONTS['header'])
        auto_layout.addWidget(auto_title)
        
        rules = QLabel(
            "- Symbols with 3+ consecutive losses are auto-blacklisted\n"
            "- Auto-blacklisted pairs are removed after 3 days\n"
            "- After removal, pairs are re-analyzed after 1 week\n"
            "- Manual blacklist entries persist until manually removed"
        )
        rules.setFont(theme.FONTS['small'])
        rules.setStyleSheet(f"color: {theme.colors['text_secondary']};")
        auto_layout.addWidget(rules)
        
        layout.addWidget(auto_group)
        layout.addStretch()
    
    def _refresh_list(self):
        """Refresh blacklist table."""
        symbols = self.engine.get_blacklist()
        
        self.table.setRowCount(len(symbols))
        
        for i, symbol in enumerate(symbols):
            self.table.setItem(i, 0, QTableWidgetItem(symbol))
            self.table.setItem(i, 1, QTableWidgetItem("Manual"))
            self.table.setItem(i, 2, QTableWidgetItem("User added"))
            
            # Remove button
            btn = QPushButton("Remove")
            btn.setFixedWidth(70)
            btn.setProperty('symbol', symbol)
            btn.clicked.connect(self._remove_symbol)
            self.table.setCellWidget(i, 3, btn)
    
    def _add_symbol(self):
        """Add symbol to blacklist."""
        symbol = self.add_input.text().strip().upper()
        if not symbol:
            return
        
        # Format symbol
        if '-' not in symbol:
            symbol = f"{symbol}-USDT"
        
        try:
            self.engine.add_to_blacklist(symbol, "manual")
            self.add_input.clear()
            self._refresh_list()
            logger.info(f"Added {symbol} to blacklist")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add: {e}")
    
    def _remove_symbol(self):
        """Remove symbol from blacklist."""
        btn = self.sender()
        symbol = btn.property('symbol')
        
        reply = QMessageBox.question(
            self, "Remove from Blacklist",
            f"Remove {symbol} from blacklist?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                self.engine.remove_from_blacklist(symbol)
                self._refresh_list()
                logger.info(f"Removed {symbol} from blacklist")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to remove: {e}")
    
    def _show_context_menu(self, position):
        """Show context menu."""
        row = self.table.rowAt(position.y())
        if row < 0:
            return
        
        symbol = self.table.item(row, 0).text()
        
        menu = QMenu(self)
        remove_action = menu.addAction(f"Remove {symbol}")
        view_action = menu.addAction(f"View history")
        
        action = menu.exec_(self.table.viewport().mapToGlobal(position))
        
        if action == remove_action:
            self.engine.remove_from_blacklist(symbol)
            self._refresh_list()
        elif action == view_action:
            QMessageBox.information(self, "History", f"History for {symbol}:\nAdded manually")
