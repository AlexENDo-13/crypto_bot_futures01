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
    QMessageBox, QDateEdit, QApplication
)
from PyQt5.QtCore import Qt, QDate, QThread, pyqtSignal

from ui.styles import theme

logger = logging.getLogger(__name__)


class BacktestWorker(QThread):
    """Поток для выполнения бэктеста без зависания интерфейса."""
    finished = pyqtSignal(dict)
    progress = pyqtSignal(int)

    def __init__(self, engine, strategy_name, symbol, timeframe, start_ts, end_ts, initial_balance):
        super().__init__()
        self.engine = engine
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.timeframe = timeframe
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.initial_balance = initial_balance

    def run(self):
        from ml.backtest_engine import BacktestEngine
        be = BacktestEngine(self.engine)
        # Для больших периодов можно сообщать о прогрессе, но пока просто запускаем
        self.progress.emit(10)
        try:
            # Бэктест на истории
            result = be.run(
                strategy_name=self.strategy_name,
                symbol=self.symbol,
                timeframe=self.timeframe,
                start_date=None if not self.start_ts else datetime.utcfromtimestamp(self.start_ts).isoformat(),
                end_date=None if not self.end_ts else datetime.utcfromtimestamp(self.end_ts).isoformat(),
                initial_balance=self.initial_balance
            )
            self.progress.emit(90)
            self.finished.emit(result if result else {'error': 'Нет результатов'})
        except Exception as e:
            self.finished.emit({'error': str(e)})
        self.progress.emit(100)


class BacktestTab(QWidget):
    """Tab for backtesting strategies on historical data."""

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._is_running = False
        self._worker = None
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
        self.start_date.setDate(QDate.currentDate().addMonths(-1))
        settings_layout.addRow("Start Date:", self.start_date)

        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDate(QDate.currentDate())
        settings_layout.addRow("End Date:", self.end_date)

        # Strategy selection
        self.strategy_select = QComboBox()
        self.strategy_select.addItem("All Strategies (Ensemble)")
        settings_layout.addRow("Strategy:", self.strategy_select)

        # Symbol
        self.backtest_symbol = QComboBox()
        self.backtest_symbol.setEditable(True)
        self.backtest_symbol.addItems(['BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'XRP-USDT', 'DOGE-USDT'])
        settings_layout.addRow("Symbol:", self.backtest_symbol)

        # Timeframe
        self.backtest_timeframe = QComboBox()
        self.backtest_timeframe.addItems(["15m", "1h", "4h", "1d"])
        self.backtest_timeframe.setCurrentText("1h")
        settings_layout.addRow("Timeframe:", self.backtest_timeframe)

        # Initial balance
        self.initial_balance = QDoubleSpinBox()
        self.initial_balance.setRange(100, 100000)
        self.initial_balance.setValue(1000)
        self.initial_balance.setPrefix("$")
        settings_layout.addRow("Initial Balance:", self.initial_balance)

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

        self.results_summary = QLabel("No backtest results yet")
        self.results_summary.setFont(theme.FONTS['mono'])
        results_layout.addWidget(self.results_summary)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(2)
        self.results_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setMaximumHeight(260)
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
        idx = self.strategy_select.findText(current)
        if idx >= 0:
            self.strategy_select.setCurrentIndex(idx)

    def _run_backtest(self):
        """Run backtest in a worker thread."""
        if self.engine._running and not self.engine._paused:
            QMessageBox.warning(self, "Trading Active", "Please pause trading before running backtest.")
            return

        self._is_running = True
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0)

        # Get settings
        start_date = self.start_date.date().toPyDate()
        end_date = self.end_date.date().toPyDate()
        start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
        end_ts = int(datetime.combine(end_date, datetime.min.time()).timestamp())
        strategy = self.strategy_select.currentText()
        if strategy == "All Strategies (Ensemble)":
            # Пока не поддерживается ансамбль в бэктестере, берём первую активную
            active = [name for name, s in self.engine.strategies.items() if s.enabled]
            strategy = active[0] if active else "TrendFollowing"
            logger.info(f"Backtesting ensemble not supported, using {strategy}")

        symbol = self.backtest_symbol.currentText()
        timeframe = self.backtest_timeframe.currentText()
        initial_balance = self.initial_balance.value()

        logger.info(f"Starting backtest: {start_date} to {end_date}, {strategy} on {symbol} {timeframe}")

        # Create and start worker thread
        self._worker = BacktestWorker(self.engine, strategy, symbol, timeframe, start_ts, end_ts, initial_balance)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _stop_backtest(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait()
        self._is_running = False
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setValue(0)

    def _on_progress(self, value):
        self.progress_bar.setValue(value)

    def _on_finished(self, result):
        self._is_running = False
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setValue(100)

        if 'error' in result:
            QMessageBox.warning(self, "Backtest Error", result['error'])
            self.results_summary.setText(f"Error: {result['error']}")
            return

        self._show_results(result)

    def _show_results(self, results: dict):
        """Display backtest results."""
        total_return = ((results.get('final_balance', 0) - results.get('initial_balance', 0)) / results.get('initial_balance', 1)) * 100
        summary_text = f"""
Backtest Results:
  Strategy: {results.get('strategy', 'Unknown')}
  Period: {results.get('start', '?')} – {results.get('end', '?')}
  Initial Balance: ${results.get('initial_balance', 0):.2f}
  Final Balance:   ${results.get('final_balance', 0):.2f}
  Total Return:    {total_return:+.2f}%
  Total PnL:       {results.get('total_pnl', 0):+.4f}
  Number of Trades:{results.get('num_trades', 0)}
  Winrate:         {results.get('winrate', 0)*100:.1f}%
  Sharpe Ratio:    {results.get('sharpe', 0):.2f}
  Avg PnL per Trade: {results.get('avg_pnl', 0):.4f}
        """
        self.results_summary.setText(summary_text)

        # Populate table
        self.results_table.setRowCount(8)
        metrics = [
            ("Initial Balance", f"${results.get('initial_balance', 0):.2f}"),
            ("Final Balance", f"${results.get('final_balance', 0):.2f}"),
            ("Total Return", f"{total_return:+.2f}%"),
            ("Total PnL", f"{results.get('total_pnl', 0):+.4f}"),
            ("Number of Trades", str(results.get('num_trades', 0))),
            ("Winrate", f"{results.get('winrate', 0)*100:.1f}%"),
            ("Sharpe Ratio", f"{results.get('sharpe', 0):.2f}"),
            ("Avg PnL per Trade", f"{results.get('avg_pnl', 0):.4f}"),
        ]
        for i, (metric, value) in enumerate(metrics):
            self.results_table.setItem(i, 0, QTableWidgetItem(metric))
            self.results_table.setItem(i, 1, QTableWidgetItem(value))
