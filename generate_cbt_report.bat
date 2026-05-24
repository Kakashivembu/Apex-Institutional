@echo off
echo [CBT-FRAMEWORK] Running Daily Forensic Equity Decay Analysis...
:: Run the cbt-framework analysis CLI against our live MT5 trades
python -m cbt_framework.cli --input "%USERPROFILE%\.apex_trader\state\trades.jsonl" --decay-report > "%USERPROFILE%\.apex_trader\state\cbt_daily_report.txt"
echo [CBT-FRAMEWORK] Report generated at %USERPROFILE%\.apex_trader\state\cbt_daily_report.txt
:: Optionally output to console so PM2 cron can capture it
type "%USERPROFILE%\.apex_trader\state\cbt_daily_report.txt"
