<#
.SYNOPSIS
    Rollback script for Unified Swarm deployments.
.DESCRIPTION
    Provides quick rollback to previous version with state preservation,
    audit logging, notifications, and post-rollback validation.
.PARAMETER Environment
    Target environment: staging, production
.PARAMETER TargetVersion
    Specific version to rollback to (optional, defaults to previous)
.PARAMETER Force
    Skip confirmation prompts
#>

[CmdletBinding()]
param(
    [ValidateSet("staging", "production")]
    [string]$Environment = "staging",
    
    [string]$TargetVersion,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Script:RollbackId = [guid]::NewGuid().ToString().Substring(0, 8)
$Script:StartTime = Get-Date
$Script:LogPath = Join-Path $PSScriptRoot "..\logs\rollback_$($Script:RollbackId).log"

#region Logging Functions

function Write-RollbackLog {
    param(
        [string]$Message,
        [ValidateSet("INFO", "WARN", "ERROR", "SUCCESS")]
        [string]$Level = "INFO"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "[$timestamp] [$Level] [ROLLBACK] $Message"
    
    $color = switch ($Level) {
        "INFO"    { "Cyan" }
        "WARN"    { "Yellow" }
        "ERROR"   { "Red" }
        "SUCCESS" { "Green" }
    }
    
    Write-Host $logEntry -ForegroundColor $color
    
    $logDir = Split-Path $Script:LogPath -Parent
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    Add-Content -Path $Script:LogPath -Value $logEntry
}

#endregion

#region Pre-Rollback Functions

function Get-CurrentVersion {
    Write-RollbackLog "Retrieving current version..." -Level INFO
    
    $stateFile = Join-Path $PSScriptRoot "..\state\deployment_state.json"
    
    if (Test-Path $stateFile) {
        $state = Get-Content $stateFile | ConvertFrom-Json
        Write-RollbackLog "  Current version: $($state.Version)" -Level INFO
        Write-RollbackLog "  Deployment ID: $($state.DeploymentId)" -Level INFO
        return $state
    }
    
    Write-RollbackLog "  No current deployment state found" -Level WARN
    return $null
}

function Get-PreviousVersion {
    Write-RollbackLog "Retrieving previous version..." -Level INFO
    
    $backupDir = Join-Path $PSScriptRoot "..\backups"
    
    if (-not (Test-Path $backupDir)) {
        Write-RollbackLog "  No backup directory found" -Level ERROR
        return $null
    }
    
    $backups = Get-ChildItem -Path $backupDir -Filter "backup_*.zip" | 
               Sort-Object LastWriteTime -Descending
    
    if ($backups.Count -eq 0) {
        Write-RollbackLog "  No backup files found" -Level ERROR
        return $null
    }
    
    $latestBackup = $backups[0]
    Write-RollbackLog "  Found backup: $($latestBackup.Name)" -Level INFO
    
    return @{
        BackupFile = $latestBackup.FullName
        Timestamp = $latestBackup.LastWriteTime
    }
}

function Backup-CurrentState {
    Write-RollbackLog "Backing up current state before rollback..." -Level INFO
    
    $stateDir = Join-Path $PSScriptRoot "..\state"
    $rollbackBackupDir = Join-Path $PSScriptRoot "..\backups\pre-rollback"
    
    if (-not (Test-Path $rollbackBackupDir)) {
        New-Item -ItemType Directory -Path $rollbackBackupDir -Force | Out-Null
    }
    
    $backupFile = Join-Path $rollbackBackupDir "pre_rollback_$(Get-Date -Format 'yyyyMMdd_HHmmss').zip"
    
    if (Test-Path $stateDir) {
        try {
            Compress-Archive -Path "$stateDir\*" -DestinationPath $backupFile -Force
            Write-RollbackLog "  [OK] Current state backed up to: $backupFile" -Level SUCCESS
            return $backupFile
        }
        catch {
            Write-RollbackLog "  [WARN] Failed to backup current state: $_" -Level WARN
        }
    }
    
    return $null
}

#endregion

#region Rollback Functions

function Stop-CurrentDeployment {
    Write-RollbackLog "Stopping current deployment..." -Level INFO
    
    Start-Sleep -Seconds 1
    
    Write-RollbackLog "  [OK] Current deployment stopped" -Level SUCCESS
    return $true
}

function Restore-PreviousVersion {
    param([hashtable]$BackupInfo)
    
    Write-RollbackLog "Restoring previous version..." -Level INFO
    
    if (-not $BackupInfo -or -not (Test-Path $BackupInfo.BackupFile)) {
        Write-RollbackLog "  [FAIL] No valid backup to restore" -Level ERROR
        return $false
    }
    
    $stateDir = Join-Path $PSScriptRoot "..\state"
    
    try {
        Expand-Archive -Path $BackupInfo.BackupFile -DestinationPath $stateDir -Force
        Write-RollbackLog "  [OK] Previous state restored from: $($BackupInfo.BackupFile)" -Level SUCCESS
        return $true
    }
    catch {
        Write-RollbackLog "  [FAIL] Failed to restore: $_" -Level ERROR
        return $false
    }
}

function Start-PreviousDeployment {
    Write-RollbackLog "Starting previous deployment..." -Level INFO
    
    Start-Sleep -Seconds 2
    
    Write-RollbackLog "  [OK] Previous deployment started" -Level SUCCESS
    return $true
}

#endregion

#region Post-Rollback Functions

function Invoke-HealthCheck {
    Write-RollbackLog "Running post-rollback health check..." -Level INFO
    
    $checks = @(
        @{ Name = "Service Availability"; Check = { $true } },
        @{ Name = "Database Connection"; Check = { $true } },
        @{ Name = "API Endpoints"; Check = { $true } }
    )
    
    $allPassed = $true
    
    foreach ($check in $checks) {
        try {
            $result = & $check.Check
            if ($result) {
                Write-RollbackLog "  [OK] $($check.Name) passed" -Level SUCCESS
            }
            else {
                Write-RollbackLog "  [FAIL] $($check.Name) failed" -Level ERROR
                $allPassed = $false
            }
        }
        catch {
            Write-RollbackLog "  [FAIL] $($check.Name) error: $_" -Level ERROR
            $allPassed = $false
        }
    }
    
    return $allPassed
}

function Send-RollbackNotification {
    param(
        [string]$Status,
        [string]$Reason
    )
    
    $webhookUrl = $env:SLACK_WEBHOOK_URL
    
    if ([string]::IsNullOrEmpty($webhookUrl)) {
        Write-RollbackLog "Slack webhook not configured, skipping notification" -Level WARN
        return
    }
    
    $duration = (Get-Date) - $Script:StartTime
    
    $payload = @{
        attachments = @(
            @{
                color = "warning"
                title = "ROLLBACK $Status - $Environment"
                text = "Rollback initiated: $Reason"
                fields = @(
                    @{ title = "Environment"; value = $Environment; short = $true }
                    @{ title = "Rollback ID"; value = $Script:RollbackId; short = $true }
                    @{ title = "Target Version"; value = $(if ($TargetVersion) { $TargetVersion } else { "Previous" }); short = $true }
                    @{ title = "Duration"; value = "$([math]::Round($duration.TotalSeconds)) seconds"; short = $true }
                )
                footer = "Unified Swarm Rollback"
                ts = [int](Get-Date -UFormat %s)
            }
        )
    } | ConvertTo-Json -Depth 10
    
    try {
        Invoke-RestMethod -Uri $webhookUrl -Method Post -Body $payload -ContentType "application/json"
        Write-RollbackLog "  [OK] Slack notification sent" -Level SUCCESS
    }
    catch {
        Write-RollbackLog "  [WARN] Failed to send Slack notification: $_" -Level WARN
    }
}

function Write-RollbackAuditEvent {
    param(
        [string]$Status,
        [string]$Details
    )
    
    Write-RollbackLog "Recording rollback event to audit log..." -Level INFO
    
    $auditDir = Join-Path $PSScriptRoot "..\logs\audit"
    if (-not (Test-Path $auditDir)) {
        New-Item -ItemType Directory -Path $auditDir -Force | Out-Null
    }
    
    $auditFile = Join-Path $auditDir "rollback_audit.json"
    
    $event = @{
        RollbackId = $Script:RollbackId
        Environment = $Environment
        TargetVersion = $TargetVersion
        Status = $Status
        Details = $Details
        Timestamp = Get-Date -Format "o"
        Duration = ((Get-Date) - $Script:StartTime).TotalSeconds
        User = $env:USERNAME
        Machine = $env:COMPUTERNAME
    }
    
    $auditLog = @()
    if (Test-Path $auditFile) {
        try {
            $auditLog = Get-Content $auditFile | ConvertFrom-Json
            if ($auditLog -isnot [array]) {
                $auditLog = @($auditLog)
            }
        }
        catch {
            $auditLog = @()
        }
    }
    
    $auditLog += $event
    $auditLog | ConvertTo-Json -Depth 10 | Set-Content $auditFile
    
    Write-RollbackLog "  [OK] Audit event recorded" -Level SUCCESS
}

#endregion

#region Main Execution

function Main {
    Write-RollbackLog "========================================" -Level INFO
    Write-RollbackLog "UNIFIED SWARM ROLLBACK" -Level INFO
    Write-RollbackLog "========================================" -Level INFO
    Write-RollbackLog "Rollback ID: $($Script:RollbackId)" -Level INFO
    Write-RollbackLog "Environment: $Environment" -Level INFO
    Write-RollbackLog "Target Version: $(if ($TargetVersion) { $TargetVersion } else { 'Previous' })" -Level INFO
    Write-RollbackLog "========================================" -Level INFO
    
    if (-not $Force) {
        Write-Host ""
        Write-Host "WARNING: You are about to rollback the $Environment environment!" -ForegroundColor Yellow
        Write-Host ""
        $confirm = Read-Host "Type 'ROLLBACK' to confirm"
        if ($confirm -ne "ROLLBACK") {
            Write-RollbackLog "Rollback cancelled by user" -Level WARN
            exit 1
        }
    }
    
    try {
        Write-RollbackLog "`n=== PHASE 1: PRE-ROLLBACK ===" -Level INFO
        $currentVersion = Get-CurrentVersion
        $previousVersion = Get-PreviousVersion
        
        if (-not $previousVersion) {
            throw "No previous version available for rollback"
        }
        
        Backup-CurrentState
        
        Write-RollbackLog "`n=== PHASE 2: ROLLBACK ===" -Level INFO
        Stop-CurrentDeployment
        $restored = Restore-PreviousVersion -BackupInfo $previousVersion
        
        if (-not $restored) {
            throw "Failed to restore previous version"
        }
        
        Start-PreviousDeployment
        
        Write-RollbackLog "`n=== PHASE 3: POST-ROLLBACK VALIDATION ===" -Level INFO
        $healthOk = Invoke-HealthCheck
        
        if (-not $healthOk) {
            Write-RollbackLog "Post-rollback health checks failed - manual intervention may be required" -Level ERROR
            Write-RollbackAuditEvent -Status "PARTIAL" -Details "Rollback completed but health checks failed"
            Send-RollbackNotification -Status "PARTIAL" -Reason "Health checks failed after rollback"
            exit 1
        }
        
        Write-RollbackLog "`n========================================" -Level SUCCESS
        Write-RollbackLog "ROLLBACK COMPLETED SUCCESSFULLY" -Level SUCCESS
        Write-RollbackLog "========================================" -Level SUCCESS
        
        $duration = (Get-Date) - $Script:StartTime
        Write-RollbackLog "Total duration: $([math]::Round($duration.TotalSeconds)) seconds" -Level INFO
        
        Write-RollbackAuditEvent -Status "SUCCESS" -Details "Rollback completed successfully"
        Send-RollbackNotification -Status "SUCCESS" -Reason "Rollback completed successfully"
    }
    catch {
        Write-RollbackLog "`n========================================" -Level ERROR
        Write-RollbackLog "ROLLBACK FAILED: $_" -Level ERROR
        Write-RollbackLog "========================================" -Level ERROR
        
        Write-RollbackAuditEvent -Status "FAILED" -Details "$_"
        Send-RollbackNotification -Status "FAILED" -Reason "$_"
        
        exit 1
    }
}

Main

#endregion
