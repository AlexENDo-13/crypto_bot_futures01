"""
Logs tab: colored log display with filtering (thread-safe).
"""
import logging
from datetime import datetime, timezone
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QComboBox, QPushButton, QCheckBox,
    QLineEdit
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QColor, QTextCharFormat, QFont

from ui.styles import theme

logger = logging.getLogger(__name__)

LOG_COLORS = {
    'PROFIT': '#3fb950',
    'LOSS': '#f85149',
    'TP': '#2ea043',
    'SL': '#da3633',
    'INFO': '#58a6ff',
    'WARNING': '#d29922',
    'ERROR': '#f85149',
    'DEBUG': '#6e7681',
    'TRADE': '#a371f7',
    'START': '#00d4aa',
    'STOP': '#f85149',
}


class LogSignalEmitter(QObject):
    """Thread-safe signal for log messages."""
    message_signal = pyqtSignal(str, str)


class ColoredLogHandler(logging.Handler):
    """Custom log handler that emits to a Qt signal instead of directly modifying GUI."""

    def __init__(self, signal_emitter: LogSignalEmitter):
        super().__init__()
        self.signal_emitter = signal_emitter
        self.setFormatter(logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))

    def emit(self, record):
        try:
            msg = self.format(record)
            level = record.levelname

            # Определяем специальные типы логов
            msg_upper = record.getMessage().upper()
            if 'PROFIT' in msg_upper or 'PnL=' in record.getMessage():
                if record.getMessage().split('PnL=')[-1].strip().startswith('-'):
                    level = 'LOSS'
                else:
                    level = 'PROFIT'
            elif 'TP' in msg_upper[:5]:
                level = 'TP'
            elif 'SL' in msg_upper[:5]:
                level = 'SL'
            elif 'TRADE' in msg_upper:
                level = 'TRADE'
            elif 'START' in msg_upper:
                level = 'START'
            elif 'STOP' in msg_upper:
                level = 'STOP'

            # Отправляем через сигнал!
            self.signal_emitter.message_signal.emit(msg, level)
        except Exception:
            pass


class LogsTab(QWidget):
    """Tab for viewing application logs with color coding."""

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._max_lines = 1000
        self._signal_emitter = LogSignalEmitter()
        self._setup_ui()
        self._setup_logging()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Toolbar
        toolbar = QHBoxLayout()
        title = QLabel("Application Logs")
        title.setFont(theme.FONTS['header'])
        toolbar.addWidget(title)

        toolbar.addStretch()

        toolbar.addWidget(QLabel("Filter:"))
        self.filter_level = QComboBox()
        self.filter_level.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "TRADE"])
        self.filter_level.currentTextChanged.connect(self._apply_filter)
        toolbar.addWidget(self.filter_level)

        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)
        toolbar.addWidget(self.auto_scroll)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self._clear_logs)
        toolbar.addWidget(self.btn_clear)

        layout.addLayout(toolbar)

        # Log display
        self.log_display = QPlainTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setMaximumBlockCount(self._max_lines)
        self.log_display.setFont(theme.FONTS['mono'])
        self.log_display.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {theme.colors['bg_secondary']};
                color: {theme.colors['text_primary']};
                border: 1px solid {theme.colors['border']};
                border-radius: 4px;
                padding: 10px;
            }}
        """)
        layout.addWidget(self.log_display)

        # Search bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search logs...")
        self.search_input.returnPressed.connect(self._search_logs)
        search_layout.addWidget(self.search_input)

        self.btn_search = QPushButton("Find")
        self.btn_search.clicked.connect(self._search_logs)
        search_layout.addWidget(self.btn_search)

        layout.addLayout(search_layout)

        # Подключаем сигнал к слоту (безопасное обновление GUI)
        self._signal_emitter.message_signal.connect(self._append_log_safe)

    def _setup_logging(self):
        """Настраиваем обработчик, который отправляет логи через сигнал."""
        handler = ColoredLogHandler(self._signal_emitter)
        handler.setLevel(logging.DEBUG)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

    def _append_log_safe(self, message: str, level: str):
        """Слот, который гарантированно выполняется в GUI-потоке."""
        color = LOG_COLORS.get(level, theme.colors['text_primary'])

        # Фильтр по уровню
        current_filter = self.filter_level.currentText()
        if current_filter != "ALL" and level != current_filter:
            level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
            filter_level_num = level_order.get(current_filter, 0)
            msg_level_num = level_order.get(level, 1)
            if msg_level_num < filter_level_num:
                return

        # Форматируем HTML
        timestamp = datetime.now(timezone.utc).strftime('%H:%M:%S')
        colored_msg = f'<span style="color: {color}">[{timestamp}] {message}</span>'

        self.log_display.appendHtml(colored_msg)

        # Автопрокрутка
        if self.auto_scroll.isChecked():
            self.log_display.verticalScrollBar().setValue(
                self.log_display.verticalScrollBar().maximum()
            )

    # Метод append_log оставлен для обратной совместимости (не вызывается из фона)
    def append_log(self, message: str, level: str = "INFO"):
        self._append_log_safe(message, level)

    def _apply_filter(self, filter_text: str):
        pass

    def _clear_logs(self):
        self.log_display.clear()

    def _search_logs(self):
        query = self.search_input.text().lower()
        if not query:
            return
        text = self.log_display.toPlainText()
        lines = text.split('\n')
        results = [line for line in lines if query in line.lower()]
        if results:
            self.log_display.clear()
            for line in results:
                self.log_display.appendPlainText(line)
        else:
            self.log_display.appendHtml(
                f'<span style="color: {theme.colors["warning"]}">'
                f'No results found for "{query}"</span>'
            )
