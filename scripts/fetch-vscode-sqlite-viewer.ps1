[CmdletBinding()]
param(
    [string]$Version = "26.9.1",
    [string]$OutDir = (Join-Path $PSScriptRoot "..\vendor\vscode")
)

$ErrorActionPreference = "Stop"
$url = "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/qwtel/vsextensions/sqlite-viewer/$Version/vspackage"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$out = Join-Path $OutDir "sqlite-viewer-$Version.vsix"

Write-Host "Downloading SQLite Viewer $Version"
Write-Host "  from $url"
Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing -TimeoutSec 600

$bytes = [System.IO.File]::ReadAllBytes($out)[0..3]
if (-not ($bytes[0] -eq 0x50 -and $bytes[1] -eq 0x4B)) {
    throw "Downloaded file is not a VSIX/ZIP: $out"
}

$hash = (Get-FileHash $out -Algorithm SHA256).Hash.ToLower()
Write-Host ""
Write-Host "Saved:  $out"
Write-Host "SHA256: $hash"
Write-Host ""
Write-Host "Install:"
Write-Host "  code --install-extension `"$out`""
Write-Host ""
Write-Host "Note: the publisher forbids redistribution. Do not commit the .vsix."
