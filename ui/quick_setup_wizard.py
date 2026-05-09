"""
Quick Setup Wizard – автоматически заполняет параметры бота
в зависимости от выбранного стиля торговли.
"""
import logging
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QFormLayout, QMessageBox, QDoubleSpinBox, QSpinBox, QCheckBox, QGroupBox
)
from PyQt5.QtCore import Qt

logger = logging.getLogger(__name__)

# Профили быстрой настройки: стиль -> предустановки
QUICK_PROFILES = {
    "Degen": {
        "description": "Агрессивный стиль: высокий риск, высокое плечо, частые входы.",
        "risk_per_trade": 5.0,
        "max_leverage": 8,
        "max_positions": 5,
        "signal_threshold": 0.4,
        "trailing_sl_enabled": True,
        "trailing_distance_pct": 0.75,
        "partial_close_enabled": True,
        "partial_close_pct": 30.0,
        "breakeven_enabled": False,
    },
    "Day": {
        "description": "Дейтрейдинг: умеренный риск, среднее плечо, 1-3 сделки в день.",
        "risk_per_trade": 2.5,
        "max_leverage": 5,
        "max_positions": 3,
        "signal_threshold": 0.55,
        "trailing_sl_enabled": True,
        "trailing_distance_pct": 0.5,
        "partial_close_enabled": True,
        "partial_close_pct": 50.0,
        "breakeven_enabled": True,
    },
    "Swing": {
        "description": "Свинг-трейдинг: низкий риск, 4h/1d таймфреймы, длинные удержания.",
        "risk_per_trade": 1.5,
        "max_leverage": 3,
        "max_positions": 2,
        "signal_threshold": 0.65,
        "trailing_sl_enabled": True,
        "trailing_distance_pct": 1.0,
        "partial_close_enabled": False,
        "partial_close_pct": 50.0,
        "breakeven_enabled": True,
    },
    "Conservative": {
        "description": "Консервативный: минимальный риск, маленькое плечо, долгосрочные сигналы.",
        "risk_per_trade": 0.5,
        "max_leverage": 2,
        "max_positions": 1,
        "signal_threshold": 0.75,
        "trailing_sl_enabled": True,
        "trailing_distance_pct": 1.5,
        "partial_close_enabled": False,
        "partial_close_pct": 0.0,
        "breakeven_enabled": True,
    },
    "Custom": {
        "description": "Ручная настройка – параметры можно задать вручную.",
        "risk_per_trade": 2.0,
        "max_leverage": 3,
        "max_positions": 3,
        "signal_threshold": 0.5,
        "trailing_sl_enabled": True,
        "trailing_distance_pct": 0.5,
        "partial_close_enabled": True,
        "partial_close_pct": 50.0,
        "breakeven_enabled": True,
    },
}

