param(
  [string]$Version = "0.9.0-beta"
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "== Postal AutoClip Windows beta build ==" -ForegroundColor Cyan
python -m pip install --upgrade pip wheel
python -m pip install -e ".[dev,build]"

$ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source
$ffprobe = (Get-Command ffprobe -ErrorAction Stop).Source
Write-Host "Bundling FFmpeg: $ffmpeg"
Write-Host "Bundling FFprobe: $ffprobe"

Remove-Item -Recurse -Force .\build\pyinstaller -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\dist\PostalAutoClip -ErrorAction SilentlyContinue

$pyi = @(
  '--noconfirm', '--clean', '--onedir', '--windowed',
  '--name', 'PostalAutoClip',
  '--distpath', '.\dist',
  '--workpath', '.\build\pyinstaller',
  '--specpath', '.\build',
  '--add-data', 'app\static;app\static',
  '--add-data', 'config.example.json;.',
  '--add-data', 'benchmarks\corpus.example.json;benchmarks',
  '--add-data', 'references\osrs_public_metadata_seeds.json;references',
  '--add-binary', "$ffmpeg;tools",
  '--add-binary', "$ffprobe;tools",
  '--collect-all', 'uvicorn',
  '--collect-all', 'faster_whisper',
  '--collect-all', 'ctranslate2',
  '--collect-all', 'av',
  '--collect-all', 'googleapiclient',
  '--collect-all', 'google_auth_oauthlib',
  '.\desktop_entry.py'
)
python -m PyInstaller @pyi

$rl = Get-ChildItem '.\runelite-companion\build\libs\PostalAutoClipCompanion-*-all.jar' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($rl) {
  New-Item -ItemType Directory -Force '.\dist\PostalAutoClip\RuneLite' | Out-Null
  Copy-Item $rl.FullName '.\dist\PostalAutoClip\RuneLite\PostalAutoClipCompanion.jar'
  Copy-Item '.\runelite-companion\LIVE_TEST.md' '.\dist\PostalAutoClip\RuneLite\LIVE_TEST.md' -ErrorAction SilentlyContinue
}

@"
Postal AutoClip Beta
Version: $Version
Built: $(Get-Date -Format o)
Persistent data: %LOCALAPPDATA%\PostalAutoClip
"@ | Set-Content '.\dist\PostalAutoClip\BUILD_INFO.txt' -Encoding UTF8

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
  foreach ($candidate in @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
  )) {
    if (Test-Path $candidate) { $iscc = Get-Item $candidate; break }
  }
}
if (-not $iscc) { throw 'Inno Setup 6 compiler (ISCC.exe) was not found.' }

New-Item -ItemType Directory -Force '.\installer\output' | Out-Null
& $iscc.Source "/DAppVersion=$Version" '.\installer\PostalAutoClip.iss'
$installer = Resolve-Path '.\installer\output\PostalAutoClip-Beta-Setup.exe'
Write-Host "Installer ready: $installer" -ForegroundColor Green
