# Windows Task Scheduler Setup for Alpha Swarm
# Run this script as Administrator to create scheduled tasks

param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Status,
    [switch]$Help
)

$ProjectRoot = "D:\Agent Swarm Orchestration\chiefaiofficer-alpha-swarm"
$TaskPrefix = "AlphaSwarm"

# Task definitions
$Tasks = @(
    @{
        Name        = "$TaskPrefix-DailyScrape"
        Description = "Daily LinkedIn scraping (9 PM PHT)"
        Script      = "$ProjectRoot\scripts\daily_scrape.ps1"
        Time        = "21:00"  # 9 PM
        Enabled     = $true
    },
    @{
        Name        = "$TaskPrefix-DailyEnrich"
        Description = "Daily lead enrichment (11 PM PHT)"
        Script      = "$ProjectRoot\scripts\daily_enrich.ps1"
        Time        = "23:00"  # 11 PM
        Enabled     = $true
    },
    @{
        Name        = "$TaskPrefix-DailyCampaign"
        Description = "Daily campaign generation (12 AM PHT)"
        Script      = "$ProjectRoot\scripts\daily_campaign.ps1"
        Time        = "00:00"  # Midnight
        Enabled     = $true
    },
    @{
        Name        = "$TaskPrefix-DailyAnneal"
        Description = "Daily self-annealing (8 AM PHT)"
        Script      = "$ProjectRoot\scripts\daily_anneal.ps1"
        Time        = "08:00"  # 8 AM
        Enabled     = $true
    },
    @{
        Name        = "$TaskPrefix-HealthCheck"
        Description = "Hourly health check"
        Script      = "$ProjectRoot\scripts\hourly_health.ps1"
        Time        = "Hourly"
        Enabled     = $false  # Optional - enable if needed
    }
)

function Show-Help {
    Write-Host @"

╔══════════════════════════════════════════════════════════════════════════╗
║                 ALPHA SWARM SCHEDULER SETUP                              ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  USAGE:                                                                  ║
║    .\setup_scheduler.ps1 -Install    : Create all scheduled tasks       ║
║    .\setup_scheduler.ps1 -Uninstall  : Remove all scheduled tasks       ║
║    .\setup_scheduler.ps1 -Status     : Show task status                 ║
║    .\setup_scheduler.ps1 -Help       : Show this help                   ║
║                                                                          ║
║  SCHEDULED TASKS:                                                        ║
║    • DailyScrape   : 9:00 PM  - LinkedIn scraping                       ║
║    • DailyEnrich   : 11:00 PM - Lead enrichment                         ║
║    • DailyCampaign : 12:00 AM - Campaign generation                     ║
║    • DailyAnneal   : 8:00 AM  - Self-annealing                          ║
║                                                                          ║
║  NOTE: Run this script as Administrator                                  ║
╚══════════════════════════════════════════════════════════════════════════╝

"@
}

