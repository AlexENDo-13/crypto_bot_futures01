#!/usr/bin/env python3
"""
GitHub Restore Script – скачивает актуальную версию бота с GitHub.
Если локальный репозиторий уже существует, он будет принудительно сброшен
до последнего коммита из ветки main. Иначе репозиторий будет клонирован.
"""

import subprocess
import sys
import os
import shutil

def run_cmd(cmd, check=True, capture_output=False):
    try:
        if capture_output:
            result = subprocess.run(cmd, check=check, capture_output=True, text=True)
            return result.stdout.strip()
        else:
            subprocess.run(cmd, check=check)
            return None
    except subprocess.CalledProcessError as e:
        if not check and capture_output:
            return None
        print(f"ERROR: Command '{' '.join(cmd)}' failed with code {e.returncode}")
        if e.output:
            print(e.output)
        sys.exit(1)
    except FileNotFoundError:
        print(f"ERROR: Command not found: {cmd[0]}")
        sys.exit(1)

def main():
    print("=" * 60)
    print("  GitHub Restore Script – восстановление бота из репозитория")
    print("=" * 60)

    # Проверка git
    git_version = run_cmd(["git", "--version"], capture_output=True)
    if git_version:
        print(f"Найден Git: {git_version}")
    else:
        print("Ошибка: Git не установлен или не найден в PATH.")
        print("Установите Git с https://git-scm.com/download/win")
        input("Нажмите Enter для выхода...")
        sys.exit(1)

    # Запрос данных
    username = input("Введите ваш GitHub username: ").strip()
    repo_name = input("Введите название репозитория (по умолчанию crypto_bot_futures01): ").strip()
    if not repo_name:
        repo_name = "crypto_bot_futures01"
    repo_url = f"https://github.com/{username}/{repo_name}.git"

    # Путь к папке проекта (текущая директория)
    local_dir = os.getcwd()
    print(f"\nВосстанавливаем репозиторий в: {local_dir}")

    # Проверяем, есть ли уже локальный репозиторий
    if os.path.isdir(os.path.join(local_dir, ".git")):
        print("Локальный репозиторий найден.")
        print("Будет выполнен принудительный сброс до состояния origin/main.")
        confirm = input("Все локальные изменения будут потеряны. Продолжить? (y/n): ").lower()
        if confirm != 'y':
            print("Отмена.")
            sys.exit(0)

        # Убеждаемся, что remote origin указывает на правильный URL
        current_origin = run_cmd(["git", "remote", "get-url", "origin"], check=False, capture_output=True)
        if current_origin and current_origin != repo_url:
            print(f"Текущий origin: {current_origin}, меняем на {repo_url}")
            run_cmd(["git", "remote", "set-url", "origin", repo_url])
        elif not current_origin:
            run_cmd(["git", "remote", "add", "origin", repo_url])

        # Скачиваем все изменения с удалённого репозитория
        print("Загрузка последних изменений с GitHub...")
        run_cmd(["git", "fetch", "origin", "main"])

        # Жёсткий сброс до состояния origin/main
        print("Сброс к последнему коммиту...")
        run_cmd(["git", "reset", "--hard", "origin/main"])

        print("\nЛокальные файлы приведены к состоянию удалённого репозитория.")
    else:
        # Локального репозитория нет – клонируем во временную папку и переносим
        print("Локальный репозиторий отсутствует. Будет выполнено клонирование.")
        tmp_dir = os.path.join(local_dir, "tmp_restore")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)

        try:
            print(f"Клонирование {repo_url} во временную папку...")
            run_cmd(["git", "clone", "--branch", "main", repo_url, tmp_dir])

            # Перенос файлов из временной папки в текущую (кроме самой временной)
            print("Перенос файлов в проект...")
            for item in os.listdir(tmp_dir):
                if item == ".git":
                    continue  # перенесём позже
                s = os.path.join(tmp_dir, item)
                d = os.path.join(local_dir, item)
                if os.path.isdir(s):
                    if os.path.exists(d):
                        shutil.rmtree(d)
                    shutil.copytree(s, d)
                else:
                    shutil.copy2(s, d)

            # Переносим и скрытую папку .git, если её ещё нет
            git_dir_src = os.path.join(tmp_dir, ".git")
            git_dir_dst = os.path.join(local_dir, ".git")
            if not os.path.exists(git_dir_dst):
                shutil.copytree(git_dir_src, git_dir_dst)

            print("Клонирование завершено успешно.")
        finally:
            # Удаляем временную папку
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)

    print("\nВосстановление завершено. Проверьте файлы проекта.")
    input("Нажмите Enter для выхода...")

if __name__ == "__main__":
    main()
