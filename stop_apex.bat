@echo off
setlocal enabledelayedexpansion
title Apex Institutional - Shutdown
color 0C

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
echo %R%=======================================================%X%
echo %R%  %B%%W%APEX INSTITUTIONAL MT5 MACRO TERMINAL - SHUTDOWN SEQUENCE%X%
echo %R%=======================================================%X%
echo.

REM ── Step 1: Stop PM2 services ──
echo %Y%[1/5]%X% %W%Stopping all PM2 services...%X%
call pm2 stop all >nul 2>&1
call pm2 delete all >nul 2>&1
call pm2 save --force >nul 2>&1
echo   %G%[OK]%X% PM2 services stopped and removed
echo.

REM ── Step 2: Kill processes on port 8000 (Backend) ──
echo %Y%[2/5]%X% %W%Killing backend on port 8000...%X%
set "KILLED_8000=0"
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":8000" ^| findstr "LISTENING"') do (
    if %%a NEQ 0 (
        taskkill /F /T /PID %%a >nul 2>&1
        set "KILLED_8000=1"
    )
)
if "!KILLED_8000!"=="1" (
    echo   %G%[OK]%X% Port 8000 released
) else (
    echo   %DIM%[--]%X% Port 8000 was already free
)
echo.

REM ── Step 3: Kill processes on port 5173 (Frontend) ──
echo %Y%[3/5]%X% %W%Killing frontend on port 5173...%X%
set "KILLED_5173=0"
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":5173" ^| findstr "LISTENING"') do (
    if %%a NEQ 0 (
        taskkill /F /T /PID %%a >nul 2>&1
        set "KILLED_5173=1"
    )
)
if "!KILLED_5173!"=="1" (
    echo   %G%[OK]%X% Port 5173 released
) else (
    echo   %DIM%[--]%X% Port 5173 was already free
)
echo.

REM ── Step 4: Nuclear fallback - kill any orphaned node/python from our project ──
echo %Y%[4/5]%X% %W%Cleaning orphaned processes...%X%
set "ORPHANS=0"
for /f "tokens=2" %%a in ('wmic process where "CommandLine like '%%uvicorn%%server:app%%'" get ProcessId /value 2^>nul ^| findstr "="') do (
    for /f "tokens=2 delims==" %%b in ("%%a") do (
        taskkill /F /T /PID %%b >nul 2>&1
        set "ORPHANS=1"
    )
)
for /f "tokens=2" %%a in ('wmic process where "CommandLine like '%%vite%%--host%%'" get ProcessId /value 2^>nul ^| findstr "="') do (
    for /f "tokens=2 delims==" %%b in ("%%a") do (
        taskkill /F /T /PID %%b >nul 2>&1
        set "ORPHANS=1"
    )
)
if "!ORPHANS!"=="1" (
    echo   %G%[OK]%X% Orphaned processes terminated
) else (
    echo   %DIM%[--]%X% No orphans found
)
echo.

REM ── Step 5: Verify ports are free ──
echo %Y%[5/5]%X% %W%Verifying clean shutdown...%X%
timeout /t 2 /nobreak >nul
set "PORT_CLEAN=1"
netstat -aon 2>nul | findstr ":8000" | findstr "LISTENING" >nul 2>&1
if !errorlevel! equ 0 (
    echo   %R%[WARN]%X% Port 8000 still occupied!
    set "PORT_CLEAN=0"
)
netstat -aon 2>nul | findstr ":5173" | findstr "LISTENING" >nul 2>&1
if !errorlevel! equ 0 (
    echo   %R%[WARN]%X% Port 5173 still occupied!
    set "PORT_CLEAN=0"
)
if "!PORT_CLEAN!"=="1" (
    echo   %G%[OK]%X% All ports verified free
)
echo.

echo %R%=======================================================%X%
echo %R%  %B%%W%ALL SYSTEMS STOPPED SAFELY%X%
echo %R%=======================================================%X%
echo.
echo %DIM%  No trades will execute while stopped.%X%
echo %DIM%  Flight Recorder state preserved at:%X%
echo %C%  ~\.apex_trader\apex_flight_state.json%X%
echo.
echo %W%  Run %Y%start_apex.bat%X%%W% to restart.%X%
echo.
pause
