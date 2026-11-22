@echo off
rem Talk to the running game's debug server (EDEN_NX2_DEBUG_SERVER in %APPDATA%\eden\nx2_switches.txt).
rem Example: tools\dbg.cmd "{\"method\":\"status\"}"
python -I "%~dp0..\src\lichii\tools\nx2\debug_mcp.py" --server 127.0.0.1:6545 --call %*
