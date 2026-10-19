@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo Postal AutoClip RuneLite Companion - Private Launcher
echo ====================================================

echo Checking Java...
where java >nul 2>nul
if errorlevel 1 (
  echo.
  echo Java was not found on PATH.
  echo Install Eclipse Temurin JDK 11, then run this file again.
  echo.
  pause
  exit /b 1
)

if not exist "build-local.ps1" (
  echo.
  echo build-local.ps1 was not found.
  echo Run git pull in C:\PostalAutoClip and try again.
  echo.
  pause
  exit /b 1
)

echo.
echo Checking the private companion build...
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0build-local.ps1"
if errorlevel 1 (
  echo.
  echo The local RuneLite companion build failed.
  echo Scroll up for the Gradle error, or send that output to ChatGPT.
  echo.
  pause
  exit /b 1
)

set "JAR="
for %%F in (PostalAutoClipCompanion-*-all.jar) do set "JAR=%%F"
if not defined JAR (
  for %%F in (build\libs\PostalAutoClipCompanion-*-all.jar) do set "JAR=%%F"
)

if not defined JAR (
  echo.
  echo Build finished but no PostalAutoClipCompanion-*-all.jar was found.
  echo Send this window output to ChatGPT.
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
echo Press any key to launch the private RuneLite development client...
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
