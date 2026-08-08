@echo off
rem Sync the repo addon files into the installed Blender extension.
rem Run after editing addon code so the GUI Blender picks up changes
rem on next restart. ASCII only (cp932-safe).
rem
rem Usage: sync_extension.bat [blender_version]
rem   sync_extension.bat        -> 4.5 (default)
rem   sync_extension.bat 5.2    -> 5.2
rem
rem A Blender install under C:\blender\blender-<ver>.*-windows-x64 that has a
rem "portable" folder ignores %APPDATA% entirely, so that copy is the one that
rem actually loads. Prefer it when present.

setlocal enabledelayedexpansion
set REPO=%~dp0..
set VER=%~1
if "%VER%"=="" set VER=4.5

set EXT=
for /d %%D in ("C:\blender\blender-%VER%*-windows-x64") do (
  if exist "%%D\portable\" set EXT=%%D\portable\extensions\user_default\freepencil2
)
if "%EXT%"=="" set EXT=%APPDATA%\Blender Foundation\Blender\%VER%\extensions\user_default\freepencil2

if not exist "%EXT%" (
  echo [sync] extension dir not found: %EXT%
  echo [sync] creating it (first install for Blender %VER%)
  mkdir "%EXT%" 2>nul
)
if not exist "%EXT%\external_resources" mkdir "%EXT%\external_resources"
if not exist "%EXT%\locale" mkdir "%EXT%\locale"

copy /Y "%REPO%\*.py" "%EXT%\" >nul
copy /Y "%REPO%\blender_manifest.toml" "%EXT%\" >nul
copy /Y "%REPO%\external_resources\*.py" "%EXT%\external_resources\" >nul
copy /Y "%REPO%\locale\*.po" "%EXT%\locale\" >nul
if exist "%EXT%\__pycache__" rmdir /S /Q "%EXT%\__pycache__"
if exist "%EXT%\external_resources\__pycache__" rmdir /S /Q "%EXT%\external_resources\__pycache__"

echo [sync] done: %EXT%
echo [sync] restart Blender to reload the addon.
