"""
Risk Management: position sizing, leverage, SL/TP calculation, Kelly criterion.
Now with multi-step adaptive profile switching and negative TP protection.
"""
import logging
import json
import os
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

DEFAULT_ATR_MULT_SL = 1.5
DEFAULT_ATR_MULT_TP = 2.0

MIN_SL_RATIO_LONG = 0.98
MIN_SL_RATIO_SHORT = 1.02

PROFILE_RISK_ORDER = ['Conservative', 'Balanced', 'Adaptive', 'Aggressive', 'User']


class RiskManager:
    STATE_FILE = 'data/risk_state.json'

    def __init__(self):
        self.risk_per_trade_pct = 2.0
        self.max_leverage = 3
        self._night_mode = False
        self._current_profile = 'Adaptive'
        self._profiles = {
            'Conservative': {'risk_per_trade_pct': 1.0, 'max_leverage': 2},
            'Balanced':     {'risk_per_trade_pct': 2.0, 'max_leverage': 3},
            'Aggressive':   {'risk_per_trade_pct': 4.0, 'max_leverage': 5},
            'Adaptive':     {'risk_per_trade_pct': 2.0, 'max_leverage': 3},
            'User':         {'risk_per_trade_pct': 2.0, 'max_leverage': 3},
        }
        self._atr_multipliers: Dict[str, Dict[str, float]] = {}
        self._day_profiles = {
            0: {'risk_pct': 1.5, 'max_lev': 2}, 1: {'risk_pct': 1.5, 'max_lev': 2},
            2: {'risk_pct': 1.5, 'max_lev': 2}, 3: {'risk_pct': 1.5, 'max_lev': 2},
            4: {'risk_pct': 1.0, 'max_lev': 1}, 5: {'risk_pct': 1.0, 'max_lev': 1},
            6: {'risk_pct': 1.0, 'max_lev': 1},
        }
        self._kelly_enabled = False
        self._kelly_winrate = 0.5
        self._kelly_avg_win_loss_ratio = 2.0
        self.use_day_profile = True
        self.adaptive_risk_enabled = True
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        self._base_risk_pct = self.risk_per_trade_pct
        self._base_leverage = self.max_leverage

        self._original_profile = None
        self._auto_loss_stage = 0

        self._load_state()

    # ---------- Профили ----------
    def set_profile(self, profile: str):
        if profile not in self._profiles:
            return
        self._current_profile = profile
        self.risk_per_trade_pct = self._profiles[profile]['risk_per_trade_pct']
        self.max_leverage = self._profiles[profile]['max_leverage']
        self._base_risk_pct = self.risk_per_trade_pct
        self._base_leverage = self.max_leverage
        logger.info(f"Risk profile switched to: {profile} (risk={self.risk_per_trade_pct}%, max_lev={self.max_leverage})")

    def set_user_params(self, risk_pct: float, leverage: int):
        self._profiles['User']['risk_per_trade_pct'] = risk_pct
        self._profiles['User']['max_leverage'] = leverage
        self._save_state()
        if self._current_profile == 'User':
            self.set_profile('User')

    def set_night_mode(self, enabled: bool):
        self._night_mode = enabled
        if enabled:
            self.risk_per_trade_pct *= 0.5
            self.max_leverage = max(1, self.max_leverage - 1)
            logger.info("Night mode risk reduction applied")
        else:
            self.set_profile(self._current_profile)

    def apply_day_profile(self):
        if not self.use_day_profile:
            return
        dow = datetime.now(timezone.utc).weekday()
        day_cfg = self._day_profiles.get(dow)
        if day_cfg:
            self.risk_per_trade_pct = day_cfg['risk_pct']
            self.max_leverage = day_cfg['max_lev']
            logger.info(f"Day-of-week risk applied: {self.risk_per_trade_pct}%, leverage {self.max_leverage}")

    # ---------- ATR-множители ----------
    def set_atr_multipliers(self, symbol: str, sl_mult: float, tp_mult: float):
        self._atr_multipliers[symbol] = {'sl': sl_mult, 'tp': tp_mult}
        self._save_state()

    def get_atr_multipliers(self, symbol: str) -> Tuple[float, float]:
        if symbol in self._atr_multipliers:
            m = self._atr_multipliers[symbol]
            return m['sl'], m['tp']
        return DEFAULT_ATR_MULT_SL, DEFAULT_ATR_MULT_TP

    def get_sl_tp_levels(self, entry_price: float, side: str, atr: float, symbol: str = None) -> Dict[str, float]:
        sl_mult, tp_mult = self.get_atr_multipliers(symbol) if symbol else (DEFAULT_ATR_MULT_SL, DEFAULT_ATR_MULT_TP)
        min_sl_distance = entry_price * 0.005
        if side == 'BUY':
            distance = max(atr * sl_mult, min_sl_distance)
            sl = entry_price - distance
            tp = entry_price + atr * tp_mult
        else:
            distance = max(atr * sl_mult, min_sl_distance)
            sl = entry_price + distance
            tp = entry_price - atr * tp_mult

        # Первичная защита от отрицательного SL
        sl = max(entry_price * 0.001, sl)
        if side == 'BUY' and sl >= entry_price:
            sl = entry_price * 0.999
        elif side == 'SELL' and sl <= entry_price:
            sl = entry_price * 1.001

        # Минимальное расстояние SL (2% от цены)
        if side == 'BUY':
            sl = max(sl, entry_price * MIN_SL_RATIO_LONG)
        else:
            sl = max(sl, entry_price * MIN_SL_RATIO_SHORT)

        # Защита TP: для лонга не ниже цены, для шорта не отрицательный
        if side == 'BUY':
            tp = max(tp, entry_price * 1.001)
        else:
            tp = max(tp, entry_price * 0.001)

        return {'sl': sl, 'tp': tp, 'tp2': tp}

    # ---------- Плечо по волатильности ----------
    def get_optimal_leverage(self, symbol: str, price: float, atr: float) -> int:
        atr_pct = atr / price if price > 0 else 0.02
        if atr_pct > 0.05:
            return max(1, self.max_leverage - 2)
        elif atr_pct > 0.03:
            return max(1, self.max_leverage - 1)
        elif atr_pct < 0.01:
            return min(5, self.max_leverage + 1)
        return self.max_leverage

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

    def set_kelly_params(self, winrate: float, avg_win_loss_ratio: float, enabled: bool = True):
        self._kelly_winrate = winrate
        self._kelly_avg_win_loss_ratio = avg_win_loss_ratio
        self._kelly_enabled = enabled

    def update_kelly_from_history(self, portfolio):
        if not self._kelly_enabled:
            return
        trades = getattr(portfolio, '_trades', [])
        if len(trades) < 5:
            logger.debug(f"Not enough trades for Kelly update ({len(trades)} < 5)")
            return
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        total = len(trades)
        winrate = len(wins) / total if total > 0 else 0.5
        avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 1.0
        avg_loss = abs(sum(t.pnl for t in losses) / len(losses)) if losses else 1.0
        avg_wl_ratio = avg_win / avg_loss if avg_loss > 0 else 2.0
        self._kelly_winrate = 0.7 * self._kelly_winrate + 0.3 * winrate
        self._kelly_avg_win_loss_ratio = 0.7 * self._kelly_avg_win_loss_ratio + 0.3 * avg_wl_ratio
        logger.info(f"Kelly updated: winrate={self._kelly_winrate:.3f}, avg_wl={self._kelly_avg_win_loss_ratio:.2f}")
        self._save_state()

    def adapt_to_volatility(self, current_atr_pct: float):
        if self._night_mode:
            return
        if current_atr_pct > 0.05:
            self.risk_per_trade_pct = max(0.5, self.risk_per_trade_pct * 0.7)
            self.max_leverage = max(1, self.max_leverage - 1)
            logger.info(f"High volatility ({current_atr_pct:.2%}), risk reduced to {self.risk_per_trade_pct}%, leverage {self.max_leverage}")
        elif current_atr_pct < 0.01:
            self.risk_per_trade_pct = min(5.0, self.risk_per_trade_pct * 1.2)
            self.max_leverage = min(5, self.max_leverage + 1)
            logger.info(f"Low volatility ({current_atr_pct:.2%}), risk increased to {self.risk_per_trade_pct}%, leverage {self.max_leverage}")

    def can_open_position(self) -> bool:
        return True

    # =================================================================
    #   МНОГОСТУПЕНЧАТАЯ АДАПТАЦИЯ ПРОФИЛЯ ПО СЕРИЯМ
    # =================================================================
    def update_adaptive_risk(self, trade_pnl: float):
        if not self.adaptive_risk_enabled:
            return

        if trade_pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0

        if self._original_profile is None:
            self._original_profile = self._current_profile

        current_idx = PROFILE_RISK_ORDER.index(self._current_profile) if self._current_profile in PROFILE_RISK_ORDER else 2

        if self.consecutive_losses >= 3:
            if self._current_profile != 'Conservative':
                logger.warning("3 consecutive losses → switching to Conservative profile")
                self.set_profile('Conservative')
                self._auto_loss_stage = 2
        elif self.consecutive_losses >= 2:
            if current_idx > PROFILE_RISK_ORDER.index('Balanced'):
                if self._current_profile != 'Balanced':
                    logger.info("2 consecutive losses → switching to Balanced profile")
                    self.set_profile('Balanced')
                    self._auto_loss_stage = 1

        if self.consecutive_wins >= 3 and self._auto_loss_stage > 0:
            target_idx = min(current_idx + 1, len(PROFILE_RISK_ORDER) - 1)
            target_profile = PROFILE_RISK_ORDER[target_idx]
            if PROFILE_RISK_ORDER.index(self._original_profile) >= target_idx:
                if self._current_profile != target_profile:
                    logger.info(f"3 consecutive wins → upgrading to {target_profile}")
                    self.set_profile(target_profile)
                    self._auto_loss_stage -= 1
                    self.consecutive_wins = 0
                else:
                    self.consecutive_wins = 0
            else:
                if self._current_profile != self._original_profile:
                    logger.info(f"Adaptation finished, returning to original profile: {self._original_profile}")
                    self.set_profile(self._original_profile)
                self._original_profile = None
                self._auto_loss_stage = 0
                self.consecutive_wins = 0

    # ---------- Состояние ----------
    def _save_state(self):
        data = {
            'atr_multipliers': self._atr_multipliers,
            'kelly': {
                'enabled': self._kelly_enabled,
                'winrate': self._kelly_winrate,
                'avg_wl': self._kelly_avg_win_loss_ratio
            },
            'user_params': self._profiles.get('User', {'risk_per_trade_pct': 2.0, 'max_leverage': 3})
        }
        try:
            os.makedirs(os.path.dirname(self.STATE_FILE), exist_ok=True)
            with open(self.STATE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save risk state: {e}")

    def _load_state(self):
        if not os.path.exists(self.STATE_FILE):
            return
        try:
            with open(self.STATE_FILE, 'r') as f:
                data = json.load(f)
            self._atr_multipliers = data.get('atr_multipliers', {})
            k = data.get('kelly', {})
            self._kelly_enabled = k.get('enabled', False)
            self._kelly_winrate = k.get('winrate', 0.5)
            self._kelly_avg_win_loss_ratio = k.get('avg_wl', 2.0)
            user_params = data.get('user_params', {'risk_per_trade_pct': 2.0, 'max_leverage': 3})
            self._profiles['User'] = {
                'risk_per_trade_pct': user_params['risk_per_trade_pct'],
                'max_leverage': user_params['max_leverage']
            }
            logger.info("Risk state loaded")
        except Exception as e:
            logger.error(f"Failed to load risk state: {e}")
