import time
import logging
from strategies.base import Signal
from ml.market_regime import MarketRegime

logger = logging.getLogger(__name__)


def market_scan_task(engine):
    if engine._paused or not engine._running:
        return
    engine.watchdog.heartbeat()

    if engine.antidetect.should_skip_update():
        return

    if not engine._top_symbols:
        engine._discover_symbols()
        engine._load_contracts_info()

    symbols = engine.antidetect.shuffle_scan_order(engine._top_symbols)
    last_hb = time.time()

    for symbol in symbols:
        if not engine._running or engine._paused:
            break
        if time.time() - last_hb > 30:
            engine.watchdog.heartbeat()
            last_hb = time.time()

        try:
            _process_symbol(engine, symbol)
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}")

    engine._last_scan_time = time.time()


def _process_symbol(engine, symbol: str):
    if symbol in engine._blacklist:
        return

    all_candles = {}
    for tf in engine.timeframes:
        try:
            engine.antidetect.pre_request_delay()
            df = engine.api.get_klines_dataframe(symbol, tf, limit=200)
            if not df.empty:
                all_candles[tf] = df
                engine._candle_data.setdefault(symbol, {})[tf] = df
        except Exception as e:
            logger.debug(f"Failed to fetch {symbol} {tf}: {e}")

    if not all_candles:
        return

    regime = MarketRegime.UNKNOWN
    if '1h' in all_candles:
        regime = engine.regime_detector.detect(all_candles['1h'])

    signals = []
    for name, strategy in engine.strategies.items():
        if strategy.is_disabled():
            continue
        try:
            for tf in strategy.config.get('timeframes', engine.timeframes):
                if tf not in all_candles:
                    continue
                signal = strategy.evaluate(symbol, tf, all_candles[tf])
                if signal and signal.action in ('BUY', 'SELL'):
                    signal.meta['strategy'] = name
                    signal.meta['timeframe'] = tf
                    signal.meta['regime'] = regime.value
                    signals.append(signal)
                    engine._recent_signals.append({
                        'time': time.strftime('%H:%M:%S'),
                        'symbol': symbol,
                        'action': signal.action,
                        'confidence': signal.confidence,
                        'price': engine._get_current_price(symbol),
                        'strategy': name,
                        'regime': regime.value,
                    })
                    break
        except Exception as e:
            logger.warning(f"Strategy {name} error on {symbol}: {e}")
            strategy.record_error()

    if signals:
        combined = engine.voting.evaluate_signals(signals)
        if combined and combined.confidence >= engine.signal_threshold:
            engine.signal_processor.process(combined, all_candles)
