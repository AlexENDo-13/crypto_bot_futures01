"""
Chart tab: simple candlestick chart with minimal indicators.
"""
import logging
import pandas as pd
import numpy as np
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton
from PyQt5.QtCore import Qt
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import mplfinance as mpf

logger = logging.getLogger(__name__)

class ChartTab(QWidget):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Controls
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("Symbol:"))
        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(self.engine._top_symbols[:30] if self.engine._top_symbols else ['BTC-USDT'])
        control_layout.addWidget(self.symbol_combo)

        control_layout.addWidget(QLabel("TF:"))
        self.tf_combo = QComboBox()
        self.tf_combo.addItems(['15m', '1h', '4h'])
        control_layout.addWidget(self.tf_combo)

        self.btn_load = QPushButton("Load Chart")
        self.btn_load.clicked.connect(self._load_chart)
        control_layout.addWidget(self.btn_load)
        control_layout.addStretch()
        layout.addLayout(control_layout)

        # Canvas
        self.figure = Figure(figsize=(12, 6), dpi=80)
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

    def _load_chart(self):
        symbol = self.symbol_combo.currentText()
        tf = self.tf_combo.currentText()
        try:
            df = self.engine.api.get_klines_dataframe(symbol, tf, limit=100)
            if df.empty:
                return
            # Переименуем колонки для mplfinance
            df = df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'})
            df.index = pd.to_datetime(df.index)

            self.figure.clear()
            ax = self.figure.add_subplot(111)
            mpf.plot(df, type='candle', style='charles', volume=True, ax=ax)
            ax.set_title(f"{symbol} {tf}")
            self.canvas.draw()
        except Exception as e:
            logger.error(f"Chart load error: {e}")