class QuickSetupDialog(QDialog):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setWindowTitle("Быстрая настройка бота")
        self.setMinimumWidth(500)
        self._setup_ui()
        self._update_fields(QUICK_PROFILES["Day"])  # по умолчанию Day

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Выбор стиля
        style_layout = QHBoxLayout()
        style_layout.addWidget(QLabel("Стиль торговли:"))
        self.style_combo = QComboBox()
        self.style_combo.addItems(list(QUICK_PROFILES.keys()))
        self.style_combo.currentTextChanged.connect(self._on_style_changed)
        style_layout.addWidget(self.style_combo)
        layout.addLayout(style_layout)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("font-style: italic; color: #a0a0c0;")
        layout.addWidget(self.description_label)

        # Группа параметров
        params_group = QGroupBox("Параметры")
        params_form = QFormLayout(params_group)

        self.risk_per_trade = QDoubleSpinBox()
        self.risk_per_trade.setRange(0.1, 10.0)
        self.risk_per_trade.setSingleStep(0.1)
        self.risk_per_trade.setSuffix("%")
        params_form.addRow("Риск на сделку:", self.risk_per_trade)

        self.max_leverage = QSpinBox()
        self.max_leverage.setRange(1, 20)
        params_form.addRow("Макс. плечо:", self.max_leverage)

        self.max_positions = QSpinBox()
        self.max_positions.setRange(1, 10)
        params_form.addRow("Макс. позиций:", self.max_positions)

        self.signal_threshold = QDoubleSpinBox()
        self.signal_threshold.setRange(0.1, 1.0)
        self.signal_threshold.setSingleStep(0.05)
        self.signal_threshold.setDecimals(2)
        params_form.addRow("Порог сигнала:", self.signal_threshold)

        self.trailing_sl = QCheckBox("Трейлинг стоп-лосс")
        params_form.addRow(self.trailing_sl)

        self.trailing_distance = QDoubleSpinBox()
        self.trailing_distance.setRange(0.1, 10.0)
        self.trailing_distance.setSingleStep(0.1)
        self.trailing_distance.setSuffix("%")
        params_form.addRow("Трейлинг дистанция %:", self.trailing_distance)

        self.partial_close = QCheckBox("Частичное закрытие")
        params_form.addRow(self.partial_close)

        self.partial_close_pct = QDoubleSpinBox()
        self.partial_close_pct.setRange(10.0, 90.0)
        self.partial_close_pct.setSingleStep(10.0)
        self.partial_close_pct.setSuffix("%")
        params_form.addRow("Частичное закрытие %:", self.partial_close_pct)

        self.breakeven = QCheckBox("Безубыток (breakeven)")
        params_form.addRow(self.breakeven)

        layout.addWidget(params_group)

        # Кнопки
        buttons_layout = QHBoxLayout()
        apply_btn = QPushButton("Применить")
        apply_btn.clicked.connect(self._apply_settings)
        buttons_layout.addWidget(apply_btn)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)
        layout.addLayout(buttons_layout)

    def _on_style_changed(self, style_name):
        if style_name in QUICK_PROFILES:
            self._update_fields(QUICK_PROFILES[style_name])

    def _update_fields(self, profile):
        self.description_label.setText(profile.get("description", ""))
        self.risk_per_trade.setValue(profile.get("risk_per_trade", 2.0))
        self.max_leverage.setValue(profile.get("max_leverage", 3))
        self.max_positions.setValue(profile.get("max_positions", 3))
        self.signal_threshold.setValue(profile.get("signal_threshold", 0.5))
        self.trailing_sl.setChecked(profile.get("trailing_sl_enabled", True))
        self.trailing_distance.setValue(profile.get("trailing_distance_pct", 0.5))
        self.partial_close.setChecked(profile.get("partial_close_enabled", True))
        self.partial_close_pct.setValue(profile.get("partial_close_pct", 50.0))
        self.breakeven.setChecked(profile.get("breakeven_enabled", True))

    def _apply_settings(self):
        try:
            self.engine.risk_manager.risk_per_trade_pct = self.risk_per_trade.value()
            self.engine.risk_manager.max_leverage = self.max_leverage.value()
            self.engine.max_positions = self.max_positions.value()
            self.engine.signal_threshold = self.signal_threshold.value()
            self.engine.trailing_sl_enabled = self.trailing_sl.isChecked()
            self.engine.trailing_distance_pct = self.trailing_distance.value()
            self.engine.partial_close_enabled = self.partial_close.isChecked()
            self.engine.partial_close_pct = self.partial_close_pct.value()
            self.engine.breakeven_enabled = self.breakeven.isChecked()

            # Применяем ограничения User
            self.engine.risk_manager.set_user_limits(
                risk_pct=self.risk_per_trade.value(),
                max_lev=self.max_leverage.value(),
                max_pos=self.max_positions.value()
            )
            self.engine._save_config()
            QMessageBox.information(self, "Готово", "Настройки применены и сохранены в config.ini")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось применить настройки: {e}")
