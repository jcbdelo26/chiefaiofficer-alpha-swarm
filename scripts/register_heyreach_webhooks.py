#!/usr/bin/env python3
"""
HeyReach Webhook Utility
===========================
Verifies HeyReach API connectivity and lists available campaigns/accounts.

NOTE: HeyReach webhook CRUD is UI-ONLY (no API endpoints exist).
Webhooks must be created manually in HeyReach dashboard:
  Settings → Integrations → Webhooks → "View and Create"

Target URL for all webhooks:
  https://caio-swarm-dashboard-production.up.railway.app/webhooks/heyreach

This script still provides useful utilities:
  --check-auth     Verify API key is valid
  --list-campaigns List HeyReach campaigns (to get campaign IDs for config)
  --list-accounts  List connected LinkedIn accounts
  --print-guide    Print step-by-step webhook creation guide

Requires:
    HEYREACH_API_KEY env var
"""

import os
import sys
import json
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

try:
    import asyncio
    import aiohttp
except ImportError:
    print("ERROR: aiohttp required. Run: pip install aiohttp")
    sys.exit(1)

BASE_URL = "https://api.heyreach.io/api/public"
DASHBOARD_URL = "https://caio-swarm-dashboard-production.up.railway.app"
WEBHOOK_TARGET = f"{DASHBOARD_URL}/webhooks/heyreach"

# HeyReach supports 11 webhook events
WEBHOOK_EVENTS = [
    ("CONNECTION_REQUEST_SENT", "HIGH", "Tracks outreach progress"),
    ("CONNECTION_REQUEST_ACCEPTED", "HIGH", "Triggers warm email follow-up via Instantly"),
    ("MESSAGE_SENT", "MEDIUM", "Tracks message delivery"),
    ("MESSAGE_REPLY_RECEIVED", "HIGH", "Routes to RESPONDER agent for classification"),
    ("INMAIL_SENT", "LOW", "Activity logging"),
    ("INMAIL_REPLY_RECEIVED", "MEDIUM", "Routes to RESPONDER agent"),
    ("FOLLOW_SENT", "LOW", "Activity logging"),
    ("LIKED_POST", "LOW", "Activity logging"),
    ("VIEWED_PROFILE", "LOW", "Activity logging"),
    ("CAMPAIGN_COMPLETED", "HIGH", "Marks lead as LinkedIn-exhausted"),
    ("LEAD_TAG_UPDATED", "LOW", "Sync status to pipeline"),
]


def get_headers():
    api_key = os.getenv("HEYREACH_API_KEY")
    if not api_key:
        print("ERROR: HEYREACH_API_KEY env var not set")
        sys.exit(1)
    return {
        "X-API-KEY": api_key,
        "Content-Type": "application/json",
    }


async def check_auth():
    """Verify API key is valid."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/auth/CheckApiKey", headers=get_headers()) as resp:
            if resp.status == 200:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = await resp.text()
                print(f"  [+] API key valid (HTTP {resp.status})")
                if isinstance(data, (dict, list)) and data:
                    print(f"      Response: {json.dumps(data, indent=2)}")
            else:
                text = await resp.text()
                print(f"  [X] API key invalid (HTTP {resp.status})")
                print(f"      Response: {text[:500]}")


async def list_campaigns():
    """List all HeyReach campaigns with IDs."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE_URL}/campaign/GetAll",
            headers=get_headers(),
            json={"offset": 0, "limit": 50},
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                print(f"ERROR ({resp.status}): {text[:500]}")
                return

            data = await resp.json(content_type=None)
            campaigns = data if isinstance(data, list) else data.get("items", data.get("data", []))

            if not campaigns:
                print("No campaigns found.")
                print("\nCreate campaigns in HeyReach UI first:")
                print("  - CAIO Tier 1 — VP+ Decision Makers")
                print("  - CAIO Tier 2 — Directors & Managers")
                print("  - CAIO Tier 3 — Connection Only")
                return

            print(f"\n{'Name':<45} {'Status':<12} {'ID'}")
            print("-" * 100)
            for c in campaigns:
                name = c.get("name", "unknown")
                status = c.get("status", "unknown")
                cid = c.get("id", "unknown")
                print(f"{name:<45} {status:<12} {cid}")
            print(f"\nTotal: {len(campaigns)} campaign(s)")
            print("\nCopy the campaign IDs into config/production.json:")
            print('  "campaign_templates": { "tier_1": "<ID>", "tier_2": "<ID>", "tier_3": "<ID>" }')


