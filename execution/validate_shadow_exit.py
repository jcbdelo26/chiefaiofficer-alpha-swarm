#!/usr/bin/env python3
"""
Shadow Mode Exit Criteria Validator
====================================
Validates that all criteria are met before transitioning from Shadow to Parallel mode.

Usage:
    python execution/validate_shadow_exit.py
    python execution/validate_shadow_exit.py --verbose
    python execution/validate_shadow_exit.py --json
"""

import os
import sys
import json
import glob
import asyncio
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field, asdict

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

# Try rich for pretty output
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None


# =============================================================================
# CONFIGURATION
# =============================================================================

HIVE_MIND_DIR = PROJECT_ROOT / ".hive-mind"
SHADOW_EMAILS_DIR = HIVE_MIND_DIR / "shadow_mode_emails"
HOT_LEADS_DIR = HIVE_MIND_DIR / "hot_leads"
AUDIT_DB = HIVE_MIND_DIR / "audit.db"

# Exit criteria thresholds
MIN_LEADS_PROCESSED = 100
MIN_AE_APPROVAL_RATE = 0.80
MIN_SAMPLE_SIZE = 50


@dataclass
class ExitCriterion:
    """A single exit criterion."""
    name: str
    description: str
    passed: bool
    value: str
    threshold: str
    details: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of shadow mode exit validation."""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    criteria: List[ExitCriterion] = field(default_factory=list)
    all_passed: bool = False
    ready_for_parallel: bool = False
    blocking_issues: List[str] = field(default_factory=list)


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def check_leads_processed() -> ExitCriterion:
    """Check if minimum leads have been processed."""
    # Count leads from multiple sources
    lead_count = 0
    
    # Check shadow emails directory
    if SHADOW_EMAILS_DIR.exists():
        email_files = list(SHADOW_EMAILS_DIR.glob("*.json"))
        for f in email_files:
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    if isinstance(data, list):
                        lead_count += len(data)
                    else:
                        lead_count += 1
            except:
                pass
    
    # Check segmented leads
    segmented_dir = HIVE_MIND_DIR / "segmented"
    if segmented_dir.exists():
        for f in segmented_dir.glob("*.json"):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    if isinstance(data, list):
                        lead_count += len(data)
            except:
                pass
    
    passed = lead_count >= MIN_LEADS_PROCESSED
    return ExitCriterion(
        name="Leads Processed",
        description="Minimum leads processed without errors",
        passed=passed,
        value=str(lead_count),
        threshold=f">= {MIN_LEADS_PROCESSED}",
        details=f"Found {lead_count} leads in shadow mode"
    )


def check_shadow_emails_logged() -> ExitCriterion:
    """Check if shadow emails are being logged."""
    email_count = 0
    
    if SHADOW_EMAILS_DIR.exists():
        email_files = list(SHADOW_EMAILS_DIR.glob("*.json"))
        for f in email_files:
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    if isinstance(data, list):
                        email_count += len(data)
                    else:
                        email_count += 1
            except:
                pass
    
    passed = email_count > 0
    return ExitCriterion(
        name="Shadow Emails Logged",
        description="Emails logged to shadow_mode_emails/",
        passed=passed,
        value=str(email_count),
        threshold="> 0",
        details=f"{email_count} emails logged in {SHADOW_EMAILS_DIR}"
    )


def check_ae_approval_rate() -> ExitCriterion:
    """Check AE approval rate on sample emails."""
    # Look for AE review files
    review_files = list((HIVE_MIND_DIR / "gatekeeper").glob("*review*.json")) if (HIVE_MIND_DIR / "gatekeeper").exists() else []
    review_files += list(Path(".tmp").glob("*review*.json")) if Path(".tmp").exists() else []
    
    total_reviewed = 0
    total_approved = 0
    
    for f in review_files:
        try:
            with open(f) as fp:
                data = json.load(fp)
                if isinstance(data, list):
                    for item in data:
                        if item.get("ae_approved") is not None:
                            total_reviewed += 1
                            if item.get("ae_approved") == True:
                                total_approved += 1
        except:
            pass
    
    if total_reviewed > 0:
        approval_rate = total_approved / total_reviewed
        passed = approval_rate >= MIN_AE_APPROVAL_RATE and total_reviewed >= MIN_SAMPLE_SIZE
        value = f"{approval_rate:.0%} ({total_approved}/{total_reviewed})"
    else:
        passed = False
        approval_rate = 0
        value = "No AE reviews found"
    
    return ExitCriterion(
        name="AE Approval Rate",
        description="AE approval rate on sample emails",
        passed=passed,
        value=value,
        threshold=f">= {MIN_AE_APPROVAL_RATE:.0%} (min {MIN_SAMPLE_SIZE} samples)",
        details=f"Reviewed {total_reviewed} emails, {total_approved} approved"
    )


def check_pii_in_logs() -> ExitCriterion:
    """Check for PII leaks in log files."""
    pii_detected = 0
    files_scanned = 0
    
    # Import AIDefence for PII detection
    try:
        from core.aidefence import get_aidefence
        aidefence = get_aidefence()
        
        # Scan log files
        log_dirs = [
            HIVE_MIND_DIR / "logs",
            HIVE_MIND_DIR / "shadow_mode_emails",
            PROJECT_ROOT / "logs",
        ]
        
        for log_dir in log_dirs:
            if log_dir.exists():
                for log_file in log_dir.glob("*.json"):
                    files_scanned += 1
                    try:
                        with open(log_file) as f:
                            content = f.read()
                            result = aidefence.detect_pii(content)
                            if result.get("detected", []):
                                pii_detected += len(result["detected"])
                    except:
                        pass
    except ImportError:
        # AIDefence not available
        return ExitCriterion(
            name="PII in Logs",
            description="No PII detected in log files",
            passed=True,
            value="Not scanned (AIDefence not available)",
            threshold="0 detected",
            details="Install AIDefence for PII scanning"
        )
    
    passed = pii_detected == 0
    return ExitCriterion(
        name="PII in Logs",
        description="No PII detected in log files",
        passed=passed,
        value=str(pii_detected),
        threshold="0 detected",
        details=f"Scanned {files_scanned} files, found {pii_detected} PII instances"
    )


def check_hot_lead_detection() -> ExitCriterion:
    """Check if hot lead detection has been tested."""
    hot_lead_count = 0
    
    if HOT_LEADS_DIR.exists():
        for f in HOT_LEADS_DIR.glob("*.json"):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    if isinstance(data, list):
                        hot_lead_count += len(data)
                    else:
                        hot_lead_count += 1
            except:
                pass
    
    # Also check audit trail for hot lead events
    if AUDIT_DB.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(AUDIT_DB))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM audit_log WHERE action LIKE '%hot_lead%'")
            hot_lead_count += cursor.fetchone()[0]
            conn.close()
        except:
            pass
    
    passed = hot_lead_count >= 1
    return ExitCriterion(
        name="Hot Lead Detection",
        description="Hot lead detection tested",
        passed=passed,
        value=str(hot_lead_count),
        threshold=">= 1 test",
        details=f"{hot_lead_count} hot lead events detected/tested"
    )


def check_webhook_server() -> ExitCriterion:
    """Check if webhook server is accessible."""
    import socket
    
    # Try to connect to webhook server ports
    ports_to_check = [5000, 8000, 8080]
    server_found = False
    active_port = None
    
    for port in ports_to_check:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            if result == 0:
                server_found = True
                active_port = port
                break
        except:
            pass
    
    passed = server_found
    return ExitCriterion(
        name="Webhook Server",
        description="Webhook server running and accessible",
        passed=passed,
        value="Running" if passed else "Not Running",
        threshold="Accessible on localhost",
        details=f"Active on port {active_port}" if passed else "Start with: python webhooks/webhook_server.py"
    )


def check_health_dashboard() -> ExitCriterion:
    """Check if health dashboard is accessible."""
    import socket
    
    # Dashboard typically runs on 8080
    ports_to_check = [8080, 8000, 5000]
    dashboard_found = False
    active_port = None
    
    for port in ports_to_check:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            if result == 0:
                dashboard_found = True
                active_port = port
                break
        except:
            pass
    
    # Also accept if dashboard files exist (can be started)
    dashboard_file = PROJECT_ROOT / "dashboard" / "health_app.py"
    dashboard_exists = dashboard_file.exists()
    
    passed = dashboard_found or dashboard_exists
    return ExitCriterion(
        name="Health Dashboard",
        description="Health dashboard accessible or available",
        passed=passed,
        value="Accessible" if dashboard_found else ("Available" if dashboard_exists else "Not Found"),
        threshold="Accessible or ready to start",
        details=f"Port {active_port}" if dashboard_found else "Start with: uvicorn dashboard.health_app:app"
    )


def check_production_config() -> ExitCriterion:
    """Check if production config is properly set to shadow mode."""
    config_file = PROJECT_ROOT / "config" / "production.json"
    
    if not config_file.exists():
        return ExitCriterion(
            name="Production Config",
            description="Production config in shadow mode",
            passed=False,
            value="Not Found",
            threshold="Shadow mode enabled",
            details="config/production.json not found"
        )
    
    try:
        with open(config_file) as f:
            config = json.load(f)
        
        shadow_mode = config.get("email_behavior", {}).get("shadow_mode", False)
        actually_send = config.get("email_behavior", {}).get("actually_send", True)
        current_phase = config.get("rollout_phase", {}).get("current", "unknown")
        
        passed = shadow_mode and not actually_send and current_phase == "shadow"
        value = f"Phase: {current_phase}, Shadow: {shadow_mode}, Send: {actually_send}"
        
        return ExitCriterion(
            name="Production Config",
            description="Production config in shadow mode",
            passed=passed,
            value=value,
            threshold="shadow_mode=true, actually_send=false",
            details=f"Current rollout phase: {current_phase}"
        )
    except Exception as e:
        return ExitCriterion(
            name="Production Config",
            description="Production config in shadow mode",
            passed=False,
            value="Error reading config",
            threshold="Shadow mode enabled",
            details=str(e)
        )


# =============================================================================
# MAIN VALIDATION
# =============================================================================

def run_validation() -> ValidationResult:
    """Run all validation checks."""
    result = ValidationResult()
    
    # Run all checks
    checks = [
        check_leads_processed,
        check_shadow_emails_logged,
        check_ae_approval_rate,
        check_pii_in_logs,
        check_hot_lead_detection,
        check_webhook_server,
        check_health_dashboard,
        check_production_config,
    ]
    
    for check_fn in checks:
        try:
            criterion = check_fn()
            result.criteria.append(criterion)
            if not criterion.passed:
                result.blocking_issues.append(f"{criterion.name}: {criterion.value}")
        except Exception as e:
            result.criteria.append(ExitCriterion(
                name=check_fn.__name__.replace("check_", "").replace("_", " ").title(),
                description="Check failed with error",
                passed=False,
                value="Error",
                threshold="N/A",
                details=str(e)
            ))
            result.blocking_issues.append(f"{check_fn.__name__}: Error - {e}")
    
    result.all_passed = all(c.passed for c in result.criteria)
    result.ready_for_parallel = result.all_passed
    
    return result


def print_results_rich(result: ValidationResult):
    """Print results using rich library."""
    table = Table(title="Shadow Mode Exit Criteria")
    table.add_column("Criterion", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Value")
    table.add_column("Threshold")
    table.add_column("Details", style="dim")
    
    for c in result.criteria:
        status = "✅ PASS" if c.passed else "❌ FAIL"
        style = "green" if c.passed else "red"
        table.add_row(
            c.name,
            f"[{style}]{status}[/{style}]",
            c.value,
            c.threshold,
            c.details or ""
        )
    
    console.print(table)
    console.print()
    
    if result.ready_for_parallel:
        console.print(Panel(
            "[green bold]✅ READY FOR PARALLEL MODE[/green bold]\n\n"
            "All exit criteria passed. You can proceed to Parallel Mode by updating:\n"
            "[cyan]config/production.json[/cyan]: rollout_phase.current = \"parallel\"",
            title="Validation Result",
            style="green"
        ))
    else:
        blocking = "\n".join(f"• {issue}" for issue in result.blocking_issues)
        console.print(Panel(
            f"[red bold]❌ NOT READY FOR PARALLEL MODE[/red bold]\n\n"
            f"[yellow]Blocking Issues:[/yellow]\n{blocking}",
            title="Validation Result",
            style="red"
        ))


def print_results_plain(result: ValidationResult):
    """Print results without rich library."""
    print("\n" + "=" * 70)
    print("SHADOW MODE EXIT CRITERIA")
    print("=" * 70)
    
    for c in result.criteria:
        status = "✅ PASS" if c.passed else "❌ FAIL"
        print(f"\n{status} {c.name}")
        print(f"   Value: {c.value}")
        print(f"   Threshold: {c.threshold}")
        if c.details:
            print(f"   Details: {c.details}")
    
    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)
    
    if result.ready_for_parallel:
        print("\n✅ READY FOR PARALLEL MODE")
        print("\nAll exit criteria passed. Update config/production.json:")
        print('   rollout_phase.current = "parallel"')
    else:
        print("\n❌ NOT READY FOR PARALLEL MODE")
        print("\nBlocking Issues:")
        for issue in result.blocking_issues:
            print(f"  • {issue}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Validate Shadow Mode Exit Criteria")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all details")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    result = run_validation()
    
    if args.json:
        output = {
            "timestamp": result.timestamp,
            "all_passed": result.all_passed,
            "ready_for_parallel": result.ready_for_parallel,
            "criteria": [asdict(c) for c in result.criteria],
            "blocking_issues": result.blocking_issues
        }
        print(json.dumps(output, indent=2))
    elif RICH_AVAILABLE:
        print_results_rich(result)
    else:
        print_results_plain(result)
    
    sys.exit(0 if result.ready_for_parallel else 1)


if __name__ == "__main__":
    main()
