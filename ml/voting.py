"""
Voting System: combines signals from multiple strategies with weighted confidence.
Auto-disables losing strategies based on winrate and PnL.
Now with automatic re-enable after timeout (24 hours).
"""
import json
import logging
import os
import time
from typing import Dict, List, Optional

from strategies.base import Signal

logger = logging.getLogger(__name__)


class VotingSystem:
    WEIGHTS_FILE = 'data/strategy_weights.json'

    MIN_WINRATE = 0.40
    MIN_TOTAL_PNL = -100.0
    MAX_CONSECUTIVE_LOSSES = 5
    WEIGHT_PENALTY = 0.1
    DISABLE_TIMEOUT_HOURS = 24       # изменено с 12

    def __init__(self):
        self._weights: Dict[str, dict] = {}
        self._load_weights()
        self._cleanup_expired_disables()

    def _load_weights(self):
        if os.path.exists(self.WEIGHTS_FILE):
            try:
                with open(self.WEIGHTS_FILE, 'r') as f:
                    self._weights = json.load(f)
                for stats in self._weights.values():
                    if 'disabled' in stats and stats['disabled'] and 'disabled_at' not in stats:
                        stats['disabled_at'] = time.time()
            except Exception as e:
                logger.error(f"Failed to load weights: {e}")
                self._weights = {}
        else:
            self._weights = {}

    def _save_weights(self):
        try:
            os.makedirs(os.path.dirname(self.WEIGHTS_FILE), exist_ok=True)
            with open(self.WEIGHTS_FILE, 'w') as f:
                json.dump(self._weights, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save weights: {e}")

    def _cleanup_expired_disables(self):
        now = time.time()
        timeout_seconds = self.DISABLE_TIMEOUT_HOURS * 3600
        changed = False
        for name, stats in self._weights.items():
            if stats.get('disabled') and 'disabled_at' in stats:
                if now - stats['disabled_at'] > timeout_seconds:
                    stats['disabled'] = False
                    stats['disabled_reason'] = None
                    stats['consecutive_losses'] = 0
                    stats['weight'] = 1.0
                    del stats['disabled_at']
                    logger.info(f"Strategy {name} re-enabled after timeout")
                    changed = True
        if changed:
            self._save_weights()

    def register_strategy(self, name: str, weight: float = 1.0):
        if name not in self._weights:
            self._weights[name] = {
                'weight': weight,
                'trades': 0,
                'wins': 0,
                'total_pnl': 0.0,
                'avg_pnl': 0.0,
                'winrate': 0.0,
                'consecutive_losses': 0,
                'disabled': False,
                'disabled_reason': None,
            }
        else:
            self._weights[name]['weight'] = weight

    def evaluate_signals(self, signals: List[Signal]) -> Optional[Signal]:
        if not signals:
            return None

        by_symbol_action = {}
        for s in signals:
            key = (s.symbol, s.action)
            by_symbol_action.setdefault(key, []).append(s)

        best_signal = None
        best_score = 0.0

        for key, sigs in by_symbol_action.items():
            total_weight = 0.0
            weighted_conf = 0.0

            for s in sigs:
                strategy = s.meta.get('strategy', 'Unknown')
                stats = self._weights.get(strategy, {})

                if stats.get('disabled', False):
                    continue

                w = stats.get('weight', 1.0)
                if stats.get('consecutive_losses', 0) >= 3:
                    w = self.WEIGHT_PENALTY

                weighted_conf += s.confidence * w
                total_weight += w

            if total_weight > 0:
                avg_conf = weighted_conf / total_weight
                if avg_conf > best_score:
                    best_score = avg_conf
                    best_signal = sigs[0]
                    best_signal.confidence = min(1.0, avg_conf)

        return best_signal

    def update_weights(self):
        changed = False
        for name, stats in self._weights.items():
            if stats.get('disabled', False):
                continue

            trades = stats.get('trades', 0)
            winrate = stats.get('winrate', 0.0)
            total_pnl = stats.get('total_pnl', 0.0)
            consecutive_losses = stats.get('consecutive_losses', 0)

            disabled = False
            reason = None

            if trades >= 5:
                if winrate < self.MIN_WINRATE * 100:
                    disabled = True
                    reason = f"winrate {winrate:.1f}% < {self.MIN_WINRATE*100:.0f}%"
                elif total_pnl < self.MIN_TOTAL_PNL:
                    disabled = True
                    reason = f"total PnL ${total_pnl:.2f} < ${self.MIN_TOTAL_PNL:.0f}"

            if consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES:
                disabled = True
                reason = f"{consecutive_losses} consecutive losses"

            if disabled:
                stats['disabled'] = True
                stats['disabled_reason'] = reason
                stats['weight'] = 0.0
                stats['disabled_at'] = time.time()
                logger.warning(f"Strategy {name} AUTO-DISABLED: {reason}")
                changed = True

        if changed:
            self._save_weights()

    def record_trade(self, strategy_name: str, pnl: float):
        if strategy_name not in self._weights:
            return

        stats = self._weights[strategy_name]
        stats['trades'] = stats.get('trades', 0) + 1
        stats['total_pnl'] = stats.get('total_pnl', 0.0) + pnl

        if pnl > 0:
            stats['wins'] = stats.get('wins', 0) + 1
            stats['consecutive_losses'] = 0
        else:
            stats['consecutive_losses'] = stats.get('consecutive_losses', 0) + 1

        trades = stats['trades']
        stats['winrate'] = (stats['wins'] / trades * 100) if trades > 0 else 0.0
        stats['avg_pnl'] = stats['total_pnl'] / trades if trades > 0 else 0.0

        self._save_weights()
        self.update_weights()

    def get_weights(self) -> Dict[str, float]:
        return {name: stats.get('weight', 1.0) for name, stats in self._weights.items()}

    def get_strategy_stats(self) -> Dict[str, dict]:
        return self._weights.copy()

    def is_strategy_disabled(self, name: str) -> bool:
        return self._weights.get(name, {}).get('disabled', False)

    def enable_strategy(self, name: str):
        if name in self._weights:
            self._weights[name]['disabled'] = False
            self._weights[name]['disabled_reason'] = None
            self._weights[name]['consecutive_losses'] = 0
            self._weights[name]['weight'] = 1.0
            self._weights[name].pop('disabled_at', None)
            self._save_weights()
            logger.info(f"Strategy {name} re-enabled manually")
