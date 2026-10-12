$ErrorActionPreference = 'Stop'
Write-Host "== Postal AutoClip installer ==" -ForegroundColor Cyan
$py = $null
foreach ($cmd in @('py -3.12','py -3.11')) {
  try { Invoke-Expression "$cmd --version" | Out-Null; $py=$cmd; break } catch {}
}
if (-not $py) { throw "Install Python 3.11 or 3.12 first: winget install Python.Python.3.12" }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  Write-Host "FFmpeg not found. Trying winget..."
  winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements
  Write-Host "If FFmpeg was just installed, reopen PowerShell once before launch.ps1."
}
Invoke-Expression "$py -m venv .venv"
& .\.venv\Scripts\python.exe -m pip install --upgrade pip wheel
& .\.venv\Scripts\python.exe -m pip install -e .
if (-not (Test-Path config.json)) { Copy-Item config.example.json config.json }
Write-Host "Installed. Run .\launch.ps1" -ForegroundColor Green
