"""
Preset Manager – сохранение и загрузка конфигураций бота.
Сохраняет: risk settings, engine settings, enabled strategies/filters,
timeframes, trading flags, moonshot, whale shield, human emulator params.
"""
import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

PRESETS_DIR = "data/presets"


class PresetManager:
    def __init__(self, engine):
        self.engine = engine
        os.makedirs(PRESETS_DIR, exist_ok=True)

    def save_preset(self, name: str) -> bool:
        """Сохраняет текущую конфигурацию в пресет."""
        preset = {
            'name': name,
            'created': datetime.now(timezone.utc).isoformat(),
            'risk': {
                'profile': self.engine.risk_manager._current_profile,
                'risk_per_trade_pct': self.engine.risk_manager.risk_per_trade_pct,
                'max_leverage': self.engine.risk_manager.max_leverage,
                'max_positions': self.engine.max_positions,
                'use_day_profile': self.engine.risk_manager.use_day_profile,
                'kelly_enabled': self.engine.risk_manager._kelly_enabled,
                'kelly_winrate': self.engine.risk_manager._kelly_winrate,
                'kelly_avg_win_loss': self.engine.risk_manager._kelly_avg_win_loss_ratio,
                'user_limits': {
                    'risk_pct': self.engine.risk_manager._user_risk_pct,
                    'max_lev': self.engine.risk_manager._user_max_leverage,
                    'max_pos': self.engine.risk_manager._user_max_positions,
                }
            },
            'engine': {
                'scan_interval': self.engine.scan_interval,
                'signal_threshold': self.engine.signal_threshold,
                'timeframes': self.engine.timeframes,
                'top_symbols': self.engine.top_n_symbols,
                'trailing_sl_enabled': self.engine.trailing_sl_enabled,
                'trailing_distance_pct': self.engine.trailing_distance_pct,
                'partial_close_enabled': self.engine.partial_close_enabled,
                'partial_close_pct': self.engine.partial_close_pct,
                'breakeven_enabled': self.engine.breakeven_enabled,
                'breakeven_atr_mult': self.engine.breakeven_atr_mult,
                'slippage_timeout_sec': self.engine.slippage_timeout_sec,
                'reinvest_profits': self.engine.reinvest_profits,
            },
            'strategies': [],
            'filters': [],
            'moonshot': {},
            'human': {},
        }

        # Стратегии
        for name, s in self.engine.strategies.items():
            preset['strategies'].append({
                'name': name,
                'enabled': s.enabled,
                'weight': s.weight,
                'config': s.config
            })

        # Фильтры
        for name, f in self.engine.filters.items():
            preset['filters'].append({
                'name': name,
                'enabled': f.enabled,
                'config': f.config
            })

        # Moonshot
        if hasattr(self.engine, 'moonshot') and self.engine.moonshot:
            preset['moonshot'] = {
                'capital_pct': self.engine.moonshot.capital_pct,
                'max_risk_pct': self.engine.moonshot.max_risk_pct,
                'scan_interval': self.engine.moonshot.scan_interval,
            }

        # Human Emulator
        if hasattr(self.engine, 'human_emulator') and self.engine.human_emulator:
            he = self.engine.human_emulator
            preset['human'] = {
                'ua_rotation': he.ua_rotation,
                'interface_delay_min': he.interface_delay_min,
                'interface_delay_max': he.interface_delay_max,
                'scan_jitter_min': he.scan_jitter_min,
                'scan_jitter_max': he.scan_jitter_max,
                'split_entry_enabled': he.split_entry_enabled,
                'tweak_tpsl_enabled': he.tweak_tpsl_enabled,
                'idle_mode': he.idle_mode,
            }

        path = os.path.join(PRESETS_DIR, f"{name}.json")
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(preset, f, indent=2, ensure_ascii=False)
            logger.info(f"Preset '{name}' saved to {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save preset {name}: {e}")
            return False

    def load_preset(self, name: str) -> bool:
        """Загружает пресет и применяет настройки к движку."""
        path = os.path.join(PRESETS_DIR, f"{name}.json")
        if not os.path.exists(path):
            logger.error(f"Preset '{name}' not found at {path}")
            return False

        try:
            with open(path, 'r', encoding='utf-8') as f:
                preset = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read preset {name}: {e}")
            return False

        try:
            # Риск
            risk = preset.get('risk', {})
            profile = risk.get('profile', 'SmartTurbo')
            self.engine.risk_manager.set_profile(profile)
            if 'risk_per_trade_pct' in risk:
                self.engine.risk_manager.risk_per_trade_pct = risk['risk_per_trade_pct']
            if 'max_leverage' in risk:
                self.engine.risk_manager.max_leverage = risk['max_leverage']
            if 'max_positions' in risk:
                self.engine.max_positions = risk['max_positions']
            self.engine.risk_manager.use_day_profile = risk.get('use_day_profile', True)
            self.engine.risk_manager._kelly_enabled = risk.get('kelly_enabled', False)
            self.engine.risk_manager._kelly_winrate = risk.get('kelly_winrate', 0.5)
            self.engine.risk_manager._kelly_avg_win_loss_ratio = risk.get('kelly_avg_win_loss', 2.0)
            user_limits = risk.get('user_limits', {})
            if user_limits.get('risk_pct') is not None:
                self.engine.risk_manager.set_user_limits(
                    risk_pct=user_limits['risk_pct'],
                    max_lev=user_limits['max_lev'],
                    max_pos=user_limits['max_pos']
                )

            # Engine
            eng = preset.get('engine', {})
            for key in ['scan_interval', 'signal_threshold', 'timeframes', 'top_symbols',
                        'trailing_sl_enabled', 'trailing_distance_pct',
                        'partial_close_enabled', 'partial_close_pct',
                        'breakeven_enabled', 'breakeven_atr_mult',
                        'slippage_timeout_sec', 'reinvest_profits']:
                if key in eng:
                    setattr(self.engine, key, eng[key])
            self.engine._save_config()

            # Стратегии
            for sdata in preset.get('strategies', []):
                name = sdata['name']
                if name in self.engine.strategies:
                    strat = self.engine.strategies[name]
                    strat.enabled = sdata.get('enabled', True)
                    strat.weight = sdata.get('weight', 1.0)
                    strat.config.update(sdata.get('config', {}))

            # Фильтры
            for fdata in preset.get('filters', []):
                name = fdata['name']
                if name in self.engine.filters:
                    flt = self.engine.filters[name]
                    flt.enabled = fdata.get('enabled', True)
                    flt.config.update(fdata.get('config', {}))

            # Moonshot
            moonshot = preset.get('moonshot')
            if moonshot and hasattr(self.engine, 'moonshot') and self.engine.moonshot:
                self.engine.moonshot.capital_pct = moonshot.get('capital_pct', 10)
                self.engine.moonshot.max_risk_pct = moonshot.get('max_risk_pct', 1)
                self.engine.moonshot.scan_interval = moonshot.get('scan_interval', 300)
                if self.engine.moonshot._running:
                    self.engine.moonshot.stop()
                    self.engine.moonshot.start()

            # Human Emulator
            human = preset.get('human')
            if human and hasattr(self.engine, 'human_emulator') and self.engine.human_emulator:
                he = self.engine.human_emulator
                for key in ['ua_rotation', 'interface_delay_min', 'interface_delay_max',
                            'scan_jitter_min', 'scan_jitter_max', 'split_entry_enabled',
                            'tweak_tpsl_enabled', 'idle_mode']:
                    if key in human:
                        setattr(he, key, human[key])

            self.engine.risk_manager._save_state()
            self.engine._save_config()
            logger.info(f"Preset '{name}' loaded successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to apply preset {name}: {e}")
            return False

    def list_presets(self) -> List[str]:
        """Возвращает имена доступных пресетов (без .json)."""
        try:
            files = [f for f in os.listdir(PRESETS_DIR) if f.endswith('.json')]
            return [os.path.splitext(f)[0] for f in files]
        except Exception:
            return []

    def delete_preset(self, name: str) -> bool:
        """Удаляет пресет."""
        path = os.path.join(PRESETS_DIR, f"{name}.json")
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"Preset '{name}' deleted")
            return True
        return False
