@echo off
rem FreePencil batch evaluation pipeline
rem Usage: run_batch.bat [limit] [extra run_batch.py args...]
setlocal
set "HERE=%~dp0"
if not exist "%HERE%out" mkdir "%HERE%out"

call "%HERE%_find_blender.cmd"
if not defined BLENDER_EXE (
  echo ERROR: Blender 4.5 executable not found. Edit _find_blender.cmd
  exit /b 1
)

rem use Blender's bundled python for the driver (host python not required)
set "BLENDER_PY="
for %%i in ("%BLENDER_EXE%") do set "BLENDER_DIR=%%~dpi"
for /d %%v in ("%BLENDER_DIR%*") do (
  if exist "%%v\python\bin\python.exe" set "BLENDER_PY=%%v\python\bin\python.exe"
)
if not defined BLENDER_PY (
  echo ERROR: bundled python not found under %BLENDER_DIR%
  exit /b 1
)

set "LIMIT=%~1"
if "%LIMIT%"=="" set "LIMIT=100"
if not "%~1"=="" shift

"%BLENDER_PY%" "%HERE%run_batch.py" --limit %LIMIT% --blender "%BLENDER_EXE%" %1 %2 %3 %4 %5 %6 %7 %8 > "%HERE%out\batch.log" 2>&1
set "RC=%ERRORLEVEL%"
type "%HERE%out\batch.log"
exit /b %RC%
