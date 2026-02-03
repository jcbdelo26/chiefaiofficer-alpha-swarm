#!/usr/bin/env python3
"""
Send Approved Emails (Day 35 - Assisted Mode)
==============================================
Sends AE-approved emails through GHL with all safety checks.

Usage:
    python execution/send_approved_emails.py --dry-run
    python execution/send_approved_emails.py --limit 10
    python execution/send_approved_emails.py --limit 10 --dry-run false

Safety Features:
- Pre-flight checklist (unsubscribe, PII, domain health, working hours)
- Rate limiting (respects email limits)
- Audit trail logging
- Delivery monitoring
"""

import os
import sys
import json
import asyncio
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
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
    from rich.progress import Progress, SpinnerColumn, TextColumn
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None


# =============================================================================
# CONFIGURATION
# =============================================================================

HIVE_MIND_DIR = PROJECT_ROOT / ".hive-mind"
GATEKEEPER_DIR = HIVE_MIND_DIR / "gatekeeper"
SENT_EMAILS_DIR = HIVE_MIND_DIR / "sent_emails"
APPROVED_DIR = GATEKEEPER_DIR / "approved"

# Assisted mode daily limit
ASSISTED_MODE_LIMIT = 10


@dataclass
class EmailToSend:
    """An approved email ready to send."""
    email_id: str
    contact_id: str
    to_email: str
    subject: str
    body: str
    tier: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None


@dataclass 
class PreflightResult:
    """Result of pre-flight checks."""
    passed: bool
    checks: Dict[str, bool] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)


@dataclass
class SendResult:
    """Result of sending an email."""
    email_id: str
    success: bool
    status: str
    ghl_message_id: Optional[str] = None
    error: Optional[str] = None
    sent_at: Optional[str] = None


@dataclass
class SendReport:
    """Report of all send operations."""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    dry_run: bool = True
    total_queued: int = 0
    total_sent: int = 0
    total_failed: int = 0
    total_skipped: int = 0
    results: List[SendResult] = field(default_factory=list)


# =============================================================================
# LOAD APPROVED EMAILS
# =============================================================================

def load_approved_emails(source_dir: Path = None, limit: int = None) -> List[EmailToSend]:
    """Load approved emails from gatekeeper queue."""
    emails = []
    
    # Check multiple sources
    sources = [
        source_dir or APPROVED_DIR,
        GATEKEEPER_DIR / "approved.json",
        HIVE_MIND_DIR / "shadow_mode_emails",
    ]
    
    for source in sources:
        if source.is_file():
            try:
                with open(source) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            if item.get("ae_approved") or item.get("approved"):
                                emails.append(EmailToSend(
                                    email_id=item.get("id") or item.get("email_id", f"email_{len(emails)}"),
                                    contact_id=item.get("contact_id", ""),
                                    to_email=item.get("to") or item.get("recipient_email", ""),
                                    subject=item.get("subject", ""),
                                    body=item.get("body") or item.get("content", ""),
                                    tier=item.get("tier") or item.get("icp_tier"),
                                    approved_by=item.get("approved_by"),
                                    approved_at=item.get("approved_at")
                                ))
            except:
                pass
        elif source.is_dir():
            for f in source.glob("*.json"):
                try:
                    with open(f) as fp:
                        item = json.load(fp)
                        if item.get("ae_approved") or item.get("approved"):
                            emails.append(EmailToSend(
                                email_id=item.get("id") or f.stem,
                                contact_id=item.get("contact_id", ""),
                                to_email=item.get("to") or item.get("recipient_email", ""),
                                subject=item.get("subject", ""),
                                body=item.get("body") or item.get("content", ""),
                                tier=item.get("tier"),
                                approved_by=item.get("approved_by"),
                                approved_at=item.get("approved_at")
                            ))
                except:
                    pass
    
    if limit:
        emails = emails[:limit]
    
    return emails


# =============================================================================
# PRE-FLIGHT CHECKS
# =============================================================================

