@echo off
title Apex Institutional - Single Click Stop
color 0C

echo =======================================================
echo   APEX INSTITUTIONAL MT5 MACRO TERMINAL - SINGLE STOP
echo =======================================================
echo.

echo Stopping the Apex ecosystem...
call pm2 stop all
echo Ecosystem stopped.
pause
