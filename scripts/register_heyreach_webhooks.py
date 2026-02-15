#!/usr/bin/env python3
"""
Register HeyReach Webhooks
============================
Registers webhook subscriptions so HeyReach sends LinkedIn events
(connection accepted, reply, campaign completed, etc.) to the CAIO dashboard.

Usage:
    python scripts/register_heyreach_webhooks.py
    python scripts/register_heyreach_webhooks.py --list          # list existing
    python scripts/register_heyreach_webhooks.py --delete-all    # remove all
    python scripts/register_heyreach_webhooks.py --check-auth    # verify API key

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

# HeyReach supports 11 webhook events — register all of them
WEBHOOK_EVENTS = [
    "CONNECTION_REQUEST_SENT",
    "CONNECTION_REQUEST_ACCEPTED",
    "MESSAGE_SENT",
    "MESSAGE_REPLY_RECEIVED",
    "INMAIL_SENT",
    "INMAIL_REPLY_RECEIVED",
    "FOLLOW_SENT",
    "LIKED_POST",
    "VIEWED_PROFILE",
    "CAMPAIGN_COMPLETED",
    "LEAD_TAG_UPDATED",
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
                data = await resp.json()
                print(f"  [+] API key valid")
                print(f"      Response: {json.dumps(data, indent=2)}")
            else:
                text = await resp.text()
                print(f"  [X] API key invalid (HTTP {resp.status})")
                print(f"      Response: {text[:500]}")


async def list_webhooks():
    """List all registered webhooks."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/webhook/GetAll", headers=get_headers()) as resp:
            if resp.status != 200:
                text = await resp.text()
                print(f"ERROR ({resp.status}): {text[:500]}")
                return

            data = await resp.json()
            webhooks = data if isinstance(data, list) else data.get("items", data.get("data", []))

            if not webhooks:
                print("No webhooks registered.")
                return

            print(f"\n{'Event':<35} {'URL':<65} {'ID'}")
            print("-" * 130)
            for wh in webhooks:
                event = wh.get("eventType", wh.get("event_type", "unknown"))
                url = wh.get("url", wh.get("targetUrl", "unknown"))
                wh_id = wh.get("id", "unknown")
                print(f"{event:<35} {url:<65} {wh_id}")
            print(f"\nTotal: {len(webhooks)} webhook(s)")


async def register_webhooks():
    """Register webhook subscriptions for all 11 HeyReach events."""
    headers = get_headers()
    target_url = f"{DASHBOARD_URL}/webhooks/heyreach"
    results = []

    print(f"Target URL: {target_url}")
    print(f"Events: {len(WEBHOOK_EVENTS)}\n")

    async with aiohttp.ClientSession() as session:
        for event in WEBHOOK_EVENTS:
            # HeyReach webhook creation payload — field names may need
            # empirical validation as docs are sparse on exact format
            payload = {
                "url": target_url,
                "eventType": event,
            }

            async with session.post(
                f"{BASE_URL}/webhook/Create",
                headers=headers,
                json=payload,
            ) as resp:
                try:
                    data = await resp.json()
                except Exception:
                    data = {"raw": await resp.text()}

                ok = resp.status in (200, 201)
                status = "OK" if ok else f"FAIL ({resp.status})"
                results.append({
                    "event": event,
                    "status": status,
                    "response": data,
                })
                symbol = "+" if ok else "X"
                print(f"  [{symbol}] {event:<35} [{status}]")

    success_count = sum(1 for r in results if "OK" in r["status"])
    print(f"\nRegistered: {success_count}/{len(WEBHOOK_EVENTS)} webhooks")

    if success_count < len(WEBHOOK_EVENTS):
        print("\nFailed webhooks:")
        for r in results:
            if "OK" not in r["status"]:
                print(f"  {r['event']}: {json.dumps(r['response'], indent=2)}")

    return results


async def delete_all_webhooks():
    """Delete all registered webhooks."""
    headers = get_headers()

    async with aiohttp.ClientSession() as session:
        # First list
        async with session.get(f"{BASE_URL}/webhook/GetAll", headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                print(f"ERROR listing webhooks ({resp.status}): {text[:500]}")
                return

            data = await resp.json()
            webhooks = data if isinstance(data, list) else data.get("items", data.get("data", []))

        if not webhooks:
            print("No webhooks to delete.")
            return

        for wh in webhooks:
            wh_id = wh.get("id")
            event = wh.get("eventType", wh.get("event_type", "unknown"))

            async with session.delete(
                f"{BASE_URL}/webhook/Delete",
                headers=headers,
                params={"webhookId": wh_id},
            ) as resp:
                ok = resp.status in (200, 204)
                symbol = "+" if ok else "X"
                print(f"  [{symbol}] Deleted {event} (ID: {wh_id})")

        print(f"\nDeleted {len(webhooks)} webhook(s)")


def main():
    parser = argparse.ArgumentParser(description="Register HeyReach Webhooks")
    parser.add_argument("--list", action="store_true", help="List existing webhooks")
    parser.add_argument("--delete-all", action="store_true", help="Delete all webhooks")
    parser.add_argument("--check-auth", action="store_true", help="Verify API key")
    args = parser.parse_args()

    print("HeyReach Webhook Manager")
    print(f"Dashboard: {DASHBOARD_URL}")
    print(f"API Base:  {BASE_URL}")
    print()

    if args.check_auth:
        asyncio.run(check_auth())
    elif args.list:
        asyncio.run(list_webhooks())
    elif args.delete_all:
        asyncio.run(delete_all_webhooks())
    else:
        print("Registering webhooks...")
        asyncio.run(register_webhooks())


if __name__ == "__main__":
    main()
