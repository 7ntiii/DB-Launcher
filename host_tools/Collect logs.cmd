@echo off
rem Copies the log files of every game on this PC into a new folder "DuskLogs_<PC>_<date-time>" next to the
rem package folder and opens it (lan_fix\collect_logs.ps1). Only copies: nothing is deleted, changed or sent.
rem No Python and no admin rights needed. "-ExecutionPolicy Bypass" applies to this one run only (no setting).
setlocal
set "S=%~dp0collect_logs.ps1"
if not exist "%S%" set "S=%~dp0lan_fix\collect_logs.ps1"
if not exist "%S%" (
  echo collect_logs.ps1 not found next to this file or in lan_fix.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%S%" -Here "%~dp0."
pause
