"""
Risk Management – специальный микро-скальпинговый режим для баланса <100 USDT.
Исправлено: гарантированный минимальный размер позиции (5 USDT), чтобы избежать "Zero quantity".
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
        self._min_trade_interval_seconds = 90
        self._last_trade_time = 0.0

        self._profiles = {
            'Micro': {'risk_pct': 20.0, 'max_lev': 3, 'max_pos': 1, 'atr_mult': {'sl': 0.15, 'tp': 0.3}},
            'User':  {'risk_pct': 5.0,  'max_lev': 5, 'max_pos': 1, 'atr_mult': {'sl': 0.8, 'tp': 1.6}},
        }
        self._load_state()
        self.set_profile('Micro')

    def set_profile(self, profile: str):
        if profile not in self._profiles:
            return
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
        if self.engine:
            self.engine.max_positions = max_pos

    def adapt_to_market(self, engine):
        if not engine or not self.adaptive_risk_enabled:
            return
        now = time.time()
        if now - self._last_adaptation_time < self._adaptation_interval:
            return
        self._last_adaptation_time = now
        balance = engine.portfolio._balance or 0.0
        if balance < 100:
            self._apply_micro_mode(engine)
        elif balance < 200:
            self.risk_per_trade_pct = 10.0
            self.max_leverage = 4
            if engine:
                engine.max_positions = 2
        else:
            self.risk_per_trade_pct = 5.0
            self.max_leverage = 5
            if engine:
                engine.max_positions = 3

    def _apply_micro_mode(self, engine):
        self.risk_per_trade_pct = 20.0
        self.max_leverage = 3
        self._current_profile = 'Micro'
        self._atr_multipliers['__default__'] = {'sl': 0.15, 'tp': 0.3}
        if engine:
            engine.max_positions = 1
            engine.signal_threshold = 0.2
            for name, f in engine.filters.items():
                if name not in ('ATRFilter', 'MicroLotFilter'):
                    f.enabled = False
            for name, s in engine.strategies.items():
                if name not in ('MultiTFConsensus', 'MicroScalper'):
                    s.enabled = False
        logger.info("Micro-mode for scalping: TP=0.3%%, SL=0.15%%, 1 position, threshold=0.2")

    def set_night_mode(self, enabled: bool):
        self._night_mode = enabled

    def get_sl_tp_levels(self, entry_price, side, atr, symbol=None):
        sl_mult, tp_mult = self.get_atr_multipliers(symbol)
        if self._current_profile == 'Micro':
            sl_pct = sl_mult / 100.0
            tp_pct = tp_mult / 100.0
            if side == 'BUY':
                sl = entry_price * (1 - sl_pct)
                tp = entry_price * (1 + tp_pct)
            else:
                sl = entry_price * (1 + sl_pct)
                tp = entry_price * (1 - tp_pct)
            return {'sl': max(sl, 1e-8), 'tp': max(tp, 1e-8), 'tp2': tp}
        else:
            min_sl = entry_price * 0.003
            if side == 'BUY':
                sl = entry_price - max(atr * sl_mult, min_sl)
                tp = entry_price + atr * tp_mult
            else:
                sl = entry_price + max(atr * sl_mult, min_sl)
                tp = entry_price - atr * tp_mult
            return {'sl': max(sl, 1e-8), 'tp': max(tp, 1e-8), 'tp2': tp}

    def calculate_position_size(self, free_margin, entry_price, sl_price, confidence,
                                min_qty=0.0, step_size=0.0):
        now = time.time()
        if now - self._last_trade_time < self._min_trade_interval_seconds:
            logger.debug(f"Trade cooldown active, need wait {self._min_trade_interval_seconds - (now - self._last_trade_time):.0f}s")
            return 0.0, 1
        self._last_trade_time = now

        if entry_price <= 0 or free_margin <= 0:
            logger.warning(f"Invalid entry or margin: entry={entry_price}, margin={free_margin}")
            return 0.0, 1

        risk_amount = free_margin * (self.risk_per_trade_pct / 100.0) * confidence
        sl_distance = abs(entry_price - sl_price)
        if sl_distance == 0:
            sl_distance = entry_price * 0.001

        quantity = risk_amount / sl_distance
        leverage = self.max_leverage

        # Микро-режим: гарантируем минимальную сумму сделки (5 USDT)
        if self._current_profile == 'Micro':
            min_position_value = 5.0  # минимальная стоимость позиции в USDT
            min_qty_needed = min_position_value / entry_price
            if quantity < min_qty_needed:
                quantity = min_qty_needed
                logger.debug(f"Micro-mode: increased quantity to {quantity:.6f} to meet min position value {min_position_value} USDT")

        max_qty_by_margin = (free_margin * leverage) / entry_price
        if quantity > max_qty_by_margin:
            quantity = max_qty_by_margin

        # Применяем minQty и stepSize
        if min_qty > 0 and quantity < min_qty:
            quantity = min_qty
        if step_size > 0:
            quantity = ((quantity + step_size - 1e-10) // step_size) * step_size
            if min_qty > 0 and quantity < min_qty:
                quantity = min_qty

        required_margin = (quantity * entry_price) / leverage
        if required_margin > free_margin:
            logger.warning(f"Insufficient margin: need {required_margin:.2f}, have {free_margin:.2f}")
            # В микро-режиме всё равно пробуем открыть с максимально возможным количеством
            if self._current_profile == 'Micro':
                quantity = (free_margin * leverage) / entry_price
                quantity = round(quantity, 8)
                if quantity <= 0:
                    return 0.0, 1
                logger.info(f"Micro-mode: adjusted quantity to {quantity} due to margin limit")
            else:
                return 0.0, 1

        quantity = round(quantity, 8)
        if quantity <= 0:
            return 0.0, 1

        logger.debug(f"Calculated position: qty={quantity}, lev={leverage}, margin={required_margin:.2f}")
        return quantity, leverage

    def get_atr_multipliers(self, symbol=None):
        default = self._atr_multipliers.get('__default__', {'sl': 0.8, 'tp': 1.6})
        return default['sl'], default['tp']

    def record_trade_result(self, pnl):
        self._trade_pnls.append(pnl)
        if len(self._trade_pnls) > 50:
            self._trade_pnls.pop(0)

    def get_optimal_leverage(self, symbol, price, atr):
        return self.max_leverage

    def apply_day_profile(self):
        pass

    def adapt_to_volatility(self, current_atr_pct):
        pass

    def check_low_balance(self, balance):
        if balance < 30 and self.engine and not self.engine._paused:
            logger.critical(f"Balance critically low ({balance:.2f} USDT) – pausing trading")
            self.engine._paused = True

    def _load_state(self):
        if not os.path.exists(self.STATE_FILE):
            return
        try:
            with open(self.STATE_FILE) as f:
                data = json.load(f)
            self._atr_multipliers = data.get('atr_multipliers', {})
        except:
            pass

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.STATE_FILE), exist_ok=True)
            with open(self.STATE_FILE, 'w') as f:
                json.dump({'atr_multipliers': self._atr_multipliers}, f, indent=2)
        except:
            pass