async def list_accounts():
    """List connected LinkedIn accounts."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{BASE_URL}/linkedinaccount/GetAll",
            headers=get_headers(),
            json={},
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                print(f"ERROR ({resp.status}): {text[:500]}")
                return

            data = await resp.json(content_type=None)
            accounts = data if isinstance(data, list) else data.get("items", data.get("data", []))

            if not accounts:
                print("No LinkedIn accounts connected.")
                print("\nConnect your LinkedIn account in HeyReach:")
                print("  Dashboard → LinkedIn Accounts → Add Account")
                return

            print(f"\n{'Name':<35} {'Status':<15} {'ID'}")
            print("-" * 80)
            for a in accounts:
                name = a.get("name", a.get("firstName", "unknown"))
                status = a.get("status", a.get("connectionStatus", "unknown"))
                aid = a.get("id", "unknown")
                print(f"{name:<35} {status:<15} {aid}")
            print(f"\nTotal: {len(accounts)} account(s)")


def print_webhook_guide():
    """Print step-by-step guide for creating webhooks in HeyReach UI."""
    print("=" * 70)
    print("  HEYREACH WEBHOOK SETUP GUIDE (UI-Only)")
    print("=" * 70)
    print()
    print("HeyReach does NOT support webhook creation via API.")
    print("You must create webhooks manually in the HeyReach dashboard.")
    print()
    print("STEPS:")
    print("  1. Go to HeyReach dashboard (app.heyreach.io)")
    print("  2. Click gear icon (bottom-left) -> Integrations")
    print("  3. Find 'Webhooks' -> Click 'View and Create'")
    print("  4. For each event below, create a webhook:")
    print()
    print(f"  Webhook URL (same for all):")
    print(f"    {WEBHOOK_TARGET}")
    print()
    print(f"  {'Priority':<8} {'Event Type':<35} {'Why'}")
    print(f"  {'-'*8} {'-'*35} {'-'*40}")
    for event, priority, reason in WEBHOOK_EVENTS:
        marker = "***" if priority == "HIGH" else "   "
        print(f"  {marker}{priority:<5} {event:<35} {reason}")
    print()
    print("  *** = Create these FIRST (minimum viable setup)")
    print()
    print("CONFIGURATION PER WEBHOOK:")
    print("  - Name: 'CAIO - <Event Name>' (e.g., 'CAIO - Connection Accepted')")
    print(f"  - URL:  {WEBHOOK_TARGET}")
    print("  - Campaign: 'All campaigns' (or select specific ones)")
    print("  - Event: Select from dropdown")
    print()
    print("MINIMUM VIABLE (4 webhooks):")
    print("  1. CONNECTION_REQUEST_ACCEPTED  (triggers Instantly follow-up)")
    print("  2. MESSAGE_REPLY_RECEIVED       (routes to RESPONDER agent)")
    print("  3. CAMPAIGN_COMPLETED           (marks lead LinkedIn-exhausted)")
    print("  4. CONNECTION_REQUEST_SENT      (tracks outreach progress)")
    print()
    print("VERIFY:")
    print(f"  After creating, test by visiting:")
    print(f"    {DASHBOARD_URL}/webhooks/heyreach/health")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="HeyReach Utility — API verification + webhook setup guide",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
NOTE: Webhook creation is UI-only in HeyReach. Use --print-guide
for step-by-step instructions to create webhooks in the dashboard.
        """,
    )
    parser.add_argument("--check-auth", action="store_true", help="Verify API key is valid")
    parser.add_argument("--list-campaigns", action="store_true", help="List campaigns (get IDs for config)")
    parser.add_argument("--list-accounts", action="store_true", help="List connected LinkedIn accounts")
    parser.add_argument("--print-guide", action="store_true", help="Print webhook creation guide")
    args = parser.parse_args()

    print("HeyReach Utility")
    print(f"Dashboard: {DASHBOARD_URL}")
    print(f"API Base:  {BASE_URL}")
    print()

    if args.check_auth:
        asyncio.run(check_auth())
    elif args.list_campaigns:
        asyncio.run(list_campaigns())
    elif args.list_accounts:
        asyncio.run(list_accounts())
    elif args.print_guide:
        print_webhook_guide()
    else:
        # Default: check auth + print guide
        asyncio.run(check_auth())
        print()
        print_webhook_guide()


if __name__ == "__main__":
    main()
