@echo off
setlocal enabledelayedexpansion
title Apex Institutional - Single Click Start
color 0B

echo =======================================================
echo   APEX INSTITUTIONAL MT5 MACRO TERMINAL - SINGLE START
echo =======================================================
echo.

echo [1/3] Checking LM Studio...
echo Please ensure LM Studio is running on http://127.0.0.1:1234/v1
echo with the Qwen3.6 35B model loaded.
echo.

echo [2/3] Checking Hermes on WSL...
echo Please ensure Hermes API gateway is running in your Ubuntu WSL.
echo Example command in WSL: hermes gateway run --host 0.0.0.0 --port 8080
echo (Binding to 0.0.0.0 is required for Windows to connect to WSL)
pause

echo [3/3] Starting the Apex ecosystem...
call "%~dp0start_apex.bat"

echo.
echo Setup Complete!
