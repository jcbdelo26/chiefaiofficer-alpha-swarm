# CAIO RevOps Swarm - Local Start Script (Windows PowerShell)
# Run this script to start the entire system locally

param(
    [switch]$DashboardOnly,
    [switch]$SkipVenv
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  CAIO RevOps Swarm - Local Startup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
Write-Host "[1/5] Checking Python..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Python not found. Please install Python 3.11+" -ForegroundColor Red
    exit 1
}
Write-Host "  Found: $pythonVersion" -ForegroundColor Green

# Setup virtual environment
if (-not $SkipVenv) {
    Write-Host "[2/5] Setting up virtual environment..." -ForegroundColor Yellow
    Set-Location $ProjectRoot
    
    if (-not (Test-Path ".venv")) {
        Write-Host "  Creating .venv..." -ForegroundColor Gray
        python -m venv .venv
    }
    
    Write-Host "  Activating .venv..." -ForegroundColor Gray
    & ".\.venv\Scripts\Activate.ps1"
    
    Write-Host "  Installing dependencies..." -ForegroundColor Gray
    pip install -r requirements.txt -q
    Write-Host "  Dependencies installed" -ForegroundColor Green
} else {
    Write-Host "[2/5] Skipping venv setup" -ForegroundColor Gray
}

# Check .env file
Write-Host "[3/5] Checking configuration..." -ForegroundColor Yellow
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Write-Host "  Creating .env from .env.example..." -ForegroundColor Gray
        Copy-Item ".env.example" ".env"
        Write-Host "  IMPORTANT: Edit .env with your API keys before continuing!" -ForegroundColor Yellow
        Write-Host "  Run: notepad .env" -ForegroundColor Yellow
        exit 0
    } else {
        Write-Host "  WARNING: No .env file found" -ForegroundColor Yellow
    }
} else {
    Write-Host "  .env file found" -ForegroundColor Green
}

# Create necessary directories
Write-Host "[4/5] Creating directories..." -ForegroundColor Yellow
$dirs = @(
    ".hive-mind/knowledge",
    ".hive-mind/scraped", 
    ".hive-mind/enriched",
    ".hive-mind/campaigns",
    "credentials"
)
foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}
Write-Host "  Directories ready" -ForegroundColor Green

# Start services
Write-Host "[5/5] Starting services..." -ForegroundColor Yellow
Write-Host ""

if ($DashboardOnly) {
    Write-Host "Starting Dashboard only..." -ForegroundColor Cyan
    Write-Host "  Dashboard: http://localhost:8080" -ForegroundColor Green
    Write-Host ""
    python -m uvicorn dashboard.health_app:app --host 0.0.0.0 --port 8080 --reload
} else {
    Write-Host "Starting full system..." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This will open multiple terminals:" -ForegroundColor Yellow
    Write-Host "  1. Dashboard (port 8080)" -ForegroundColor White
    Write-Host "  2. Health Monitor WebSocket (port 8765)" -ForegroundColor White
    Write-Host ""
    
    # Start Dashboard in new terminal
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ProjectRoot'; .\.venv\Scripts\Activate.ps1; python -m uvicorn dashboard.health_app:app --host 0.0.0.0 --port 8080 --reload"
    
    # Start Health Monitor in new terminal
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ProjectRoot'; .\.venv\Scripts\Activate.ps1; python -c `"from core.unified_health_monitor import HealthMonitor; import asyncio; m = HealthMonitor(); asyncio.run(m.start())`""
    
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  System Started!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Dashboard:     http://localhost:8080" -ForegroundColor Cyan
    Write-Host "  Health API:    http://localhost:8080/api/health" -ForegroundColor Cyan
    Write-Host "  WebSocket:     ws://localhost:8765" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Press Ctrl+C in each terminal to stop." -ForegroundColor Yellow
}