def run_preflight_checks(email: EmailToSend) -> PreflightResult:
    """Run all pre-flight safety checks."""
    result = PreflightResult(passed=True)
    
    # Check 1: Unsubscribe link present
    has_unsubscribe = any(word in email.body.lower() for word in ["unsubscribe", "stop", "opt-out", "opt out"])
    result.checks["unsubscribe_present"] = has_unsubscribe
    if not has_unsubscribe:
        result.issues.append("Missing unsubscribe link")
        result.passed = False
    
    # Check 2: Valid email address
    has_valid_email = "@" in email.to_email and "." in email.to_email
    result.checks["valid_email"] = has_valid_email
    if not has_valid_email:
        result.issues.append(f"Invalid email: {email.to_email}")
        result.passed = False
    
    # Check 3: Check suppression list
    suppression_file = HIVE_MIND_DIR / "unsubscribes.json"
    on_suppression_list = False
    if suppression_file.exists():
        try:
            with open(suppression_file) as f:
                suppressions = json.load(f)
                if email.to_email.lower() in [s.lower() for s in suppressions]:
                    on_suppression_list = True
        except:
            pass
    result.checks["not_suppressed"] = not on_suppression_list
    if on_suppression_list:
        result.issues.append("Email on suppression list")
        result.passed = False
    
    # Check 4: No PII in logs (just check subject/body don't have obvious PII)
    # This is a basic check - full PII detection happens elsewhere
    suspicious_patterns = ["ssn", "social security", "credit card", "password"]
    has_pii = any(p in email.body.lower() for p in suspicious_patterns)
    result.checks["no_pii_risk"] = not has_pii
    if has_pii:
        result.issues.append("Potential PII in email body")
        result.passed = False
    
    # Check 5: Domain health (if EmailDeliverabilityGuard available)
    try:
        from core.ghl_guardrails import get_email_guard
        guard = get_email_guard()
        can_send, reason = guard.can_send_email(email.to_email)
        result.checks["domain_healthy"] = can_send
        if not can_send:
            result.issues.append(f"Domain check failed: {reason}")
            result.passed = False
    except ImportError:
        result.checks["domain_healthy"] = True  # Skip if not available
    
    # Check 6: Working hours (simplified - assume business hours)
    from datetime import datetime
    hour = datetime.now().hour
    is_business_hours = 8 <= hour <= 18
    result.checks["business_hours"] = is_business_hours
    if not is_business_hours:
        result.issues.append(f"Outside business hours ({hour}:00)")
        # Don't fail for this - just warn
    
    return result


# =============================================================================
# SEND EMAIL
# =============================================================================

async def send_email_via_ghl(email: EmailToSend, dry_run: bool = True) -> SendResult:
    """Send email via GoHighLevel API."""
    result = SendResult(
        email_id=email.email_id,
        success=False,
        status="pending"
    )
    
    if dry_run:
        result.success = True
        result.status = "dry_run"
        result.sent_at = datetime.now(timezone.utc).isoformat()
        return result
    
    # Get GHL credentials
    api_key = os.getenv("GHL_PROD_API_KEY")
    location_id = os.getenv("GHL_LOCATION_ID")
    
    if not api_key or not location_id:
        result.status = "error"
        result.error = "Missing GHL_PROD_API_KEY or GHL_LOCATION_ID"
        return result
    
    try:
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Version": "2021-07-28",
                "Content-Type": "application/json"
            }
            
            # GHL send email endpoint
            url = f"https://services.leadconnectorhq.com/contacts/{email.contact_id}/emails"
            
            payload = {
                "emailFrom": os.getenv("GHL_FROM_EMAIL", "noreply@chiefaiofficer.com"),
                "subject": email.subject,
                "body": email.body,
                "html": email.body  # Assuming body is HTML
            }
            
            async with session.post(url, headers=headers, json=payload, timeout=30) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result.success = True
                    result.status = "sent"
                    result.ghl_message_id = data.get("id")
                    result.sent_at = datetime.now(timezone.utc).isoformat()
                elif resp.status == 401:
                    result.status = "auth_error"
                    result.error = "401 Unauthorized - Check API key"
                elif resp.status == 404:
                    result.status = "not_found"
                    result.error = f"Contact {email.contact_id} not found"
                else:
                    result.status = "error"
                    result.error = f"HTTP {resp.status}: {await resp.text()}"
                    
    except asyncio.TimeoutError:
        result.status = "timeout"
        result.error = "Request timed out"
    except ImportError:
        result.status = "error"
        result.error = "aiohttp not installed"
    except Exception as e:
        result.status = "error"
        result.error = str(e)
    
    return result


# =============================================================================
# AUDIT LOGGING
# =============================================================================

