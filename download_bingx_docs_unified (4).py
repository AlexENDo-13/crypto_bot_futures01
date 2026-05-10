#!/usr/bin/env python3
"""
BingX API Docs v3 Downloader — Универсальный скрипт v5
Радикально новый подход:
  1. Playwright — перебирает ВСЕ известные URL из списка разделов
  2. GitHub API — скачивает репозиторий и ищет markdown-исходники
  3. Static fallback — requests с перебором URL

УСТАНОВКА:
    python download_bingx_docs_unified.py

ВЫХОД:
    bingx_docs_output/
      bingx_api_docs_playwright.md
      bingx_api_docs_github.md
"""

import sys
import subprocess
import time
import re
import os
import json
import zipfile
from pathlib import Path
from urllib.parse import quote

OUTPUT_DIR = Path("bingx_docs_output")
OUTPUT_PLAYWRIGHT = OUTPUT_DIR / "bingx_api_docs_playwright.md"
OUTPUT_GITHUB = OUTPUT_DIR / "bingx_api_docs_github.md"
BASE_URL = "https://bingx-api.github.io/docs-v3"
REPO_ZIP = "https://github.com/BingX-API/docs-v3/archive/refs/heads/main.zip"

# Все известные разделы из документации BingX v3
KNOWN_SECTIONS = [
    # Introduce / Quick Start
    ("#/en", "Introduce"),
    ("#/en", "Quick Start"),
    ("#/en", "Signature Authentication"),
    ("#/en", "Basic Information"),
    ("#/en", "FAQ"),
    ("#/en", "Error Code Reference"),
    ("#/en", "WebSocket Rules"),
    ("#/en", "Generate Listen Key"),
    ("#/en", "Extend Listen Key Validity"),
    ("#/en", "Close Listen Key"),

    # Swap
    ("#/en/swap", "Market Data"),
    ("#/en/swap", "USDT-M Perp Futures symbols"),
    ("#/en/swap", "Order Book"),
    ("#/en/swap", "Recent Trades List"),
    ("#/en/swap", "Mark Price and Funding Rate"),
    ("#/en/swap", "Get Funding Rate History"),
    ("#/en/swap", "Kline/Candlestick Data"),
    ("#/en/swap", "Open Interest Statistics"),
    ("#/en/swap", "24hr Ticker Price Change Statistics"),
    ("#/en/swap", "Query historical transaction orders"),
    ("#/en/swap", "Symbol Order Book Ticker"),
    ("#/en/swap", "Mark Price Kline/Candlestick Data"),
    ("#/en/swap", "Symbol Price Ticker"),
    ("#/en/swap", "Trading Rules"),
    ("#/en/swap", "Trades Endpoints"),
    ("#/en/swap", "Test Order"),
    ("#/en/swap", "Place order"),
    ("#/en/swap", "Modify Order"),
    ("#/en/swap", "Place multiple orders"),
    ("#/en/swap", "Close All Positions"),
    ("#/en/swap", "Cancel Order"),
    ("#/en/swap", "Cancel multiple orders"),
    ("#/en/swap", "Cancel All Open Orders"),
    ("#/en/swap", "Current All Open Orders"),
    ("#/en/swap", "Query pending order status"),
    ("#/en/swap", "Query Order details"),
    ("#/en/swap", "Query Margin Type"),
    ("#/en/swap", "Change Margin Type"),
    ("#/en/swap", "Query Leverage and Available Positions"),
    ("#/en/swap", "Set Leverage"),
    ("#/en/swap", "User's Force Orders"),
    ("#/en/swap", "Query Order history"),
    ("#/en/swap", "Modify Isolated Position Margin"),
    ("#/en/swap", "Set Position Mode"),
    ("#/en/swap", "Query position mode"),
    ("#/en/swap", "Cancel an Existing Order and Send a New Order"),
    ("#/en/swap", "Cancel orders in batches and place orders in batches"),
    ("#/en/swap", "Cancel All After"),
    ("#/en/swap", "Close position by position ID"),
    ("#/en/swap", "All Orders"),
    ("#/en/swap", "Position and Maintenance Margin Ratio"),
    ("#/en/swap", "Query historical transaction details"),
    ("#/en/swap", "Query Position History"),
    ("#/en/swap", "Isolated Margin Change History"),
    ("#/en/swap", "Apply VST"),
    ("#/en/swap", "Place TWAP Order"),
    ("#/en/swap", "Query TWAP Entrusted Order"),
    ("#/en/swap", "Query TWAP Historical Orders"),
    ("#/en/swap", "TWAP Order Details"),
    ("#/en/swap", "Cancel TWAP Order"),
    ("#/en/swap", "Switch Multi-Assets Mode"),
    ("#/en/swap", "Query Multi-Assets Mode"),
    ("#/en/swap", "Query Multi-Assets Rules"),
    ("#/en/swap", "Query Multi-Assets Margin"),
    ("#/en/swap", "One-Click Reverse Position"),
    ("#/en/swap", "Hedge mode Position - Automatic Margin Addition"),
    ("#/en/swap", "Account Endpoints"),
    ("#/en/swap", "Query account data"),
    ("#/en/swap", "Query position data"),
    ("#/en/swap", "Get Account Profit and Loss Fund Flow"),
    ("#/en/swap", "Export fund flow"),
    ("#/en/swap", "Query Trading Commission Rate"),
    ("#/en/swap", "Websocket Market Data"),
    ("#/en/swap", "Partial Order Book Depth"),
    ("#/en/swap", "Subscribe the Latest Trade Detail"),
    ("#/en/swap", "Subscribe K-Line Data"),
    ("#/en/swap", "Subscribe to 24-hour price changes"),
    ("#/en/swap", "Subscribe to latest price changes"),
    ("#/en/swap", "Subscribe to latest mark price changes"),
    ("#/en/swap", "Subscribe to the Book Ticker Streams"),
    ("#/en/swap", "Incremental Depth Information"),
    ("#/en/swap", "Websocket Account Data"),
    ("#/en/swap", "Order update push"),
    ("#/en/swap", "Account balance and position update push"),
    ("#/en/swap", "Configuration updates such as leverage and margin mode"),

    # Spot
    ("#/en/spot", "Market Data"),
    ("#/en/spot", "Spot trading symbols"),
    ("#/en/spot", "Recent Trades List"),
    ("#/en/spot", "Order Book"),
    ("#/en/spot", "Kline/Candlestick Data"),
    ("#/en/spot", "24hr Ticker Price Change Statistics"),
    ("#/en/spot", "Order Book aggregation"),
    ("#/en/spot", "Symbol Price Ticker"),
    ("#/en/spot", "Symbol Order Book Ticker"),
    ("#/en/spot", "Historical K-line"),
    ("#/en/spot", "Old Trade Lookup"),
    ("#/en/spot", "Account Endpoints"),
    ("#/en/spot", "Query Assets"),
    ("#/en/spot", "Asset transfer records"),
    ("#/en/spot", "Main Account internal transfer"),
    ("#/en/spot", "Asset Transfer New"),
    ("#/en/spot", "Query transferable currency"),
    ("#/en/spot", "Asset transfer records new"),
    ("#/en/spot", "Query Fund Account Assets"),
    ("#/en/spot", "Main account internal transfer records"),
    ("#/en/spot", "Asset overview"),
    ("#/en/spot", "Wallet deposits and withdrawals"),
    ("#/en/spot", "Deposit records"),
    ("#/en/spot", "Withdraw records"),
    ("#/en/spot", "Query currency deposit and withdrawal data"),
    ("#/en/spot", "Withdraw"),
    ("#/en/spot", "Main Account Deposit Address"),
    ("#/en/spot", "Deposit risk control records"),
    ("#/en/spot", "Trades Endpoints"),
    ("#/en/spot", "Place order"),
    ("#/en/spot", "Place multiple orders"),
    ("#/en/spot", "Cancel Order"),
    ("#/en/spot", "Cancel multiple orders"),
    ("#/en/spot", "Cancel all Open Orders on a Symbol"),
    ("#/en/spot", "Cancel an Existing Order and Send a New Order"),
    ("#/en/spot", "Query Order details"),
    ("#/en/spot", "Current Open Orders"),
    ("#/en/spot", "Query Order history"),
    ("#/en/spot", "Query transaction details"),
    ("#/en/spot", "Query Trading Commission Rate"),
    ("#/en/spot", "Cancel All After"),
    ("#/en/spot", "Create an OCO Order"),
    ("#/en/spot", "Cancel an OCO Order List"),
    ("#/en/spot", "Query an OCO Order List"),
    ("#/en/spot", "Query All Open OCO Orders"),
    ("#/en/spot", "Query OCO Historical Order List"),
    ("#/en/spot", "Websocket Market Data"),
    ("#/en/spot", "Subscription transaction by transaction"),
    ("#/en/spot", "K-line Streams"),
    ("#/en/spot", "Subscribe Market Depth Data"),
    ("#/en/spot", "Subscribe to 24-hour Price Change"),
    ("#/en/spot", "Spot Latest Trade Price"),
    ("#/en/spot", "Spot Best Order Book"),
    ("#/en/spot", "Incremental and Full Depth Information"),
    ("#/en/spot", "Websocket Account Data"),
    ("#/en/spot", "order update event"),
    ("#/en/spot", "Subscription account balance push"),

    # Coin-M Futures
    ("#/en/coin_m", "Market Data"),
    ("#/en/coin_m", "Contract Information"),
    ("#/en/coin_m", "Price & Current Funding Rate"),
    ("#/en/coin_m", "Get Swap Open Positions"),
    ("#/en/coin_m", "Get K-line Data"),
    ("#/en/coin_m", "Query Depth Data"),
    ("#/en/coin_m", "Query 24-Hour Price Change"),
    ("#/en/coin_m", "Trades Endpoints"),
    ("#/en/coin_m", "Trade order"),
    ("#/en/coin_m", "Query Trade Commission Rate"),
    ("#/en/coin_m", "Query Leverage"),
    ("#/en/coin_m", "Modify Leverage"),
    ("#/en/coin_m", "Cancel all orders"),
    ("#/en/coin_m", "Close all positions in bulk"),
    ("#/en/coin_m", "Query warehouse"),
    ("#/en/coin_m", "Query Account Assets"),
    ("#/en/coin_m", "Query force orders"),
    ("#/en/coin_m", "Query Order Trade Detail"),
    ("#/en/coin_m", "Cancel an Order"),
    ("#/en/coin_m", "Query all current pending orders"),
    ("#/en/coin_m", "Query Order"),
    ("#/en/coin_m", "User's History Orders"),
    ("#/en/coin_m", "Query Margin Type"),
    ("#/en/coin_m", "Set Margin Type"),
    ("#/en/coin_m", "Adjust Isolated Margin"),
    ("#/en/coin_m", "Websocket Market Data"),
    ("#/en/coin_m", "Subscription transaction by transaction"),
    ("#/en/coin_m", "Subscribe to the Latest Transaction Price"),
    ("#/en/coin_m", "Subscribe to Mark Price"),
    ("#/en/coin_m", "Subscribe to Limited Depth"),
    ("#/en/coin_m", "Subscribe to Best Bid and Ask"),
    ("#/en/coin_m", "Subscribe to Latest Trading Pair K-Line"),
    ("#/en/coin_m", "Subscribe to 24-Hour Price Change"),
    ("#/en/coin_m", "Websocket Account Data"),
    ("#/en/coin_m", "Account balance and position update push"),
    ("#/en/coin_m", "Order update push"),
    ("#/en/coin_m", "Configuration updates such as leverage and margin mode"),

    # Account and Wallet
    ("#/en/account", "Fund Account"),
    ("#/en/account", "Query Assets"),
    ("#/en/account", "Asset transfer records"),
    ("#/en/account", "Main Account internal transfer"),
    ("#/en/account", "Asset Transfer New"),
    ("#/en/account", "Query transferable currency"),
    ("#/en/account", "Asset transfer records new"),
    ("#/en/account", "Query Fund Account Assets"),
    ("#/en/account", "Main account internal transfer records"),
    ("#/en/account", "Asset overview"),
    ("#/en/account", "Wallet Deposits and Withdrawals"),
    ("#/en/account", "Deposit records"),
    ("#/en/account", "Withdraw records"),
    ("#/en/account", "Query currency deposit and withdrawal data"),
    ("#/en/account", "Withdraw"),
    ("#/en/account", "Main Account Deposit Address"),
    ("#/en/account", "Deposit risk control records"),
    ("#/en/account", "Sub-account Management"),
    ("#/en/account", "Create Sub-account"),
    ("#/en/account", "Query API KEY Permissions"),
    ("#/en/account", "Query Account UID"),
    ("#/en/account", "Query Sub-account List"),
    ("#/en/account", "Query Sub-account Asset Account"),
    ("#/en/account", "Create Sub-account API Key"),
    ("#/en/account", "Query API Key Information"),
    ("#/en/account", "Edit Sub-Account API Key"),
    ("#/en/account", "Delete Sub-Account API Key"),
    ("#/en/account", "Freeze/Unfreeze Sub-Account"),
    ("#/en/account", "Authorize Sub-Account Internal Transfer"),
    ("#/en/account", "Sub-account Internal Transfer"),
    ("#/en/account", "Main Account internal transfer"),
    ("#/en/account", "Query Sub-account Deposit Address"),
    ("#/en/account", "Query Sub-account Deposit Address"),
    ("#/en/account", "Get Sub-account Deposit Records"),
    ("#/en/account", "Query Sub-account Internal Transfer Records"),
    ("#/en/account", "Query Sub-Mother Account Transfer History"),
    ("#/en/account", "Query Sub-Mother Account Transferable Amount"),
    ("#/en/account", "Sub-Mother Account Asset Transfer Interface"),
    ("#/en/account", "Batch Query Sub-Account Asset Overview"),

    # Agent
    ("#/en/agent", "Query Invited Users"),
    ("#/en/agent", "Daily commission details"),
    ("#/en/agent", "Query agent user information"),
    ("#/en/agent", "Query the deposit details of invited users"),
    ("#/en/agent", "Query API transaction commission"),
    ("#/en/agent", "Query partner information"),
    ("#/en/agent", "Invitation code data"),
    ("#/en/agent", "Superior verification"),

    # Copy Trade
    ("#/en/copy_trade", "USDT-M Perpetual Contracts"),
    ("#/en/copy_trade", "Trader's current order"),
    ("#/en/copy_trade", "Traders close positions according to the order number"),
    ("#/en/copy_trade", "Traders set take profit and stop loss based on order numbers"),
    ("#/en/copy_trade", "Personal Trading Overview"),
    ("#/en/copy_trade", "Profit Overview"),
    ("#/en/copy_trade", "Profit Details"),
    ("#/en/copy_trade", "Set Commission Rate"),
    ("#/en/copy_trade", "Trader Gets Copy Trading Pairs"),
    ("#/en/copy_trade", "Spot Trading"),
    ("#/en/copy_trade", "Trader sells spot assets based on buy order number"),
    ("#/en/copy_trade", "Personal Trading Overview"),
    ("#/en/copy_trade", "Profit Summary"),
    ("#/en/copy_trade", "Profit Details"),
    ("#/en/copy_trade", "Query Historical Orders"),

    # CHANGE LOGS
    ("#/en", "CHANGE LOGS"),
]


