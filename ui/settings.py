"""Settings tab: API keys, risk, strategies/indicators/filters, Moonshot configuration."""
import logging
from configparser import ConfigParser
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox, QGroupBox, QFormLayout, QMessageBox,
    QSpinBox, QDoubleSpinBox, QFileDialog, QScrollArea, QFrame,
    QDialog, QDialogButtonBox
)
from PyQt5.QtCore import Qt

from ui.styles import theme

logger = logging.getLogger(__name__)


class ParameterDialog(QDialog):
    def __init__(self, name, params_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Параметры: {name}")
        self.params_config = params_config
        self.widgets = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        for key, value in self.params_config.items():
            if isinstance(value, bool):
                cb = QCheckBox()
                cb.setChecked(value)
                self.widgets[key] = cb
                form.addRow(key, cb)
            elif isinstance(value, int):
                sb = QSpinBox()
                sb.setRange(1, 1000)
                sb.setValue(value)
                self.widgets[key] = sb
                form.addRow(key, sb)
            elif isinstance(value, float):
                dsb = QDoubleSpinBox()
                dsb.setDecimals(2)
                dsb.setRange(0.01, 1000.0)
                dsb.setValue(value)
                self.widgets[key] = dsb
                form.addRow(key, dsb)
            elif isinstance(value, list):
                le = QLineEdit()
                le.setText(', '.join(map(str, value)))
                self.widgets[key] = le
                form.addRow(key, le)
            else:
                le = QLineEdit()
                le.setText(str(value))
                self.widgets[key] = le
                form.addRow(key, le)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self):
        result = {}
        for key, w in self.widgets.items():
            if isinstance(w, QCheckBox):
                result[key] = w.isChecked()
            elif isinstance(w, QSpinBox):
                result[key] = w.value()
            elif isinstance(w, QDoubleSpinBox):
                result[key] = w.value()
            elif isinstance(w, QLineEdit):
                text = w.text()
                if ',' in text:
                    result[key] = [x.strip() for x in text.split(',') if x.strip()]
                else:
                    try:
                        result[key] = float(text) if '.' in text else int(text)
                    except ValueError:
                        result[key] = text
        return result


