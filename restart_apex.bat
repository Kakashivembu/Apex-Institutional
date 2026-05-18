@echo off
setlocal enabledelayedexpansion
title Apex Institutional - Restart
color 0E

REM ── Enable ANSI colors ──
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
echo %Y%=======================================================%X%
echo %Y%  %B%%W%APEX INSTITUTIONAL MT5 MACRO TERMINAL - RESTART SEQUENCE%X%
echo %Y%=======================================================%X%
echo.

REM ── Step 1: Nuclear stop (same logic as stop_apex.bat) ──
echo %Y%[1/6]%X% %W%Stopping all services (nuclear cleanup)...%X%
call pm2 stop all >nul 2>&1
call pm2 delete all >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000" ^| findstr "LISTENING"') do (
    if %%a NEQ 0 taskkill /F /T /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":5173" ^| findstr "LISTENING"') do (
    if %%a NEQ 0 taskkill /F /T /PID %%a >nul 2>&1
)
for /f "tokens=2" %%a in ('wmic process where "CommandLine like '%%uvicorn%%server:app%%'" get ProcessId /value 2^>nul ^| findstr "="') do (
    for /f "tokens=2 delims==" %%b in ("%%a") do taskkill /F /T /PID %%b >nul 2>&1
)
for /f "tokens=2" %%a in ('wmic process where "CommandLine like '%%vite%%--host%%'" get ProcessId /value 2^>nul ^| findstr "="') do (
    for /f "tokens=2 delims==" %%b in ("%%a") do taskkill /F /T /PID %%b >nul 2>&1
)
echo   %G%[OK]%X% All processes and ports cleared
echo.

REM ── Step 2: Wait for ports to fully release ──
echo %Y%[2/6]%X% %W%Waiting for port release...%X%
timeout /t 3 /nobreak >nul
echo   %G%[OK]%X% Ports released
echo.

REM ── Step 3: Flush logs ──
echo %Y%[3/6]%X% %W%Flushing old PM2 logs...%X%
call pm2 flush >nul 2>&1
echo   %G%[OK]%X% Log files cleaned
echo.

REM ── Step 4: Start ecosystem ──
echo %Y%[4/6]%X% %W%Starting PM2 ecosystem...%X%
echo   %DIM%  +-- Apex-Frontend  (Vite direct, port 5173, 512MB limit)%X%
echo   %DIM%  +-- Apex-Backend   (Uvicorn, port 8000, 1GB limit)%X%
echo.
call pm2 start "%~dp0ecosystem.config.js"
if !errorlevel! neq 0 (
    echo   %R%[FAIL]%X% PM2 start failed!
    pause
    exit /b 1
)
echo   %G%[OK]%X% All services restarted
echo.

REM ── Step 5: Save state ──
echo %Y%[5/6]%X% %W%Saving PM2 state...%X%
call pm2 save >nul 2>&1
echo   %G%[OK]%X% State saved
echo.

REM ── Step 6: Wait and verify ──
echo %Y%[6/6]%X% %W%Verifying services...%X%
timeout /t 6 /nobreak >nul
python -c "import requests;r=requests.get('http://localhost:8000/docs',timeout=5);print(f'Backend: HTTP {r.status_code}')" 2>nul
if !errorlevel! equ 0 (
    echo   %G%[OK]%X% Backend verified
) else (
    echo   %Y%[WAIT]%X% Backend still initializing
)
echo.

echo %G%=======================================================%X%
echo %G%  %B%%W%RESTART COMPLETE - SHADOW MODE ACTIVE%X%
echo %G%=======================================================%X%
echo.
echo %W%  Dashboard:%X%   %C%http://localhost:5173%X%
echo %W%  Backend:%X%     %C%http://localhost:8000%X%
echo %W%  PM2 Status:%X%  %C%pm2 status%X%
echo.
echo %M%-------------------------------------------------------%X%
echo %M%  STREAMING LOGS%X%
echo %M%  Press Ctrl+C to stop streaming logs (services keep running)%X%
echo %M%-------------------------------------------------------%X%
echo.
pm2 logs Apex-Backend Apex-Frontend
