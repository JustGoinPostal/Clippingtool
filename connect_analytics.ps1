$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Virtual environment not found. Run .\install.ps1 first." }
& $python -m app.analytics --connect-youtube
Write-Host "YouTube analytics authorization complete." -ForegroundColor Green
Write-Host "TikTok analytics also requires video.list on your TikTok user access token." -ForegroundColor Yellow
