#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run all tests with comprehensive reporting.
    
.DESCRIPTION
    Executes the full test suite with coverage, generates reports,
    and provides pass/fail summary.
    
.EXAMPLE
    .\scripts\test-all.ps1
    .\scripts\test-all.ps1 -Coverage
    .\scripts\test-all.ps1 -Quick
#>

param(
    [switch]$Coverage,
    [switch]$Quick,
    [switch]$Parallel,
    [string]$Pattern = ""
)

$ErrorActionPreference = "Continue"
$startTime = Get-Date

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  ALPHA SWARM TEST SUITE" -ForegroundColor Cyan
Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Activate venv if exists
if (Test-Path ".venv\Scripts\Activate.ps1") {
    . .\.venv\Scripts\Activate.ps1
}

# Test categories
$testGroups = @{
    "Core" = @(
        "tests/test_unified_guardrails.py",
        "tests/test_multi_layer_failsafe.py",
        "tests/test_self_annealing_engine.py",
        "tests/test_swarm_coordination.py"
    )
    "Agents" = @(
        "tests/test_unified_queen_orchestrator.py",
        "tests/test_scheduler_agent.py",
        "tests/test_communicator_agent.py"
    )
    "MCP" = @(
        "tests/test_google_calendar_mcp.py",
        "tests/test_calendar_integration.py",
        "tests/test_calendar_timezone.py"
    )
    "Integration" = @(
        "tests/test_unified_integration_gateway.py",
        "tests/test_unified_queen_integration.py",
        "tests/test_workflow_simulator.py"
    )
}

$results = @{}
$totalPassed = 0
$totalFailed = 0
$totalErrors = 0

if ($Quick) {
    Write-Host "[QUICK MODE] Running core tests only`n" -ForegroundColor Yellow
    $testGroups = @{ "Core" = $testGroups["Core"] }
}

foreach ($group in $testGroups.Keys) {
    Write-Host "[$group Tests]" -ForegroundColor Yellow
    
    $files = $testGroups[$group] -join " "
    
    if ($Coverage) {
        $cmd = "python -m pytest $files -v --tb=short --cov=core --cov=execution --cov-report=term-missing"
    } else {
        $cmd = "python -m pytest $files -v --tb=short"
    }
    
    if ($Pattern) {
        $cmd += " -k `"$Pattern`""
    }
    
    $output = Invoke-Expression $cmd 2>&1
    $lastOutput = $output | Select-Object -Last 5
    
    # Parse results
    $passMatch = $lastOutput | Select-String -Pattern "(\d+) passed"
    $failMatch = $lastOutput | Select-String -Pattern "(\d+) failed"
    $errorMatch = $lastOutput | Select-String -Pattern "(\d+) error"
    
    $passed = if ($passMatch) { [int]$passMatch.Matches[0].Groups[1].Value } else { 0 }
    $failed = if ($failMatch) { [int]$failMatch.Matches[0].Groups[1].Value } else { 0 }
    $errors = if ($errorMatch) { [int]$errorMatch.Matches[0].Groups[1].Value } else { 0 }
    
    $totalPassed += $passed
    $totalFailed += $failed
    $totalErrors += $errors
    
    $status = if ($failed -eq 0 -and $errors -eq 0) { "✅ PASS" } else { "❌ FAIL" }
    Write-Host "  $status - $passed passed, $failed failed, $errors errors`n"
    
    $results[$group] = @{
        Passed = $passed
        Failed = $failed
        Errors = $errors
    }
}

$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  SUMMARY" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Total: $totalPassed passed, $totalFailed failed, $totalErrors errors" -ForegroundColor $(if ($totalFailed -eq 0 -and $totalErrors -eq 0) { "Green" } else { "Red" })
Write-Host "Duration: $([math]::Round($duration, 2))s"

if ($totalFailed -eq 0 -and $totalErrors -eq 0) {
    Write-Host "`n✅ ALL TESTS PASSED`n" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n❌ TESTS FAILED`n" -ForegroundColor Red
    exit 1
}
