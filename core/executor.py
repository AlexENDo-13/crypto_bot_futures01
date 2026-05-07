"""
Trade executor: places orders, handles trailing stop, breakeven, partial close,
slippage protection and sound notifications.
"""
import time
import logging
from datetime import datetime, timezone
from typing import Optional

try:
    import winsound
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False

from core.portfolio import Position

logger = logging.getLogger(__name__)

class TradeExecutor:
    def __init__(self, engine):
        self.engine = engine

    # ------------------------------------------------------------------
    def execute(self, signal, entry_price, quantity, leverage, tp_price, sl_price):
        side = signal.action
        pos_side = "LONG" if side == "BUY" else "SHORT"
        logger.info(f"Executing {side} {signal.symbol} @ {entry_price}, qty={quantity}, lev={leverage}")

        if self.engine.auth.demo_mode:
            self._simulate(signal, entry_price, quantity, leverage, tp_price, sl_price)
            return

        # Повтор с увеличением количества при ошибке минимального лота
        max_attempts = 3
        contract_info = self.engine._contracts_info.get(signal.symbol, {})
        min_qty = contract_info.get('minQty', 0)
        step_size = contract_info.get('stepSize', 0.001)

        for attempt in range(max_attempts):
            try:
                resp = self.engine.api.set_leverage(signal.symbol, leverage, pos_side)
                if resp.get('code') != 0:
                    logger.error(f"Set leverage failed: {resp}")
                    return

                order = self.engine.api.place_order(
                    symbol=signal.symbol, side=side, position_side=pos_side,
                    order_type='LIMIT', quantity=quantity, price=entry_price
                )
                if order.get('code') == 101400:
                    if min_qty > 0:
                        quantity = quantity + step_size
                        if quantity < min_qty:
                            quantity = min_qty
                        logger.info(f"Increasing quantity to {quantity} due to min order amount")
                        continue
                    else:
                        logger.error(f"Limit order failed with min amount error, but no minQty info")
                        return
                elif order.get('code') != 0:
                    logger.error(f"Limit order failed: {order}")
                    return
                else:
                    break
            except Exception as e:
                logger.error(f"Order attempt {attempt+1} failed: {e}")
                return
        else:
            logger.error(f"Failed to place order after {max_attempts} attempts")
            return

        # Ожидание исполнения
        timeout = getattr(self.engine, 'slippage_timeout_sec', 10.0)
        if timeout > 0:
            executed = False
            for _ in range(int(timeout * 2)):
                time.sleep(0.5)
                positions = self.engine.api.get_positions(signal.symbol)
                if any(p['symbol'] == signal.symbol and p['positionSide'] == pos_side for p in positions):
                    executed = True
                    break
            if not executed:
                self.engine.api.cancel_order(signal.symbol, order.get('orderId', ''))
                logger.warning(f"Limit order not filled, switching to market for {signal.symbol}")
                self.engine.api.place_order(
                    symbol=signal.symbol, side=side, position_side=pos_side,
                    order_type='MARKET', quantity=quantity
                )

        # Фактическая цена входа
        actual_entry = entry_price
        try:
            positions = self.engine.api.get_positions(signal.symbol)
            for p in positions:
                if p.get('symbol') == signal.symbol and p.get('positionSide') == pos_side:
                    actual_entry = float(p.get('avgPrice', p.get('entryPrice', entry_price)))
                    break
        except Exception as e:
            logger.warning(f"Could not fetch actual entry price, using original: {e}")

        logger.info(f"Actual entry price for {signal.symbol}: {actual_entry} (requested: {entry_price})")

        atr = self.engine._get_current_atr(signal.symbol)
        sl_tp = self.engine.risk_manager.get_sl_tp_levels(actual_entry, side, atr, signal.symbol)
        final_tp = sl_tp['tp2']
        final_sl = sl_tp['sl']

        min_sl_distance = actual_entry * 0.005
        if pos_side == 'LONG':
            if final_sl <= 0 or final_sl >= actual_entry:
                final_sl = actual_entry - max(atr * 1.5, min_sl_distance)
            if final_sl <= 0:
                final_sl = actual_entry * 0.995
        else:
            if final_sl <= 0 or final_sl <= actual_entry:
                final_sl = actual_entry + max(atr * 1.5, min_sl_distance)

        self._place_tpsl_orders(signal.symbol, pos_side, quantity, final_tp, final_sl)

        position = Position(
            symbol=signal.symbol, side=pos_side, entry_price=actual_entry,
            quantity=quantity, leverage=leverage,
            margin=(quantity * actual_entry) / leverage,
            tp_price=final_tp, sl_price=final_sl,
            open_time=datetime.now(timezone.utc).isoformat(),
            trailing=False
        )
        self.engine.portfolio.add_position(position)

        strategy_name = signal.meta.get('strategy', 'Unknown')
        self.engine.voting.record_trade(strategy_name, 0.0)

        self._play_sound('trade_open')
        logger.info(f"Trade executed: {signal.symbol} {side} @ {actual_entry}, TP={final_tp}, SL={final_sl}")

    # ... остальные методы остаются без изменений (apply_trailing_stop, apply_breakeven, apply_partial_close, _place_tpsl_orders, _simulate, _play_sound)
    # Они полностью совпадают с предыдущей версией.
    def apply_trailing_stop(self, pos, current_price: float):
        atr = self.engine._get_current_atr(pos.symbol)
        price = current_price or pos.entry_price
        atr_based_pct = (atr / price * 100 * 1.5) if price > 0 else 0.4
        min_pct = getattr(self.engine, 'trailing_distance_pct', 0.4)
        dist_pct = max(min_pct, atr_based_pct) / 100.0
        trail_dist = current_price * dist_pct
        if pos.side == 'LONG':
            new_sl = current_price - trail_dist
            if new_sl > pos.sl_price and new_sl > pos.entry_price:
                pos.sl_price = new_sl
                pos.trailing = True
                logger.info(f"Trailing SL updated for {pos.symbol} LONG: {new_sl:.6f} (dist={dist_pct*100:.2f}%)")
                return True
        else:
            new_sl = current_price + trail_dist
            if new_sl < pos.sl_price and new_sl < pos.entry_price:
                pos.sl_price = new_sl
                pos.trailing = True
                logger.info(f"Trailing SL updated for {pos.symbol} SHORT: {new_sl:.6f} (dist={dist_pct*100:.2f}%)")
                return True
        return False

    def apply_breakeven(self, pos, current_price: float, atr_val: float):
        mult = self.engine.breakeven_atr_mult * 0.2
        be_price = pos.entry_price + (atr_val * mult) if pos.side == 'LONG' else pos.entry_price - (atr_val * mult)
        if pos.side == 'LONG' and current_price > be_price and pos.sl_price < pos.entry_price:
            pos.sl_price = pos.entry_price * 1.001
            logger.info(f"Breakeven applied for {pos.symbol} LONG")
            return True
        elif pos.side == 'SHORT' and current_price < be_price and pos.sl_price > pos.entry_price:
            pos.sl_price = pos.entry_price * 0.999
            logger.info(f"Breakeven applied for {pos.symbol} SHORT")
            return True
        return False

    def apply_partial_close(self, pos, current_price: float):
        if getattr(pos, 'partial_done', False):
            return False
        if (pos.side == 'LONG' and current_price >= pos.tp_price) or (pos.side == 'SHORT' and current_price <= pos.tp_price):
            close_qty = pos.quantity * (self.engine.partial_close_pct / 100.0)
            try:
                self.engine.api.close_position(pos.symbol, pos.side, close_qty)
                pos.quantity -= close_qty
                pos.partial_done = True
                logger.info(f"Partial close {self.engine.partial_close_pct}% for {pos.symbol}")
                self._play_sound('profit')
                return True
            except Exception as e:
                logger.error(f"Partial close failed for {pos.symbol}: {e}")
        return False

    def _place_tpsl_orders(self, symbol, pos_side, quantity, tp_price, sl_price):
        close_side = 'SELL' if pos_side == 'LONG' else 'BUY'
        if tp_price is not None:
            self.engine.api.place_order(
                symbol=symbol, side=close_side, position_side=pos_side,
                order_type='TAKE_PROFIT_MARKET', quantity=quantity, stop_price=tp_price
            )
        if sl_price is not None:
            if pos_side == 'LONG' and sl_price >= tp_price:
                logger.error(f"Invalid SL for LONG: {sl_price} >= TP {tp_price}, skipping SL order")
                return
            if pos_side == 'SHORT' and sl_price <= tp_price:
                logger.error(f"Invalid SL for SHORT: {sl_price} <= TP {tp_price}, skipping SL order")
                return
            self.engine.api.place_order(
                symbol=symbol, side=close_side, position_side=pos_side,
                order_type='STOP_MARKET', quantity=quantity, stop_price=sl_price
            )

    def _simulate(self, signal, entry_price, quantity, leverage, tp_price, sl_price):
        pos_side = "LONG" if signal.action == "BUY" else "SHORT"
        position = Position(
            symbol=signal.symbol, side=pos_side, entry_price=entry_price,
            quantity=quantity, leverage=leverage,
            margin=(quantity * entry_price) / leverage,
            tp_price=tp_price, sl_price=sl_price,
            open_time=datetime.now(timezone.utc).isoformat(),
            trailing=False
        )
        self.engine.portfolio.add_position(position)
        logger.info(f"[DEMO] Simulated {signal.action} {signal.symbol}")

    def _play_sound(self, event: str):
        if not SOUND_AVAILABLE:
            return
        try:
            sound_map = {
                'profit': 'sounds/profit.wav',
                'loss': 'sounds/loss.wav',
                'error': 'sounds/error.wav',
                'trade_open': 'sounds/trade.wav'
            }
            path = sound_map.get(event)
            if path:
                winsound.PlaySound(path, winsound.SND_ASYNC)
        except Exception:
            pass
