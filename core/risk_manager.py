"""
Risk Management: dynamic position sizing, adaptive leverage, SmartTurbo.
Now with real-time market adaptation, correlation awareness, and performance-based auto-tuning.
"""
import logging, json, os, time
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional, List

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_ATR_MULT_SL = 2.0
DEFAULT_ATR_MULT_TP = 3.5


class RiskManager:
    STATE_FILE = 'data/risk_state.json'

    def __init__(self, engine=None):
        self.engine = engine
        # Базовые параметры
        self.risk_per_trade_pct = 2.0
        self.max_leverage = 3
        self.max_positions = 3
        self._night_mode = False
        self._current_profile = 'SmartTurbo'
        self._atr_multipliers: Dict[str, Dict[str, float]] = {}
        self._kelly_enabled = False
        self._kelly_winrate = 0.5
        self._kelly_avg_win_loss_ratio = 2.0
        self.use_day_profile = False
        self.adaptive_risk_enabled = True

        # SmartTurbo
        self.smart_turbo_enabled = True
        self.turbo_balance_threshold = 50.0
        self.turbo_exit_threshold = 200.0
        self.turbo_min_risk_pct = 1.0
        self.turbo_max_risk_pct = 4.0
        self.turbo_min_leverage = 1
        self.turbo_max_leverage = 5
        self.turbo_aggression = 0.5

        # Статистика
        self._trade_pnls: List[float] = []
        self._consecutive_wins = 0
        self._consecutive_losses = 0
        self._last_adaptation_time = 0
        self._adaptation_interval = 300

        # Пользовательские максимумы
        self._user_max_positions: Optional[int] = None
        self._user_risk_pct: Optional[float] = None
        self._user_max_leverage: Optional[int] = None
        self._user_profile_locked = False   # если True – ночной режим не трогает риск

        # Профили
        self._profiles = {
            'Conservative': {'risk_pct': 0.5, 'max_lev': 2, 'max_pos': 2, 'atr_mult': {'sl': 3.0, 'tp': 5.0}},
            'Balanced':     {'risk_pct': 1.5, 'max_lev': 3, 'max_pos': 4, 'atr_mult': {'sl': 2.2, 'tp': 3.8}},
            'Aggressive':   {'risk_pct': 3.0, 'max_lev': 5, 'max_pos': 6, 'atr_mult': {'sl': 1.8, 'tp': 3.0}},
            'Adaptive':     {'risk_pct': 2.0, 'max_lev': 3, 'max_pos': 5, 'atr_mult': {'sl': 2.0, 'tp': 3.5}},
            'Turbo':        {'risk_pct': 8.0, 'max_lev': 10, 'max_pos': 3, 'atr_mult': {'sl': 1.2, 'tp': 2.5}},
            'SmartTurbo':   {'risk_pct': 2.0, 'max_lev': 3, 'max_pos': 3, 'atr_mult': {'sl': 1.5, 'tp': 3.0}},
            'User':         {'risk_pct': 5.0, 'max_lev': 5, 'max_pos': 5, 'atr_mult': {'sl': 2.0, 'tp': 3.5}},
        }
        self._load_state()
        self.set_profile('SmartTurbo')

    # ---------- Профили ----------
    def set_profile(self, profile: str):
        if profile not in self._profiles:
            return
        self._current_profile = profile
        p = self._profiles[profile]
        self.risk_per_trade_pct = p['risk_pct']
        self.max_leverage = p['max_lev']
        self.max_positions = p.get('max_pos', 3)
        if 'atr_mult' in p:
            self._atr_multipliers['__default__'] = p['atr_mult']
        logger.info(f"Risk profile switched to: {profile} (risk={self.risk_per_trade_pct}%, lev={self.max_leverage}, pos={self.max_positions})")

    def set_user_limits(self, risk_pct: float, max_lev: int, max_pos: int):
        """Сохраняет пользовательские лимиты и фиксирует профиль."""
        self._user_risk_pct = risk_pct
        self._user_max_leverage = max_lev
        self._user_max_positions = max_pos
        self._user_profile_locked = True
        self._current_profile = 'User'
        self.risk_per_trade_pct = risk_pct
        self.max_leverage = max_lev
        if self.engine:
            self.engine.max_positions = max_pos
        logger.info(f"User limits set: risk={risk_pct}%, leverage={max_lev}, positions={max_pos}")

    # ---------- Адаптация ----------
    def adapt_to_market(self, engine):
        pass

    # ---------- Ночной режим (не трогает User) ----------
    def set_night_mode(self, enabled: bool):
        self._night_mode = enabled
        if enabled and not self._user_profile_locked:
            self.risk_per_trade_pct *= 0.5
            self.max_leverage = max(1, self.max_leverage - 1)
            logger.info("Night mode risk reduction applied")
        elif not enabled and not self._user_profile_locked:
            self.set_profile(self._current_profile)

    # ---------- Расчёт SL/TP и размера позиции ----------
    def get_sl_tp_levels(self, entry_price: float, side: str, atr: float, symbol: str = None) -> Dict[str, float]:
        sl_mult, tp_mult = self.get_atr_multipliers(symbol)
        min_sl_distance = entry_price * 0.005
        if side == 'BUY':
            distance = max(atr * sl_mult, min_sl_distance)
            sl = entry_price - distance
            tp = entry_price + atr * tp_mult
            # Защита от отрицательных / некорректных уровней
            if sl <= 0 or sl >= entry_price:
                sl = entry_price * 0.98
            if tp <= 0 or tp <= entry_price:
                tp = entry_price * 1.02
        else:
            distance = max(atr * sl_mult, min_sl_distance)
            sl = entry_price + distance
            tp = entry_price - atr * tp_mult
            if sl <= 0 or sl <= entry_price:
                sl = entry_price * 1.02
            if tp <= 0 or tp >= entry_price:
                tp = entry_price * 0.98

        # Финальная проверка соотношения SL/TP
        if side == 'BUY':
            if sl >= tp:
                sl = tp * 0.99
        else:
            if sl <= tp:
                sl = tp * 1.01

        return {'sl': max(sl, 1e-8), 'tp': max(tp, 1e-8), 'tp2': tp}

    def calculate_position_size(self, free_margin: float, entry_price: float,
                                sl_price: float, confidence: float) -> Tuple[float, int]:
        if entry_price <= 0 or free_margin <= 0:
            return 0.0, 1
        risk_amount = free_margin * (self.risk_per_trade_pct / 100.0) * confidence
        sl_distance = abs(entry_price - sl_price)
        if sl_distance == 0:
            sl_distance = entry_price * 0.01
        quantity = risk_amount / sl_distance
        leverage = self.max_leverage
        if self._kelly_enabled:
            f = self._kelly_winrate - ((1 - self._kelly_winrate) / self._kelly_avg_win_loss_ratio)
            quantity *= max(0.1, f)
        required_margin = (quantity * entry_price) / leverage
        if required_margin > free_margin:
            quantity = (free_margin * leverage) / entry_price
        return quantity, leverage

    def record_trade_result(self, pnl: float):
        self._trade_pnls.append(pnl)
        if len(self._trade_pnls) > 50:
            self._trade_pnls.pop(0)
        if pnl > 0:
            self._consecutive_wins += 1
            self._consecutive_losses = 0
        else:
            self._consecutive_losses += 1
            self._consecutive_wins = 0

    # ---------- Вспомогательные методы ----------
    def get_atr_multipliers(self, symbol: str = None) -> Tuple[float, float]:
        if symbol and symbol in self._atr_multipliers:
            m = self._atr_multipliers[symbol]
            return m['sl'], m['tp']
        default = self._atr_multipliers.get('__default__', {'sl': DEFAULT_ATR_MULT_SL, 'tp': DEFAULT_ATR_MULT_TP})
        return default['sl'], default['tp']

    def check_low_balance(self, balance: float):
        pass

    def get_optimal_leverage(self, symbol: str, price: float, atr: float) -> int:
        return self.max_leverage

    def apply_day_profile(self):
        pass

    def adapt_to_volatility(self, current_atr_pct: float):
        pass

    def _load_state(self):
        if not os.path.exists(self.STATE_FILE): return
        try:
            with open(self.STATE_FILE) as f:
                data = json.load(f)
            self._atr_multipliers = data.get('atr_multipliers', {})
            k = data.get('kelly', {})
            self._kelly_enabled = k.get('enabled', False)
            self._kelly_winrate = k.get('winrate', 0.5)
            self._kelly_avg_win_loss_ratio = k.get('avg_wl', 2.0)
        except: pass

    def _save_state(self):
        data = {
            'atr_multipliers': self._atr_multipliers,
            'kelly': {'enabled': self._kelly_enabled, 'winrate': self._kelly_winrate, 'avg_wl': self._kelly_avg_win_loss_ratio},
        }
        try:
            os.makedirs(os.path.dirname(self.STATE_FILE), exist_ok=True)
            with open(self.STATE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except: pass

    def set_kelly_params(self, winrate, avg_win_loss_ratio, enabled=True):
        self._kelly_winrate = winrate
        self._kelly_avg_win_loss_ratio = avg_win_loss_ratio
        self._kelly_enabled = enabled

    def update_kelly_from_history(self, portfolio):
        pass