def install(package, mirror=None):
    cmd = [sys.executable, "-m", "pip", "install", "-q", package]
    if mirror:
        cmd.extend(["-i", mirror])
    print(f"[📦] Установка: {package}" + (f" (зеркало: {mirror})" if mirror else ""))
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"  [✓] {package} установлен")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [!] Ошибка: {e.stderr[:200]}")
        return False


def ensure_playwright():
    if install("playwright"):
        print("[📦] Установка Chromium...")
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                          check=True, capture_output=True, text=True)
            print("  [✓] Chromium готов")
            return True
        except:
            pass
    mirrors = [
        "https://pypi.tuna.tsinghua.edu.cn/simple",
        "https://mirrors.aliyun.com/pypi/simple/",
    ]
    for mirror in mirrors:
        if install("playwright", mirror):
            try:
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                              check=True, capture_output=True, text=True)
                print("  [✓] Chromium готов (зеркало)")
                return True
            except:
                continue
    return False


def ensure_requests():
    if not install("requests"):
        for mirror in ["https://pypi.tuna.tsinghua.edu.cn/simple", "https://mirrors.aliyun.com/pypi/simple/"]:
            if install("requests", mirror):
                break
        else:
            return False
    return True


# --- Playwright scraper v3 — перебирает ВСЕ известные URL ---

