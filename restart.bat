@echo off
title Apex Institutional - Single Click Restart
color 0E

echo =======================================================
echo   APEX INSTITUTIONAL MT5 MACRO TERMINAL - SINGLE RESTART
echo =======================================================
echo.

echo Restarting the Apex ecosystem...
call pm2 restart all
echo Ecosystem restarted.
pause
