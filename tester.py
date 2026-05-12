from core.auth import AuthManager
from core.engine import TradingEngine
auth = AuthManager()
engine = TradingEngine(auth)
engine.load_all_modules()

# Принудительно загрузим символы и свечи
engine._discover_symbols()
print("Top symbols:", engine._top_symbols[:5])

# Попробуем получить свечи для первого символа
if engine._top_symbols:
    sym = engine._top_symbols[0]
    df = engine.api.get_klines_dataframe(sym, '5m', limit=50)
    print(f"DataFrame for {sym}:\n", df.head())
else:
    print("No symbols discovered")
