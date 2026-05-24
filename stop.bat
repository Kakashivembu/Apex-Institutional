@echo off
setlocal enabledelayedexpansion
title Apex Institutional - Single Click Stop
color 0C

echo =======================================================
echo   APEX INSTITUTIONAL MT5 MACRO TERMINAL - SINGLE STOP
echo =======================================================
echo.

echo Stopping the Apex ecosystem...
call "%~dp0stop_apex.bat"

echo.
echo If you also want to stop Hermes and LM Studio, please close their respective windows.
pause
