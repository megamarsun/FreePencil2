@echo off
rem FreePencil smoke tests (headless, no external assets)
rem Usage: run_tests.bat [assets]
rem   assets : also run tests_assets.py (car/human/robot, BlenderKit cache)
setlocal
set "HERE=%~dp0"
if not exist "%HERE%out" mkdir "%HERE%out"

call "%HERE%_find_blender.cmd"
if not defined BLENDER_EXE (
  echo ERROR: Blender 4.5 executable not found. Edit _find_blender.cmd > "%HERE%out\tests.log"
  type "%HERE%out\tests.log"
  exit /b 1
)
echo using: %BLENDER_EXE% > "%HERE%out\tests.log"
"%BLENDER_EXE%" -b --factory-startup -P "%HERE%tests_smoke.py" >> "%HERE%out\tests.log" 2>&1
set "RC=%ERRORLEVEL%"

if /i "%~1"=="assets" (
  "%BLENDER_EXE%" -b --factory-startup -P "%HERE%tests_assets.py" >> "%HERE%out\tests.log" 2>&1
  if errorlevel 1 set "RC=1"
)
type "%HERE%out\tests.log"
exit /b %RC%
