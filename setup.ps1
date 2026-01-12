# OpenAgent Setup Script (Windows)
# Creates virtual environment and installs dependencies

$ErrorActionPreference = "Stop"

Write-Host "Setting up OpenAgent..." -ForegroundColor Cyan

# Check Python version
$pythonCmd = $null
foreach ($cmd in @("python3", "python")) {
    try {
        $version = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($version) {
            $parts = $version.Split('.')
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 11) {
                $pythonCmd = $cmd
                break
            }
        }
    } catch {}
}

if (-not $pythonCmd) {
    Write-Host "Python 3.11+ is required but not found" -ForegroundColor Red
    exit 1
}

Write-Host "Using $pythonCmd" -ForegroundColor Green

# Create virtual environment if it doesn't exist
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    & $pythonCmd -m venv .venv
} else {
    Write-Host "Virtual environment already exists" -ForegroundColor Yellow
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# Upgrade pip
Write-Host "Upgrading pip..." -ForegroundColor Yellow
pip install --upgrade pip --quiet

# Install the package in editable mode with dev dependencies
Write-Host "Installing OpenAgent and dependencies..." -ForegroundColor Yellow
pip install -e ".[dev]" --quiet

# Check if Rust/Cargo is available for TUI
if (Get-Command cargo -ErrorAction SilentlyContinue) {
    Write-Host "Rust found, building TUI..." -ForegroundColor Yellow
    Push-Location TUI
    cargo build --release --quiet
    Pop-Location
    Write-Host "TUI built successfully" -ForegroundColor Green
} else {
    Write-Host "Rust not found - TUI will not be built" -ForegroundColor Yellow
    Write-Host "Install Rust from https://rustup.rs/ to build the TUI" -ForegroundColor Yellow
}

# Create .env from example if it doesn't exist
if (-not (Test-Path ".env") -and (Test-Path ".env.example")) {
    Write-Host "Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host "Please edit .env with your Azure OpenAI credentials" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "To activate the environment:"
Write-Host "  .\.venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "To run OpenAgent:"
Write-Host "  .\run.ps1"
Write-Host ""
Write-Host "To run in offline mode (no backend):"
Write-Host "  .\run.ps1 -Offline"
