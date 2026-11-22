@echo off
rem Compile one object (default: dusk_lan.cpp) without linking, so bin\ stays as it is.
rem Usage: tools\compile_check.cmd [ninja-target]
setlocal
set "WS=%~dp0.."
for %%I in ("%WS%") do set "WS=%%~fI"
set "OUT=%WS%\build\lichii"
set "QT=%WS%\toolchain\Qt\6.8.3\msvc2022_64"
for /f "delims=" %%P in ('python -c "import cmake;print(cmake.CMAKE_BIN_DIR)"') do set "CMAKE_DIR=%%P"
for /f "delims=" %%P in ('python -c "import ninja;print(ninja.BIN_DIR)"') do set "NINJA_DIR=%%P"
set "PATH=%CMAKE_DIR%;%NINJA_DIR%;%QT%\bin;%PATH%"
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || (echo vcvars64 failed & exit /b 1)
set "T=%~1"
if "%T%"=="" set "T=src/core/CMakeFiles/core.dir/dusk_lan.cpp.obj"
ninja -C "%OUT%" "%T%" || exit /b 1
echo COMPILE OK: %T%
