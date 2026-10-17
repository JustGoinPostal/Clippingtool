@echo off
setlocal
cd /d "%~dp0"
title Postal AutoClip

echo Starting Postal AutoClip...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch.ps1"

set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo Postal AutoClip exited with code %EXITCODE%.
  echo Press any key to close this window.
  pause >nul
)

endlocal
