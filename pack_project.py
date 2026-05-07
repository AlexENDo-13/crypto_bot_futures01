import os
import platform
import psutil
from pathlib import Path
from datetime import datetime, timezone
import json

# === Директории, в которые НЕ заходим (полностью пропускаем) ===
EXCLUDE_DIRS = {
    '__pycache__', '.git', '.venv', 'venv', 'env', 'logs',
    '.idea', '.vscode', 'node_modules', 'dist', 'build',
    '.pytest_cache', '.mypy_cache', 'htmlcov', '.tox', 'coverage',
}

# === Файлы, которые игнорируем по точному имени ===
EXCLUDE_FILES = {
    'keys.json',              # 🔒 ключи биржи
    'project_base64.txt',
    'project_packed.txt',
    'telegram_config.json',
    'discord_config.json',
    '.env', '.env.local', '.env.production', '.env.development',
    '.gitignore', '.gitattributes', '.dockerignore',
    'pack_project.py',        # сам себя не упаковываем (опционально)
}

# === Расширения, которые игнорируем ===
EXCLUDE_EXTENSIONS = {
    '.log', '.db', '.sqlite', '.sqlite3', '.pyc', '.pyo',
    '.tmp', '.bak', '.swp', '.swo', '.egg', '.egg-info',
    '.whl', '.tar', '.gz', '.zip', '.rar', '.7z',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.svg', '.webp',
    '.mp3', '.mp4', '.avi', '.mov', '.wav', '.mkv',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.exe', '.dll', '.so', '.dylib', '.bin', '.dat',
}

# === Подстроки в имени файла, которые вызывают исключение ===
EXCLUDE_NAME_PATTERNS = [
    'secret', 'token', 'private', 'password', 
    'credential', 'api_key', 'apikey'
]


def should_include(file_path: Path, root: Path) -> bool:
    """Определяет, нужно ли включать файл в упаковку."""
    try:
        rel_path = file_path.relative_to(root)
    except ValueError:
        return False

    parts = rel_path.parts
    filename = file_path.name
    lower_name = filename.lower()

    # 1. Проверяем, не находится ли файл внутри исключённой директории
    for part in parts[:-1]:  # все части пути кроме имени файла
        if part in EXCLUDE_DIRS:
            return False
        # Исключаем скрытые директории (начинающиеся с точки)
        if part.startswith('.'):
            return False

    # 2. Точное совпадение с запрещёнными именами файлов
    if filename in EXCLUDE_FILES:
        return False

    # 3. Проверка расширения
    if file_path.suffix.lower() in EXCLUDE_EXTENSIONS:
        return False

    # 4. Проверка подстрок в имени файла
    for pattern in EXCLUDE_NAME_PATTERNS:
        if pattern in lower_name:
            return False

    # 5. Исключаем скрытые файлы (начинающиеся с точки)
    if filename.startswith('.'):
        return False

    return True


def get_system_info():
    info = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'os': platform.platform(),
        'python_version': platform.python_version(),
        'cpu': {
            'model': platform.processor() or 'Unknown',
            'cores_physical': psutil.cpu_count(logical=False),
            'cores_logical': psutil.cpu_count(logical=True),
            'usage_percent': psutil.cpu_percent(interval=1)
        },
        'memory': {
            'total_gb': round(psutil.virtual_memory().total / (1024**3), 2),
            'available_gb': round(psutil.virtual_memory().available / (1024**3), 2),
            'percent_used': psutil.virtual_memory().percent
        },
        'disk': {
            'total_gb': round(psutil.disk_usage('/').total / (1024**3), 2),
            'free_gb': round(psutil.disk_usage('/').free / (1024**3), 2),
            'percent_used': psutil.disk_usage('/').percent
        }
    }
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for entries in temps.values():
                if entries:
                    info['cpu']['temperature_c'] = entries[0].current
                    break
    except Exception:
        pass
    return info


def pack_project():
    root = Path(__file__).resolve().parent
    output_file = root / 'project_packed.txt'

    system_info = get_system_info()

    # Собираем ВСЕ файлы рекурсивно
    all_files = []
    for file_path in root.rglob('*'):
        if file_path.is_file() and should_include(file_path, root):
            all_files.append(file_path)

    # Сортируем для стабильного порядка
    all_files.sort()

    print(f"📦 Найдено файлов для упаковки: {len(all_files)}")
    for f in all_files:
        print(f"   + {f.relative_to(root)}")

    with open(output_file, 'w', encoding='utf-8') as out:
        out.write("=== SYSTEM INFO ===\n")
        out.write(json.dumps(system_info, indent=2, ensure_ascii=False))
        out.write("\n\n")

        for file_path in all_files:
            rel_path = file_path.relative_to(root)
            out.write(f'=== BEGIN FILE: {rel_path} ===\n')
            try:
                content = file_path.read_text(encoding='utf-8')
                out.write(content)
            except UnicodeDecodeError:
                out.write('[BINARY FILE SKIPPED]\n')
            except Exception as e:
                out.write(f'[ERROR READING FILE: {e}]\n')
            out.write(f'\n=== END FILE: {rel_path} ===\n\n')

    print(f"\n✅ Упаковано в: {output_file}")
    print(f"🖥  Система: {system_info['cpu']['model']}, "
          f"RAM {system_info['memory']['total_gb']}GB")
    if 'temperature_c' in system_info['cpu']:
        print(f"🌡  Температура CPU: {system_info['cpu']['temperature_c']}°C")


if __name__ == '__main__':
    pack_project()
