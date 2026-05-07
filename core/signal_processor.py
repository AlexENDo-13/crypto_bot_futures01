"""
Signal Processor: validates signals through filters, risk controller,
on-chain checks, and delegates execution.
"""
import logging
from typing import Dict

import pandas as pd

from strategies.base import Signal

logger = logging.getLogger(__name__)

class SignalProcessor:
    def __init__(self, engine):
        self.engine = engine

    def process(self, signal: Signal, all_candles: Dict[str, pd.DataFrame]):
        """Полная обработка сигнала с проверками и исполнением."""

        # --- Дедупликация: не входить в ту же сторону, если позиция уже есть ---
        current_positions = self.engine.portfolio.get_positions()
        for pos in current_positions:
            if pos.symbol == signal.symbol and pos.side == ("LONG" if signal.action == "BUY" else "SHORT"):
                logger.info(f"Position already exists for {signal.symbol} {pos.side}, skipping duplicate signal")
                return

        # Принудительная синхронизация позиций перед проверкой лимита
        if not self.engine.auth.demo_mode:
            try:
                self.engine.sync_manager.background_sync()
            except Exception as e:
                logger.debug(f"Pre-check sync failed: {e}")

        price = self.engine._get_current_price(signal.symbol)
        if price <= 0:
            logger.warning(f"Invalid price for {signal.symbol}")
            return
        atr_val = self.engine._get_current_atr(signal.symbol, all_candles)

        if price > 0:
            self.engine.risk_manager.adapt_to_volatility(atr_val / price)

        # --- Фильтрация по рыночному режиму ---
        regime = signal.meta.get('regime', 'unknown')
        strategy_name = signal.meta.get('strategy', '')

        trend_strategies = ['TrendFollowing', 'Momentum', 'Ichimoku', 'DualThrust']
        mean_rev_strategies = ['MeanReversion', 'RSIDivergence', 'Squeeze']

        if regime == 'RANGING' and strategy_name in trend_strategies:
            logger.info(f"Strategy {strategy_name} blocked: market is RANGING")
            return
        if regime == 'TRENDING' and strategy_name in mean_rev_strategies:
            logger.info(f"Strategy {strategy_name} blocked: market is TRENDING")
            return

        # --- Адаптивный порог уверенности ---
        threshold = self.engine.signal_threshold
        if regime in ('HIGH_VOLATILITY', 'TRENDING'):
            threshold = max(0.3, threshold - 0.15)   # легче войти в тренд
        elif regime in ('LOW_VOLATILITY', 'RANGE', 'RANGING'):
            threshold = min(0.8, threshold + 0.2)    # строже в боковике
        logger.debug(f"Adaptive threshold for {regime}: {threshold:.2f}")

        if signal.confidence < threshold:
            logger.info(f"Signal confidence {signal.confidence:.2f} below adaptive threshold {threshold:.2f}, skipping {signal.symbol}")
            return

        # --- Предторговая проверка (спред, ликвидность через фильтр, VaR) ---
        allowed, reason = self.engine.risk_controller.pre_trade_check(
            signal.symbol, signal, all_candles, 0, price
        )
        if not allowed:
            logger.info(f"Pre-trade check blocked {signal.symbol}: {reason}")
            return

        # Ончейн-фильтр
        onchain_filter = self.engine.filters.get('OnChainFilter')
        if onchain_filter and onchain_filter.enabled:
            new_conf = onchain_filter.assess(signal, {})
            if new_conf <= 0:
                logger.info(f"On-chain filter blocked {signal.symbol}")
                return
            signal.confidence = new_conf

        signal = self._apply_tradingview_boost(signal)

        # Обновляем данные по текущим позициям
        current_positions = self.engine.portfolio.get_positions()
        available_margin = self.engine.portfolio.available_margin or self._get_free_margin()

        # --- Запуск каскада фильтров (включая LiquidityFilter вместо жёсткой проверки) ---
        filter_data = {
            'open_positions': [{'symbol': p.symbol, 'side': p.side} for p in current_positions],
            'current_drawdown_pct': self.engine.portfolio.get_stats().get('current_drawdown_pct', 0.0),
            'current_atr': atr_val,
            'current_price': price,
            'market_regime': regime,
            'candle_data': all_candles,
            'available_margin': available_margin,
            'correlations': self._calculate_correlations(signal.symbol, current_positions, all_candles),
        }

        # --- ВАЖНО: сначала прогоняем все фильтры, только потом думаем о замене ---
        for filter_name, filter_obj in sorted(self.engine.filters.items(),
                                              key=lambda x: getattr(x[1], 'PRIORITY', 100)):
            if not getattr(filter_obj, 'enabled', True):
                continue
            try:
                new_conf = filter_obj.assess(signal, filter_data)
                if new_conf <= 0:
                    logger.info(f"Filter {filter_name} blocked {signal.symbol}")
                    return
                signal.confidence = new_conf
            except Exception as e:
                logger.warning(f"Filter {filter_name} error: {e}")

        # --- Проверка лимита позиций с умной заменой (только если сигнал прошёл все фильтры) ---
        if len(current_positions) >= self.engine.max_positions:
            if not self.engine.sync_manager.try_replace_weakest(signal.confidence, signal.symbol):
                logger.info(f"Max positions reached ({self.engine.max_positions}), skipping {signal.symbol}")
                return

        free_margin = available_margin
        sl_tp = self.engine.risk_manager.get_sl_tp_levels(price, signal.action, atr_val, signal.symbol)

        # Реинвестирование прибыли — используем equity вместо free_margin
        equity = self.engine.portfolio._equity or free_margin
        reinvest = getattr(self.engine, 'reinvest_profits', True)
        base_for_calc = equity if reinvest else free_margin

        quantity, leverage = self.engine.risk_manager.calculate_position_size(
            base_for_calc, price, sl_tp['sl'], signal.confidence
        )
        leverage = self.engine.risk_manager.get_optimal_leverage(signal.symbol, price, atr_val)

        min_qty = self.engine._contracts_info.get(signal.symbol, {}).get('minQty', 0)
        if min_qty > 0 and quantity < min_qty:
            logger.info(f"Quantity {quantity} < minQty {min_qty}, adjusting...")
            quantity = min_qty

        required_margin = (quantity * price) / leverage
        if required_margin > free_margin:
            logger.info(f"Insufficient margin for {signal.symbol}: required {required_margin:.2f}, available {free_margin:.2f}")
            return

        self.engine.executor.execute(signal, price, quantity, leverage, sl_tp['tp2'], sl_tp['sl'])

    def _apply_tradingview_boost(self, signal: Signal) -> Signal:
        if signal.meta.get('source') == 'tradingview':
            boost = signal.meta.get('boost', 0.0)
            signal.confidence = min(1.0, signal.confidence + boost)
        return signal

    def _calculate_correlations(self, symbol: str, positions: list, all_candles: dict) -> dict:
        correlations = {}
        if not positions or symbol not in all_candles:
            return correlations

        try:
            import numpy as np
            new_closes = all_candles[symbol]['close'].values[-50:]
            for pos in positions:
                pos_symbol = pos.symbol
                if pos_symbol in all_candles:
                    pos_closes = all_candles[pos_symbol]['close'].values[-50:]
                    if len(new_closes) == len(pos_closes) and len(new_closes) > 1:
                        corr = np.corrcoef(new_closes, pos_closes)[0, 1]
                        if not np.isnan(corr):
                            correlations[f"{symbol}_{pos_symbol}"] = corr
        except Exception as e:
            logger.debug(f"Correlation calc failed: {e}")
        return correlations

    def _get_free_margin(self):
        try:
            bal = self.engine.api.get_balance().get('data', {}).get('balance', {})
            return float(bal.get('availableMargin', 0))
        except Exception:
            return 0.0
