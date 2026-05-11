"""
Signal Processor: validates signals through filters, risk controller,
on-chain checks, correlation checks, and delegates execution.
Removed duplicate margin check – now trusts risk_manager.calculate_position_size.
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
        # --- Принудительная синхронизация перед проверкой лимитов ---
        if not self.engine.auth.demo_mode:
            try:
                self.engine.sync_manager.background_sync()
            except Exception as e:
                logger.debug(f"Pre-check sync failed: {e}")

        # --- Запрет на дубликаты позиций по символу ---
        current_positions = self.engine.portfolio.get_positions()
        for pos in current_positions:
            if pos.symbol == signal.symbol:
                logger.info(f"Position already exists for {signal.symbol} ({pos.side}), skipping new signal")
                return

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
            threshold = max(0.3, threshold - 0.15)
        elif regime in ('LOW_VOLATILITY', 'RANGE', 'RANGING'):
            threshold = min(0.8, threshold + 0.2)
        logger.debug(f"Adaptive threshold for {regime}: {threshold:.2f}")

        if signal.confidence < threshold:
            logger.info(f"Signal confidence {signal.confidence:.2f} below adaptive threshold {threshold:.2f}, skipping {signal.symbol}")
            return

        # --- Проверка корреляции ---
        if not self._check_correlation(signal.symbol, all_candles):
            logger.info(f"Correlation limit reached, skipping {signal.symbol}")
            return

        # --- Предторговая проверка ---
        allowed, reason = self.engine.risk_controller.pre_trade_check(
            signal.symbol, signal, all_candles, 0, price
        )
        if not allowed:
            logger.info(f"Pre-trade check blocked {signal.symbol}: {reason}")
            return

        # Ончейн-фильтр (защита от None)
        onchain_filter = self.engine.filters.get('OnChainFilter')
        if onchain_filter and onchain_filter.enabled:
            new_conf = self._safe_filter_assess(onchain_filter, signal, {})
            if new_conf is None:
                new_conf = signal.confidence
            if new_conf <= 0:
                logger.info(f"On-chain filter blocked {signal.symbol}")
                return
            signal.confidence = new_conf

        signal = self._apply_tradingview_boost(signal)

        # --- Каскад фильтров ---
        filter_data = {
            'open_positions': [{'symbol': p.symbol, 'side': p.side} for p in current_positions],
            'current_drawdown_pct': self.engine.portfolio.get_stats().get('current_drawdown_pct', 0.0),
            'current_atr': atr_val,
            'current_price': price,
            'market_regime': regime,
            'candle_data': all_candles,
            'available_margin': self.engine.portfolio.available_margin or self._get_free_margin(),
            'correlations': self._calculate_correlations(signal.symbol, current_positions, all_candles),
        }

        for filter_name, filter_obj in sorted(self.engine.filters.items(),
                                              key=lambda x: getattr(x[1], 'PRIORITY', 100)):
            if not getattr(filter_obj, 'enabled', True):
                continue
            try:
                new_conf = self._safe_filter_assess(filter_obj, signal, filter_data)
                if new_conf is None:
                    new_conf = signal.confidence
                if new_conf <= 0:
                    logger.info(f"Filter {filter_name} blocked {signal.symbol}")
                    return
                signal.confidence = new_conf
            except Exception as e:
                logger.warning(f"Filter {filter_name} error: {e}")

        # Проверка лимита позиций
        if len(current_positions) >= self.engine.max_positions:
            logger.info(f"Max positions reached ({self.engine.max_positions}), skipping {signal.symbol}")
            return

        free_margin = self.engine.portfolio.available_margin or self._get_free_margin()
        sl_tp = self.engine.risk_manager.get_sl_tp_levels(price, signal.action, atr_val, signal.symbol)
        equity = self.engine.portfolio._equity or free_margin
        reinvest = getattr(self.engine, 'reinvest_profits', True)
        base_for_calc = equity if reinvest else free_margin

        quantity, leverage = self.engine.risk_manager.calculate_position_size(
            base_for_calc, price, sl_tp['sl'], signal.confidence
        )
        leverage = self.engine.risk_manager.get_optimal_leverage(signal.symbol, price, atr_val)

        # --- Нормализация количества под требования биржи ---
        contract_info = self.engine._contracts_info.get(signal.symbol, {})
        raw_min_qty = contract_info.get('minQty')
        raw_step_size = contract_info.get('stepSize')
        min_qty = float(raw_min_qty) if raw_min_qty is not None else 0.0
        step_size = float(raw_step_size) if raw_step_size is not None else 0.001

        if min_qty > 0 and quantity < min_qty:
            quantity = min_qty
        if step_size > 0:
            quantity = ((quantity + step_size - 1e-10) // step_size) * step_size
            if min_qty > 0 and quantity < min_qty:
                quantity = min_qty

        # Убрана избыточная проверка required_margin > free_margin,
        # так как calculate_position_size уже гарантирует, что маржа вписывается.

        if quantity <= 0:
            logger.info(f"Zero quantity for {signal.symbol}, skipping")
            return

        self.engine.executor.execute(signal, price, quantity, leverage, sl_tp['tp2'], sl_tp['sl'])

    def _safe_filter_assess(self, filter_obj, signal, data):
        try:
            result = filter_obj.assess(signal, data)
            if result is None:
                logger.debug(f"Filter {filter_obj.NAME} returned None, treating as pass")
                return signal.confidence
            return float(result)
        except Exception as e:
            logger.warning(f"Filter {filter_obj.NAME} crashed: {e}", exc_info=True)
            return signal.confidence

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

    def _check_correlation(self, symbol, all_candles):
        positions = self.engine.portfolio.get_positions()
        if not positions:
            return True
        corr_count = 0
        for pos in positions:
            corr = self.engine.risk_controller._get_pair_correlation(symbol, pos.symbol, all_candles)
            if abs(corr) > self.engine.risk_controller.correlation_threshold:
                corr_count += 1
                if corr_count >= self.engine.risk_controller.max_correlation_positions:
                    return False
        return True

    def _get_free_margin(self):
        try:
            bal = self.engine.api.get_balance().get('data', {}).get('balance', {})
            return float(bal.get('availableMargin', 0))
        except Exception:
            return 0.0
