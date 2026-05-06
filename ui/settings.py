"""Settings tab: API keys, risk profiles, strategy toggles, configuration."""
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QComboBox, QSlider,
    QCheckBox, QGroupBox, QFormLayout, QMessageBox,
    QTabWidget, QSpinBox, QDoubleSpinBox, QFileDialog,
    QScrollArea, QFrame
)
from PyQt5.QtCore import Qt

from ui.styles import theme

logger = logging.getLogger(__name__)


class SettingsTab(QWidget):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)

        # === API Keys Section ===
        keys_group = QGroupBox("API Keys")
        keys_layout = QFormLayout(keys_group)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("Enter BingX API Key")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        keys_layout.addRow("API Key:", self.api_key_input)

        self.api_secret_input = QLineEdit()
        self.api_secret_input.setPlaceholderText("Enter BingX API Secret")
        self.api_secret_input.setEchoMode(QLineEdit.Password)
        keys_layout.addRow("API Secret:", self.api_secret_input)

        keys_buttons = QHBoxLayout()
        self.btn_save_keys = QPushButton("Save Keys")
        self.btn_save_keys.clicked.connect(self._save_keys)
        keys_buttons.addWidget(self.btn_save_keys)

        self.btn_test_keys = QPushButton("Test Connection")
        self.btn_test_keys.clicked.connect(self._test_connection)
        keys_buttons.addWidget(self.btn_test_keys)

        self.btn_toggle_visible = QPushButton("Show/Hide")
        self.btn_toggle_visible.setCheckable(True)
        self.btn_toggle_visible.toggled.connect(self._toggle_key_visibility)
        keys_buttons.addWidget(self.btn_toggle_visible)

        keys_buttons.addStretch()
        keys_layout.addRow(keys_buttons)

        self.lbl_key_status = QLabel("Status: No keys configured (Demo mode)")
        self.lbl_key_status.setStyleSheet(f"color: {theme.colors['warning']};")
        keys_layout.addRow(self.lbl_key_status)

        content_layout.addWidget(keys_group)

        # === Risk Profile Section ===
        risk_group = QGroupBox("Risk Management")
        risk_layout = QFormLayout(risk_group)

        self.risk_profile = QComboBox()
        self.risk_profile.addItems(["Conservative", "Balanced", "Aggressive", "Adaptive"])
        self.risk_profile.currentTextChanged.connect(self._on_profile_change)
        risk_layout.addRow("Risk Profile:", self.risk_profile)

        self.risk_per_trade = QDoubleSpinBox()
        self.risk_per_trade.setRange(0.1, 10.0)
        self.risk_per_trade.setSingleStep(0.1)
        self.risk_per_trade.setDecimals(1)
        self.risk_per_trade.setSuffix("%")
        self.risk_per_trade.setValue(2.0)
        risk_layout.addRow("Risk per Trade:", self.risk_per_trade)

        self.max_leverage = QSpinBox()
        self.max_leverage.setRange(1, 20)
        self.max_leverage.setValue(3)
        risk_layout.addRow("Max Leverage:", self.max_leverage)

        self.max_positions = QSpinBox()
        self.max_positions.setRange(1, 20)
        self.max_positions.setValue(4)
        risk_layout.addRow("Max Positions:", self.max_positions)

        # --- Day-of-week risk override ---
        self.use_day_profile = QCheckBox("Reduce risk on weekdays (day-of-week profile)")
        self.use_day_profile.setChecked(True)
        risk_layout.addRow(self.use_day_profile)

        # --- Kelly Criterion ---
        self.kelly_enabled = QCheckBox("Use Kelly criterion for position sizing")
        self.kelly_enabled.setChecked(False)
        risk_layout.addRow(self.kelly_enabled)

        self.kelly_winrate = QDoubleSpinBox()
        self.kelly_winrate.setRange(0.0, 1.0)
        self.kelly_winrate.setSingleStep(0.05)
        self.kelly_winrate.setDecimals(2)
        self.kelly_winrate.setValue(0.5)
        self.kelly_winrate.setToolTip("Expected win rate (0.0 - 1.0)")
        risk_layout.addRow("Kelly Win Rate:", self.kelly_winrate)

        self.kelly_avg_win_loss = QDoubleSpinBox()
        self.kelly_avg_win_loss.setRange(0.5, 10.0)
        self.kelly_avg_win_loss.setSingleStep(0.1)
        self.kelly_avg_win_loss.setDecimals(1)
        self.kelly_avg_win_loss.setValue(2.0)
        self.kelly_avg_win_loss.setToolTip("Average Win/Loss ratio")
        risk_layout.addRow("Kelly Win/Loss ratio:", self.kelly_avg_win_loss)

        content_layout.addWidget(risk_group)

        # === Trading Settings ===
        trading_group = QGroupBox("Trading Settings")
        trading_layout = QFormLayout(trading_group)

        self.signal_threshold = QDoubleSpinBox()
        self.signal_threshold.setRange(0.1, 1.0)
        self.signal_threshold.setSingleStep(0.05)
        self.signal_threshold.setDecimals(2)
        self.signal_threshold.setValue(0.5)
        trading_layout.addRow("Signal Threshold:", self.signal_threshold)

        self.scan_interval = QSpinBox()
        self.scan_interval.setRange(10, 600)
        self.scan_interval.setSingleStep(10)
        self.scan_interval.setSuffix(" sec")
        self.scan_interval.setValue(60)
        trading_layout.addRow("Scan Interval:", self.scan_interval)

        self.timeframes = QLineEdit()
        self.timeframes.setText("15m,1h,4h")
        trading_layout.addRow("Timeframes:", self.timeframes)

        self.top_symbols = QSpinBox()
        self.top_symbols.setRange(10, 100)
        self.top_symbols.setValue(50)
        trading_layout.addRow("Top Symbols:", self.top_symbols)

        # --- Trailing Stop Settings ---
        self.trailing_sl = QCheckBox("Enable trailing stop loss")
        self.trailing_sl.setChecked(True)
        trading_layout.addRow(self.trailing_sl)

        self.trailing_distance = QDoubleSpinBox()
        self.trailing_distance.setRange(0.1, 10.0)
        self.trailing_distance.setSingleStep(0.1)
        self.trailing_distance.setDecimals(2)
        self.trailing_distance.setSuffix("%")
        self.trailing_distance.setValue(0.5)
        self.trailing_distance.setToolTip("Distance from current price to place trailing stop (%)")
        trading_layout.addRow("Trailing distance %:", self.trailing_distance)

        # --- Partial Close Settings ---
        self.partial_close = QCheckBox("Enable partial close")
        self.partial_close.setChecked(True)
        trading_layout.addRow(self.partial_close)

        self.partial_close_pct = QDoubleSpinBox()
        self.partial_close_pct.setRange(10.0, 90.0)
        self.partial_close_pct.setSingleStep(5.0)
        self.partial_close_pct.setDecimals(1)
        self.partial_close_pct.setSuffix("%")
        self.partial_close_pct.setValue(50.0)
        self.partial_close_pct.setToolTip("Percentage of position to close at first TP")
        trading_layout.addRow("Partial close %:", self.partial_close_pct)

        # --- Breakeven Settings ---
        self.breakeven = QCheckBox("Enable breakeven SL")
        self.breakeven.setChecked(True)
        trading_layout.addRow(self.breakeven)

        self.breakeven_atr_mult = QDoubleSpinBox()
        self.breakeven_atr_mult.setRange(0.5, 3.0)
        self.breakeven_atr_mult.setSingleStep(0.1)
        self.breakeven_atr_mult.setDecimals(1)
        self.breakeven_atr_mult.setValue(1.0)
        self.breakeven_atr_mult.setToolTip("ATR multiplier to trigger breakeven")
        trading_layout.addRow("Breakeven ATR mult:", self.breakeven_atr_mult)

        # --- Slippage protection ---
        self.slippage_timeout = QDoubleSpinBox()
        self.slippage_timeout.setRange(0.0, 60.0)
        self.slippage_timeout.setSingleStep(1.0)
        self.slippage_timeout.setDecimals(1)
        self.slippage_timeout.setSuffix(" sec")
        self.slippage_timeout.setValue(10.0)
        self.slippage_timeout.setToolTip("Max time to wait for limit order fill before switching to market")
        trading_layout.addRow("Slippage timeout:", self.slippage_timeout)

        content_layout.addWidget(trading_group)

        # === Strategy Toggles ===
        strategies_group = QGroupBox("Strategies")
        strategies_layout = QVBoxLayout(strategies_group)

        self.strategies_scroll = QScrollArea()
        self.strategies_scroll.setWidgetResizable(True)
        self.strategies_container = QWidget()
        self.strategies_list = QVBoxLayout(self.strategies_container)
        self.strategies_scroll.setWidget(self.strategies_container)
        self.strategies_scroll.setMaximumHeight(150)

        strategies_layout.addWidget(self.strategies_scroll)

        self.btn_reload_modules = QPushButton("Reload Modules")
        self.btn_reload_modules.clicked.connect(self._reload_modules)
        strategies_layout.addWidget(self.btn_reload_modules)

        content_layout.addWidget(strategies_group)

        # === Action Buttons ===
        actions_group = QGroupBox("Actions")
        actions_layout = QHBoxLayout(actions_group)

        self.btn_scan_now = QPushButton("Scan Now")
        self.btn_scan_now.clicked.connect(self._scan_now)
        actions_layout.addWidget(self.btn_scan_now)

        self.btn_optimize = QPushButton("Optimize Strategies")
        self.btn_optimize.clicked.connect(self._optimize)
        actions_layout.addWidget(self.btn_optimize)

        self.btn_export = QPushButton("Export Trades (CSV)")
        self.btn_export.clicked.connect(self._export_trades)
        actions_layout.addWidget(self.btn_export)

        self.btn_save_settings = QPushButton("Save Settings")
        self.btn_save_settings.clicked.connect(self._save_settings)
        actions_layout.addWidget(self.btn_save_settings)

        actions_layout.addStretch()
        content_layout.addWidget(actions_group)

        # === Notifications ===
        notif_group = QGroupBox("Notifications")
        notif_layout = QFormLayout(notif_group)

        self.enable_notifications = QCheckBox("Enable Windows notifications")
        self.enable_notifications.setChecked(True)
        notif_layout.addRow(self.enable_notifications)

        self.sound_notifications = QCheckBox("Enable sound alerts")
        self.sound_notifications.setChecked(True)
        notif_layout.addRow(self.sound_notifications)

        content_layout.addWidget(notif_group)

        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

    # ---------- Load / Save ----------
    def _load_settings(self):
        if not self.engine.auth.demo_mode:
            self.lbl_key_status.setText("Status: Keys configured")
            self.lbl_key_status.setStyleSheet(f"color: {theme.colors['success']};")

        self.risk_profile.setCurrentText(self.engine.risk_manager._current_profile)
        self.risk_per_trade.setValue(self.engine.risk_manager.risk_per_trade_pct)
        self.max_leverage.setValue(self.engine.risk_manager.max_leverage)
        self.max_positions.setValue(self.engine.max_positions)
        self.signal_threshold.setValue(self.engine.signal_threshold)
        self.scan_interval.setValue(self.engine.scan_interval)
        self.timeframes.setText(','.join(self.engine.timeframes))
        self.top_symbols.setValue(self.engine.top_n_symbols)

        self.trailing_sl.setChecked(self.engine.trailing_sl_enabled)
        self.trailing_distance.setValue(self.engine.trailing_distance_pct)
        self.partial_close.setChecked(self.engine.partial_close_enabled)
        self.partial_close_pct.setValue(self.engine.partial_close_pct)
        self.breakeven.setChecked(self.engine.breakeven_enabled)
        self.breakeven_atr_mult.setValue(self.engine.breakeven_atr_mult)
        self.slippage_timeout.setValue(self.engine.slippage_timeout_sec)

        # Загрузка настроек дня недели и Келли
        self.use_day_profile.setChecked(getattr(self.engine.risk_manager, 'use_day_profile', True))
        self.kelly_enabled.setChecked(self.engine.risk_manager._kelly_enabled)
        self.kelly_winrate.setValue(self.engine.risk_manager._kelly_winrate)
        self.kelly_avg_win_loss.setValue(self.engine.risk_manager._kelly_avg_win_loss_ratio)

        self._refresh_strategy_list()

    def _refresh_strategy_list(self):
        while self.strategies_list.count():
            item = self.strategies_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for name, strategy in self.engine.strategies.items():
            cb = QCheckBox(f"{name} (weight: {strategy.weight:.1f})")
            cb.setChecked(strategy.enabled)
            cb.stateChanged.connect(lambda state, n=name: self._toggle_strategy(n, state))
            self.strategies_list.addWidget(cb)

    def _toggle_strategy(self, name: str, state: int):
        if name in self.engine.strategies:
            self.engine.strategies[name].enabled = (state == Qt.Checked)
            logger.info(f"Strategy {name} {'enabled' if state else 'disabled'}")

    def _save_keys(self):
        key = self.api_key_input.text().strip()
        secret = self.api_secret_input.text().strip()
        if not key or not secret:
            QMessageBox.warning(self, "Error", "Please enter both API key and secret")
            return
        try:
            if self.engine.auth.save_keys(key, secret):
                QMessageBox.information(self, "Success", "API keys saved!")
                self.lbl_key_status.setText("Status: Keys saved (restart required)")
                self.lbl_key_status.setStyleSheet(f"color: {theme.colors['success']};")
            else:
                QMessageBox.critical(self, "Error", "Failed to save keys")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Save failed: {e}")

    def _test_connection(self):
        try:
            if self.engine.auth.test_connection():
                QMessageBox.information(self, "Success", "API connection successful!")
            else:
                QMessageBox.warning(self, "Failed", "Could not connect to BingX API")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Connection test failed: {e}")

    def _toggle_key_visibility(self, visible: bool):
        mode = QLineEdit.Normal if visible else QLineEdit.Password
        self.api_key_input.setEchoMode(mode)
        self.api_secret_input.setEchoMode(mode)

    def _on_profile_change(self, profile: str):
        self.engine.risk_manager.set_profile(profile)
        if profile == 'Conservative':
            self.risk_per_trade.setValue(1.0)
            self.max_leverage.setValue(2)
            self.max_positions.setValue(3)
        elif profile == 'Balanced':
            self.risk_per_trade.setValue(2.0)
            self.max_leverage.setValue(3)
            self.max_positions.setValue(5)
        elif profile == 'Aggressive':
            self.risk_per_trade.setValue(4.0)
            self.max_leverage.setValue(5)
            self.max_positions.setValue(8)

    def _reload_modules(self):
        try:
            self.engine.reload_modules()
            self._refresh_strategy_list()
            QMessageBox.information(self, "Success", "Modules reloaded!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Reload failed: {e}")

    def _scan_now(self):
        try:
            self.engine.manual_scan()
            QMessageBox.information(self, "Scan", "Market scan completed")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Scan failed: {e}")

    def _optimize(self):
        try:
            self.engine.optimize_strategies()
            QMessageBox.information(self, "Optimize", "Optimization started (check logs)")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Optimization failed: {e}")

    def _export_trades(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Trades", "trades.csv", "CSV Files (*.csv)"
        )
        if filepath:
            if self.engine.portfolio.export_trades_csv(filepath):
                QMessageBox.information(self, "Success", f"Trades exported to {filepath}")
            else:
                QMessageBox.warning(self, "Error", "Failed to export trades")

    def _save_settings(self):
        try:
            settings = {
                'max_positions': self.max_positions.value(),
                'scan_interval': self.scan_interval.value(),
                'signal_threshold': self.signal_threshold.value(),
                'timeframes': self.timeframes.text(),
                'top_symbols': self.top_symbols.value(),
                'risk_per_trade': self.risk_per_trade.value(),
                'max_leverage': self.max_leverage.value(),
                'risk_profile': self.risk_profile.currentText(),
            }
            self.engine.timeframes = self.timeframes.text().split(',')
            self.engine.top_n_symbols = self.top_symbols.value()
            # Применяем параметры
            self.engine.trailing_sl_enabled = self.trailing_sl.isChecked()
            self.engine.trailing_distance_pct = self.trailing_distance.value()
            self.engine.partial_close_enabled = self.partial_close.isChecked()
            self.engine.partial_close_pct = self.partial_close_pct.value()
            self.engine.breakeven_enabled = self.breakeven.isChecked()
            self.engine.breakeven_atr_mult = self.breakeven_atr_mult.value()
            self.engine.slippage_timeout_sec = self.slippage_timeout.value()

            # Сохраняем day-of-week и Kelly
            self.engine.risk_manager.use_day_profile = self.use_day_profile.isChecked()
            self.engine.risk_manager._kelly_enabled = self.kelly_enabled.isChecked()
            self.engine.risk_manager._kelly_winrate = self.kelly_winrate.value()
            self.engine.risk_manager._kelly_avg_win_loss_ratio = self.kelly_avg_win_loss.value()
            self.engine.risk_manager._save_state()   # сохраняем в risk_state.json
            # Пробрасываем в конфиг (чтобы при следующем старте подхватилось)
            self.engine._save_config()

            self.engine.update_settings(settings)
            QMessageBox.information(self, "Success", "Settings saved to config.ini")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Save failed: {e}")
