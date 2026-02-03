#!/usr/bin/env pwsh
# Quick test runner for development

param([string]$File = "", [string]$Pattern = "")

if ($File) {
    python -m pytest $File -v --tb=short
} elseif ($Pattern) {
    python -m pytest tests/ -v --tb=short -k $Pattern
} else {
    python -m pytest tests/ -v --tb=line -q --ignore=tests/test_unified_integration.py
}
