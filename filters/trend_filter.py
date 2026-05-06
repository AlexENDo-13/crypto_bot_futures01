from filters.base import BaseFilter
from strategies.base import Signal
from indicators.adx import ADX

class TrendFilter(BaseFilter):
    NAME = "TrendFilter"
    DESCRIPTION = "Blocks counter-trend signals using real ADX"
    PRIORITY = 25
    PARAMS = {'enabled': True, 'adx_period': 14, 'min_adx': 20}

    def __init__(self, params=None):
        super().__init__(params)
        self.adx = ADX({'period': self.config['adx_period']})

    def assess(self, signal: Signal, data: dict) -> float:
        if not self.enabled:
            return signal.confidence

        # === FIX: Используем реальный ADX вместо ATR ===
        candle_data = data.get('candle_data')
        adx_val = data.get('current_atr', 0)  # fallback

        if candle_data and '1h' in candle_data:
            try:
                adx_series = self.adx.calculate(candle_data['1h'])
                adx_val = adx_series.iloc[-1] if len(adx_series) > 0 else adx_val
            except Exception:
                pass

        # Если ADX ниже порога — рынок в боковике, трендовые фильтры не применяем
        if adx_val < self.config['min_adx']:
            return signal.confidence

        # Блокируем контр-трендовые сигналы
        if signal.action == 'BUY' and data.get('market_regime') == 'DOWNTREND':
            return 0.0
        if signal.action == 'SELL' and data.get('market_regime') == 'UPTREND':
            return 0.0
        return signal.confidence
