@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================
echo   大乐透数据更新
echo ========================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)

echo 正在检查依赖...
python -c "import requests" 2>nul
if %errorlevel% neq 0 (
    echo 正在安装 requests 库...
    pip install requests
)

echo.
echo 正在更新数据...
echo.
python scripts\local_update.py

echo.
echo ========================================
echo   更新完成
echo ========================================
pause
