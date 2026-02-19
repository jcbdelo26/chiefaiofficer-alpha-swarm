#!/usr/bin/env python3
"""
Lane B: Canary Live Training — Safe Emails for HoS Review Practice
===================================================================

Generates realistic shadow queue emails from SYNTHETIC leads so the
Head of Sales can practice the approve/reject workflow on the /sales
dashboard WITHOUT any risk to real contacts.

How it works:
  1. Creates synthetic Tier 1 ICP leads (fake companies, fake people)
  2. Runs them through the real CRAFTER to generate HoS-quality copy
  3. Pushes the emails to the Redis shadow queue with `canary: true`
  4. Emails appear on the /sales dashboard for HoS review
  5. OPERATOR refuses to dispatch any canary-tagged email

Usage:
    python scripts/canary_lane_b.py                  # Generate 5 canary emails (default)
    python scripts/canary_lane_b.py --count 3        # Generate 3 canary emails
    python scripts/canary_lane_b.py --clear           # Clear all canary emails from queue
    python scripts/canary_lane_b.py --status          # Show canary email statuses
"""

import os
import sys
import json
import uuid
import random
import argparse
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env', override=True)

# Fix Windows console encoding
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


# ---------------------------------------------------------------------------
# Synthetic Tier 1 ICP leads — realistic but CLEARLY FAKE
# All use @canary-training.internal domain (non-routable, safe)
# ---------------------------------------------------------------------------

CANARY_COMPANIES = [
    {
        "name": "Apex Digital Partners",
        "domain": "canary-training.internal",
        "industry": "Digital Marketing Agency",
        "employees": 180,
        "revenue": "$22M",
        "website": "https://apex-digital-partners.example.com",
    },
    {
        "name": "Summit Consulting Group",
        "domain": "canary-training.internal",
        "industry": "Management Consulting",
        "employees": 250,
        "revenue": "$35M",
        "website": "https://summit-consulting.example.com",
    },
    {
        "name": "Brightpath Staffing Solutions",
        "domain": "canary-training.internal",
        "industry": "Staffing & Recruiting",
        "employees": 120,
        "revenue": "$15M",
        "website": "https://brightpath-staffing.example.com",
    },
    {
        "name": "Ironclad Legal Advisors",
        "domain": "canary-training.internal",
        "industry": "Law Firm",
        "employees": 85,
        "revenue": "$18M",
        "website": "https://ironclad-legal.example.com",
    },
    {
        "name": "Meridian Growth Partners",
        "domain": "canary-training.internal",
        "industry": "Private Equity / Growth Consulting",
        "employees": 60,
        "revenue": "$12M",
        "website": "https://meridian-growth.example.com",
    },
    {
        "name": "Vanguard Media Agency",
        "domain": "canary-training.internal",
        "industry": "Marketing & Advertising Agency",
        "employees": 200,
        "revenue": "$28M",
        "website": "https://vanguard-media.example.com",
    },
    {
        "name": "Pinnacle Tech Solutions",
        "domain": "canary-training.internal",
        "industry": "IT Consulting",
        "employees": 300,
        "revenue": "$40M",
        "website": "https://pinnacle-tech.example.com",
    },
]

CANARY_PEOPLE = [
    {"first": "Sarah", "last": "Mitchell", "title": "VP of Revenue Operations"},
    {"first": "David", "last": "Chen", "title": "Chief Operating Officer"},
    {"first": "Rachel", "last": "Torres", "title": "VP of Client Services"},
    {"first": "Michael", "last": "Andersen", "title": "Managing Partner"},
    {"first": "Jennifer", "last": "Walsh", "title": "VP of Business Development"},
    {"first": "Brian", "last": "Nakamura", "title": "Chief Revenue Officer"},
    {"first": "Katherine", "last": "Rhodes", "title": "VP of Strategic Partnerships"},
    {"first": "Thomas", "last": "Gutierrez", "title": "Director of Operations"},
    {"first": "Amanda", "last": "Fitzgerald", "title": "VP of Marketing"},
    {"first": "Robert", "last": "Kimball", "title": "Chief Technology Officer"},
]


def _build_canary_lead(company: dict, person: dict) -> dict:
    """Build a synthetic lead dict that matches what CRAFTER expects."""
    first = person["first"]
    last = person["last"]
    email_local = f"{first.lower()}.{last.lower()}"
    return {
        "lead_id": f"canary_{uuid.uuid4().hex[:8]}",
        "email": f"{email_local}@{company['domain']}",
        "firstName": first,
        "lastName": last,
        "first_name": first,
        "last_name": last,
        "name": f"{first} {last}",
        "title": person["title"],
        "company": company["name"],
        "companyName": company["name"],
        "company_domain": company["domain"],
        "industry": company["industry"],
        "employee_count": company["employees"],
        "icp_tier": "tier_1",
        "icp_score": round(random.uniform(0.82, 0.97), 2),
        "source_type": "canary_training",
        "recommended_campaign": "",
        # Canary metadata
        "canary": True,
        "canary_company": company["name"],
    }


