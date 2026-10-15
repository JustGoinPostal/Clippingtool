@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo Postal AutoClip RuneLite Companion - Live Test Launcher
echo ======================================================

echo Checking Java...
where java >nul 2>nul
if errorlevel 1 (
  echo.
  echo Java was not found on PATH.
  echo Install Eclipse Temurin JDK 11, then run this file again.
  echo RuneLite plugin development currently targets Java 11.
  echo.
  pause
  exit /b 1
)

set "JAR="
for %%F in (PostalAutoClipCompanion-*-all.jar) do set "JAR=%%F"
if not defined JAR (
  echo.
  echo Could not find PostalAutoClipCompanion-*-all.jar in this folder.
  echo Download/extract the complete RuneLite companion artifact from GitHub Actions.
  echo.
  pause
  exit /b 1
)

echo Found %JAR%
echo.
echo IMPORTANT FOR JAGEX ACCOUNTS:
echo  1. Use RuneLite ^(configure^) and add --insecure-write-credentials to Client arguments.
echo  2. Launch normal RuneLite once through Jagex Launcher so RuneLite writes its temporary dev credentials.
echo  3. Close that RuneLite client, then return here.
echo  4. Never share %%USERPROFILE%%\.runelite\credentials.properties.
echo.
echo Start Postal AutoClip before logging in so the bridge heartbeat appears immediately.
echo Press any key to launch the RuneLite development client...
pause >nul

java -ea -jar "%JAR%" --developer-mode --debug
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" echo RuneLite exited with code %RC%.
echo When testing is complete, remove --insecure-write-credentials from RuneLite configure.
echo You may also delete %%USERPROFILE%%\.runelite\credentials.properties after development testing.
echo.
pause
exit /b %RC%
