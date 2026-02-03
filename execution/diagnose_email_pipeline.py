#!/usr/bin/env python3
"""
Email Pipeline Diagnostic Tool
==============================

Diagnoses issues with the pending email approval pipeline.
Checks all stages from RB2B webhook -> Intent Monitor -> Dashboard Queue.

Usage:
    python execution/diagnose_email_pipeline.py
    python execution/diagnose_email_pipeline.py --test-visitor  # Simulate a test visitor
"""

import os
import sys
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')


def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_section(title):
    print(f"\n--- {title} ---\n")


def check_directories():
    """Check that required directories exist and have content."""
    print_section("DIRECTORY CHECK")
    
    dirs_to_check = [
        (".hive-mind/shadow_mode_emails", "Dashboard pending emails"),
        (".hive-mind/gatekeeper_queue", "Gatekeeper backup queue"),
        (".hive-mind/website_intent", "Website intent visitor data"),
        (".hive-mind/metrics", "Pipeline metrics"),
        (".hive-mind/logs", "Log files"),
    ]
    
    print(f"{'Directory':<40} {'Exists':<8} {'Files':<8} {'Purpose'}")
    print("-" * 80)
    
    for rel_path, purpose in dirs_to_check:
        full_path = PROJECT_ROOT / rel_path
        exists = "YES" if full_path.exists() else "NO"
        file_count = len(list(full_path.glob("*"))) if full_path.exists() else 0
        print(f"{rel_path:<40} {exists:<8} {file_count:<8} {purpose}")


def check_pending_emails():
    """Check pending email counts and show samples."""
    print_section("PENDING EMAILS CHECK")
    
    shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
    
    if not shadow_dir.exists():
        print("[X] shadow_mode_emails directory does not exist!")
        print("    This is where dashboard reads pending approvals from.")
        return
    
    pending = []
    approved = []
    rejected = []
    
    for f in shadow_dir.glob("*.json"):
        try:
            with open(f) as fp:
                data = json.load(fp)
                status = data.get("status", "unknown")
                if status == "pending":
                    pending.append((f.name, data))
                elif status == "approved":
                    approved.append((f.name, data))
                elif status == "rejected":
                    rejected.append((f.name, data))
        except Exception as e:
            print(f"  Warning: Could not read {f.name}: {e}")
    
    print(f"  Pending:  {len(pending)}")
    print(f"  Approved: {len(approved)}")
    print(f"  Rejected: {len(rejected)}")
    
    if pending:
        print("\n  Sample pending emails:")
        for name, data in pending[:3]:
            print(f"    - {name}: {data.get('to')} - {data.get('subject', 'No subject')[:50]}")
    else:
        print("\n  [!] No pending emails in queue!")
        print("  This is why dashboard shows 'All caught up'")


def check_daily_limits():
    """Check daily email limits."""
    print_section("DAILY LIMITS CHECK")
    
    metrics_file = PROJECT_ROOT / ".hive-mind" / "metrics" / "daily_email_counts.json"
    
    if not metrics_file.exists():
        print("  No daily counts file yet (first run)")
        print("  Limit: 25/day in Live Mode")
        return
    
    try:
        with open(metrics_file) as f:
            data = json.load(f)
            
        print(f"  Date: {data.get('date', 'N/A')}")
        print(f"  Queued today: {data.get('queued', 0)}/25")
        print(f"  Sent today: {data.get('sent', 0)}")
        print(f"  Last queued: {data.get('last_queued_at', 'N/A')}")
        
        remaining = 25 - data.get('queued', 0)
        if remaining > 0:
            print(f"  [OK] {remaining} emails remaining today")
        else:
            print(f"  [X] Daily limit reached!")
    except Exception as e:
        print(f"  Error reading metrics: {e}")


def check_intent_monitor():
    """Check Website Intent Monitor state."""
    print_section("INTENT MONITOR CHECK")
    
    state_file = PROJECT_ROOT / ".hive-mind" / "website_intent" / "processed_visitors.json"
    
    if not state_file.exists():
        print("  No processed visitors yet")
        return
    
    try:
        with open(state_file) as f:
            data = json.load(f)
        
        processed_count = len(data.get("processed_ids", []))
        print(f"  Processed visitors: {processed_count}")
        print(f"  Last updated: {data.get('updated_at', 'N/A')}")
    except Exception as e:
        print(f"  Error: {e}")