def scrape_playwright():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[!] Playwright не установлен")
        return False

    import asyncio

    async def _scrape():
        sections = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = await context.new_page()

            # Сначала открываем базовый URL чтобы docsify загрузился
            print(f"[→] Playwright: загружаю базовую страницу...")
            await page.goto(f"{BASE_URL}/info", wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(5000)

            # Перебираем все известные разделы
            total = len(KNOWN_SECTIONS)
            print(f"[📁] Playwright: перебираю {total} известных разделов...")

            for i, (hash_path, title) in enumerate(KNOWN_SECTIONS, 1):
                url = f"{BASE_URL}/{hash_path.lstrip('#/')}" if not hash_path.startswith("http") else hash_path
                # Добавляем hash
                if not "#" in url:
                    url = f"{BASE_URL}/{hash_path.lstrip('#/')}" if hash_path != "#/en" else BASE_URL

                print(f"  [{i}/{total}] {title[:50]}...")

                try:
                    # Навигируем через hash
                    full_url = f"{BASE_URL}{hash_path.lstrip('#')}" if hash_path.startswith("#/") else hash_path
                    await page.goto(full_url, wait_until="networkidle", timeout=20000)
                    await page.wait_for_timeout(2500)

                    # Извлекаем контент через JavaScript
                    content = await page.evaluate("""
                        () => {
                            const selectors = [
                                '.content article', '.markdown-section', '#main .content',
                                '.content', 'main', 'article', '.markdown-body', 'body'
                            ];
                            for (const sel of selectors) {
                                const el = document.querySelector(sel);
                                if (el && el.innerText.length > 50) {
                                    return el.innerText;
                                }
                            }
                            return document.body ? document.body.innerText : '';
                        }
                    """)

                    if len(content) > 100:
                        sections.append((title, content))
                    else:
                        print(f"    [!] Контент пустой или слишком короткий ({len(content)} символов)")

                except Exception as e:
                    print(f"    [!] Ошибка: {e}")
                    continue

            await browser.close()
        return sections

    sections = asyncio.run(_scrape())
    if not sections:
        return False
    _save_markdown(sections, OUTPUT_PLAYWRIGHT, "Playwright")
    return True


# --- GitHub Repo Parser v2 — улучшенный ---

def scrape_github():
    try:
        import requests
    except ImportError:
        print("[!] requests не установлен")
        return False

    sections = []
    temp_zip = OUTPUT_DIR / "docs-v3.zip"
    extract_dir = OUTPUT_DIR / "docs-v3-main"

    # 1. Скачиваем ZIP
    print(f"[→] GitHub: скачиваю репозиторий...")
    try:
        resp = requests.get(REPO_ZIP, headers={"User-Agent": "Mozilla/5.0"}, timeout=120, stream=True)
        resp.raise_for_status()
        with open(temp_zip, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"  [✓] ZIP скачан ({temp_zip.stat().st_size / 1024:.0f} KB)")
    except Exception as e:
        print(f"  [!] Ошибка: {e}")
        return False

    # 2. Распаковываем
    try:
        with zipfile.ZipFile(temp_zip, "r") as z:
            z.extractall(OUTPUT_DIR)
        print("  [✓] Распаковано")
    except Exception as e:
        print(f"  [!] Ошибка распаковки: {e}")
        return False

    # 3. Ищем JS-файлы
    js_dir = extract_dir / "static" / "js"
    if not js_dir.exists():
        print("  [!] JS-директория не найдена")
        return False

    js_files = [f for f in js_dir.iterdir() if f.suffix == ".js" and not f.name.endswith(".map")]
    print(f"  [📁] Найдено JS-файлов: {len(js_files)}")

    # 4. Извлекаем markdown — улучшенные паттерны
    all_texts = []
    seen = set()

    for js_file in js_files:
        print(f"  [🔍] Анализ: {js_file.name}")
        try:
            with open(js_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except:
            continue

        # Паттерн 1: Длинные строки с markdown (content:"...")
        # Ищем строки длиной 500+ символов с markdown-признаками
        for match in re.finditer(r'"((?:[^"\\]|\\.){500,15000})"', content):
            text = match.group(1)
            text = text.replace('\\n', '\n').replace('\\t', '\t')
            text = text.replace('\\"', '"').replace("\\'", "'")
            text = text.replace('\\\\', '\\').replace('\\/', '/')
            text = text.replace('\\u003c', '<').replace('\\u003e', '>')
            text = text.replace('\\u0026', '&').replace('\\u0022', '"')

            if len(text) > 200 and looks_like_markdown(text):
                fingerprint = text[:200].strip()
                if fingerprint not in seen:
                    seen.add(fingerprint)
                    all_texts.append(text)

        # Паттерн 2: Одинарные кавычки
        for match in re.finditer(r"'((?:[^'\\]|\\.){500,15000})'", content):
            text = match.group(1)
            text = text.replace('\\n', '\n').replace('\\t', '\t')
            text = text.replace('\\"', '"').replace("\\'", "'")
            text = text.replace('\\\\', '\\').replace('\\/', '/')

            if len(text) > 200 and looks_like_markdown(text):
                fingerprint = text[:200].strip()
                if fingerprint not in seen:
                    seen.add(fingerprint)
                    all_texts.append(text)

        # Паттерн 3: Шаблонные строки (backticks) с markdown
        for match in re.finditer(r'`((?:[^`]|\\`){500,15000})`', content):
            text = match.group(1)
            text = text.replace('\\n', '\n').replace('\\t', '\t')
            text = text.replace('\\"', '"').replace("\\'", "'")

            if len(text) > 200 and looks_like_markdown(text):
                fingerprint = text[:200].strip()
                if fingerprint not in seen:
                    seen.add(fingerprint)
                    all_texts.append(text)

    print(f"  [📊] Извлечено уникальных блоков: {len(all_texts)}")

    if not all_texts:
        print("  [!] Не удалось извлечь контент")
        return False

    # 5. Собираем в markdown
    with open(OUTPUT_GITHUB, "w", encoding="utf-8") as f:
        f.write("# BingX API Documentation v3\n\n")
        f.write("> Собрано из GitHub репозитория (JS-бандлы)\n")
        f.write("> Источник: https://github.com/BingX-API/docs-v3\n\n")
        f.write("---\n\n")

        for i, text in enumerate(all_texts, 1):
            f.write(f"\n\n<!-- Block {i} -->\n\n")
            f.write(text)
            f.write("\n\n---\n")

    size_kb = OUTPUT_GITHUB.stat().st_size / 1024
    print(f"\n[✓] GitHub: сохранено {OUTPUT_GITHUB} ({size_kb:.1f} KB, {len(all_texts)} блоков)")
    return True


def looks_like_markdown(text):
    if not text or len(text) < 100:
        return False
    score = 0
    checks = [
        (r'^\s*#{1,3}\s+\w', "heading"),
        (r'\*\*\w+\*\*', "bold"),
        (r'`\w+`', "inline_code"),
        (r'```', "code_block"),
        (r'\|\s*\w+\s*\|', "table"),
        (r'\b(GET|POST|PUT|DELETE|PATCH)\b', "http_method"),
        (r'\bendpoint\b', "endpoint"),
        (r'\b(Request|Response|Parameters|Header|URL|Path)\b', "api_term"),
        (r'\b(BTC|ETH|USDT|symbol|price|quantity|order|position)\b', "crypto_term"),
    ]
    for pattern, _ in checks:
        if re.search(pattern, text, re.IGNORECASE):
            score += 1
    return score >= 2


def _save_markdown(sections, path, method):
    seen = set()
    unique = []
    for title, content in sections:
        fp = content[:200].strip()
        if fp not in seen:
            seen.add(fp)
            unique.append((title, content))

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# BingX API Documentation v3\n\n")
        f.write(f"> Собрано автоматически через {method}\n")
        f.write(f"> Источник: {BASE_URL}\n\n")
        f.write("---\n\n")
        for title, content in unique:
            f.write(f"\n\n# {title if title else 'Раздел'}\n\n")
            f.write(content)
            f.write("\n\n---\n")

    size_kb = path.stat().st_size / 1024
    print(f"\n[✓] {method}: сохранено {path} ({size_kb:.1f} KB, {len(unique)} разделов)")


def main():
    print("=" * 60)
    print("BingX API Docs v3 — Универсальный Downloader v5")
    print("=" * 60)

    OUTPUT_DIR.mkdir(exist_ok=True)
    results = {"playwright": False, "github": False}

    # 1. Playwright
    print("\n--- Playwright ---")
    if ensure_playwright():
        results["playwright"] = scrape_playwright()
    else:
        print("[!] Playwright не удалось установить")

    # 2. GitHub Repo Parser
    print("\n--- GitHub Repo Parser ---")
    if ensure_requests():
        results["github"] = scrape_github()
    else:
        print("[!] requests не удалось установить")

    # Summary
    print("\n" + "=" * 60)
    print("РЕЗУЛЬТАТ:")
    for name, ok in results.items():
        status = "✓ ГОТОВО" if ok else "✗ НЕ УДАЛОСЬ"
        path = OUTPUT_PLAYWRIGHT if name == "playwright" else OUTPUT_GITHUB
        exists = "(файл создан)" if (ok and path.exists()) else ""
        print(f"  {name:12} → {status}  {exists}")
    print("=" * 60)

    if not any(results.values()):
        print("\n[!] Ни один метод не сработал.")


if __name__ == "__main__":
    main()
