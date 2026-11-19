[CmdletBinding()]
param(
    [switch]$AddToUserPath,
    [switch]$InstallVsix
)

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$sqliteDir = Join-Path $root "vendor\sqlite"
$sqliteExe = Join-Path $sqliteDir "sqlite3.exe"

if (-not (Test-Path $sqliteExe)) {
    throw "Missing $sqliteExe"
}

Write-Host "SQLite: $(& $sqliteExe --version)"
Write-Host "Path:   $sqliteExe"

if ($AddToUserPath) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$sqliteDir*") {
        [Environment]::SetEnvironmentVariable("Path", "$userPath;$sqliteDir", "User")
        Write-Host "Added to user PATH (open a new shell to use it): $sqliteDir"
    } else {
        Write-Host "Already on user PATH: $sqliteDir"
    }
}

if ($InstallVsix) {
    $vsix = Get-ChildItem (Join-Path $root "vendor\vscode") -Filter "*.vsix" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $vsix) {
        Write-Host "No .vsix found."
        Write-Host "Run: powershell -ExecutionPolicy Bypass -File scripts\fetch-vscode-sqlite-viewer.ps1"
        exit 1
    }
    $code = Get-Command code -ErrorAction SilentlyContinue
    if (-not $code) {
        throw "VS Code 'code' command not found on PATH."
    }
    & code --install-extension $vsix.FullName
    Write-Host "Installed: $($vsix.Name)"
}
