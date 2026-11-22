@echo off
rem Gets the newest game program from the host PC of the home network into this folder (lan_fix\update_from_host.ps1).
rem Close the game first. The old program is kept as Lichii\lichii.exe.old. No saves or settings are touched.
rem "-ExecutionPolicy Bypass" applies to this one run only (no setting is changed).
setlocal
set "S=%~dp0update_from_host.ps1"
if not exist "%S%" set "S=%~dp0lan_fix\update_from_host.ps1"
if not exist "%S%" (
  echo update_from_host.ps1 not found next to this file or in lan_fix.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%S%" %*
pause
