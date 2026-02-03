# Hourly Health Check Script
# Optional: Enable in setup_scheduler.ps1 if you want hourly monitoring

$ErrorActionPreference = "Continue"
$ProjectRoot = "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
$LogFile = "$ProjectRoot\.tmp\logs\health_$(Get-Date -Format 'yyyy-MM-dd').log"

# Activate virtual environment
& "$ProjectRoot\.venv\Scripts\Activate.ps1"

try {
    # Run health check
    $result = python "$ProjectRoot\execution\health_check.py" --format json 2>&1
    
    # Parse result
    $health = $result | ConvertFrom-Json -ErrorAction SilentlyContinue
    
    if ($health) {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        $status = $health.overall
        
        # Log status
        "$timestamp | Health: $status" | Out-File -Append $LogFile
        
        # Alert if degraded or error
        if ($status -in @("degraded", "error")) {
            $message = "Alpha Swarm health check: $status"
            python "$ProjectRoot\execution\send_alert.py" --level warning --message $message
        }
    }
}
catch {
    # Log error but don't fail
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$timestamp | Health check error: $_" | Out-File -Append $LogFile
}
