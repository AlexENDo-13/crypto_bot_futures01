#!/usr/bin/env python3
"""
Тестер BingX Futures API v2/v3 (ТОЛЬКО ДЛЯ ФЬЮЧЕРСОВ USDT-M)
Проверяет: баланс, позиции, контракты, плечо, ордера, TP/SL, свечи, закрытие.
Использует актуальный модуль core.api (с исправлениями подписи и klines).
"""
import sys
import os
import time
import logging
from pathlib import Path

# Добавляем корень проекта в путь, чтобы импортировать core
project_root = Path(__file__).parent.absolute()
sys.path.insert(0, str(project_root))

# Настройка логирования на экран
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("APITester")

from core.api import BingXAPI
from core.auth import AuthManager

def confirm(message: str) -> bool:
    """Запрос подтверждения у пользователя."""
    while True:
        choice = input(f"⚠️  {message} (y/n): ").strip().lower()
        if choice in ('y', 'yes'):
            return True
        elif choice in ('n', 'no'):
            return False

def main():
    print("=" * 60)
    print(" BingX Futures API Tester")
    print("=" * 60)
    auth = AuthManager()
    if auth.demo_mode:
        logger.error("❌ API keys not found. Please create keys.json with api_key and api_secret.")
        sys.exit(1)

    api = BingXAPI(auth)
    logger.info("✅ API client created")

    # Выбираем символ для тестов (малая цена, маленький минимальный лот)
    # Используем XLM-USDT из ваших логов (цена ~0.16, мин.лот ~1)
    test_symbol = "XLM-USDT"
    test_quantity = 1           # минимально возможное количество
    test_leverage = 3           # небольшое плечо для безопасности

    # -----------------------------------------------------------------
    # 1. Проверка соединения (ping)
    # -----------------------------------------------------------------
    logger.info("1️⃣  Проверка соединения (ping)...")
    ping = api.ping()
    if ping is not None:
        logger.info(f"✅ Пинг: {ping:.0f} мс")
    else:
        logger.error("❌ Не удалось выполнить ping")
        sys.exit(1)

    # -----------------------------------------------------------------
    # 2. Баланс
    # -----------------------------------------------------------------
    logger.info("2️⃣  Получение баланса...")
    try:
        resp = api.get_balance()
        data_list = resp.get('data', [])
        if not data_list:
            logger.error("❌ Пустой ответ баланса")
            return
        usdt_info = next((x for x in data_list if x.get('asset') == 'USDT'), None) or data_list[0]
        balance = float(usdt_info.get('balance', 0))
        logger.info(f"✅ Баланс USDT: {balance:.2f}")
        if balance < 5.0:
            logger.warning("⚠️  Баланс очень низкий, тестовые операции могут не выполниться.")
    except Exception as e:
        logger.error(f"❌ Ошибка баланса: {e}")
        return

    # -----------------------------------------------------------------
    # 3. Контракты (торговые правила)
    # -----------------------------------------------------------------
    logger.info("3️⃣  Получение информации о контрактах...")
    try:
        contracts = api.get_contracts()
        contract = next((c for c in contracts if c.get('symbol') == test_symbol), None)
        if contract:
            min_qty = float(contract.get('tradeMinQuantity', 0))
            price_precision = int(contract.get('pricePrecision', 1))
            logger.info(f"✅ {test_symbol}: мин.лот={min_qty}, точность цены={price_precision}")
            # Корректируем тестовое количество, если нужно
            if test_quantity < min_qty:
                test_quantity = int(min_qty) if min_qty >= 1 else min_qty
                logger.info(f"   Скорректировано тестовое количество до: {test_quantity}")
        else:
            logger.warning(f"⚠️  Символ {test_symbol} не найден в контрактах")
    except Exception as e:
        logger.error(f"❌ Ошибка контрактов: {e}")
        return

    # -----------------------------------------------------------------
    # 4. Текущие позиции и ордера (перед тестом)
    # -----------------------------------------------------------------
    logger.info("4️⃣  Текущие позиции...")
    try:
        positions = api.get_positions()
        logger.info(f"✅ Открыто позиций: {len(positions)}")
        if positions:
            for p in positions[:3]:
                logger.info(f"   {p.get('symbol')} {p.get('positionSide')} {p.get('positionAmt')}")
    except Exception as e:
        logger.error(f"❌ Ошибка получения позиций: {e}")

    logger.info("   Открытые ордера...")
    try:
        orders = api.get_open_orders()
        logger.info(f"✅ Открытых ордеров: {len(orders)}")
        if orders:
            for o in orders[:3]:
                logger.info(f"   {o.get('symbol')} {o.get('type')} {o.get('origQty')}")
    except Exception as e:
        logger.error(f"❌ Ошибка получения ордеров: {e}")

    # Убедимся, что по тестовому символу нет открытой позиции
    existing_pos = next((p for p in positions if p.get('symbol') == test_symbol), None)
    if existing_pos:
        logger.warning(f"⚠️  По символу {test_symbol} уже есть позиция. Закройте её перед тестом.")
        if confirm("Закрыть существующую позицию по рыночной цене?"):
            side = existing_pos.get('positionSide', 'LONG')
            try:
                api.close_position(test_symbol, side)
                logger.info("✅ Позиция закрыта")
            except Exception as e:
                logger.error(f"❌ Не удалось закрыть позицию: {e}")
        else:
            logger.info("Тест продолжен с существующей позицией (может повлиять на результат).")

    # -----------------------------------------------------------------
    # 5. Установка плеча (изменение leverage)
    # -----------------------------------------------------------------
    logger.info(f"5️⃣  Установка плеча {test_leverage}x для {test_symbol} LONG...")
    try:
        resp = api.set_leverage(test_symbol, test_leverage, "LONG")
        if resp.get('code') == 0:
            logger.info(f"✅ Плечо установлено: {resp.get('data', {}).get('leverage', test_leverage)}x")
        else:
            logger.error(f"❌ Ошибка установки плеча: {resp}")
    except Exception as e:
        logger.error(f"❌ Исключение: {e}")

    # -----------------------------------------------------------------
    # 6. Размещение лимитного ордера и отмена
    # -----------------------------------------------------------------
    logger.info(f"6️⃣  Размещение тестового лимитного ордера на {test_symbol}...")
    ticker = api.get_ticker(test_symbol)
    last_price = float(ticker.get('data', {}).get('lastPrice', 0))
    if last_price <= 0:
        logger.error("❌ Не удалось получить цену")
        return
    # Лимитная цена чуть хуже рынка, чтобы не исполнился мгновенно
    limit_price = round(last_price * 0.95, 1)   # BUY лимит ниже рынка
    logger.info(f"   Текущая цена: {last_price}, лимит: {limit_price}")

    try:
        order = api.place_order(
            symbol=test_symbol,
            side="BUY",
            position_side="LONG",
            order_type="LIMIT",
            quantity=test_quantity,
            price=limit_price
        )
        if order.get('code') == 0:
            order_id = order.get('data', {}).get('order', {}).get('orderId', '???')
            logger.info(f"✅ Ордер размещён, ID: {order_id}")
            # Отмена ордера
            logger.info("   Отмена ордера...")
            cancel_resp = api.cancel_order(test_symbol, order_id)
            if cancel_resp.get('code') == 0:
                logger.info("✅ Ордер отменён")
            else:
                logger.error(f"❌ Ошибка отмены: {cancel_resp}")
        else:
            logger.error(f"❌ Ошибка размещения ордера: {order}")
    except Exception as e:
        logger.error(f"❌ Исключение при работе с ордером: {e}")

    # -----------------------------------------------------------------
    # 7. Рыночный ордер (открытие позиции) и TP/SL
    # -----------------------------------------------------------------
    if not confirm(f"Открыть РЫНОЧНЫЙ ордер на {test_symbol} BUY (кол-во {test_quantity}, плечо {test_leverage})?"):
        logger.info("Пропущено открытие рыночного ордера.")
    else:
        logger.info("7️⃣  Открытие рыночной позиции...")
        try:
            order = api.place_order(
                symbol=test_symbol,
                side="BUY",
                position_side="LONG",
                order_type="MARKET",
                quantity=test_quantity
            )
            if order.get('code') == 0:
                logger.info("✅ Рыночный ордер отправлен")
                time.sleep(2)   # даём время на исполнение
                # Проверяем позицию
                positions_after = api.get_positions()
                pos = next((p for p in positions_after if p.get('symbol') == test_symbol and p.get('positionSide') == 'LONG'), None)
                if pos:
                    entry_price = float(pos.get('avgPrice', 0))
                    logger.info(f"   Позиция открыта, цена входа: {entry_price}")
                    # Установка TP/SL
                    if confirm("Установить TP (+5%) и SL (-2%) для этой позиции?"):
                        tp_price = round(entry_price * 1.05, 4)
                        sl_price = round(entry_price * 0.98, 4)
                        logger.info(f"   TP={tp_price}, SL={sl_price}")
                        try:
                            tp_order = api.place_order(
                                symbol=test_symbol,
                                side="SELL",
                                position_side="LONG",
                                order_type="TAKE_PROFIT_MARKET",
                                quantity=test_quantity,
                                stop_price=tp_price
                            )
                            sl_order = api.place_order(
                                symbol=test_symbol,
                                side="SELL",
                                position_side="LONG",
                                order_type="STOP_MARKET",
                                quantity=test_quantity,
                                stop_price=sl_price
                            )
                            if tp_order.get('code') == 0 and sl_order.get('code') == 0:
                                logger.info("✅ TP и SL ордера установлены")
                            else:
                                logger.error(f"❌ Ошибка TP/SL: TP={tp_order.get('msg')}, SL={sl_order.get('msg')}")
                        except Exception as e:
                            logger.error(f"❌ Исключение TP/SL: {e}")
                    # Закрытие позиции
                    if confirm("Закрыть эту позицию по рынку?"):
                        logger.info("   Закрытие позиции...")
                        try:
                            api.close_position(test_symbol, "LONG")
                            logger.info("✅ Позиция закрыта")
                        except Exception as e:
                            logger.error(f"❌ Ошибка закрытия: {e}")
                else:
                    logger.warning("   Позиция не обнаружена сразу после ордера (возможно, ещё не исполнилась).")
            else:
                logger.error(f"❌ Ошибка рыночного ордера: {order}")
        except Exception as e:
            logger.error(f"❌ Исключение: {e}")

    # -----------------------------------------------------------------
    # 8. K-Lines (проверка v3)
    # -----------------------------------------------------------------
    logger.info("8️⃣  Получение свечей (K-Lines v3)...")
    try:
        klines = api.get_klines(test_symbol, "1h", limit=5)
        if klines:
            logger.info(f"✅ Получено {len(klines)} свечей (v3)")
            # покажем первую и последнюю
            logger.info(f"   Первая: open={klines[0].get('open')}, close={klines[0].get('close')}")
            logger.info(f"   Последняя: open={klines[-1].get('open')}, close={klines[-1].get('close')}")
        else:
            logger.warning("⚠️  Пустой ответ K-Lines")
    except Exception as e:
        logger.error(f"❌ Ошибка K-Lines: {e}")

    logger.info("=" * 60)
    logger.info(" Тестирование завершено.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
