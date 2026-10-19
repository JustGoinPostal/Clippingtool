param(
  [Parameter(Mandatory=$true, Position=0)][string]$File
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
& (Join-Path $root 'scripts\sign_windows.ps1') -Files @($File) -RequireSigning
