import logging
import json
import os
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

DEFAULT_ATR_MULT_SL = 1.5
DEFAULT_ATR_MULT_TP = 2.0


class RiskManager:
    STATE_FILE = 'data/risk_state.json'

    def __init__(self):
        self.risk_per_trade_pct = 2.0
        self.max_leverage = 3
        self._night_mode = False
        self._current_profile = 'Adaptive'
        self._profiles = {
            'Conservative': {'risk_per_trade_pct': 1.0, 'max_leverage': 2},
            'Balanced': {'risk_per_trade_pct': 2.0, 'max_leverage': 3},
            'Aggressive': {'risk_per_trade_pct': 4.0, 'max_leverage': 5},
            'Adaptive': {'risk_per_trade_pct': 2.0, 'max_leverage': 3},
        }
        # Пользовательские множители ATR на пару (из автотюнинга)
        self._atr_multipliers: Dict[str, Dict[str, float]] = {}  # symbol -> {sl_mult, tp_mult}
        self._day_profiles = {
            0: {'risk_pct': 1.5, 'max_lev': 2},  # Пн
            1: {'risk_pct': 1.5, 'max_lev': 2},  # Вт
            2: {'risk_pct': 1.5, 'max_lev': 2},  # Ср
            3: {'risk_pct': 1.5, 'max_lev': 2},  # Чт
            4: {'risk_pct': 1.0, 'max_lev': 1},  # Пт (снижаем)
            5: {'risk_pct': 1.0, 'max_lev': 1},  # Сб
            6: {'risk_pct': 1.0, 'max_lev': 1},  # Вс
        }
        self._kelly_enabled = False
        self._kelly_winrate = 0.5
        self._kelly_avg_win_loss_ratio = 2.0
        self.use_day_profile = True

        # === Адаптивное изменение риска по сериям ===
        self.adaptive_risk_enabled = True
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        self._base_risk_pct = self.risk_per_trade_pct
        self._base_leverage = self.max_leverage

        self._load_state()

    # ---------- Профили ----------
    def set_profile(self, profile: str):
        if profile in self._profiles:
            self._current_profile = profile
            self.risk_per_trade_pct = self._profiles[profile]['risk_per_trade_pct']
            self.max_leverage = self._profiles[profile]['max_leverage']
            self._base_risk_pct = self.risk_per_trade_pct
            self._base_leverage = self.max_leverage
            logger.info(f"Risk profile switched to: {profile} (risk={self.risk_per_trade_pct}%, max_lev={self.max_leverage})")

    def set_night_mode(self, enabled: bool):
        self._night_mode = enabled
        if enabled:
            self.risk_per_trade_pct *= 0.5
            self.max_leverage = max(1, self.max_leverage - 1)
            logger.info("Night mode risk reduction applied")
        else:
            self.set_profile(self._current_profile)

    def apply_day_profile(self):
        """Применяет профиль риска по текущему дню недели (UTC)."""
        if not self.use_day_profile:
            return
        dow = datetime.now(timezone.utc).weekday()
        day_cfg = self._day_profiles.get(dow)
        if day_cfg:
            self.risk_per_trade_pct = day_cfg['risk_pct']
            self.max_leverage = day_cfg['max_lev']
            logger.info(f"Day-of-week risk applied: {self.risk_per_trade_pct}%, leverage {self.max_leverage}")

    # ---------- ATR-множители (индивидуальные для пары) ----------
    def set_atr_multipliers(self, symbol: str, sl_mult: float, tp_mult: float):
        self._atr_multipliers[symbol] = {'sl': sl_mult, 'tp': tp_mult}
        self._save_state()

    def get_atr_multipliers(self, symbol: str) -> Tuple[float, float]:
        """Возвращает (sl_mult, tp_mult) для символа, иначе дефолтные."""
        if symbol in self._atr_multipliers:
            m = self._atr_multipliers[symbol]
            return m['sl'], m['tp']
        return DEFAULT_ATR_MULT_SL, DEFAULT_ATR_MULT_TP

    def get_sl_tp_levels(self, entry_price: float, side: str, atr: float, symbol: str = None) -> Dict[str, float]:
        """Расчёт SL/TP с учётом индивидуальных множителей пары и защитой от отрицательного SL."""
        sl_mult, tp_mult = self.get_atr_multipliers(symbol) if symbol else (DEFAULT_ATR_MULT_SL, DEFAULT_ATR_MULT_TP)

        # Минимальное расстояние SL от входа — 0.5% от цены
        min_sl_distance = entry_price * 0.005

        if side == 'BUY':
            sl = entry_price - max(atr * sl_mult, min_sl_distance)
            tp = entry_price + atr * tp_mult
        else:
            sl = entry_price + max(atr * sl_mult, min_sl_distance)
            tp = entry_price - atr * tp_mult

        return {'sl': sl, 'tp': tp, 'tp2': tp}

    # ---------- Плечо по волатильности ----------
    def get_optimal_leverage(self, symbol: str, price: float, atr: float) -> int:
        """Автоопределение безопасного плеча исходя из волатильности."""
        atr_pct = atr / price if price > 0 else 0.02
        if atr_pct > 0.05:
            return max(1, self.max_leverage - 2)
        elif atr_pct > 0.03:
            return max(1, self.max_leverage - 1)
        elif atr_pct < 0.01:
            return min(5, self.max_leverage + 1)
        return self.max_leverage

    # ---------- Позиционирование ----------
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
        # Kelly adjustment с реальным winrate
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

    # === FIX 3: Обновление Kelly из реальной истории ===
    def update_kelly_from_history(self, portfolio):
        """Обновляет Kelly параметры из реальной истории сделок."""
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

        # Плавное обновление (сглаживание)
        self._kelly_winrate = 0.7 * self._kelly_winrate + 0.3 * winrate
        self._kelly_avg_win_loss_ratio = 0.7 * self._kelly_avg_win_loss_ratio + 0.3 * avg_wl_ratio

        logger.info(f"Kelly updated: winrate={self._kelly_winrate:.3f}, avg_wl={self._kelly_avg_win_loss_ratio:.2f}")
        self._save_state()

    # ---------- Адаптация ----------
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

    # ---------- Адаптивный риск по сериям ----------
    def update_adaptive_risk(self, trade_pnl: float):
        """Автоматически меняет риск в зависимости от серии результатов."""
        if not self.adaptive_risk_enabled:
            return
        if trade_pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0

        # Корректируем риск
        if self.consecutive_wins >= 3:
            self.risk_per_trade_pct = min(5.0, self._base_risk_pct * (1 + 0.1 * self.consecutive_wins))
            self.max_leverage = min(5, self._base_leverage + 1)
        elif self.consecutive_losses >= 2:
            self.risk_per_trade_pct = max(0.5, self._base_risk_pct * (1 - 0.1 * self.consecutive_losses))
            self.max_leverage = max(1, self._base_leverage - 1)
        else:
            # Возвращаем к базовым, если серия прервалась
            self.risk_per_trade_pct = self._base_risk_pct
            self.max_leverage = self._base_leverage

    # ---------- Состояние ----------
    def _save_state(self):
        data = {
            'atr_multipliers': self._atr_multipliers,
            'kelly': {
                'enabled': self._kelly_enabled,
                'winrate': self._kelly_winrate,
                'avg_wl': self._kelly_avg_win_loss_ratio
            }
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
            logger.info("Risk state loaded")
        except Exception as e:
            logger.error(f"Failed to load risk state: {e}")