def generate_canary_emails(count: int = 5) -> list:
    """Generate canary training emails using the real CRAFTER."""
    from core.shadow_queue import push as shadow_push
    from execution.crafter_campaign import CampaignCrafter

    crafter = CampaignCrafter()
    shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)

    # Pick N unique company+person combos
    combos = []
    companies = list(CANARY_COMPANIES)
    people = list(CANARY_PEOPLE)
    random.shuffle(companies)
    random.shuffle(people)
    for i in range(min(count, len(companies), len(people))):
        combos.append((companies[i], people[i]))

    # If we need more than available combos, repeat with shuffled
    while len(combos) < count:
        combos.append((random.choice(CANARY_COMPANIES), random.choice(CANARY_PEOPLE)))

    generated = []
    for company, person in combos[:count]:
        lead = _build_canary_lead(company, person)

        # Use real CRAFTER to generate email copy
        email_data = crafter.generate_email(lead)

        # Build shadow email matching the pipeline format
        email_id = f"canary_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{lead['first_name'].lower()}_{lead['last_name'].lower()}_{uuid.uuid4().hex[:6]}"

        shadow_email = {
            "email_id": email_id,
            "to": lead["email"],
            "subject": email_data["subject_a"],
            "body": email_data["body"],
            "status": "pending",
            "source": "canary_lane_b",
            "direction": "outbound",
            "delivery_platform": "training",
            "delivery_path": "canary_lane_b_safe",
            "timestamp": datetime.now().isoformat() + "+00:00",
            "created_at": datetime.now().isoformat() + "+00:00",
            "tier": "tier_1",
            "angle": email_data.get("template", "t1_executive_buyin"),
            "icp_score": lead["icp_score"],
            "recipient_data": {
                "name": lead["name"],
                "email": lead["email"],
                "company": company["name"],
                "title": person["title"],
                "industry": company["industry"],
            },
            "context": {
                "source": "canary_lane_b",
                "source_type": "canary_training",
                "company_domain": company["domain"],
                "industry": company["industry"],
                "campaign_type": "canary_lane_b",
                "campaign_id": "canary_training",
            },
            # CANARY SAFETY FLAGS
            "canary": True,
            "canary_training": True,
            "canary_company": company["name"],
            "_do_not_dispatch": True,
        }

        # Push to Redis shadow queue (appears on /sales dashboard)
        shadow_push(shadow_email, shadow_dir=shadow_dir)
        generated.append(shadow_email)

        print(f"  [CANARY] {lead['name']:25} @ {company['name']:30} | {email_data['template']}")

    return generated


def show_canary_status():
    """Show current canary email statuses in Redis."""
    from core.shadow_queue import list_pending, _prefix, _get_redis

    prefix = _prefix()
    r = _get_redis()
    if not r:
        print("ERROR: Redis not connected")
        return

    # Scan for all canary emails
    canary_count = 0
    statuses = {"pending": 0, "approved": 0, "rejected": 0, "other": 0}

    for key in r.scan_iter(f"{prefix}:shadow:email:*"):
        data = json.loads(r.get(key))
        if not data.get("canary"):
            continue
        canary_count += 1
        status = data.get("status", "other")
        statuses[status] = statuses.get(status, 0) + 1
        to = data.get("to", "N/A")
        company = data.get("recipient_data", {}).get("company", "N/A")
        print(f"  [{status:10}] {to:40} | {company}")

    print(f"\nCanary emails: {canary_count}")
    print(f"  Pending:  {statuses['pending']}")
    print(f"  Approved: {statuses['approved']}")
    print(f"  Rejected: {statuses['rejected']}")


def clear_canary_emails():
    """Remove all canary emails from Redis shadow queue."""
    from core.shadow_queue import _prefix, _get_redis

    prefix = _prefix()
    r = _get_redis()
    if not r:
        print("ERROR: Redis not connected")
        return

    removed = 0
    pending_key = f"{prefix}:shadow:pending_ids"

    for key in r.scan_iter(f"{prefix}:shadow:email:*"):
        data = json.loads(r.get(key))
        if not data.get("canary"):
            continue
        email_id = data.get("email_id", key.decode().split(":")[-1])
        r.delete(key)
        r.zrem(pending_key, email_id)
        removed += 1

    print(f"Removed {removed} canary emails from Redis")


def main():
    parser = argparse.ArgumentParser(
        description="Lane B: Canary Live Training -- safe emails for HoS review"
    )
    parser.add_argument("--count", type=int, default=5, help="Number of canary emails to generate (default: 5)")
    parser.add_argument("--clear", action="store_true", help="Clear all canary emails from queue")
    parser.add_argument("--status", action="store_true", help="Show canary email statuses")
    args = parser.parse_args()

    print("=" * 70)
    print("  LANE B: Canary Live Training")
    print("  Safe emails for HoS review practice (no real contacts)")
    print("=" * 70)

    if args.clear:
        clear_canary_emails()
    elif args.status:
        show_canary_status()
    else:
        print(f"\nGenerating {args.count} canary training emails...\n")
        emails = generate_canary_emails(args.count)
        print(f"\n{len(emails)} canary emails pushed to shadow queue.")
        print("HoS can now review them at /sales dashboard.")
        print("\nSafety: All canary emails use @canary-training.internal domain")
        print("        and are flagged canary=true / _do_not_dispatch=true.")
        print("        OPERATOR will refuse to dispatch them even if approved.")

    print("=" * 70)


if __name__ == "__main__":
    main()
