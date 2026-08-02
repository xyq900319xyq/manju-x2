@echo off
chcp 65001 >nul
title Hermes Workspace Launcher

echo ========================================
echo    Hermes Workspace
echo ========================================
echo.

echo Starting services via WSL...
wsl bash ~/start-workspace.sh
if %errorlevel% neq 0 (
    echo ERROR: WSL script failed. Is WSL running?
    pause
    exit /b 1
)

echo.
echo Waiting for Vite to compile (6s)...
timeout /t 6 /nobreak >nul

echo Opening browser...
start http://localhost:3000

echo.
echo Done! If the page doesn't load, wait a few more seconds and refresh.
timeout /t 2 /nobreak >nul