function Test-Administrator {
    $currentUser = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentUser.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Install-Tasks {
    if (-not (Test-Administrator)) {
        Write-Host "❌ This script must be run as Administrator" -ForegroundColor Red
        Write-Host "   Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
        return
    }
    
    Write-Host "`n📅 Installing Alpha Swarm scheduled tasks...`n" -ForegroundColor Cyan
    
    foreach ($task in $Tasks) {
        if (-not $task.Enabled) {
            Write-Host "⏸️  Skipping $($task.Name) (disabled)" -ForegroundColor Gray
            continue
        }
        
        Write-Host "Creating task: $($task.Name)" -ForegroundColor Yellow
        
        # Check if script exists
        if (-not (Test-Path $task.Script)) {
            Write-Host "   ⚠️  Script not found: $($task.Script)" -ForegroundColor Red
            continue
        }
        
        # Create action
        $action = New-ScheduledTaskAction -Execute "powershell.exe" `
            -Argument "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File `"$($task.Script)`""
        
        # Create trigger based on type
        if ($task.Time -eq "Hourly") {
            $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
        }
        else {
            $trigger = New-ScheduledTaskTrigger -Daily -At $task.Time
        }
        
        # Create settings
        $settings = New-ScheduledTaskSettingsSet `
            -StartWhenAvailable `
            -DontStopOnIdleEnd `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -ExecutionTimeLimit (New-TimeSpan -Hours 2)
        
        # Create principal (run as current user)
        $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U -RunLevel Limited
        
        # Remove existing task if present
        $existingTask = Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue
        if ($existingTask) {
            Unregister-ScheduledTask -TaskName $task.Name -Confirm:$false
            Write-Host "   Removed existing task" -ForegroundColor Gray
        }
        
        # Register new task
        try {
            Register-ScheduledTask `
                -TaskName $task.Name `
                -Description $task.Description `
                -Action $action `
                -Trigger $trigger `
                -Settings $settings `
                -Principal $principal | Out-Null
            
            Write-Host "   ✅ Created: $($task.Name) at $($task.Time)" -ForegroundColor Green
        }
        catch {
            Write-Host "   ❌ Failed: $($_.Exception.Message)" -ForegroundColor Red
        }
    }
    
    Write-Host "`n✅ Scheduler setup complete!`n" -ForegroundColor Green
    Write-Host "To view tasks: .\setup_scheduler.ps1 -Status" -ForegroundColor Cyan
}

function Uninstall-Tasks {
    if (-not (Test-Administrator)) {
        Write-Host "❌ This script must be run as Administrator" -ForegroundColor Red
        return
    }
    
    Write-Host "`n🗑️  Removing Alpha Swarm scheduled tasks...`n" -ForegroundColor Cyan
    
    foreach ($task in $Tasks) {
        $existingTask = Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue
        if ($existingTask) {
            try {
                Unregister-ScheduledTask -TaskName $task.Name -Confirm:$false
                Write-Host "   ✅ Removed: $($task.Name)" -ForegroundColor Green
            }
            catch {
                Write-Host "   ❌ Failed to remove: $($task.Name)" -ForegroundColor Red
            }
        }
        else {
            Write-Host "   ⏸️  Not found: $($task.Name)" -ForegroundColor Gray
        }
    }
    
    Write-Host "`n✅ Tasks removed`n" -ForegroundColor Green
}

function Show-Status {
    Write-Host "`n📊 Alpha Swarm Task Status`n" -ForegroundColor Cyan
    Write-Host ("-" * 80) -ForegroundColor Gray
    
    $format = "{0,-30} {1,-12} {2,-15} {3,-20}"
    Write-Host ($format -f "Task Name", "Status", "Last Run", "Next Run") -ForegroundColor White
    Write-Host ("-" * 80) -ForegroundColor Gray
    
    foreach ($task in $Tasks) {
        $scheduledTask = Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue
        
        if ($scheduledTask) {
            $taskInfo = Get-ScheduledTaskInfo -TaskName $task.Name -ErrorAction SilentlyContinue
            
            $status = switch ($scheduledTask.State) {
                "Ready" { "✅ Ready" }
                "Running" { "🔄 Running" }
                "Disabled" { "⏸️ Disabled" }
                default { "❓ $($scheduledTask.State)" }
            }
            
            $lastRun = if ($taskInfo.LastRunTime -gt [DateTime]::MinValue) {
                $taskInfo.LastRunTime.ToString("MM/dd HH:mm")
            }
            else { "Never" }
            
            $nextRun = if ($taskInfo.NextRunTime -gt [DateTime]::MinValue) {
                $taskInfo.NextRunTime.ToString("MM/dd HH:mm")
            }
            else { "N/A" }
            
            Write-Host ($format -f $task.Name, $status, $lastRun, $nextRun)
        }
        else {
            Write-Host ($format -f $task.Name, "❌ Not Found", "-", "-") -ForegroundColor Gray
        }
    }
    
    Write-Host ("-" * 80) -ForegroundColor Gray
    Write-Host ""
}

# Main execution
if ($Help -or (-not $Install -and -not $Uninstall -and -not $Status)) {
    Show-Help
}
elseif ($Install) {
    Install-Tasks
}
elseif ($Uninstall) {
    Uninstall-Tasks
}
elseif ($Status) {
    Show-Status
}
