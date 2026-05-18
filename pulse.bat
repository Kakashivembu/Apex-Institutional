@echo off
title Apex Pulse - Clean Execution Feed
color 0A
echo =====================================================
echo   APEX PULSE - FILTERED HEARTBEAT (LIVE MODE)
echo   Waiting for critical trade, AI, and tunnel events...
echo   Press Ctrl+C to exit
echo =====================================================
echo.
pm2 logs Apex-Backend --raw | findstr /I "STEP-TRAIL SCALPER FINAL TRADE AUTOPSY LOCKING GUARD FLIP DEFENSE COOLDOWN VELOCITY SHIELD MOMENTUM SNAP FLEET EXECUTION TRIGGERED KILLSWITCH TUNNEL RECONCILE CONSENSUS OPTIONS THETA"
