$ErrorActionPreference = 'Stop'
if (-not (Test-Path .\.venv\Scripts\python.exe)) { throw "Run .\install.ps1 first." }
Start-Process "http://127.0.0.1:8787"
& .\.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8787
