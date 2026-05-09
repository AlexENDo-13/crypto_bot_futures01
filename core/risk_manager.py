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
MIN_SL_RATIO_LONG = 0.98
MIN_SL_RATIO_SHORT = 1.02
MIN_TP_RATIO = 0.005


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

        # Пользовательские максимумы (не будут уменьшаться адаптацией)
        self._user_max_positions: Optional[int] = None
        self._user_risk_pct: Optional[float] = None
        self._user_max_leverage: Optional[int] = None

        # Профили
        self._profiles = {
            'Conservative': {'risk_pct': 0.5, 'max_lev': 2, 'max_pos': 2, 'atr_mult': {'sl': 3.0, 'tp': 5.0}},
            'Balanced':     {'risk_pct': 1.5, 'max_lev': 3, 'max_pos': 4, 'atr_mult': {'sl': 2.2, 'tp': 3.8}},
            'Aggressive':   {'risk_pct': 3.0, 'max_lev': 5, 'max_pos': 6, 'atr_mult': {'sl': 1.8, 'tp': 3.0}},
            'Adaptive':     {'risk_pct': 2.0, 'max_lev': 3, 'max_pos': 5, 'atr_mult': {'sl': 2.0, 'tp': 3.5}},
            'Turbo':        {'risk_pct': 8.0, 'max_lev': 10, 'max_pos': 3, 'atr_mult': {'sl': 1.2, 'tp': 2.5}},
            'SmartTurbo':   {'risk_pct': 2.0, 'max_lev': 3, 'max_pos': 3, 'atr_mult': {'sl': 1.5, 'tp': 3.0}},
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
        """Сохраняет пользовательские лимиты, которые адаптация не будет уменьшать."""
        self._user_risk_pct = risk_pct
        self._user_max_leverage = max_lev
        self._user_max_positions = max_pos
        # Сразу применяем
        self.risk_per_trade_pct = risk_pct
        self.max_leverage = max_lev
        if self.engine:
            self.engine.max_positions = max_pos
        logger.info(f"User limits set: risk={risk_pct}%, leverage={max_lev}, positions={max_pos}")

    def adapt_to_market(self, engine):
        """Периодическая адаптация к рынку."""
        if not self.adaptive_risk_enabled or not engine:
            return
        now = time.time()
        if now - self._last_adaptation_time < self._adaptation_interval:
            return
        self._last_adaptation_time = now

        regime = engine.regime_detector.get_current_regime().value
        winrate, pf = self._calculate_recent_stats()
        dd_pct = engine.portfolio.get_stats().get('current_drawdown_pct', 0)

        dyn_risk, dyn_lev, dyn_pos = self._calculate_dynamic_parameters(regime, winrate, pf, dd_pct)

        if not getattr(getattr(engine, 'risk_controller', None), '_emergency_lock', False):
            # Применяем, но не опускаемся ниже пользовательских минимумов
            if self._user_risk_pct is not None and dyn_risk < self._user_risk_pct:
                dyn_risk = self._user_risk_pct
            if self._user_max_leverage is not None and dyn_lev < self._user_max_leverage:
                dyn_lev = self._user_max_leverage
            if self._user_max_positions is not None and dyn_pos < self._user_max_positions:
                dyn_pos = self._user_max_positions

            self.risk_per_trade_pct = dyn_risk
            self.max_leverage = dyn_lev
            if engine.max_positions < dyn_pos:   # только увеличиваем, если адаптация советует
                engine.max_positions = dyn_pos
            logger.debug(f"Dynamic risk: risk={dyn_risk:.2f}%, lev={dyn_lev}, pos={dyn_pos}")

        self._adapt_atr_multipliers(regime, winrate)

    def _calculate_dynamic_parameters(self, regime, winrate, profit_factor, dd_pct):
        """Вычисляет динамические риск, плечо и количество позиций с учётом ограничений."""
        base = self._profiles['SmartTurbo']
        vol_factor = 1.0
        if self.engine and self.engine._candle_data:
            vols = []
            for sym in list(self.engine._candle_data.keys())[:5]:
                atr = self.engine._get_current_atr(sym)
                price = self.engine._get_current_price(sym)
                if price > 0:
                    vols.append(atr / price)
            if vols:
                avg_vol = np.mean(vols)
                if avg_vol > 0.05: vol_factor = 0.5
                elif avg_vol > 0.03: vol_factor = 0.7
                elif avg_vol < 0.005: vol_factor = 1.2

        wr_factor = 1.0
        if len(self._trade_pnls) >= 5:
            if winrate < 0.35: wr_factor = 0.5
            elif winrate < 0.45: wr_factor = 0.8
            elif winrate > 0.6: wr_factor = 1.2

        dd_factor = 1.0
        if dd_pct > 5: dd_factor = 0.5
        elif dd_pct > 2: dd_factor = 0.8

        risk = base['risk_pct'] * vol_factor * wr_factor * dd_factor
        # Ограничиваем верхней планкой из SmartTurbo и пользовательским значением
        max_risk = self.turbo_max_risk_pct if self._user_risk_pct is None else max(self.turbo_max_risk_pct, self._user_risk_pct)
        min_risk = self.turbo_min_risk_pct if self._user_risk_pct is None else self._user_risk_pct
        risk = max(min_risk, min(max_risk, risk))

        lev = int(base['max_lev'] * vol_factor)
        max_lev = self.turbo_max_leverage if self._user_max_leverage is None else max(self.turbo_max_leverage, self._user_max_leverage)
        lev = max(1, min(max_lev, lev))

        # Позиции: не снижаем ниже пользовательского лимита
        pos = max(1, min(5, base['max_pos']))
        if self._user_max_positions is not None:
            pos = max(pos, self._user_max_positions)

        return risk, lev, pos

    def _calculate_recent_stats(self):
        if len(self._trade_pnls) < 5:
            return 0.5, 1.0
        wins = sum(1 for p in self._trade_pnls if p > 0)
        winrate = wins / len(self._trade_pnls)
        avg_win = np.mean([p for p in self._trade_pnls if p > 0]) if wins else 1
        losses = [abs(p) for p in self._trade_pnls if p <= 0]
        avg_loss = np.mean(losses) if losses else 1
        profit_factor = avg_win / avg_loss if avg_loss else 2.0
        return winrate, profit_factor

    def _adapt_atr_multipliers(self, regime, winrate):
        base = self._atr_multipliers.get('__default__', (DEFAULT_ATR_MULT_SL, DEFAULT_ATR_MULT_TP))
        if winrate > 0.6:
            new_sl = max(1.0, base[0] * 0.9)
            new_tp = base[1] * 1.1
        elif winrate < 0.4:
            new_sl = base[0] * 1.2
            new_tp = max(1.5, base[1] * 0.9)
        else:
            new_sl, new_tp = base
        self._atr_multipliers['__default__'] = {'sl': round(new_sl,2), 'tp': round(new_tp,2)}

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

    def set_night_mode(self, enabled: bool):
        self._night_mode = enabled
        if enabled:
            self.risk_per_trade_pct *= 0.5
            self.max_leverage = max(1, self.max_leverage - 1)
            logger.info("Night mode risk reduction applied")
        else:
            self.set_profile(self._current_profile)

    def get_sl_tp_levels(self, entry_price: float, side: str, atr: float, symbol: str = None) -> Dict[str, float]:
        sl_mult, tp_mult = self.get_atr_multipliers(symbol)
        min_sl_distance = entry_price * 0.005
        if side == 'BUY':
            distance = max(atr * sl_mult, min_sl_distance)
            sl = entry_price - distance
            tp = entry_price + atr * tp_mult
        else:
            distance = max(atr * sl_mult, min_sl_distance)
            sl = entry_price + distance
            tp = entry_price - atr * tp_mult

        # Принудительная корректировка
        if side == 'BUY':
            if sl >= entry_price: sl = entry_price * 0.999
            if tp <= entry_price: tp = entry_price * 1.001
            if sl >= tp: sl = tp * 0.99
        else:
            if sl <= entry_price: sl = entry_price * 1.001
            if tp >= entry_price: tp = entry_price * 0.999
            if sl <= tp: sl = tp * 1.01
        return {'sl': max(sl, 1e-8), 'tp': max(tp, 1e-8), 'tp2': tp}

    def get_atr_multipliers(self, symbol: str = None) -> Tuple[float, float]:
        if symbol and symbol in self._atr_multipliers:
            m = self._atr_multipliers[symbol]
            return m['sl'], m['tp']
        default = self._atr_multipliers.get('__default__', {'sl': DEFAULT_ATR_MULT_SL, 'tp': DEFAULT_ATR_MULT_TP})
        return default['sl'], default['tp']

    def check_low_balance(self, balance: float):
        pass

    def get_optimal_leverage(self, symbol: str, price: float, atr: float) -> int:
        if price <= 0:
            return self.max_leverage
        atr_pct = atr / price
        if atr_pct > 0.05:
            return max(1, self.max_leverage - 2)
        elif atr_pct > 0.03:
            return max(1, self.max_leverage - 1)
        elif atr_pct < 0.01:
            return min(self.max_leverage, self.max_leverage + 1)
        return self.max_leverage

    def apply_day_profile(self):
        pass

    def adapt_to_volatility(self, current_atr_pct: float):
        if self._night_mode:
            return
        if current_atr_pct > 0.05:
            self.risk_per_trade_pct = max(self.turbo_min_risk_pct, self.risk_per_trade_pct * 0.7)
            self.max_leverage = max(1, self.max_leverage - 1)
            logger.info(f"High volatility ({current_atr_pct:.2%}), risk reduced")
        elif current_atr_pct < 0.01:
            self.risk_per_trade_pct = min(self.turbo_max_risk_pct, self.risk_per_trade_pct * 1.2)
            self.max_leverage = min(self.turbo_max_leverage, self.max_leverage + 1)
            logger.info(f"Low volatility ({current_atr_pct:.2%}), risk increased")

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
        if not self._kelly_enabled: return
        trades = getattr(portfolio, '_trades', [])
        if len(trades) < 5: return
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        wr = len(wins) / len(trades) if trades else 0.5
        avg_win = np.mean([t.pnl for t in wins]) if wins else 1
        avg_loss = np.mean([abs(t.pnl) for t in losses]) if losses else 1
        self._kelly_winrate = 0.7 * self._kelly_winrate + 0.3 * wr
        self._kelly_avg_win_loss_ratio = 0.7 * self._kelly_avg_win_loss_ratio + 0.3 * (avg_win / avg_loss if avg_loss else 2)
        self._save_state()
