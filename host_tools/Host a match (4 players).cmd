@echo off
rem Host a LAN match where PCs may run a second player (lan_fix\host_plus.py, then lan_fix_host.py).
rem Use it instead of "Host a match (v3.9).cmd". Works from the package folder or from lan_fix.
setlocal
set "S=%~dp0host_plus.py"
if not exist "%S%" set "S=%~dp0lan_fix\host_plus.py"
rem N11: "where python" also finds Windows' Store shortcut (WindowsApps\python.exe) when no Python
rem is installed; only a real start of Python counts. "py -3" (python.org's launcher) also counts.
set "PY="
python -c "import sys; sys.exit(sys.version_info < (3, 8))" >nul 2>nul && set "PY=python"
if not defined PY (
  py -3 -c "import sys; sys.exit(sys.version_info < (3, 8))" >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  echo Python 3 is needed to host. Install it from python.org and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
%PY% "%S%"
if errorlevel 1 pause
