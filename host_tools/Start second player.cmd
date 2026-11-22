@echo off
rem Second player on this PC (lan_fix\second_player.py). Start the first game with the launcher first.
rem The host must run "Host a match (4 players).cmd". Works from the package folder or from lan_fix.
setlocal
set "S=%~dp0second_player.py"
if not exist "%S%" set "S=%~dp0lan_fix\second_player.py"
rem N11: "where python" also finds Windows' Store shortcut when no Python is installed.
set "PY="
python -c "import sys; sys.exit(sys.version_info < (3, 8))" >nul 2>nul && set "PY=python"
if not defined PY (
  py -3 -c "import sys; sys.exit(sys.version_info < (3, 8))" >nul 2>nul && set "PY=py -3"
)
if not defined PY goto nopython
%PY% "%S%" %*
pause
exit /b
:nopython
rem No Python: the launcher's own Python runs the script (messages come as small windows).
set "L=%~dp0Play.Duskbloods.exe"
if not exist "%L%" set "L=%~dp0..\Play.Duskbloods.exe"
"%L%" --run-script "%S%" %*
