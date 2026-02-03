# GATEKEEPER Dashboard Startup Script
# Launches the AE review dashboard

$ErrorActionPreference = "Stop"
$ProjectRoot = "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"

Write-Host @"

╔══════════════════════════════════════════════════════════════════════════╗
║                    🚪 GATEKEEPER Dashboard                               ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  Starting AE Campaign Review Dashboard...                                ║
║                                                                          ║
║  URL: http://localhost:5000                                              ║
║                                                                          ║
║  Press Ctrl+C to stop                                                    ║
╚══════════════════════════════════════════════════════════════════════════╝

"@ -ForegroundColor Cyan

# Activate virtual environment
& "$ProjectRoot\.venv\Scripts\Activate.ps1"

# Change to dashboard directory
Set-Location "$ProjectRoot\dashboard"

# Run Flask app
python app.py