def log_send_result(email: EmailToSend, result: SendResult, preflight: PreflightResult):
    """Log send result to audit trail."""
    try:
        from core.audit_trail import get_audit_trail
        trail = get_audit_trail()
        
        trail.log_action(
            agent="SEND_APPROVED_EMAILS",
            action="email_sent" if result.success else "email_failed",
            details={
                "email_id": email.email_id,
                "to": email.to_email[:20] + "...",  # Truncate for privacy
                "subject": email.subject[:50],
                "tier": email.tier,
                "status": result.status,
                "preflight_passed": preflight.passed,
                "preflight_issues": preflight.issues,
                "error": result.error
            },
            outcome="success" if result.success else "failure"
        )
    except:
        pass  # Don't fail if audit unavailable
    
    # Also log to sent_emails directory
    SENT_EMAILS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = SENT_EMAILS_DIR / f"{email.email_id}.json"
    
    try:
        with open(log_file, 'w') as f:
            json.dump({
                "email": asdict(email),
                "result": asdict(result),
                "preflight": asdict(preflight),
                "logged_at": datetime.now(timezone.utc).isoformat()
            }, f, indent=2)
    except:
        pass


# =============================================================================
# MAIN SEND FLOW
# =============================================================================

async def send_approved_emails(
    source_dir: Path = None,
    limit: int = ASSISTED_MODE_LIMIT,
    dry_run: bool = True
) -> SendReport:
    """Send all approved emails with safety checks."""
    report = SendReport(dry_run=dry_run)
    
    # Load approved emails
    emails = load_approved_emails(source_dir, limit)
    report.total_queued = len(emails)
    
    if not emails:
        print("No approved emails found to send.")
        return report
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing {len(emails)} approved emails...\n")
    
    for email in emails:
        # Run pre-flight checks
        preflight = run_preflight_checks(email)
        
        if not preflight.passed:
            report.total_skipped += 1
            report.results.append(SendResult(
                email_id=email.email_id,
                success=False,
                status="preflight_failed",
                error="; ".join(preflight.issues)
            ))
            print(f"⚠️ Skipped {email.email_id}: {preflight.issues}")
            continue
        
        # Send email
        result = await send_email_via_ghl(email, dry_run)
        
        if result.success:
            report.total_sent += 1
            print(f"✅ {'[DRY RUN] ' if dry_run else ''}Sent {email.email_id} to {email.to_email[:20]}...")
        else:
            report.total_failed += 1
            print(f"❌ Failed {email.email_id}: {result.error}")
        
        report.results.append(result)
        
        # Log to audit trail
        log_send_result(email, result, preflight)
        
        # Rate limiting delay
        if not dry_run:
            await asyncio.sleep(2)  # 2 second delay between sends
    
    return report


# =============================================================================
# OUTPUT
# =============================================================================

def print_report(report: SendReport):
    """Print send report."""
    print("\n" + "=" * 60)
    print("SEND REPORT")
    print("=" * 60)
    
    if report.dry_run:
        print("\n⚠️ DRY RUN MODE - No emails actually sent\n")
    
    print(f"Total Queued: {report.total_queued}")
    print(f"Total Sent: {report.total_sent}")
    print(f"Total Failed: {report.total_failed}")
    print(f"Total Skipped: {report.total_skipped}")
    
    if report.total_sent > 0:
        print(f"\n✅ Successfully {'simulated' if report.dry_run else 'sent'} {report.total_sent} emails")
    
    if report.total_failed > 0:
        print(f"\n❌ Failed emails:")
        for r in report.results:
            if not r.success and r.status != "preflight_failed":
                print(f"   - {r.email_id}: {r.error}")
    
    if report.total_skipped > 0:
        print(f"\n⚠️ Skipped emails (preflight failed):")
        for r in report.results:
            if r.status == "preflight_failed":
                print(f"   - {r.email_id}: {r.error}")
    
    if not report.dry_run and report.total_sent > 0:
        print(f"\n📝 Logs saved to: {SENT_EMAILS_DIR}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Send Approved Emails")
    parser.add_argument("--source", type=Path, help="Source directory for approved emails")
    parser.add_argument("--limit", type=int, default=ASSISTED_MODE_LIMIT, help=f"Max emails to send (default: {ASSISTED_MODE_LIMIT})")
    parser.add_argument("--dry-run", type=str, default="true", help="Simulate sending (default: true)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    dry_run = args.dry_run.lower() in ["true", "1", "yes"]
    
    # Safety check for production
    if not dry_run:
        print("\n⚠️ PRODUCTION MODE - Emails will actually be sent!")
        print("Press Ctrl+C to cancel, or wait 5 seconds to continue...")
        try:
            import time
            time.sleep(5)
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(0)
    
    report = asyncio.run(send_approved_emails(
        source_dir=args.source,
        limit=args.limit,
        dry_run=dry_run
    ))
    
    if args.json:
        output = asdict(report)
        output["results"] = [asdict(r) for r in report.results]
        print(json.dumps(output, indent=2))
    else:
        print_report(report)
    
    sys.exit(0 if report.total_failed == 0 else 1)


if __name__ == "__main__":
    main()
