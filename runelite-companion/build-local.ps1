$ErrorActionPreference = 'Stop'

$GradleVersion = '8.14.3'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ToolRoot = Join-Path $env:LOCALAPPDATA 'PostalAutoClip\tools'
$GradleHome = Join-Path $ToolRoot ("gradle-" + $GradleVersion)
$GradleBat = Join-Path $GradleHome 'bin\gradle.bat'
$ZipPath = Join-Path $ToolRoot ("gradle-" + $GradleVersion + '-bin.zip')
$ShaPath = $ZipPath + '.sha256'
$GradleUrl = "https://services.gradle.org/distributions/gradle-$GradleVersion-bin.zip"
$ShaUrl = $GradleUrl + '.sha256'
$OutputPattern = Join-Path $ProjectDir 'build\libs\PostalAutoClipCompanion-*-all.jar'

Write-Host ''
Write-Host 'Postal AutoClip RuneLite Companion - Local Build'
Write-Host '================================================='
Write-Host "Project: $ProjectDir"

if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    throw 'Java was not found on PATH. Install Eclipse Temurin JDK 11 first.'
}

if (-not (Get-Command javac -ErrorAction SilentlyContinue)) {
    throw 'javac was not found on PATH. Install the full Eclipse Temurin JDK 11, not only a JRE.'
}

if (-not (Test-Path $GradleBat)) {
    New-Item -ItemType Directory -Force -Path $ToolRoot | Out-Null

    Write-Host "Downloading Gradle $GradleVersion from the official Gradle distribution service..."
    Invoke-WebRequest -Uri $GradleUrl -OutFile $ZipPath -UseBasicParsing
    Invoke-WebRequest -Uri $ShaUrl -OutFile $ShaPath -UseBasicParsing

    $expected = ((Get-Content $ShaPath -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
    $actual = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $expected) {
        Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue
        Remove-Item $ShaPath -Force -ErrorAction SilentlyContinue
        throw "Gradle download SHA-256 verification failed. Expected $expected but got $actual."
    }

    Write-Host 'Checksum verified. Extracting Gradle...'
    Expand-Archive -Path $ZipPath -DestinationPath $ToolRoot -Force
    Remove-Item $ZipPath -Force -ErrorAction SilentlyContinue
    Remove-Item $ShaPath -Force -ErrorAction SilentlyContinue
}

if (-not (Test-Path $GradleBat)) {
    throw "Gradle launcher was not found after extraction: $GradleBat"
}

Write-Host ''
Write-Host 'Building against the current RuneLite API...'
& $GradleBat -p $ProjectDir clean testClasses shadowJar --no-daemon
if ($LASTEXITCODE -ne 0) {
    throw "Gradle build failed with exit code $LASTEXITCODE."
}

$jar = Get-ChildItem -Path $OutputPattern -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $jar) {
    throw 'Gradle completed, but the PostalAutoClipCompanion-*-all.jar output was not found.'
}

$destination = Join-Path $ProjectDir $jar.Name
Copy-Item -Path $jar.FullName -Destination $destination -Force

Write-Host ''
Write-Host "Private companion built successfully: $destination"
Write-Host 'The JAR stays local on this PC and is not published to the RuneLite Plugin Hub.'
Write-Host ''
