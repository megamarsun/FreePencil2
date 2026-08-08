@echo off
rem Resolve Blender executable path. Sets BLENDER_EXE or leaves it empty.
rem Search order:
rem   1. BLENDER_EXE already set and exists
rem   2. Desktop shortcut "blender4.5.lnk" target
rem   3. Common install locations

if defined BLENDER_EXE if exist "%BLENDER_EXE%" exit /b 0
set "BLENDER_EXE="

for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command ^
  "$d=[Environment]::GetFolderPath('Desktop'); $s=Get-ChildItem -Path $d -Filter 'blender*4.5*.lnk' -ErrorAction SilentlyContinue | Select-Object -First 1; if($s){(New-Object -ComObject WScript.Shell).CreateShortcut($s.FullName).TargetPath}"`) do set "BLENDER_EXE=%%i"
if defined BLENDER_EXE if exist "%BLENDER_EXE%" exit /b 0
set "BLENDER_EXE="

for %%p in (
  "C:\blender\blender-4.5.2-windows-x64\blender.exe"
  "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
  "D:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
) do (
  if not defined BLENDER_EXE if exist "%%~p" set "BLENDER_EXE=%%~p"
)
if not defined BLENDER_EXE (
  for /d %%d in ("C:\blender\blender-4.5*") do (
    if exist "%%d\blender.exe" set "BLENDER_EXE=%%d\blender.exe"
  )
)
exit /b 0
