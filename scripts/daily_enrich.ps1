# Daily Enrichment Script for Alpha Swarm
# Runs daily at 7:00 AM PST (11:00 PM PHT)

$ErrorActionPreference = "Stop"
$ProjectRoot = "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
$LogDir = "$ProjectRoot\.tmp\logs"
$LogFile = "$LogDir\enrich_$(Get-Date -Format 'yyyy-MM-dd').log"

# Ensure log directory exists
if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir }

function Write-Log {
    param($Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp | $Message" | Tee-Object -Append $LogFile
}

try {
    Write-Log "=========================================="
    Write-Log "Starting daily enrichment workflow"
    Write-Log "=========================================="
    
    # Activate virtual environment
    & "$ProjectRoot\.venv\Scripts\Activate.ps1"
    
    # Check for scraped data
    $scrapedFile = "$ProjectRoot\.hive-mind\scraped\latest.json"
    
    if (!(Test-Path $scrapedFile)) {
        Write-Log "No scraped data found - skipping enrichment"
        exit 0
    }
    
    $scrapedAge = ((Get-Date) - (Get-Item $scrapedFile).LastWriteTime).TotalHours
    if ($scrapedAge -gt 24) {
        Write-Log "WARNING: Scraped data is $([math]::Round($scrapedAge, 1)) hours old"
    }
    
    $todayDate = Get-Date -Format 'yyyy-MM-dd'
    $enrichedOutput = "$ProjectRoot\.hive-mind\enriched\enriched_$todayDate.json"
    
    # Run Clay waterfall enrichment
    Write-Log "Starting Clay waterfall enrichment..."
    python "$ProjectRoot\execution\enricher_clay_waterfall.py" `
        --input $scrapedFile `
        --output $enrichedOutput `
        2>&1 | ForEach-Object { Write-Log $_ }
    
    if (Test-Path $enrichedOutput) {
        # Get enrichment stats
        $enrichedData = Get-Content $enrichedOutput | ConvertFrom-Json
        $totalLeads = ($enrichedData | Measure-Object).Count
        $enrichedCount = ($enrichedData | Where-Object { $_.email -and $_.email -ne "" } | Measure-Object).Count
        $successRate = if ($totalLeads -gt 0) { [math]::Round(($enrichedCount / $totalLeads) * 100, 1) } else { 0 }
        
        Write-Log "Enrichment complete: $enrichedCount / $totalLeads leads enriched ($successRate%)"
        
        # Alert if success rate is too low
        if ($successRate -lt 80) {
            python "$ProjectRoot\execution\send_alert.py" `
                --level warning `
                --message "Enrichment success rate low: $successRate% (target: 80%)"
        }
        
        # Run segmentation
        Write-Log "Starting segmentation..."
        python "$ProjectRoot\execution\segmentor_classify.py" `
            --input $enrichedOutput `
            2>&1 | ForEach-Object { Write-Log $_ }
        
        # Create latest link
        Copy-Item $enrichedOutput "$ProjectRoot\.hive-mind\enriched\latest.json" -Force
    }
    else {
        Write-Log "ERROR: Enrichment output not created"
        throw "Enrichment failed to produce output"
    }
    
    Write-Log "Daily enrichment complete"
    Write-Log "=========================================="
    
}
catch {
    Write-Log "ERROR: $_"
    Write-Log $_.ScriptStackTrace
    
    python "$ProjectRoot\execution\send_alert.py" `
        --level error `
        --message "Daily enrichment failed: $_"
    
    exit 1
}
