@echo off
setlocal EnableExtensions
cd /d "%~dp0runelite-companion"
if not exist "run-windows.bat" (
  echo RuneLite companion launcher was not found.
  pause
  exit /b 1
)
call "run-windows.bat"
