# Setup script for Alpha Swarm environment

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Chief AI Officer Alpha Swarm Setup" -ForegroundColor Cyan
Write-Host "  LinkedIn Intelligence & Lead Generation" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

$PROJECT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path

# Step 1: Create virtual environment
Write-Host "[1/5] Creating Python virtual environment..." -ForegroundColor Yellow
if (Test-Path "$PROJECT_DIR\.venv") {
    Write-Host "  Virtual environment already exists." -ForegroundColor Green
}
else {
    python -m venv "$PROJECT_DIR\.venv"
    Write-Host "  Virtual environment created." -ForegroundColor Green
}

# Step 2: Activate and install dependencies
Write-Host "[2/5] Installing Python dependencies..." -ForegroundColor Yellow
& "$PROJECT_DIR\.venv\Scripts\Activate.ps1"
pip install -r "$PROJECT_DIR\requirements.txt" --quiet
Write-Host "  Dependencies installed." -ForegroundColor Green

# Step 3: Create necessary directories
Write-Host "[3/5] Creating directory structure..." -ForegroundColor Yellow
$directories = @(
    ".hive-mind\knowledge",
    ".hive-mind\scraped",
    ".hive-mind\enriched",
    ".hive-mind\segmented",
    ".hive-mind\campaigns",
    ".tmp",
    ".agent\workflows"
)

foreach ($dir in $directories) {
    $fullPath = Join-Path $PROJECT_DIR $dir
    if (!(Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force | Out-Null
    }
}
Write-Host "  Directories created." -ForegroundColor Green

# Step 4: Setup environment file
Write-Host "[4/5] Checking environment variables..." -ForegroundColor Yellow
$envFile = Join-Path $PROJECT_DIR ".env"
$envTemplate = Join-Path $PROJECT_DIR ".env.template"

if (!(Test-Path $envFile)) {
    if (Test-Path $envTemplate) {
        Copy-Item $envTemplate $envFile
        Write-Host "  Created .env from template. Please fill in your API keys!" -ForegroundColor Yellow
    }
}
else {
    Write-Host "  .env file already exists." -ForegroundColor Green
}

# Step 5: Test Python setup
Write-Host "[5/5] Verifying Python environment..." -ForegroundColor Yellow
python -c "import sys; print(f'  Python {sys.version_info.major}.{sys.version_info.minor} ready')"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Setup Complete!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Edit .env file with your API keys"
Write-Host "  2. Run connection test:"
Write-Host "     python execution\test_connections.py" -ForegroundColor Cyan
Write-Host ""
Write-Host "  3. Initialize Claude-Flow (optional):"
Write-Host "     npx claude-flow@alpha swarm init --topology mesh" -ForegroundColor Cyan
Write-Host ""
Write-Host "  4. Start scraping:"
Write-Host "     python execution\hunter_scrape_followers.py --company gong" -ForegroundColor Cyan
Write-Host ""
