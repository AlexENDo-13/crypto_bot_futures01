import os
import shutil
from pathlib import Path

def clean_pycache(root_dir="."):
    deleted = 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Удаляем __pycache__ директории
        if '__pycache__' in dirnames:
            pycache_path = os.path.join(dirpath, '__pycache__')
            try:
                shutil.rmtree(pycache_path)
                print(f"Удалена папка: {pycache_path}")
                deleted += 1
                dirnames.remove('__pycache__')  # чтобы не заходить внутрь
            except Exception as e:
                print(f"Не удалось удалить {pycache_path}: {e}")
        
        # Удаляем .pyc файлы (на всякий случай)
        for filename in filenames:
            if filename.endswith('.pyc'):
                file_path = os.path.join(dirpath, filename)
                try:
                    os.remove(file_path)
                    print(f"Удалён файл: {file_path}")
                    deleted += 1
                except Exception as e:
                    print(f"Не удалось удалить {file_path}: {e}")
    
    print(f"Очистка завершена. Удалено {deleted} объектов.")

if __name__ == "__main__":
    # Укажите путь к корню проекта, если скрипт запускается не из корня
    project_root = os.path.dirname(os.path.abspath(__file__))
    clean_pycache(project_root)
