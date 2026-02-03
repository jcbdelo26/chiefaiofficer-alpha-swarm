# Daily Scrape Script for Alpha Swarm
# Runs daily at 5:00 AM PST (9:00 PM PHT)

$ErrorActionPreference = "Stop"
$ProjectRoot = "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
$LogDir = "$ProjectRoot\.tmp\logs"
$LogFile = "$LogDir\scrape_$(Get-Date -Format 'yyyy-MM-dd').log"

# Ensure log directory exists
if (!(Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir }

function Write-Log {
    param($Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp | $Message" | Tee-Object -Append $LogFile
}

try {
    Write-Log "=========================================="
    Write-Log "Starting daily scrape workflow"
    Write-Log "=========================================="
    
    # Activate virtual environment
    & "$ProjectRoot\.venv\Scripts\Activate.ps1"
    
    # Rotate through competitors based on day of week
    $dayOfWeek = (Get-Date).DayOfWeek.value__
    $competitors = @("gong", "clari", "chorus", "hubspot", "salesloft", "outreach", "apollo")
    $todayTarget = $competitors[$dayOfWeek % $competitors.Count]
    
    Write-Log "Today's scrape target: $todayTarget"
    
    # Scrape competitor followers
    Write-Log "Scraping followers..."
    python "$ProjectRoot\execution\hunter_scrape_followers.py" `
        --company $todayTarget `
        --limit 100 `
        --output "$ProjectRoot\.hive-mind\scraped\followers_$($todayTarget)_$(Get-Date -Format 'yyyy-MM-dd').json" `
        2>&1 | ForEach-Object { Write-Log $_ }
    
    # Scrape events on Wednesdays only (day 3)
    if ($dayOfWeek -eq 3) {
        Write-Log "Wednesday - Scraping events..."
        python "$ProjectRoot\execution\hunter_scrape_events.py" `
            --category "AI RevOps" `
            --limit 50 `
            2>&1 | ForEach-Object { Write-Log $_ }
    }
    
    # Scrape posts on Fridays (day 5)
    if ($dayOfWeek -eq 5) {
        Write-Log "Friday - Scraping post engagers..."
        python "$ProjectRoot\execution\hunter_scrape_posts.py" `
            --limit 50 `
            2>&1 | ForEach-Object { Write-Log $_ }
    }
    
    # Create "latest" symlink/copy for enrichment
    $latestScraped = Get-ChildItem "$ProjectRoot\.hive-mind\scraped\*.json" | 
    Sort-Object LastWriteTime -Descending | 
    Select-Object -First 1
    
    if ($latestScraped) {
        Copy-Item $latestScraped.FullName "$ProjectRoot\.hive-mind\scraped\latest.json" -Force
        Write-Log "Latest scraped file: $($latestScraped.Name)"
    }
    
    Write-Log "Daily scrape complete"
    Write-Log "=========================================="
    
}
catch {
    Write-Log "ERROR: $_"
    Write-Log $_.ScriptStackTrace
    
    # Send alert
    try {
        python "$ProjectRoot\execution\send_alert.py" `
            --level error `
            --message "Daily scrape failed: $_"
    }
    catch {
        Write-Log "Failed to send alert: $_"
    }
    
    exit 1
}
