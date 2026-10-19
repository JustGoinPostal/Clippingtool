param(
  [string]$Version = "0.9.0-beta",
  [string]$ReleaseTag = ""
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
if (-not $ReleaseTag) { $ReleaseTag = "v$Version" }
$requireSigning = $env:POSTAL_REQUIRE_SIGNING -eq '1'

Write-Host "== Postal AutoClip Windows beta build ==" -ForegroundColor Cyan
python -m pip install --upgrade pip wheel
python -m pip install -e ".[dev,build]"

$ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source
$ffprobe = (Get-Command ffprobe -ErrorAction Stop).Source
Write-Host "Bundling FFmpeg: $ffmpeg"
Write-Host "Bundling FFprobe: $ffprobe"

Remove-Item -Recurse -Force .\build\pyinstaller -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\build\pyinstaller-updater -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\dist\PostalAutoClip -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force .\dist\Updater -ErrorAction SilentlyContinue

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
  '--hidden-import', 'app.updater',
  '--hidden-import', 'app.updater_runner',
  '--hidden-import', 'packaging.version',
  '--collect-all', 'uvicorn',
  '--collect-all', 'faster_whisper',
  '--collect-all', 'ctranslate2',
  '--collect-all', 'av',
  '--collect-all', 'googleapiclient',
  '--collect-all', 'google_auth_oauthlib',
  '.\desktop_entry.py'
)
python -m PyInstaller @pyi
if ($LASTEXITCODE -ne 0) { throw "PostalAutoClip PyInstaller build failed with exit code $LASTEXITCODE" }

$updaterPyi = @(
  '--noconfirm', '--clean', '--onefile', '--windowed',
  '--name', 'PostalAutoClipUpdater',
  '--distpath', '.\dist\Updater',
  '--workpath', '.\build\pyinstaller-updater',
  '--specpath', '.\build',
  '--hidden-import', 'app.updater',
  '--hidden-import', 'app.paths',
  '--hidden-import', 'packaging.version',
  '.\updater_entry.py'
)
python -m PyInstaller @updaterPyi
if ($LASTEXITCODE -ne 0) { throw "PostalAutoClipUpdater PyInstaller build failed with exit code $LASTEXITCODE" }
Copy-Item '.\dist\Updater\PostalAutoClipUpdater.exe' '.\dist\PostalAutoClip\PostalAutoClipUpdater.exe' -Force

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

& '.\scripts\sign_windows.ps1' -Files @(
  '.\dist\PostalAutoClip\PostalAutoClip.exe',
  '.\dist\PostalAutoClip\PostalAutoClipUpdater.exe'
) -RequireSigning:$requireSigning

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
  foreach ($candidate in @(
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
  )) {
    if (Test-Path $candidate) { $iscc = Get-Item $candidate; break }
  }
}
if (-not $iscc) { throw 'Inno Setup compiler (ISCC.exe) was not found.' }

New-Item -ItemType Directory -Force '.\installer\output' | Out-Null
$compileArgs = @("/DAppVersion=$Version")
if ($requireSigning) {
  $bridge = (Resolve-Path '.\scripts\inno_sign_file.ps1').Path
  # Keep certificate/password out of the compiler command line. Inno receives a
  # fixed bridge command; the bridge reads protected CI/release environment vars.
  $innoSignCommand = 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $q' + $bridge + '$q $f'
  $compileArgs += '/DSignInstaller'
  $compileArgs += "--signtool=PostalSign=$innoSignCommand"
}
$compileArgs += '.\installer\PostalAutoClip.iss'
& $iscc.Source @compileArgs
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compiler failed with exit code $LASTEXITCODE" }
$installer = (Resolve-Path '.\installer\output\PostalAutoClip-Beta-Setup.exe').Path

# In signed builds Inno signs Setup plus the generated uninstaller through the
# configured SignTool. Unsigned local developer builds remain supported.
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLowerInvariant()
$signature = Get-AuthenticodeSignature -LiteralPath $installer
$subject = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { '' }
if ($requireSigning -and ($signature.Status -ne 'Valid' -or -not $subject)) {
  throw "Release signing was required but final installer signature is not valid: $($signature.Status)"
}
$assetName = 'PostalAutoClip-Beta-Setup.exe'
$base = "https://github.com/JustGoinPostal/Clippingtool/releases/download/$ReleaseTag"
$manifest = [ordered]@{
  schema_version = 1
  version = $Version
  channel = 'beta'
  installer_url = "$base/$assetName"
  sha256 = $hash
  signer_subject = $subject
  release_notes_url = "https://github.com/JustGoinPostal/Clippingtool/releases/tag/$ReleaseTag"
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content '.\installer\output\postal-autoclip-update.json' -Encoding UTF8

Write-Host "Installer ready: $installer" -ForegroundColor Green
Write-Host "SHA256: $hash" -ForegroundColor Green
Write-Host "Signer: $subject" -ForegroundColor Green
