#!/usr/bin/env python3
"""
GitHub Upload Script for Trading Bot
Выполняет автоматический git add, commit и push с force в репозиторий.
Аналог git_commit.bat, но на Python.
"""

import subprocess
import sys
import os
from datetime import datetime

def run_cmd(cmd, check=True, capture_output=False):
    """Выполняет команду через subprocess с обработкой ошибок."""
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
    print("=" * 50)
    print("  GitHub Upload Script for Trading Bot")
    print("=" * 50)

    # Проверяем, установлен ли git
    git_version = run_cmd(["git", "--version"], capture_output=True)
    if git_version:
        print(f"Found: {git_version}")
    else:
        print("ERROR: Git is not installed or not in PATH.")
        print("Please install Git from https://git-scm.com/download/win")
        input("Press Enter to exit...")
        sys.exit(1)

    # Читаем глобальные настройки
    git_email = run_cmd(["git", "config", "--global", "user.email"], check=False, capture_output=True) or ""
    git_username = run_cmd(["git", "config", "--global", "user.name"], check=False, capture_output=True) or ""

    print("\nCurrent global Git settings:")
    print(f"  Email   : [{git_email}]")
    print(f"  Username: [{git_username}]\n")

    # Запрашиваем, если не заданы
    changed = False
    if not git_email:
        git_email = input("Enter your GitHub email: ").strip()
        run_cmd(["git", "config", "--global", "user.email", git_email])
        changed = True
    if not git_username:
        git_username = input("Enter your GitHub username: ").strip()
        run_cmd(["git", "config", "--global", "user.name", git_username])
        changed = True
    if changed:
        print("\nUpdated global Git settings.\n")
    else:
        print(f"Using email   : {git_email}")
        print(f"Using username: {git_username}\n")

    # Создаём .gitignore, если его нет
    if not os.path.exists(".gitignore"):
        print("Creating .gitignore...")
        with open(".gitignore", "w") as f:
            f.write("""keys.json
*.log
data/*.db
project_base64.txt
__pycache__/
*.pyc
Thumbs.db
""")
        print(".gitignore created.\n")

    # Инициализируем репозиторий, если нет
    if not os.path.isdir(".git"):
        print("Initializing git repository...")
        run_cmd(["git", "init"])
    else:
        print("Git repository already exists.\n")

    # Добавляем все файлы
    print("Adding files...")
    run_cmd(["git", "add", "."])

    # Формируем сообщение коммита с временной меткой
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    commit_msg = f"Update {timestamp}"
    print(f"Committing with message: {commit_msg}")
    # Если нечего коммитить, git commit вернёт ошибку, но мы не хотим падать
    commit_result = subprocess.run(["git", "commit", "-m", commit_msg], capture_output=True, text=True)
    if commit_result.returncode != 0:
        # Проверим, есть ли вообще изменения
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout
        if not status.strip():
            print("Nothing to commit, but continuing to push...")
        else:
            print(f"ERROR: git commit failed:\n{commit_result.stderr}")
            # Не выходим, возможно пользователь хочет пропустить
    else:
        print(commit_result.stdout.strip())

    # Настраиваем remote origin
    repo_url = f"https://github.com/{git_username}/crypto_bot_futures01.git"
    print(f"\nSetting remote origin to: {repo_url}")
    # Удаляем старый origin, если есть
    run_cmd(["git", "remote", "remove", "origin"], check=False)
    run_cmd(["git", "remote", "add", "origin", repo_url])

    # Переключаемся на ветку main (если ещё не)
    print("Switching to branch main...")
    # Создаём ветку main, если её нет (git branch -M main)
    run_cmd(["git", "branch", "-M", "main"])

    # Пушим с force
    print("\nPushing to GitHub...")
    push_result = subprocess.run(["git", "push", "-u", "origin", "main", "--force"], capture_output=True, text=True)
    if push_result.returncode == 0:
        print("=" * 50)
        print("  Upload successful!")
        print(f"  Repository: {repo_url}")
        print("=" * 50)
    else:
        print("=" * 50)
        print("  Push failed. Possible reasons:")
        print(f"  1. The repository {repo_url} does not exist.")
        print("     Create it first on GitHub (make sure it's empty).")
        print("  2. Authentication error – use a personal access token")
        print("     or configure SSH key or Git Credential Manager.")
        print("  3. Network error or repository already has unrelated history.")
        print("     Force push may be blocked.")
        print("=" * 50)
        print(f"\nGit push output:\n{push_result.stderr}")

    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
