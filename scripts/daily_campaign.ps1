# Daily Campaign Generation Script for Alpha Swarm
# Runs daily at 8:00 AM PST (12:00 AM PHT next day)

$ErrorActionPreference = "Stop"
$ProjectRoot = "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
$LogDir = "$ProjectRoot\.tmp\logs"
$LogFile = "$LogDir\campaign_$(Get-Date -Format 'yyyy-MM-dd').log"

# Ensure log directory exists
if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir }

function Write-Log {
    param($Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp | $Message" | Tee-Object -Append $LogFile
}

try {
    Write-Log "=========================================="
    Write-Log "Starting daily campaign generation"
    Write-Log "=========================================="
    
    # Activate virtual environment
    & "$ProjectRoot\.venv\Scripts\Activate.ps1"
    
    # Check for segmented data
    $segmentedDir = "$ProjectRoot\.hive-mind\segmented"
    
    if (!(Test-Path $segmentedDir)) {
        Write-Log "No segmented data found - skipping campaign generation"
        exit 0
    }
    
    $totalCampaigns = 0
    $totalLeads = 0
    
    # Generate campaigns by tier
    # Tier 1: VIP - max 25 leads, deep personalization
    Write-Log "Generating Tier 1 VIP campaigns..."
    $tier1Result = python "$ProjectRoot\execution\crafter_campaign.py" `
        --segment tier1_vip `
        --max-leads 25 `
        --personalization deep `
        2>&1
    $tier1Result | ForEach-Object { Write-Log $_ }
    
    # Tier 2: High priority - max 50 leads
    Write-Log "Generating Tier 2 High Priority campaigns..."
    $tier2Result = python "$ProjectRoot\execution\crafter_campaign.py" `
        --segment tier2_high `
        --max-leads 50 `
        --personalization medium `
        2>&1
    $tier2Result | ForEach-Object { Write-Log $_ }
    
    # Tier 3: Standard - max 100 leads
    Write-Log "Generating Tier 3 Standard campaigns..."
    $tier3Result = python "$ProjectRoot\execution\crafter_campaign.py" `
        --segment tier3_standard `
        --max-leads 100 `
        --personalization light `
        2>&1
    $tier3Result | ForEach-Object { Write-Log $_ }
    
    # Queue all campaigns for AE review
    Write-Log "Queuing campaigns for AE review..."
    python "$ProjectRoot\execution\gatekeeper_queue.py" `
        --action queue-pending `
        2>&1 | ForEach-Object { Write-Log $_ }
    
    # Get queue stats
    $queueStats = python "$ProjectRoot\execution\gatekeeper_queue.py" `
        --action status `
        2>&1
    Write-Log "Queue status: $queueStats"
    
    # Notify AE team
    python "$ProjectRoot\execution\send_alert.py" `
        --level info `
        --message "📬 New campaigns ready for review in GATEKEEPER dashboard"
    
    Write-Log "Daily campaign generation complete"
    Write-Log "=========================================="
    
}
catch {
    Write-Log "ERROR: $_"
    Write-Log $_.ScriptStackTrace
    
    python "$ProjectRoot\execution\send_alert.py" `
        --level error `
        --message "Daily campaign generation failed: $_"
    
    exit 1
}
