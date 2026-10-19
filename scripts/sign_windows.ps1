param(
  [Parameter(Mandatory=$true)][string[]]$Files,
  [switch]$RequireSigning
)

$ErrorActionPreference = 'Stop'

function Find-SignTool {
  $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  $roots = @(
    "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
    "$env:ProgramFiles\Windows Kits\10\bin"
  ) | Where-Object { $_ -and (Test-Path $_) }
  foreach ($root in $roots) {
    $candidate = Get-ChildItem -Path $root -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
      Sort-Object FullName -Descending |
      Select-Object -First 1
    if ($candidate) { return $candidate.FullName }
  }
  throw 'signtool.exe was not found. Install the Windows SDK signing tools.'
}

$pfx = $env:POSTAL_CODESIGN_PFX
$password = $env:POSTAL_CODESIGN_PASSWORD
if (-not $pfx -or -not (Test-Path $pfx)) {
  if ($RequireSigning) { throw 'Code signing is required but POSTAL_CODESIGN_PFX is not configured.' }
  Write-Host 'Code signing credentials are not configured; leaving local developer artifacts unsigned.' -ForegroundColor Yellow
  exit 0
}
if ($null -eq $password) { throw 'POSTAL_CODESIGN_PASSWORD is required when POSTAL_CODESIGN_PFX is configured.' }

$signtool = Find-SignTool
$timestamp = $env:POSTAL_CODESIGN_TIMESTAMP_URL
$skipTimestamp = $env:POSTAL_CODESIGN_SKIP_TIMESTAMP -eq '1'
if (-not $skipTimestamp -and -not $timestamp) {
  throw 'POSTAL_CODESIGN_TIMESTAMP_URL is required for production signing. RFC 3161 timestamping is mandatory for release builds.'
}

foreach ($file in $Files) {
  $resolved = (Resolve-Path $file).Path
  $args = @('sign','/fd','SHA256','/f',$pfx,'/p',$password)
  if (-not $skipTimestamp) {
    $args += @('/tr',$timestamp,'/td','SHA256')
  }
  $args += $resolved
  & $signtool @args
  if ($LASTEXITCODE -ne 0) { throw "SignTool failed for $resolved with exit code $LASTEXITCODE" }

  & $signtool verify /pa /all $resolved
  if ($LASTEXITCODE -ne 0) { throw "Authenticode verification failed for $resolved" }

  $signature = Get-AuthenticodeSignature -LiteralPath $resolved
  if ($signature.Status -ne 'Valid') {
    throw "PowerShell Authenticode verification failed for $resolved: $($signature.Status)"
  }
  Write-Host "SIGNED: $resolved :: $($signature.SignerCertificate.Subject)" -ForegroundColor Green
}
