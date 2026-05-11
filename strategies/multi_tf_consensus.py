import pandas as pd
from typing import Optional
from strategies.base import BaseStrategy, Signal
from indicators.base import EMA

class MultiTFConsensusStrategy(BaseStrategy):
    NAME = "MultiTFConsensus"
    DESCRIPTION = "Голосование трендов по 5m, 15m, 1h, 4h, 1d. Сигнал при ≥75% согласии."
    VERSION = "1.0.0"
    PARAMS = {
        'enabled': True,
        'weight': 2.0,
        'timeframes': ['5m', '15m', '1h', '4h', '1d'],
        'ema_period': 50,
        'min_agreement_pct': 75,
    }

    def __init__(self, params=None, engine=None):
        super().__init__(params, engine=engine)
        self.ema = EMA({'period': self.config['ema_period']})

    def evaluate(self, symbol: str, timeframe: str, candles: pd.DataFrame) -> Optional[Signal]:
        if self.engine is None:
            return None
        all_tfs = self.config['timeframes']
        votes = []
        for tf in all_tfs:
            df = self.engine._candle_data.get(symbol, {}).get(tf)
            if df is None or len(df) < self.config['ema_period'] + 5:
                continue
            ema_series = self.ema.calculate(df)
            if ema_series.empty:
                continue
            current_price = df['close'].iloc[-1]
            ema_val = ema_series.iloc[-1]
            if current_price > ema_val:
                votes.append('BUY')
            else:
                votes.append('SELL')

        if len(votes) < 3:
            return None

        total = len(votes)
        buy_votes = votes.count('BUY')
        sell_votes = votes.count('SELL')
        agreement = max(buy_votes, sell_votes) / total * 100

        if agreement >= self.config['min_agreement_pct']:
            action = 'BUY' if buy_votes > sell_votes else 'SELL'
            confidence = 0.6 + 0.35 * (agreement / 100)
            return Signal(
                symbol=symbol,
                action=action,
                confidence=min(1.0, confidence),
                meta={'strategy': self.NAME, 'timeframe': timeframe, 'agreement': agreement}
            )
        return None
