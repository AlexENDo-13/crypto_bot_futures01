@echo off
setlocal enabledelayedexpansion

echo ============================================
echo   GitHub Upload Script for Trading Bot
echo ============================================

:: Проверяем, установлен ли git
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: Git is not installed or not in PATH.
    echo Please install Git from https://git-scm.com/download/win
    pause
    exit /b 1
)

:: Читаем текущие глобальные настройки
for /f "tokens=*" %%i in ('git config --global user.email 2^>nul') do set GIT_EMAIL=%%i
for /f "tokens=*" %%i in ('git config --global user.name 2^>nul') do set GIT_USERNAME=%%i

echo Current global Git settings:
echo   Email   : [!GIT_EMAIL!]
echo   Username: [!GIT_USERNAME!]
echo.

:: Запрашиваем только если не заданы
if "!GIT_EMAIL!"=="" (
    set /p GIT_EMAIL="Enter your GitHub email: "
    git config --global user.email "!GIT_EMAIL!"
)
if "!GIT_USERNAME!"=="" (
    set /p GIT_USERNAME="Enter your GitHub username: "
    git config --global user.name "!GIT_USERNAME!"
)

echo.
echo Using email   : !GIT_EMAIL!
echo Using username: !GIT_USERNAME!
echo.

:: Создаём .gitignore, если его нет
if not exist .gitignore (
    echo Creating .gitignore...
    (
        echo keys.json
        echo *.log
        echo data\*.db
        echo project_base64.txt
        echo __pycache__/
        echo *.pyc
        echo Thumbs.db
    ) > .gitignore
)

:: Инициализируем репозиторий
if not exist .git (
    echo Initializing git repository...
    git init
) else (
    echo Git repository already exists.
)

:: Добавляем файлы и коммитим
echo Adding files...
git add .

set TIMESTAMP=%date:~-4%-%date:~3,2%-%date:~0,2%_%time:~0,2%-%time:~3,2%-%time:~6,2%
set TIMESTAMP=!TIMESTAMP: =0!
echo Committing with message: Update !TIMESTAMP!
git commit -m "Update !TIMESTAMP!"

:: Настраиваем remote и пушим
set REPO_URL=https://github.com/!GIT_USERNAME!/crypto_bot_futures01.git
echo Setting remote origin to: !REPO_URL!
git remote remove origin 2>nul
git remote add origin !REPO_URL!

echo Switching to branch main...
git branch -M main

echo Pushing to GitHub...
git push -u origin main --force

if !errorlevel! equ 0 (
    echo ============================================
    echo   Upload successful!
    echo   Repository: !REPO_URL!
    echo ============================================
) else (
    echo ============================================
    echo   Push failed. Possible reasons:
    echo   1. The repository !REPO_URL! does not exist.
    echo      Create it first on GitHub.
    echo   2. Authentication error - use a personal access token.
    echo ============================================
)

pause