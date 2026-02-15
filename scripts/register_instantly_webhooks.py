#!/usr/bin/env python3
"""
Register Instantly V2 Webhooks
===============================
Registers webhook subscriptions so Instantly sends events (reply, bounce, open,
unsubscribe) to the CAIO dashboard.

Usage:
    python scripts/register_instantly_webhooks.py
    python scripts/register_instantly_webhooks.py --list          # list existing
    python scripts/register_instantly_webhooks.py --delete-all    # remove all
    python scripts/register_instantly_webhooks.py --test          # test first webhook

Requires:
    INSTANTLY_API_KEY env var (V2 Bearer token)
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

BASE_URL = "https://api.instantly.ai/api/v2"
DASHBOARD_URL = "https://caio-swarm-dashboard-production.up.railway.app"

WEBHOOK_MAP = {
    "reply_received": "reply",
    "email_bounced": "bounce",
    "email_opened": "open",
    "lead_unsubscribed": "unsubscribe",
}


def get_headers():
    api_key = os.getenv("INSTANTLY_API_KEY")
    if not api_key:
        print("ERROR: INSTANTLY_API_KEY env var not set")
        sys.exit(1)
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


async def list_webhooks():
    """List all registered webhooks."""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/webhooks", headers=get_headers()) as resp:
            data = await resp.json()
            if resp.status != 200:
                print(f"ERROR ({resp.status}): {json.dumps(data, indent=2)}")
                return

            webhooks = data if isinstance(data, list) else data.get("items", data.get("data", data.get("webhooks", [])))
            if not webhooks:
                print("No webhooks registered.")
                return

            print(f"\n{'Event Type':<25} {'URL':<70} {'ID'}")
            print("-" * 120)
            for wh in webhooks:
                event = wh.get("event_type", wh.get("eventType", "unknown"))
                url = wh.get("target_hook_url", wh.get("webhook_url", "unknown"))
                wh_id = wh.get("id", "unknown")
                print(f"{event:<25} {url:<70} {wh_id}")
            print(f"\nTotal: {len(webhooks)} webhook(s)")


async def register_webhooks():
    """Register all 4 webhook subscriptions."""
    headers = get_headers()
    results = []

    async with aiohttp.ClientSession() as session:
        for event_type, path_suffix in WEBHOOK_MAP.items():
            target_url = f"{DASHBOARD_URL}/webhooks/instantly/{path_suffix}"

            payload = {
                "event_type": event_type,
                "target_hook_url": target_url,
            }

            async with session.post(f"{BASE_URL}/webhooks", headers=headers, json=payload) as resp:
                data = await resp.json()
                ok = resp.status in (200, 201)
                status = "OK" if ok else f"FAIL ({resp.status})"
                results.append({
                    "event": event_type,
                    "url": target_url,
                    "status": status,
                    "response": data,
                })
                symbol = "+" if ok else "X"
                print(f"  [{symbol}] {event_type:<25} -> /webhooks/instantly/{path_suffix}  [{status}]")

    success_count = sum(1 for r in results if "OK" in r["status"])
    print(f"\nRegistered: {success_count}/{len(WEBHOOK_MAP)} webhooks")

    if success_count < len(WEBHOOK_MAP):
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
        async with session.get(f"{BASE_URL}/webhooks", headers=headers) as resp:
            data = await resp.json()
            webhooks = data if isinstance(data, list) else data.get("items", data.get("data", data.get("webhooks", [])))

        if not webhooks:
            print("No webhooks to delete.")
            return

        for wh in webhooks:
            wh_id = wh.get("id")
            event = wh.get("event_type", wh.get("eventType", "unknown"))
            async with session.delete(f"{BASE_URL}/webhooks/{wh_id}", headers=headers) as resp:
                ok = resp.status in (200, 204)
                symbol = "+" if ok else "X"
                print(f"  [{symbol}] Deleted {event} (ID: {wh_id})")

        print(f"\nDeleted {len(webhooks)} webhook(s)")


async def test_first_webhook():
    """Send a test payload to the first registered webhook."""
    headers = get_headers()

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{BASE_URL}/webhooks", headers=headers) as resp:
            data = await resp.json()
            webhooks = data if isinstance(data, list) else data.get("items", data.get("data", data.get("webhooks", [])))

        if not webhooks:
            print("No webhooks to test. Register first.")
            return

        wh = webhooks[0]
        wh_id = wh.get("id")
        event = wh.get("event_type", wh.get("eventType", "unknown"))

        print(f"Testing webhook: {event} (ID: {wh_id})")
        async with session.post(f"{BASE_URL}/webhooks/{wh_id}/test", headers=headers) as resp:
            data = await resp.json()
            ok = resp.status in (200, 201)
            print(f"  Result: {'OK' if ok else f'FAIL ({resp.status})'}")
            print(f"  Response: {json.dumps(data, indent=2)}")


def main():
    parser = argparse.ArgumentParser(description="Register Instantly V2 Webhooks")
    parser.add_argument("--list", action="store_true", help="List existing webhooks")
    parser.add_argument("--delete-all", action="store_true", help="Delete all webhooks")
    parser.add_argument("--test", action="store_true", help="Test first webhook")
    args = parser.parse_args()

    print(f"Instantly V2 Webhook Manager")
    print(f"Dashboard: {DASHBOARD_URL}")
    print()

    if args.list:
        asyncio.run(list_webhooks())
    elif args.delete_all:
        asyncio.run(delete_all_webhooks())
    elif args.test:
        asyncio.run(test_first_webhook())
    else:
        print("Registering webhooks...")
        asyncio.run(register_webhooks())


if __name__ == "__main__":
    main()
