import logging
from typing import Dict

logger = logging.getLogger(__name__)


def discover_symbols(engine):
    try:
        contracts = engine.api.get_contracts()
        usdt_pairs = [c for c in contracts if c.get('symbol', '').endswith('USDT')]
        usdt_pairs.sort(key=lambda x: float(x.get('volume', 0) or 0), reverse=True)
        engine._top_symbols = [p['symbol'] for p in usdt_pairs[:engine.top_n_symbols]
                               if p['symbol'] not in engine._blacklist]
        logger.info(f"Discovered {len(engine._top_symbols)} symbols")
    except Exception:
        engine._top_symbols = ['BTC-USDT','ETH-USDT','SOL-USDT','XRP-USDT',
                               'DOGE-USDT','ADA-USDT','AVAX-USDT','DOT-USDT']


def load_contracts_info(engine):
    if engine.auth.demo_mode:
        engine._contracts_info = {s: {'minQty': 0.001, 'stepSize': 0.001} for s in engine._top_symbols}
        return
    try:
        contracts = engine.api.get_contracts()
        for c in contracts:
            sym = c.get('symbol', '')
            if sym.endswith('USDT'):
                engine._contracts_info[sym] = {
                    'minQty': float(c.get('tradeMinQuantity', 0)),
                    'stepSize': float(c.get('stepSize', 0.001))
                }
        logger.info(f"Loaded contract info for {len(engine._contracts_info)} symbols")
    except Exception as e:
        logger.error(f"Failed to load contracts info: {e}")


def get_current_price(engine, symbol):
    try:
        ticker = engine.api.get_ticker(symbol)
        return float(ticker.get('data', {}).get('lastPrice', 0))
    except Exception:
        if symbol in engine._candle_data and '1h' in engine._candle_data[symbol]:
            return engine._candle_data[symbol]['1h']['close'].iloc[-1]
        return 0.0


def get_current_atr(engine, symbol, candles_dict=None):
    try:
        from indicators.base import ATR
        atr_ind = ATR({'period': 14})
        data = candles_dict or engine._candle_data.get(symbol, {})
        if '1h' in data:
            atr_series = atr_ind.calculate(data['1h'])
            return float(atr_series.iloc[-1]) if len(atr_series) > 0 else 0.02
    except Exception as e:
        logger.debug(f"ATR calc failed for {symbol}: {e}")
    return 0.02
