@echo off
rem Build Lichii (duskbloods branch) from src\lichii into build\lichii with MSVC + Ninja.
rem Usage: tools\build.cmd            -> configure (first time) + build
rem        tools\build.cmd reconfigure -> force a fresh CMake configure
setlocal
set "WS=%~dp0.."
for %%I in ("%WS%") do set "WS=%%~fI"
set "SRC=%WS%\src\lichii"
set "OUT=%WS%\build\lichii"
set "QT=%WS%\toolchain\Qt\6.8.3\msvc2022_64"
set "GLSLANG=%WS%\toolchain\glslang\bin\glslang.exe"
for /f "delims=" %%P in ('python -c "import cmake;print(cmake.CMAKE_BIN_DIR)"') do set "CMAKE_DIR=%%P"
for /f "delims=" %%P in ('python -c "import ninja;print(ninja.BIN_DIR)"') do set "NINJA_DIR=%%P"
set "PATH=%CMAKE_DIR%;%NINJA_DIR%;%QT%\bin;%PATH%"

call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || (echo vcvars64 failed & exit /b 1)

if /i "%~1"=="reconfigure" if exist "%OUT%\CMakeCache.txt" del "%OUT%\CMakeCache.txt"
if not exist "%OUT%\CMakeCache.txt" (
  cmake -S "%SRC%" -B "%OUT%" -G Ninja ^
    -DCMAKE_BUILD_TYPE=RelWithDebInfo ^
    -DBUILD_TESTING=OFF -DYUZU_TESTS=OFF -DYUZU_CMD=ON ^
    -DYUZU_ROOM=OFF -DYUZU_ROOM_STANDALONE=OFF ^
    -DYUZU_USE_BUNDLED_QT=OFF -DYUZU_USE_BUNDLED_SDL3=ON ^
    -DENABLE_UPDATE_CHECKER=OFF -DUSE_DISCORD_PRESENCE=OFF ^
    -DLICHII_BUILD_TAG=duskbloods-local -DLICHII_BUILD_PLATFORM=windows-x86_64 ^
    "-DCMAKE_PREFIX_PATH=%QT%" "-DGLSLANGVALIDATOR=%GLSLANG%" ^
    "-DCPM_SOURCE_CACHE=%WS%\toolchain\cpm-cache" || exit /b 1
)
cmake --build "%OUT%" --parallel -- -k 0 || exit /b 1
echo.
echo BUILD OK: %OUT%\bin
