"""
Auto Strategy Selector – автоматически включает/выключает стратегии и фильтры
в зависимости от текущего рыночного режима (тренд, боковик, высокая волатильность).
Исправлено: режимы UNKNOWN и LOW_VOLATILITY теперь не отключают все стратегии/фильтры.
"""
import logging
import threading
import time
from ml.market_regime import MarketRegime

logger = logging.getLogger(__name__)

# Маппинг: режим -> список рекомендуемых стратегий (остальные будут отключены)
REGIME_STRATEGIES = {
    MarketRegime.TREND_UP: [
        'TrendFollowing', 'Momentum', 'Ichimoku', 'DualThrust',
        'Breakout', 'BreakoutSwing', 'SuperTrendSwing',
        'SmartPyramiding', 'EMACrossoverSwing', 'TurtleTrading'
    ],
    MarketRegime.TREND_DOWN: [
        'TrendFollowing', 'Momentum', 'Ichimoku', 'DualThrust',
        'Breakout', 'BreakoutSwing', 'SuperTrendSwing',
        'SmartPyramiding', 'EMACrossoverSwing', 'TurtleTrading'
    ],
    MarketRegime.RANGE: [
        'MeanReversion', 'RSIDivergence', 'Squeeze', 'Range',
        'DynamicRebalance', 'GridStrategy'
    ],
    MarketRegime.HIGH_VOLATILITY: [
        'Breakout', 'BreakoutSwing', 'SuperTrendSwing', 'Range',
        'TrendFollowing', 'Momentum', 'DualThrust', 'TurtleTrading'
    ],
    MarketRegime.LOW_VOLATILITY: [
        'MeanReversion', 'RSIDivergence', 'Squeeze', 'Range',
        'DynamicRebalance', 'Ichimoku', 'TrendFollowing', 'Momentum',
        'DualThrust', 'GridStrategy'
    ],
    MarketRegime.UNKNOWN: [
        'TrendFollowing', 'Momentum', 'MeanReversion', 'Ichimoku',
        'Breakout', 'BreakoutSwing', 'RSIDivergence', 'Squeeze',
        'SuperTrendSwing', 'SmartPyramiding', 'EMACrossoverSwing',
        'DualThrust', 'TurtleTrading', 'GridStrategy', 'Range'
    ],
}

# Маппинг: режим -> список рекомендуемых фильтров (остальные отключаются)
REGIME_FILTERS = {
    MarketRegime.TREND_UP: [
        'ATRFilter', 'VolumeSurgeFilter', 'LiquidityFilter',
        'TrendFilter', 'MultiTFConfluenceFilter', 'OrderFlowImbalance',
        'VolumeDelta', 'CandlestickPattern', 'SentimentFilter',
        'SmartMoneyFilter', 'AdaptiveLeverage'
    ],
    MarketRegime.TREND_DOWN: [
        'ATRFilter', 'VolumeSurgeFilter', 'LiquidityFilter',
        'TrendFilter', 'MultiTFConfluenceFilter', 'OrderFlowImbalance',
        'VolumeDelta', 'CandlestickPattern', 'SentimentFilter',
        'SmartMoneyFilter', 'AdaptiveLeverage'
    ],
    MarketRegime.RANGE: [
        'ATRFilter', 'VolumeFilter', 'LiquidityFilter',
        'OrderFlowImbalance', 'VolumeProfile', 'MarketProfile',
        'CandlestickPattern', 'PortfolioCorrelation'
    ],
    MarketRegime.HIGH_VOLATILITY: [
        'ATRFilter', 'VolumeSurgeFilter', 'LiquidityFilter',
        'DrawdownLimiter', 'AdaptiveLeverage', 'SessionFilter',
        'CandlestickPattern', 'TrendFilter'
    ],
    MarketRegime.LOW_VOLATILITY: [
        'ATRFilter', 'VolumeFilter', 'LiquidityFilter',
        'OrderFlowImbalance', 'VolumeProfile', 'CandlestickPattern',
        'TrendFilter', 'MultiTFConfluenceFilter', 'SmartMoneyFilter'
    ],
    MarketRegime.UNKNOWN: [
        'ATRFilter', 'VolumeSurgeFilter', 'LiquidityFilter',
        'TrendFilter', 'MultiTFConfluenceFilter', 'SentimentFilter',
        'CandlestickPattern', 'OrderFlowImbalance', 'VolumeDelta',
        'SmartMoneyFilter', 'DrawdownLimiter'
    ],
}

class AutoStrategySelector:
    """Периодически проверяет рыночный режим и корректирует набор активных модулей."""

    def __init__(self, engine, check_interval_seconds=300):
        self.engine = engine
        self.check_interval = check_interval_seconds
        self._running = False
        self._thread = None
        self._last_regime = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="AutoStrategySelector")
        self._thread.start()
        logger.info("AutoStrategySelector started (interval %ds)", self.check_interval)

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                self._adapt_to_regime()
            except Exception as e:
                logger.error(f"AutoStrategySelector error: {e}")
            time.sleep(self.check_interval)

    def _adapt_to_regime(self):
        regime = self.engine.regime_detector.get_current_regime()
        if regime == self._last_regime:
            return
        self._last_regime = regime
        logger.info(f"Market regime changed to {regime.value}, adapting strategies and filters")

        # Адаптация стратегий
        allowed_strategies = REGIME_STRATEGIES.get(regime, [])
        for name, strat in self.engine.strategies.items():
            if name in allowed_strategies:
                if not strat.enabled:
                    strat.enabled = True
                    logger.info(f"Auto: enabled strategy {name}")
            else:
                if strat.enabled:
                    strat.enabled = False
                    logger.info(f"Auto: disabled strategy {name} (unsuitable for {regime.value})")

        # Адаптация фильтров
        allowed_filters = REGIME_FILTERS.get(regime, [])
        for name, flt in self.engine.filters.items():
            if name in allowed_filters:
                if not flt.enabled:
                    flt.enabled = True
                    logger.info(f"Auto: enabled filter {name}")
            else:
                if flt.enabled:
                    flt.enabled = False
                    logger.info(f"Auto: disabled filter {name} (unsuitable for {regime.value})")

        # Сохраняем изменения в конфигурационные файлы
        try:
            self.engine._save_config()
        except Exception as e:
            logger.warning(f"AutoStrategySelector failed to save config: {e}")