def check_intent_log():
    """Check recent intent queue events."""
    print_section("RECENT QUEUE EVENTS")
    
    log_file = PROJECT_ROOT / ".hive-mind" / "logs" / "intent_queue.jsonl"
    
    if not log_file.exists():
        print("  No queue events logged yet")
        return
    
    try:
        with open(log_file) as f:
            lines = f.readlines()
        
        print(f"  Total events: {len(lines)}")
        
        if lines:
            print("\n  Last 5 events:")
            for line in lines[-5:]:
                try:
                    event = json.loads(line.strip())
                    print(f"    - {event.get('timestamp', 'N/A')[:19]} - {event.get('visitor_email', 'N/A')} (score: {event.get('intent_score', 'N/A')})")
                except Exception:
                    pass
    except Exception as e:
        print(f"  Error: {e}")


def check_webhook_config():
    """Check webhook configuration."""
    print_section("WEBHOOK CONFIG CHECK")
    
    env_vars = [
        ("RB2B_WEBHOOK_SECRET", "RB2B webhook signature verification"),
        ("SUPABASE_URL", "Supabase for webhook logging"),
        ("CLAY_API_KEY", "Clay enrichment"),
    ]
    
    for var, purpose in env_vars:
        value = os.getenv(var)
        status = "SET" if value else "NOT SET"
        print(f"  {var}: {status}")


async def test_visitor_processing():
    """Test the full pipeline with a simulated visitor."""
    print_section("TEST VISITOR SIMULATION")
    
    try:
        from core.website_intent_monitor import get_website_monitor
        
        monitor = get_website_monitor()
        
        test_visitor = {
            "visitor_id": f"test_diag_{datetime.now().strftime('%H%M%S')}",
            "email": "test.diagnostic@example.com",
            "first_name": "Test",
            "last_name": "Diagnostic",
            "linkedin_url": "https://linkedin.com/in/testdiagnostic",
            "company_name": "Diagnostic Corp",
            "company_domain": "gong.io",  # Matches Dani's previous company
            "job_title": "VP of Sales",
            "pages_viewed": [
                "/blog/how-pg-cut-product-development-time-22-percent-using-ai"
            ],
            "work_history": [
                {"company_name": "Gong", "company_domain": "gong.io", "years": "2021-2024"}
            ]
        }
        
        print("  Processing test visitor...")
        print(f"    Email: {test_visitor['email']}")
        print(f"    Company: {test_visitor['company_name']}")
        print(f"    Page: {test_visitor['pages_viewed'][0][:50]}...")
        
        result = await monitor.process_visitor(test_visitor)
        
        if result:
            print(f"\n  [OK] SUCCESS!")
            print(f"    Intent Score: {result.intent_score}")
            print(f"    ICP Tier: {result.icp_tier}")
            print(f"    Triggers Matched: {len(result.blog_triggers_matched)}")
            print(f"    Warm Connections: {len(result.warm_connections)}")
            print(f"    Queued for Approval: {result.queued_for_approval}")
            
            if result.generated_email:
                print(f"\n    Generated Email:")
                print(f"      Subject: {result.generated_email.get('subject', 'N/A')[:60]}")
            
            if result.queued_for_approval:
                print(f"\n  [OK] Email should now appear in dashboard!")
        else:
            print(f"\n  [!] No result (triggers didn't match or visitor filtered)")
            
    except Exception as e:
        print(f"  [X] Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Diagnose email pipeline issues")
    parser.add_argument("--test-visitor", action="store_true", help="Simulate a test visitor")
    args = parser.parse_args()
    
    print_header("CAIO Swarm Email Pipeline Diagnostic")
    
    check_directories()
    check_pending_emails()
    check_daily_limits()
    check_intent_monitor()
    check_intent_log()
    check_webhook_config()
    
    if args.test_visitor:
        asyncio.run(test_visitor_processing())
    else:
        print("\n[TIP] Run with --test-visitor to simulate a full pipeline test")
    
    print_header("DIAGNOSIS SUMMARY")
    
    # Check if we have issues
    shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
    has_pending = False
    if shadow_dir.exists():
        for f in shadow_dir.glob("*.json"):
            try:
                with open(f) as fp:
                    if json.load(fp).get("status") == "pending":
                        has_pending = True
                        break
            except Exception:
                pass
    
    if not has_pending:
        print("""
ISSUE IDENTIFIED:

No pending emails in queue. This is why the dashboard shows "All caught up".

FIXES APPLIED:
1. RB2B webhook now triggers Website Intent Monitor
2. Intent Monitor now writes to shadow_mode_emails (dashboard format)
3. Added daily limit enforcement (25/day)
4. Added /api/queue-status endpoint for monitoring

NEXT STEPS:
1. Restart the webhook server to pick up changes
2. Wait for RB2B to send new visitor events
3. Or run: python execution/diagnose_email_pipeline.py --test-visitor
4. Check dashboard: /api/queue-status
""")
    else:
        print(f"\n[OK] Pipeline appears healthy - pending emails in queue")


if __name__ == "__main__":
    main()
