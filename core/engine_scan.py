"""
Market scan task – core of the trading bot.
Fetches candles for each symbol (priority: WebSocket cache -> REST),
runs strategies, combines signals, applies filters, and delegates to signal_processor.
"""
import time
import logging
from strategies.base import Signal
from ml.market_regime import MarketRegime
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def market_scan_task(engine):
    """Main scanning function called by scheduler or manually."""
    if engine._paused or not engine._running:
        logger.debug("Market scan skipped: bot paused or not running")
        return

    engine.watchdog.heartbeat()

    if engine.antidetect.should_skip_update():
        logger.debug("Market scan skipped: anti-detect random skip")
        return

    if not engine._top_symbols:
        logger.warning("No symbols discovered, running discovery...")
        engine._discover_symbols()
        engine._load_contracts_info()
        if not engine._top_symbols:
            logger.error("Still no symbols after discovery, aborting scan")
            return

    symbols = engine.antidetect.shuffle_scan_order(engine._top_symbols)
    logger.info(f"Market scan: processing {len(symbols)} symbols")

    last_hb = time.time()
    for idx, symbol in enumerate(symbols):
        if not engine._running or engine._paused:
            break
        if time.time() - last_hb > 30:
            engine.watchdog.heartbeat()
            last_hb = time.time()
        if idx % 10 == 0:
            logger.debug(f"Scanning symbol {idx+1}/{len(symbols)}: {symbol}")
        try:
            _process_symbol(engine, symbol)
        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}", exc_info=True)

    engine._last_scan_time = time.time()
    logger.debug(f"Market scan finished, last scan time: {engine._last_scan_time}")


def _process_symbol(engine, symbol: str):
    """Process a single symbol: fetch candles (WebSocket first), run strategies."""
    if symbol in engine._blacklist:
        logger.debug(f"Symbol {symbol} in blacklist, skipping")
        return

    all_candles = {}
    for tf in engine.timeframes:
        # Сначала проверяем WebSocket кэш
        if symbol in engine._candle_data and tf in engine._candle_data[symbol]:
            df = engine._candle_data[symbol][tf]
            # Проверяем, что данные свежие (последняя свеча не старше 2 минут для коротких ТФ)
            if not df.empty:
                try:
                    last_time = df.index[-1]
                    age = (datetime.now(timezone.utc) - last_time).total_seconds()
                    # Для 5m и 15m свечей считаем свежими, если не старше 2 минут
                    # Для более крупных ТФ можно больше, но оставим 2 минуты для простоты
                    if age < 120:
                        all_candles[tf] = df
                        logger.debug(f"Using WebSocket cache for {symbol} {tf} (age {age:.1f}s)")
                        continue
                except Exception:
                    pass

        # Если нет в кэше или данные устарели – fallback на REST
        try:
            engine.antidetect.pre_request_delay()
            df = engine.api.get_klines_dataframe(symbol, tf, limit=200)
            if not df.empty:
                all_candles[tf] = df
                # Сохраняем в кэш для будущих использований
                engine._candle_data.setdefault(symbol, {})[tf] = df
                logger.debug(f"Fetched {tf} for {symbol} via REST, rows={len(df)}")
            else:
                logger.warning(f"Empty DataFrame for {symbol} {tf}")
        except Exception as e:
            logger.debug(f"Failed to fetch {symbol} {tf}: {e}")

    if not all_candles:
        logger.warning(f"No candle data for {symbol}, skipping")
        return

    # Определяем рыночный режим (на основе 1h, если есть)
    regime = MarketRegime.UNKNOWN
    if '1h' in all_candles:
        regime = engine.regime_detector.detect(all_candles['1h'])
    elif '15m' in all_candles:
        regime = engine.regime_detector.detect(all_candles['15m'])
    logger.debug(f"Market regime for {symbol}: {regime.value}")

    signals = []
    for name, strategy in engine.strategies.items():
        if not strategy.enabled:
            continue
        # В микро-режиме оставляем только MultiTFConsensus и MicroScalper
        if engine.risk_manager._current_profile == 'Micro':
            if name not in ('MultiTFConsensus', 'MicroScalper'):
                continue
        try:
            tf_list = strategy.config.get('timeframes', engine.timeframes)
            for tf in tf_list:
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
                    logger.info(f"Signal from {name} on {symbol} {tf}: {signal.action} conf={signal.confidence:.2f}")
                    break
        except Exception as e:
            logger.warning(f"Strategy {name} error on {symbol}: {e}", exc_info=True)
            strategy.record_error()

    if signals:
        combined = engine.voting.evaluate_signals(signals)
        if combined and combined.confidence >= engine.signal_threshold:
            logger.info(f"Combined signal: {combined.symbol} {combined.action} conf={combined.confidence:.2f}")
            engine.signal_processor.process(combined, all_candles)
        else:
            logger.debug(f"Combined signal confidence {combined.confidence if combined else 0:.2f} below threshold {engine.signal_threshold}")
    else:
        logger.debug(f"No signals generated for {symbol}")