class SettingsTab(QWidget):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)

        # === API Keys ===
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

        # === Risk Management ===
        risk_group = QGroupBox("Risk Management")
        risk_layout = QFormLayout(risk_group)
        self.risk_profile = QComboBox()
        self.risk_profile.addItems(["Conservative", "Balanced", "Aggressive", "Adaptive", "User"])
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
        self.use_day_profile = QCheckBox("Reduce risk on weekdays (day-of-week profile)")
        self.use_day_profile.setChecked(True)
        risk_layout.addRow(self.use_day_profile)
        self.kelly_enabled = QCheckBox("Use Kelly criterion for position sizing")
        self.kelly_enabled.setChecked(False)
        risk_layout.addRow(self.kelly_enabled)
        self.kelly_winrate = QDoubleSpinBox()
        self.kelly_winrate.setRange(0.0, 1.0)
        self.kelly_winrate.setSingleStep(0.05)
        self.kelly_winrate.setDecimals(2)
        self.kelly_winrate.setValue(0.5)
        risk_layout.addRow("Kelly Win Rate:", self.kelly_winrate)
        self.kelly_avg_win_loss = QDoubleSpinBox()
        self.kelly_avg_win_loss.setRange(0.5, 10.0)
        self.kelly_avg_win_loss.setSingleStep(0.1)
        self.kelly_avg_win_loss.setDecimals(1)
        self.kelly_avg_win_loss.setValue(2.0)
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
        self.trailing_sl = QCheckBox("Enable trailing stop loss")
        self.trailing_sl.setChecked(True)
        trading_layout.addRow(self.trailing_sl)
        self.trailing_distance = QDoubleSpinBox()
        self.trailing_distance.setRange(0.1, 10.0)
        self.trailing_distance.setSingleStep(0.1)
        self.trailing_distance.setDecimals(2)
        self.trailing_distance.setSuffix("%")
        self.trailing_distance.setValue(0.5)
        trading_layout.addRow("Trailing distance %:", self.trailing_distance)
        self.partial_close = QCheckBox("Enable partial close")
        self.partial_close.setChecked(True)
        trading_layout.addRow(self.partial_close)
        self.partial_close_pct = QDoubleSpinBox()
        self.partial_close_pct.setRange(10.0, 90.0)
        self.partial_close_pct.setSingleStep(5.0)
        self.partial_close_pct.setDecimals(1)
        self.partial_close_pct.setSuffix("%")
        self.partial_close_pct.setValue(50.0)
        trading_layout.addRow("Partial close %:", self.partial_close_pct)
        self.breakeven = QCheckBox("Enable breakeven SL")
        self.breakeven.setChecked(True)
        trading_layout.addRow(self.breakeven)
        self.breakeven_atr_mult = QDoubleSpinBox()
        self.breakeven_atr_mult.setRange(0.5, 3.0)
        self.breakeven_atr_mult.setSingleStep(0.1)
        self.breakeven_atr_mult.setDecimals(1)
        self.breakeven_atr_mult.setValue(1.0)
        trading_layout.addRow("Breakeven ATR mult:", self.breakeven_atr_mult)
        self.slippage_timeout = QDoubleSpinBox()
        self.slippage_timeout.setRange(0.0, 60.0)
        self.slippage_timeout.setSingleStep(1.0)
        self.slippage_timeout.setDecimals(1)
        self.slippage_timeout.setSuffix(" sec")
        self.slippage_timeout.setValue(10.0)
        trading_layout.addRow("Slippage timeout:", self.slippage_timeout)
        content_layout.addWidget(trading_group)

        # === Moonshot Settings ===
        moonshot_group = QGroupBox("Moonshot")
        moonshot_layout = QFormLayout(moonshot_group)
        self.moonshot_capital_pct = QDoubleSpinBox()
        self.moonshot_capital_pct.setRange(0.0, 50.0)
        self.moonshot_capital_pct.setSingleStep(5.0)
        self.moonshot_capital_pct.setDecimals(1)
        self.moonshot_capital_pct.setSuffix("%")
        self.moonshot_capital_pct.setValue(10.0)
        moonshot_layout.addRow("Capital %:", self.moonshot_capital_pct)
        self.moonshot_max_risk_pct = QDoubleSpinBox()
        self.moonshot_max_risk_pct.setRange(0.1, 5.0)
        self.moonshot_max_risk_pct.setSingleStep(0.1)
        self.moonshot_max_risk_pct.setDecimals(1)
        self.moonshot_max_risk_pct.setSuffix("%")
        self.moonshot_max_risk_pct.setValue(1.0)
        moonshot_layout.addRow("Max Risk per Trade %:", self.moonshot_max_risk_pct)
        self.moonshot_scan = QSpinBox()
        self.moonshot_scan.setRange(60, 600)
        self.moonshot_scan.setSingleStep(30)
        self.moonshot_scan.setSuffix(" sec")
        self.moonshot_scan.setValue(300)
        moonshot_layout.addRow("Scan Interval:", self.moonshot_scan)
        content_layout.addWidget(moonshot_group)

        # === Strategies ===
        strat_group = QGroupBox("Strategies")
        strat_layout = QVBoxLayout(strat_group)
        self.strategies_widgets = {}
        for name, strategy in self.engine.strategies.items():
            row = QHBoxLayout()
            cb = QCheckBox(f"{name} (weight: {strategy.weight:.1f})")
            cb.setChecked(strategy.enabled)
            cb.stateChanged.connect(lambda state, n=name: self._toggle_strategy(n, state))
            row.addWidget(cb)
            btn_cfg = QPushButton("Config")
            btn_cfg.clicked.connect(lambda checked, n=name: self._configure_strategy(n))
            row.addWidget(btn_cfg)
            row.addStretch()
            strat_layout.addLayout(row)
            self.strategies_widgets[name] = (cb, btn_cfg)
        self.btn_reload_modules = QPushButton("Reload Modules")
        self.btn_reload_modules.clicked.connect(self._reload_modules)
        strat_layout.addWidget(self.btn_reload_modules)
        content_layout.addWidget(strat_group)

        # === Indicators ===
        ind_group = QGroupBox("Indicators")
        ind_layout = QVBoxLayout(ind_group)
        for name, indicator in self.engine.indicators.items():
            row = QHBoxLayout()
            lbl = QLabel(f"{name} (period: {indicator.config.get('period', 'N/A')})")
            row.addWidget(lbl)
            btn_cfg = QPushButton("Config")
            btn_cfg.clicked.connect(lambda checked, n=name: self._configure_indicator(n))
            row.addWidget(btn_cfg)
            row.addStretch()
            ind_layout.addLayout(row)
        content_layout.addWidget(ind_group)

        # === Filters ===
        flt_group = QGroupBox("Filters")
        flt_layout = QVBoxLayout(flt_group)
        for name, filter_obj in self.engine.filters.items():
            row = QHBoxLayout()
            cb = QCheckBox(f"{name} (enabled)")
            cb.setChecked(filter_obj.enabled)
            cb.stateChanged.connect(lambda state, n=name: self._toggle_filter(n, state))
            row.addWidget(cb)
            btn_cfg = QPushButton("Config")
            btn_cfg.clicked.connect(lambda checked, n=name: self._configure_filter(n))
            row.addWidget(btn_cfg)
            row.addStretch()
            flt_layout.addLayout(row)
        content_layout.addWidget(flt_group)

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

        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)

    # ---------- Вспомогательные методы ----------
    def _configure_strategy(self, name):
        strat = self.engine.strategies[name]
        dlg = ParameterDialog(name, strat.config)
        if dlg.exec_() == QDialog.Accepted:
            new_params = dlg.get_values()
            cls = type(strat)
            new_strat = cls(new_params)
            new_strat.enabled = strat.enabled
            new_strat.weight = strat.weight
            self.engine.strategies[name] = new_strat
            logger.info(f"Strategy {name} updated with params: {new_params}")

    def _configure_indicator(self, name):
        ind = self.engine.indicators[name]
        dlg = ParameterDialog(name, ind.config)
        if dlg.exec_() == QDialog.Accepted:
            new_params = dlg.get_values()
            cls = type(ind)
            new_ind = cls(new_params)
            self.engine.indicators[name] = new_ind
            logger.info(f"Indicator {name} updated: {new_params}")

    def _configure_filter(self, name):
        flt = self.engine.filters[name]
        dlg = ParameterDialog(name, flt.config)
        if dlg.exec_() == QDialog.Accepted:
            new_params = dlg.get_values()
            flt.config.update(new_params)
            if 'enabled' in new_params:
                flt.enabled = new_params['enabled']
            logger.info(f"Filter {name} updated: {new_params}")

    def _toggle_filter(self, name, state):
        if name in self.engine.filters:
            self.engine.filters[name].enabled = (state == Qt.Checked)

    def _toggle_strategy(self, name, state):
        if name in self.engine.strategies:
            self.engine.strategies[name].enabled = (state == Qt.Checked)

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
        self.use_day_profile.setChecked(getattr(self.engine.risk_manager, 'use_day_profile', True))
        self.kelly_enabled.setChecked(self.engine.risk_manager._kelly_enabled)
        self.kelly_winrate.setValue(self.engine.risk_manager._kelly_winrate)
        self.kelly_avg_win_loss.setValue(self.engine.risk_manager._kelly_avg_win_loss_ratio)
        if hasattr(self.engine, 'moonshot') and self.engine.moonshot:
            self.moonshot_capital_pct.setValue(self.engine.moonshot.capital_pct)
            self.moonshot_max_risk_pct.setValue(self.engine.moonshot.max_risk_pct)
            self.moonshot_scan.setValue(self.engine.moonshot.scan_interval)

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

    def _toggle_key_visibility(self, visible):
        mode = QLineEdit.Normal if visible else QLineEdit.Password
        self.api_key_input.setEchoMode(mode)
        self.api_secret_input.setEchoMode(mode)

    def _on_profile_change(self, profile):
        self.engine.risk_manager.set_profile(profile)
        # Apply max_positions from profile
        max_pos = self.engine.risk_manager.get_profile_max_positions(profile)
        self.engine.max_positions = max_pos
        self.max_positions.setValue(max_pos)

    def _reload_modules(self):
        try:
            self.engine.reload_modules()
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
        filepath, _ = QFileDialog.getSaveFileName(self, "Export Trades", "trades.csv", "CSV Files (*.csv)")
        if filepath:
            if self.engine.portfolio.export_trades_csv(filepath):
                QMessageBox.information(self, "Success", f"Trades exported to {filepath}")
            else:
                QMessageBox.warning(self, "Error", "Failed to export trades")

    def _save_settings(self):
        try:
            # Main params
            self.engine.max_positions = self.max_positions.value()
            self.engine.scan_interval = self.scan_interval.value()
            self.engine.signal_threshold = self.signal_threshold.value()
            self.engine.timeframes = self.timeframes.text().split(',')
            self.engine.top_n_symbols = self.top_symbols.value()

            # Risk manager
            risk_pct = self.risk_per_trade.value()
            leverage = self.max_leverage.value()
            profile = self.risk_profile.currentText()

            if profile == 'User':
                self.engine.risk_manager.set_user_params(risk_pct, leverage)
            else:
                self.engine.risk_manager.risk_per_trade_pct = risk_pct
                self.engine.risk_manager.max_leverage = leverage
                self.engine.risk_manager.set_profile(profile)

            self.engine.risk_manager.use_day_profile = self.use_day_profile.isChecked()
            self.engine.risk_manager._kelly_enabled = self.kelly_enabled.isChecked()
            self.engine.risk_manager._kelly_winrate = self.kelly_winrate.value()
            self.engine.risk_manager._kelly_avg_win_loss_ratio = self.kelly_avg_win_loss.value()

            # Trading
            self.engine.trailing_sl_enabled = self.trailing_sl.isChecked()
            self.engine.trailing_distance_pct = self.trailing_distance.value()
            self.engine.partial_close_enabled = self.partial_close.isChecked()
            self.engine.partial_close_pct = self.partial_close_pct.value()
            self.engine.breakeven_enabled = self.breakeven.isChecked()
            self.engine.breakeven_atr_mult = self.breakeven_atr_mult.value()
            self.engine.slippage_timeout_sec = self.slippage_timeout.value()

            # Moonshot
            moonshot_capital = 0.0
            moonshot_risk = 0.0
            moonshot_scan = 0
            if hasattr(self.engine, 'moonshot') and self.engine.moonshot:
                self.engine.moonshot.capital_pct = self.moonshot_capital_pct.value()
                self.engine.moonshot.max_risk_pct = self.moonshot_max_risk_pct.value()
                self.engine.moonshot.scan_interval = self.moonshot_scan.value()
                if self.engine.moonshot._running:
                    self.engine.moonshot.stop()
                    self.engine.moonshot.start()
                moonshot_capital = self.engine.moonshot.capital_pct
                moonshot_risk = self.engine.moonshot.max_risk_pct
                moonshot_scan = self.engine.moonshot.scan_interval
                logger.info("Moonshot parameters updated")

            # Save filter params to config.ini and collect current values
            volume_surge_val = 1.5
            liquidity_val = 0.3
            try:
                cfg = ConfigParser()
                cfg.read('config.ini')

                if not cfg.has_section('FILTERS'):
                    cfg.add_section('FILTERS')

                volume_surge = self.engine.filters.get('VolumeSurgeFilter')
                if volume_surge:
                    val = volume_surge.config.get('min_volume_mult', 1.5)
                    cfg.set('FILTERS', 'volume_surge_min_mult', str(val))
                    volume_surge_val = val

                liquidity = self.engine.filters.get('LiquidityFilter')
                if liquidity:
                    val = liquidity.config.get('min_volume_ratio', 0.3)
                    cfg.set('FILTERS', 'liquidity_min_ratio', str(val))
                    liquidity_val = val

                with open('config.ini', 'w') as f:
                    cfg.write(f)
                logger.info("Filter parameters saved to config.ini")
            except Exception as e:
                logger.error(f"Failed to save filter settings to config.ini: {e}")

            self.engine.risk_manager._save_state()
            self.engine._save_config()

            # Расширенное логирование
            logger.info(
                "Settings saved: risk=%.1f%%, leverage=%dx, positions=%d, profile=%s, "
                "signal_threshold=%.2f, trailing_distance=%.2f%%, breakeven_atr=%.2f, "
                "volume_surge_min_mult=%.2f, liquidity_min_ratio=%.2f, "
                "moonshot_capital=%.1f%%, moonshot_risk=%.1f%%, moonshot_scan=%ds",
                risk_pct, leverage, self.engine.max_positions, profile,
                self.engine.signal_threshold,
                self.engine.trailing_distance_pct,
                self.engine.breakeven_atr_mult,
                volume_surge_val,
                liquidity_val,
                moonshot_capital,
                moonshot_risk,
                moonshot_scan
            )
            QMessageBox.information(self, "Success", "Settings saved to config.ini")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Save failed: {e}")
