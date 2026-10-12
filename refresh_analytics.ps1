$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Virtual environment not found. Run .\install.ps1 first." }
& $python -m app.analytics --refresh
Start-Process "http://127.0.0.1:8787/static/analytics.html"
