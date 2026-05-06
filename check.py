import sys
import traceback
from pathlib import Path
import importlib

print("Python path:", sys.path[:3])
print()

for folder in ["strategies", "indicators", "filters"]:
    path = Path(folder)
    if not path.is_dir():
        print(f"[SKIP] folder '{folder}' does not exist")
        continue
    py_files = list(path.glob("*.py"))
    print(f"[{folder}] found {len(py_files)} py files:")
    for f in py_files:
        if f.name.startswith("_"):
            continue
        module_name = f"{folder}.{f.stem}"
        try:
            mod = importlib.import_module(module_name)
            # Try to find expected base class (case-insensitive)
            base_map = {
                "strategies": "BaseStrategy",
                "indicators": "BaseIndicator",
                "filters": "BaseFilter"
            }
            expected = base_map.get(folder)
            found = []
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and hasattr(obj, '__bases__'):
                    bases = [b.__name__ for b in obj.__mro__]
                    if expected and expected in bases:
                        found.append(f"{name}({expected})")
            if found:
                print(f"  [OK] {f.name}: {', '.join(found)}")
            else:
                print(f"  [WARN] {f.name}: no {expected} subclass found")
                print(f"         Classes: {[name for name in dir(mod) if isinstance(getattr(mod, name), type)]}")
        except Exception as e:
            print(f"  [FAIL] {f.name}: {e}")
            traceback.print_exc()
