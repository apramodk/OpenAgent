# OpenAgent TUI launcher for Windows
param(
    [switch]$Offline,
    [switch]$Rebuild,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$TuiBin = Join-Path $ScriptDir "TUI\target\release\openagent-tui.exe"

if ($Help) {
    Write-Host "Usage: .\run.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Offline    Run without Python backend (mock responses)"
    Write-Host "  -Rebuild    Rebuild TUI before running"
    Write-Host "  -Help       Show this help message"
    exit 0
}

# Check if TUI needs to be built
if ($Rebuild -or -not (Test-Path $TuiBin)) {
    Write-Host "Building TUI..."
    Push-Location (Join-Path $ScriptDir "TUI")
    cargo build --release
    Pop-Location
}

# Build arguments
$Args = @()
if ($Offline) {
    $Args += "--offline"
}

# Activate virtual environment for Python backend
if (-not $Offline) {
    $VenvActivate = Join-Path $ScriptDir ".venv\Scripts\Activate.ps1"
    if (Test-Path $VenvActivate) {
        & $VenvActivate
    } else {
        Write-Host "Warning: Python venv not found, running in offline mode"
        $Args += "--offline"
    }
    $env:PYTHONPATH = "$ScriptDir;$env:PYTHONPATH"
}

# Run TUI
Push-Location $ScriptDir
& $TuiBin @Args
Pop-Location
