@echo off
rem RELEASE build of the upstream merge (src\lichii-merge) for sharing outside: same settings as
rem tools\build_merge.cmd, plus two switches that keep this PC's folder names out of the program:
rem   /d1trimfile:<workspace>\   source file names in messages become relative (no user folder name)
rem   /PDBALTPATH:%%_PDB%%        the program stores only the name of its debug file, not its full path
rem Its own build folder (build\lichii-merge-rel), so the test build in build\lichii-merge stays as it is.
rem Usage: tools\build_merge_release.cmd
setlocal
set "WS=%~dp0.."
for %%I in ("%WS%") do set "WS=%%~fI"
set "SRC=%WS%\src\lichii-merge"
set "OUT=%WS%\build\lichii-merge-rel"
set "QT=%WS%\toolchain\Qt\6.8.3\msvc2022_64"
set "GLSLANG=%WS%\toolchain\glslang\bin\glslang.exe"
for /f "delims=" %%P in ('python -c "import cmake;print(cmake.CMAKE_BIN_DIR)"') do set "CMAKE_DIR=%%P"
for /f "delims=" %%P in ('python -c "import ninja;print(ninja.BIN_DIR)"') do set "NINJA_DIR=%%P"
set "PATH=%CMAKE_DIR%;%NINJA_DIR%;%QT%\bin;%PATH%"

call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul || (echo vcvars64 failed & exit /b 1)

if not exist "%OUT%\CMakeCache.txt" (
  cmake -S "%SRC%" -B "%OUT%" -G Ninja ^
    -DCMAKE_BUILD_TYPE=RelWithDebInfo ^
    -DBUILD_TESTING=OFF -DYUZU_TESTS=OFF -DYUZU_CMD=ON ^
    -DYUZU_ROOM=OFF -DYUZU_ROOM_STANDALONE=OFF ^
    -DYUZU_USE_BUNDLED_QT=OFF -DYUZU_USE_BUNDLED_SDL3=ON ^
    -DENABLE_UPDATE_CHECKER=OFF -DUSE_DISCORD_PRESENCE=OFF ^
    -DLICHII_BUILD_TAG=duskbloods-merge -DLICHII_BUILD_PLATFORM=windows-x86_64 ^
    "-DCMAKE_C_FLAGS=/d1trimfile:%WS%\\" "-DCMAKE_CXX_FLAGS=/EHsc /d1trimfile:%WS%\\" ^
    "-DCMAKE_EXE_LINKER_FLAGS=/PDBALTPATH:%%_PDB%%" "-DCMAKE_SHARED_LINKER_FLAGS=/PDBALTPATH:%%_PDB%%" ^
    "-DCMAKE_PREFIX_PATH=%QT%" "-DGLSLANGVALIDATOR=%GLSLANG%" ^
    "-DCPM_SOURCE_CACHE=%WS%\toolchain\cpm-cache" || exit /b 1
)
cmake --build "%OUT%" --parallel -- -k 0 || exit /b 1
echo.
echo BUILD OK: %OUT%\bin
