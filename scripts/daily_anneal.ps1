# Daily Self-Annealing Script for Alpha Swarm
# Runs daily at 4:00 PM PST (8:00 AM PHT)

$ErrorActionPreference = "Stop"
$ProjectRoot = "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
$LogDir = "$ProjectRoot\.tmp\logs"
$LogFile = "$LogDir\anneal_$(Get-Date -Format 'yyyy-MM-dd').log"

# Ensure log directory exists
if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir }

function Write-Log {
    param($Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp | $Message" | Tee-Object -Append $LogFile
}

try {
    Write-Log "=========================================="
    Write-Log "Starting daily self-annealing workflow"
    Write-Log "=========================================="
    
    # Activate virtual environment
    & "$ProjectRoot\.venv\Scripts\Activate.ps1"
    
    # Step 1: Sync metrics from Instantly
    Write-Log "Syncing metrics from Instantly..."
    python "$ProjectRoot\execution\instantly_sync_metrics.py" `
        2>&1 | ForEach-Object { Write-Log $_ }
    
    # Step 2: Run SPARC self-annealing
    Write-Log "Running SPARC self-annealing..."
    python "$ProjectRoot\execution\sparc_coordinator.py" `
        --self-anneal `
        2>&1 | ForEach-Object { Write-Log $_ }
    
    # Step 3: Check for drift
    Write-Log "Running drift detection..."
    $driftResult = python "$ProjectRoot\execution\drift_detector.py" `
        --check-all `
        --output json `
        2>&1
    Write-Log "Drift result: $driftResult"
    
    # Parse drift result and alert if needed
    try {
        $driftData = $driftResult | ConvertFrom-Json
        if ($driftData.has_drift -eq $true) {
            python "$ProjectRoot\execution\send_alert.py" `
                --level warning `
                --message "📊 Drift detected: $($driftData.drifts_detected | ConvertTo-Json -Compress)"
        }
    }
    catch {
        Write-Log "Could not parse drift result (may be normal)"
    }
    
    # Step 4: Update Q-table from outcomes
    Write-Log "Updating RL Q-table..."
    python "$ProjectRoot\execution\rl_engine.py" `
        --mode update `
        2>&1 | ForEach-Object { Write-Log $_ }
    
    # Step 5: Generate daily report
    $reportDate = Get-Date -Format 'yyyy-MM-dd'
    $reportPath = "$ProjectRoot\.tmp\reports\daily_$reportDate.md"
    
    Write-Log "Generating daily report..."
    python "$ProjectRoot\execution\generate_daily_report.py" `
        --output $reportPath `
        2>&1 | ForEach-Object { Write-Log $_ }
    
    if (Test-Path $reportPath) {
        Write-Log "Daily report saved: $reportPath"
    }
    
    # Step 6: Update learnings.json with today's insights
    $learningsFile = "$ProjectRoot\.hive-mind\learnings.json"
    if (Test-Path $learningsFile) {
        $learnings = Get-Content $learningsFile | ConvertFrom-Json
        $learnings | Add-Member -NotePropertyName "last_anneal" -NotePropertyValue (Get-Date -Format "o") -Force
        $learnings | ConvertTo-Json -Depth 10 | Set-Content $learningsFile
        Write-Log "Updated learnings.json last_anneal timestamp"
    }
    
    Write-Log "Daily self-annealing complete"
    Write-Log "=========================================="
    
}
catch {
    Write-Log "ERROR: $_"
    Write-Log $_.ScriptStackTrace
    
    # Self-annealing failures are non-critical, just warn
    python "$ProjectRoot\execution\send_alert.py" `
        --level warning `
        --message "Self-annealing had issues: $_"
    
    # Don't exit 1 - self-annealing failures shouldn't break the pipeline
    exit 0
}
