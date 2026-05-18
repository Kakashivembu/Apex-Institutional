@echo off
setlocal enabledelayedexpansion
title Apex Institutional - Initial Setup
color 0B

REM ── Enable ANSI colors ──
for /F "delims=" %%a in ('python -c "import ctypes;k=ctypes.windll.kernel32;h=k.GetStdHandle(-11);m=ctypes.c_ulong();k.GetConsoleMode(h,ctypes.byref(m));k.SetConsoleMode(h,m.value|4);print(chr(27))"') do set "ESC=%%a"

set "R=%ESC%[91m"
set "G=%ESC%[92m"
set "Y=%ESC%[93m"
set "C=%ESC%[96m"
set "W=%ESC%[97m"
set "DIM=%ESC%[90m"
set "B=%ESC%[1m"
set "X=%ESC%[0m"

echo.
echo %C%=======================================================%X%
echo %C%  %B%%W%APEX INSTITUTIONAL MT5 MACRO TERMINAL - FULL PROJECT SETUP%X%
echo %C%=======================================================%X%
echo.
echo %DIM%  This script installs all dependencies and prepares%X%
echo %DIM%  the trading terminal for first-time use.%X%
echo.

REM ── Check Python ──
echo %Y%[1/6]%X% %W%Verifying Python installation...%X%
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo   %R%[FAIL]%X% Python is not installed or not in PATH!
    echo   %DIM%Install Python 3.10+ from python.org and try again.%X%
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
echo   %G%[OK]%X% !PY_VER!
echo.

REM ── Check Node.js ──
echo %Y%[2/6]%X% %W%Verifying Node.js installation...%X%
node --version >nul 2>&1
if !errorlevel! neq 0 (
    echo   %R%[FAIL]%X% Node.js is not installed or not in PATH!
    echo   %DIM%Install Node.js v18+ from nodejs.org and try again.%X%
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('node --version 2^>^&1') do set "NODE_VER=%%v"
echo   %G%[OK]%X% Node.js !NODE_VER!
echo.

REM ── Install PM2 Globally ──
echo %Y%[3/6]%X% %W%Installing PM2 process manager...%X%
call npm install -g pm2 >nul 2>&1
if !errorlevel! neq 0 (
    echo   %R%[FAIL]%X% PM2 installation failed!
    pause
    exit /b 1
)
echo   %G%[OK]%X% PM2 installed globally
echo.

REM ── Frontend Dependencies ──
echo %Y%[4/6]%X% %W%Installing Frontend (React + Vite)...%X%
pushd "%~dp0frontend"
call npm install >nul 2>&1
if !errorlevel! neq 0 (
    echo   %R%[FAIL]%X% Frontend npm install failed!
    popd
    pause
    exit /b 1
)
if not exist ".env" (
    > ".env" echo VITE_BACKEND_URL=http://127.0.0.1:8000
) else (
    findstr /B /C:"VITE_BACKEND_URL=" ".env" >nul 2>&1
    if !errorlevel! neq 0 echo VITE_BACKEND_URL=http://127.0.0.1:8000>> ".env"
)
REM Create logs directory for PM2
if not exist "logs" mkdir logs
popd
echo   %G%[OK]%X% Frontend dependencies installed
echo   %G%[OK]%X% Frontend .env prepared with VITE_BACKEND_URL
echo.

REM ── Backend Dependencies ──
echo %Y%[5/6]%X% %W%Installing Backend (FastAPI + NVIDIA)...%X%
pushd "%~dp0nvidia_apex_trader"
call pip install -r requirements.txt >nul 2>&1
if !errorlevel! neq 0 (
    echo   %R%[FAIL]%X% Python pip install failed!
    popd
    pause
    exit /b 1
)
REM Create logs directory for PM2
if not exist "logs" mkdir logs
popd
echo   %G%[OK]%X% Backend dependencies installed
echo.

REM ── Create PM2 log directories ──
echo %Y%[6/6]%X% %W%Preparing log directories...%X%
if not exist "%~dp0frontend\logs" mkdir "%~dp0frontend\logs"
if not exist "%~dp0nvidia_apex_trader\logs" mkdir "%~dp0nvidia_apex_trader\logs"
echo   %G%[OK]%X% Log directories created
echo.

REM ── Final Checklist ──
echo %G%=======================================================%X%
echo %G%  %B%%W%SETUP COMPLETE - READY TO BOOT%X%
echo %G%=======================================================%X%
echo.
echo %W%  Next Steps:%X%
echo   %C%1.%X% Run %Y%start_apex.bat%X% to boot the terminal
echo   %C%2.%X% Open %Y%http://localhost:5173%X% in your browser
echo   %C%3.%X% Check the %Y%Network Access%X% card for local and remote URLs
echo   %C%4.%X% Add exchange keys in the %Y%API Fleet%X% tab
echo   %C%5.%X% Add NVIDIA API keys from the dashboard
echo.
echo %DIM%  Tip: Run %Y%stop_apex.bat%X%%DIM% to cleanly shutdown all services%X%
echo %DIM%       Run %Y%restart_apex.bat%X%%DIM% to restart without losing state%X%
echo.
    pause
