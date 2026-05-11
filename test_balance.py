#!/usr/bin/env python3
"""
Полный тестер BingX Perpetual Futures API с правильной подписью.
Выполняет: Hedge Mode, баланс, контракт, плечо, MARKET ордер,
TP/SL, запрос позиции, закрытие.
Параметры: XLM-USDT, количество 11, плечо 2.
"""
import json, time, hmac, requests, urllib.parse
from hashlib import sha256

KEYS_FILE = "keys.json"
BASE = "https://open-api.bingx.com"

def load_keys():
    with open(KEYS_FILE) as f:
        k = json.load(f)
    return k["api_key"].strip(), k["api_secret"].strip()

KEY, SECRET = load_keys()

def call(method, path, params_map):
    params = params_map.copy()
    params["timestamp"] = int(time.time() * 1000)
    sorted_keys = sorted(params.keys())
    params_str = "&".join([f"{k}={params[k]}" for k in sorted_keys])
    needs_encode = '[' in params_str or '{' in params_str
    url_parts = []
    for k in sorted_keys:
        v = str(params[k])
        if needs_encode:
            v = urllib.parse.quote(v, safe='')
        url_parts.append(f"{k}={v}")
    url_params = "&".join(url_parts)
    sign = hmac.new(SECRET.encode(), params_str.encode(), sha256).hexdigest()
    url = f"{BASE}{path}?{url_params}&signature={sign}"
    headers = {"X-BX-APIKEY": KEY}
    print(f"\n[{method}] {path} params={params_map}")
    resp = requests.request(method, url, headers=headers, data={}, timeout=15)
    data = resp.json()
    if data.get("code") != 0:
        print(f"❌ Ошибка API: {data}")
    else:
        print("✅ OK")
    return data

def ask(msg): return input(f"⚠️  {msg} (y/n): ").lower() == 'y'

SYM = "XLM-USDT"
QTY = 11           # увеличенное количество
LEV = 2            # уменьшенное плечо

print("=== 0. Hedge Mode ===")
call("POST", "/openApi/swap/v1/positionSide/dual", {"dualSidePosition": "true"})

print("\n=== 1. Баланс ===")
bal = call("GET", "/openApi/swap/v3/user/balance", {})
usdt = next((a for a in bal["data"] if a["asset"]=="USDT"), None) if bal.get("code")==0 else None
if usdt: print(f"USDT: {usdt['balance']}, доступно: {usdt['availableMargin']}")

print("\n=== 2. Контракт ===")
ct = call("GET", "/openApi/swap/v2/quote/contracts", {})
c = next((x for x in ct["data"] if x["symbol"]==SYM), None) if ct.get("code")==0 else None
if c:
    prec = int(c["pricePrecision"])
    minq = float(c["tradeMinQuantity"])
    print(f"Мин. лот: {minq}, точность цены: {prec}")
    if QTY < minq:
        print(f"⚠️ {QTY} меньше минимального лота {minq}, будет использован {minq}")
        QTY = int(minq) if minq >= 1 else minq

print(f"\n=== 3. Плечо {LEV}x ===")
call("POST", "/openApi/swap/v2/trade/leverage", {"symbol":SYM,"leverage":LEV,"side":"LONG"})

if not ask(f"Открыть MARKET BUY {QTY} {SYM}?"): exit()

print("\n=== 4. MARKET ордер ===")
order = call("POST", "/openApi/swap/v2/trade/order", {
    "symbol":SYM,"side":"BUY","positionSide":"LONG","type":"MARKET","quantity":QTY})
if order.get("code")!=0: exit()
time.sleep(3)

print("\n=== 5. Позиция ===")
pos = call("GET", "/openApi/swap/v2/user/positions", {"symbol":SYM})
p = next((x for x in pos.get("data",[]) if x["symbol"]==SYM and x["positionSide"]=="LONG"), None)
if not p: print("❌ Нет позиции"); exit()
entry = float(p["avgPrice"]); qty = abs(float(p["positionAmt"]))
print(f"Позиция: {qty} {SYM} вход {entry}")

if ask("Установить TP +5% / SL -2%?"):
    tp = round(entry * 1.05, prec); sl = round(entry * 0.98, prec)
    call("POST", "/openApi/swap/v2/trade/order", {
        "symbol":SYM,"side":"SELL","positionSide":"LONG","type":"TAKE_PROFIT_MARKET",
        "quantity":qty,"stopPrice":tp})
    call("POST", "/openApi/swap/v2/trade/order", {
        "symbol":SYM,"side":"SELL","positionSide":"LONG","type":"STOP_MARKET",
        "quantity":qty,"stopPrice":sl})

if ask("Закрыть позицию?"):
    call("POST", "/openApi/swap/v2/trade/order", {
        "symbol":SYM,"side":"SELL","positionSide":"LONG","type":"MARKET","quantity":qty})
    time.sleep(2)
    check = call("GET", "/openApi/swap/v2/user/positions", {"symbol":SYM})
    open_pos = [x for x in check.get("data",[]) if x["symbol"]==SYM and x["positionSide"]=="LONG"]
    print("✅ Закрыта" if not open_pos else "‼️ Ещё висит")

print("\nГотово.")
