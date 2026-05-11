"""
Risk Management – микро‑режим для скальпинга и наращивания депозита.
При балансе < 50 USDT: плечо 5x, 1 позиция, SL=0.8 ATR, TP=1.6 ATR, сигнал ≥0.3.
"""
import logging, json, os, time
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional, List
import numpy as np

logger = logging.getLogger(__name__)
DEFAULT_ATR_MULT_SL = 1.0
DEFAULT_ATR_MULT_TP = 2.0

class RiskManager:
    STATE_FILE = 'data/risk_state.json'
    def __init__(self, engine=None):
        self.engine = engine
        self.risk_per_trade_pct = 5.0
        self.max_leverage = 5
        self.max_positions = 1
        self._night_mode = False
        self._current_profile = 'Micro'
        self._atr_multipliers: Dict[str, Dict[str, float]] = {}
        self._kelly_enabled = False
        self.use_day_profile = False
        self.adaptive_risk_enabled = True
        self._trade_pnls: List[float] = []
        self._last_adaptation_time = 0
        self._adaptation_interval = 300
        self._user_max_positions: Optional[int] = None
        self._user_risk_pct: Optional[float] = None
        self._user_max_leverage: Optional[int] = None
        # Единственный профиль для микро‑скальпинга
        self._profiles = {
            'Micro': {'risk_pct': 5.0, 'max_lev': 5, 'max_pos': 1, 'atr_mult': {'sl': 0.8, 'tp': 1.6}},
            'User':  {'risk_pct': 5.0, 'max_lev': 5, 'max_pos': 1, 'atr_mult': {'sl': 0.8, 'tp': 1.6}},
        }
        self._load_state()
        self.set_profile('Micro')

    def set_profile(self, profile: str):
        if profile not in self._profiles: return
        self._current_profile = profile
        p = self._profiles[profile]
        self.risk_per_trade_pct = p['risk_pct']
        self.max_leverage = p['max_lev']
        self.max_positions = p.get('max_pos', 1)
        if 'atr_mult' in p:
            self._atr_multipliers['__default__'] = p['atr_mult']

    def set_user_limits(self, risk_pct: float, max_lev: int, max_pos: int):
        self._user_risk_pct = risk_pct
        self._user_max_leverage = max_lev
        self._user_max_positions = max_pos
        self._current_profile = 'User'
        self.risk_per_trade_pct = risk_pct
        self.max_leverage = max_lev
        if self.engine: self.engine.max_positions = max_pos

    def adapt_to_market(self, engine):
        if not engine or not self.adaptive_risk_enabled: return
        now = time.time()
        if now - self._last_adaptation_time < self._adaptation_interval: return
        self._last_adaptation_time = now
        balance = engine.portfolio._balance or 0.0
        if balance < 50:
            self._apply_micro_mode(engine)
            return
        # Обычная адаптация (не достигается при малом балансе)
        self.risk_per_trade_pct = 5.0
        self.max_leverage = 5
        if engine: engine.max_positions = 1

    def _apply_micro_mode(self, engine):
        self.risk_per_trade_pct = 5.0
        self.max_leverage = 5
        self._current_profile = 'Micro'
        self._atr_multipliers['__default__'] = {'sl': 0.8, 'tp': 1.6}
        if engine:
            engine.max_positions = 2
            engine.signal_threshold = 0.3
            f = engine.filters.get('OrderFlowImbalance')
            if f and f.enabled: f.config['min_delta_ratio'] = 0.6
        logger.info("Micro-mode for scalping: SL=0.8 ATR, TP=1.6 ATR, 1 position, threshold=0.3")

    def get_sl_tp_levels(self, entry_price, side, atr, symbol=None):
        sl_mult, tp_mult = self.get_atr_multipliers(symbol)
        min_sl = entry_price * 0.003
        if side == 'BUY':
            sl = entry_price - max(atr * sl_mult, min_sl)
            tp = entry_price + atr * tp_mult
        else:
            sl = entry_price + max(atr * sl_mult, min_sl)
            tp = entry_price - atr * tp_mult
        return {'sl': max(sl, 1e-8), 'tp': max(tp, 1e-8), 'tp2': tp}

    def calculate_position_size(self, free_margin, entry_price, sl_price, confidence):
        if entry_price <= 0 or free_margin <= 0: return 0.0, 1
        risk = free_margin * (self.risk_per_trade_pct / 100) * confidence
        sl_dist = abs(entry_price - sl_price)
        qty = risk / sl_dist if sl_dist != 0 else 0
        lev = self.max_leverage
        margin_req = (qty * entry_price) / lev
        if margin_req > free_margin:
            qty = (free_margin * lev) / entry_price
        return qty, lev

    def get_atr_multipliers(self, symbol=None):
        default = self._atr_multipliers.get('__default__', {'sl': 0.8, 'tp': 1.6})
        return default['sl'], default['tp']

    def record_trade_result(self, pnl):
        self._trade_pnls.append(pnl)
        if len(self._trade_pnls) > 50: self._trade_pnls.pop(0)

    def get_optimal_leverage(self, symbol, price, atr): return self.max_leverage
    def apply_day_profile(self): pass
    def adapt_to_volatility(self, current_atr_pct): pass
    def check_low_balance(self, balance): pass
    def _load_state(self):
        if not os.path.exists(self.STATE_FILE): return
        try:
            with open(self.STATE_FILE) as f:
                data = json.load(f)
            self._atr_multipliers = data.get('atr_multipliers', {})
        except: pass
    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.STATE_FILE), exist_ok=True)
            with open(self.STATE_FILE, 'w') as f:
                json.dump({'atr_multipliers': self._atr_multipliers}, f, indent=2)
        except: pass
