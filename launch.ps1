$ErrorActionPreference = 'Stop'
if (-not (Test-Path .\.venv\Scripts\python.exe)) { throw "Run .\install.ps1 first." }
& .\.venv\Scripts\python.exe -m app.desktop
