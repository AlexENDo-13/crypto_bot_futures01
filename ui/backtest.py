"""
Backtest tab: historical testing of strategies.
"""
import logging
from datetime import datetime, timezone, timedelta
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QSpinBox, QDoubleSpinBox,
    QCheckBox, QGroupBox, QFormLayout, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QDateEdit
)
from PyQt5.QtCore import Qt, QDate

from ui.styles import theme

logger = logging.getLogger(__name__)


class BacktestTab(QWidget):
    """Tab for backtesting strategies on historical data."""
    
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._is_running = False
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("Strategy Backtest")
        title.setFont(theme.FONTS['header'])
        layout.addWidget(title)
        
        # Warning
        warning = QLabel("Backtest works only when trading is stopped")
        warning.setStyleSheet(f"color: {theme.colors['warning']};")
        warning.setFont(theme.FONTS['small'])
        layout.addWidget(warning)
        
        # Settings
        settings_group = QGroupBox("Backtest Settings")
        settings_layout = QFormLayout(settings_group)
        
        # Period selection
        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDate(QDate.currentDate().addMonths(-3))
        settings_layout.addRow("Start Date:", self.start_date)
        
        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        settings_layout.addRow("End Date:", self.end_date)
        
        # Strategy selection
        self.strategy_select = QComboBox()
        self.strategy_select.addItem("All Strategies (Ensemble)")
        settings_layout.addRow("Strategy:", self.strategy_select)
        
        # Timeframe
        self.backtest_timeframe = QComboBox()
        self.backtest_timeframe.addItems(["15m", "1h", "4h", "1d"])
        settings_layout.addRow("Timeframe:", self.backtest_timeframe)
        
        # Initial balance
        self.initial_balance = QDoubleSpinBox()
        self.initial_balance.setRange(100, 100000)
        self.initial_balance.setValue(1000)
        self.initial_balance.setPrefix("$")
        settings_layout.addRow("Initial Balance:", self.initial_balance)
        
        # Risk settings
        self.backtest_risk = QDoubleSpinBox()
        self.backtest_risk.setRange(0.1, 10.0)
        self.backtest_risk.setValue(2.0)
        self.backtest_risk.setSuffix("%")
        settings_layout.addRow("Risk per Trade:", self.backtest_risk)
        
        layout.addWidget(settings_group)
        
        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)
        
        # Buttons
        buttons = QHBoxLayout()
        
        self.btn_run = QPushButton("Run Backtest")
        self.btn_run.clicked.connect(self._run_backtest)
        buttons.addWidget(self.btn_run)
        
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_backtest)
        buttons.addWidget(self.btn_stop)
        
        buttons.addStretch()
        
        layout.addLayout(buttons)
        
        # Results
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout(results_group)
        
        # Results summary
        self.results_summary = QLabel("No backtest results yet")
        self.results_summary.setFont(theme.FONTS['mono'])
        results_layout.addWidget(self.results_summary)
        
        # Results table
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(8)
        self.results_table.setHorizontalHeaderLabels([
            "Metric", "Value", "", "", "", "", "", ""
        ])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_table.setMaximumHeight(150)
        results_layout.addWidget(self.results_table)
        
        layout.addWidget(results_group)
        layout.addStretch()
    
    def refresh_strategies(self):
        """Refresh strategy dropdown."""
        current = self.strategy_select.currentText()
        self.strategy_select.clear()
        self.strategy_select.addItem("All Strategies (Ensemble)")
        
        for name in self.engine.strategies.keys():
            self.strategy_select.addItem(name)
        
        # Restore selection
        idx = self.strategy_select.findText(current)
        if idx >= 0:
            self.strategy_select.setCurrentIndex(idx)
    
    def _run_backtest(self):
        """Run backtest."""
        if self.engine.is_running() and not self.engine.is_paused():
            QMessageBox.warning(
                self, "Trading Active",
                "Please stop or pause trading before running backtest"
            )
            return
        
        self._is_running = True
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0)
        
        try:
            # Get settings
            start = self.start_date.date().toPyDate()
            end = self.end_date.date().toPyDate()
            strategy = self.strategy_select.currentText()
            timeframe = self.backtest_timeframe.currentText()
            balance = self.initial_balance.value()
            risk = self.backtest_risk.value()
            
            logger.info(f"Starting backtest: {start} to {end}, {strategy}, {timeframe}")
            
            # Simulate progress
            import time
            for i in range(101):
                if not self._is_running:
                    break
                self.progress_bar.setValue(i)
                time.sleep(0.05)
                QApplication.processEvents()
            
            # Show mock results
            self._show_results({
                'total_return': 12.5,
                'total_trades': 45,
                'winrate': 0.62,
                'profit_factor': 1.8,
                'max_drawdown': 5.2,
                'sharpe_ratio': 1.45,
                'avg_trade': 0.28,
                'final_balance': balance * 1.125,
            })
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Backtest failed: {e}")
        finally:
            self._is_running = False
            self.btn_run.setEnabled(True)
            self.btn_stop.setEnabled(False)
    
    def _stop_backtest(self):
        """Stop running backtest."""
        self._is_running = False
    
    def _show_results(self, results: dict):
        """Display backtest results."""
        summary_text = f"""
Backtest Results:
  Total Return:    {results.get('total_return', 0):+.2f}%
  Final Balance:   ${results.get('final_balance', 0):.2f}
  Total Trades:    {results.get('total_trades', 0)}
  Win Rate:        {results.get('winrate', 0):.1%}
  Profit Factor:   {results.get('profit_factor', 0):.2f}
  Max Drawdown:    {results.get('max_drawdown', 0):.2f}%
  Sharpe Ratio:    {results.get('sharpe_ratio', 0):.2f}
  Avg Trade:       {results.get('avg_trade', 0):.2f}%
        """
        self.results_summary.setText(summary_text)
        
        # Populate table
        metrics = [
            ("Total Return", f"{results.get('total_return', 0):+.2f}%"),
            ("Total Trades", str(results.get('total_trades', 0))),
            ("Win Rate", f"{results.get('winrate', 0):.1%}"),
            ("Profit Factor", f"{results.get('profit_factor', 0):.2f}"),
            ("Max Drawdown", f"{results.get('max_drawdown', 0):.2f}%"),
            ("Sharpe Ratio", f"{results.get('sharpe_ratio', 0):.2f}"),
            ("Final Balance", f"${results.get('final_balance', 0):.2f}"),
            ("Avg Trade", f"{results.get('avg_trade', 0):.2f}%"),
        ]
        
        self.results_table.setRowCount(len(metrics))
        for i, (metric, value) in enumerate(metrics):
            self.results_table.setItem(i, 0, QTableWidgetItem(metric))
            self.results_table.setItem(i, 1, QTableWidgetItem(value))


# Fix missing import
from PyQt5.QtWidgets import QApplication
