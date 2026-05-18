@echo off
setlocal enabledelayedexpansion
title Apex Institutional Trading Terminal
color 0B

REM ── Enable ANSI colors via Python ──
for /F "delims=" %%a in ('python -c "import ctypes;k=ctypes.windll.kernel32;h=k.GetStdHandle(-11);m=ctypes.c_ulong();k.GetConsoleMode(h,ctypes.byref(m));k.SetConsoleMode(h,m.value|4);print(chr(27))"') do set "ESC=%%a"

set "R=%ESC%[91m"
set "G=%ESC%[92m"
set "Y=%ESC%[93m"
set "C=%ESC%[96m"
set "M=%ESC%[95m"
set "W=%ESC%[97m"
set "DIM=%ESC%[90m"
set "B=%ESC%[1m"
set "X=%ESC%[0m"

echo.
echo %C%=======================================================%X%
echo %C%  %B%%W%APEX INSTITUTIONAL MT5 MACRO TERMINAL%X%
echo %C%  %DIM%Multi-Account Fleet Management System%X%
echo %C%=======================================================%X%
echo.

REM ── Step 1: Kill ALL conflicting processes (nuclear cleanup) ──
echo %Y%[1/5]%X% %W%Cleaning up existing processes...%X%
call pm2 stop all >nul 2>&1
call pm2 delete all >nul 2>&1
REM Kill by port with tree-kill
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000" ^| findstr "LISTENING"') do (
    if %%a NEQ 0 taskkill /F /T /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":5173" ^| findstr "LISTENING"') do (
    if %%a NEQ 0 taskkill /F /T /PID %%a >nul 2>&1
)
REM Kill orphaned uvicorn/vite processes by command line
for /f "tokens=2" %%a in ('wmic process where "CommandLine like '%%uvicorn%%server:app%%'" get ProcessId /value 2^>nul ^| findstr "="') do (
    for /f "tokens=2 delims==" %%b in ("%%a") do taskkill /F /T /PID %%b >nul 2>&1
)
for /f "tokens=2" %%a in ('wmic process where "CommandLine like '%%vite%%--host%%'" get ProcessId /value 2^>nul ^| findstr "="') do (
    for /f "tokens=2 delims==" %%b in ("%%a") do taskkill /F /T /PID %%b >nul 2>&1
)
echo   %G%[OK]%X% Ports 8000 and 5173 cleared (tree-kill)
echo.

REM ── Step 2: Flush old logs ──
echo %Y%[2/5]%X% %W%Flushing old PM2 logs...%X%
call pm2 flush >nul 2>&1
echo   %G%[OK]%X% Log files cleaned
echo.

REM ── Step 3: Start PM2 ecosystem ──
echo %Y%[3/5]%X% %W%Starting PM2 ecosystem...%X%
echo   %DIM%  +-- Apex-Frontend  (Vite direct, port 5173, 512MB limit)%X%
echo   %DIM%  +-- Apex-Backend   (Uvicorn, port 8000, 1GB limit)%X%
echo.
call pm2 start "%~dp0ecosystem.config.js"
if !errorlevel! neq 0 (
    echo   %R%[FAIL]%X% PM2 start failed!
    echo   %DIM%Check ecosystem.config.js for errors.%X%
    pause
    exit /b 1
)
echo   %G%[OK]%X% All services started
echo.

REM ── Step 4: Save PM2 state ──
echo %Y%[4/5]%X% %W%Saving PM2 state...%X%
call pm2 save >nul 2>&1
echo   %G%[OK]%X% State saved (auto-restart on reboot)
echo.

REM ── Step 5: Wait and verify ──
echo %Y%[5/5]%X% %W%Waiting for services to initialize...%X%
timeout /t 6 /nobreak >nul
REM Verify backend is responding
python -c "import requests;r=requests.get('http://localhost:8000/docs',timeout=5);print(f'Backend: HTTP {r.status_code}')" 2>nul
if !errorlevel! equ 0 (
    echo   %G%[OK]%X% Backend verified
) else (
    echo   %Y%[WAIT]%X% Backend still initializing (check logs)
)
echo.

echo %G%=======================================================%X%
echo %G%  %B%%W%ALL SYSTEMS ONLINE - SHADOW MODE%X%
echo %G%=======================================================%X%
echo.
echo %W%  Dashboard:%X%   %C%http://localhost:5173%X%
echo %W%  Backend:%X%     %C%http://localhost:8000%X%
echo %W%  PM2 Status:%X%  %C%pm2 status%X%
echo %W%  Network:%X%     %C%Open the Network Access card in the dashboard%X%
echo.
echo %M%-------------------------------------------------------%X%
echo %M%  STREAMING LOGS%X%
echo %M%  Press Ctrl+C to stop streaming logs (services keep running)%X%
echo %M%-------------------------------------------------------%X%
echo.
pm2 logs Apex-Backend Apex-Frontend
