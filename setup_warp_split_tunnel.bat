@echo off
color 0B
echo ===============================================================================
echo      APEX TRADING TERMINAL - CLOUDFLARE WARP SPLIT TUNNEL SETUP
echo ===============================================================================
echo.
echo This script will configure Cloudflare WARP to bypass Delta Exchange India 
echo so the trading bot can connect using your real ISP IP address.
echo.

:: Check if warp-cli is installed
where warp-cli >nul 2>nul
if %errorlevel% neq 0 (
    color 0C
    echo [ERROR] warp-cli is not installed or not in your system PATH.
    echo Please install Cloudflare WARP first and try again.
pause
    exit /b 1
)

echo [1/6] Adding Delta Exchange API host...
warp-cli tunnel host add api.india.delta.exchange >nul 2>nul
if %errorlevel% equ 0 (echo   - Success) else (echo   - Failed or already exists)

echo [2/6] Adding Delta Exchange AWS IPv4 Range 1...
warp-cli tunnel ip add-range 13.227.249.0/24 >nul 2>nul
if %errorlevel% equ 0 (echo   - Success) else (echo   - Failed or already exists)

echo [3/6] Adding Delta Exchange AWS IPv4 Range 2...
warp-cli tunnel ip add-range 13.227.0.0/16 >nul 2>nul
if %errorlevel% equ 0 (echo   - Success) else (echo   - Failed or already exists)

echo [4/6] Adding Delta Exchange AWS IPv6 Range...
warp-cli tunnel ip add-range 2600:9000:200a::/48 >nul 2>nul
if %errorlevel% equ 0 (echo   - Success) else (echo   - Failed or already exists)

echo [5/6] Adding IPv4 Dashboard Checker...
warp-cli tunnel host add ipv4.icanhazip.com >nul 2>nul
if %errorlevel% equ 0 (echo   - Success) else (echo   - Failed or already exists)

echo [6/6] Adding IPv6 Dashboard Checker...
warp-cli tunnel host add ipv6.icanhazip.com >nul 2>nul
if %errorlevel% equ 0 (echo   - Success) else (echo   - Failed or already exists)

echo.
color 0A
echo ===============================================================================
echo                             SETUP COMPLETE!
echo ===============================================================================
echo.
echo Cloudflare WARP is now configured to ignore Delta Exchange traffic.
echo.
echo NEXT STEPS:
echo 1. Start the Apex Terminal (start_apex.bat)
echo 2. Open the Dashboard (http://localhost:5173).
echo 3. Check the Network Access card for your LAN URL or remote tunnel URL.
echo 3. Copy your REAL IP shown in the IP Whitelist card.
echo 4. Go to Delta Exchange India API Keys and whitelist that REAL IP.
echo.
pause
