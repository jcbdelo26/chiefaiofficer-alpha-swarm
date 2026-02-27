"""
Fix email copy for Instantly campaign t2_pipeline_20260217_v1.

Approach:
1. Delete old campaign (DRAFTED, no sends)
2. Create new campaign with {{personalized_subject}} / {{personalized_body}} template
3. Add each lead with unique custom_variables containing their personalized copy

Usage:
  python scripts/fix_email_copy.py --dry-run    # Preview changes
  python scripts/fix_email_copy.py --live        # Execute against Instantly API
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

# ── Campaign to replace ──────────────────────────────────────────────
OLD_CAMPAIGN_ID = "880398c5-e6f4-4ff0-9e8a-3f248607fb43"
OLD_CAMPAIGN_NAME = "t2_pipeline_20260217_v1"
NEW_CAMPAIGN_NAME = "t2_pipeline_20260217_v2"

# ── Sending accounts (from config/production.json) ───────────────────
SENDING_ACCOUNTS = [
    "chris.d@chiefaiofficerai.com",
    "chris.d@chiefaiofficerconsulting.com",
    "chris.d@chiefaiofficerguide.com",
    "chris.d@chiefaiofficerlabs.com",
    "chris.d@chiefaiofficerresources.com",
    "chris.d@chiefaiofficersolutions.com",
]

# ── Rewritten email copy per lead ────────────────────────────────────
# Following CRAFTER templates: TPL-001 to TPL-004 patterns
# Tone: Professional, conversational, helpful — never salesy
# CTA: Soft (reply-driven), no links (cold email deliverability)

LEADS = [
    {
        "email": "marcio.arnecke@apollo.io",
        "first_name": "Marcio",
        "last_name": "Arnecke",
        "company_name": "Apollo.io",
        "custom_variables": {
            "personalized_subject": "Marcio - your 2026 AI roadmap",
            "personalized_body": (
                "Hi Marcio,\n\n"
                "Most CMOs I speak with have a dozen AI tools across marketing "
                "but no unified strategy connecting them into a cohesive GTM engine.\n\n"
                "At Apollo.io, you've built the definitive prospecting platform. "
                "But even best-in-class teams I work with tell me the orchestration "
                "layer - connecting enriched data to personalized outreach to "
                "pipeline coaching - is still largely manual.\n\n"
                "We helped a similar SaaS CMO cut CAC by 30% by automating that "
                "handoff. The system learns what makes a good lead for their "
                "specific business and gets smarter over time.\n\n"
                "Would a 15-minute call to see how this fits Apollo.io's "
                "2026 roadmap make sense?\n\n"
                "Best,\n"
                "Chris Daigle\n"
                "CEO, Chiefaiofficer.com"
            ),
        },
    },
    {
        "email": "kenny.lee@apollo.io",
        "first_name": "Kenny",
        "last_name": "Lee",
        "company_name": "Apollo.io",
        "custom_variables": {
            "personalized_subject": "4x your demand gen qualification speed",
            "personalized_body": (
                "Hi Kenny,\n\n"
                "Running demand gen at a company that builds prospecting tools "
                "creates an interesting challenge - your audience expects your "
                "own outbound to be world-class.\n\n"
                "I work with VPs of Demand Gen who were burning 15-20 hours "
                "weekly on manual lead qualification before automating it with "
                "AI agents. Results: lead enrichment time dropped from 3 hours "
                "to 20 minutes, and ICP segmentation hit 85% accuracy within "
                "30 days.\n\n"
                "Curious how Apollo.io handles the gap between data enrichment "
                "and campaign execution internally. Happy to share what's "
                "working at similar SaaS companies if useful.\n\n"
                "No pitch - just genuinely curious.\n\n"
                "Best,\n"
                "Chris Daigle\n"
                "CEO, Chiefaiofficer.com"
            ),
        },
    },
    {
        "email": "dana.hensler@apollo.io",
        "first_name": "Dana",
        "last_name": "Hensler",
        "company_name": "Apollo.io",
        "custom_variables": {
            "personalized_subject": "Quick question about your acquisition motion",
            "personalized_body": (
                "Hi Dana,\n\n"
                "Managing acquisition sales at the company that builds the "
                "prospecting platform - I imagine you see both sides of the "
                "coin: what's possible with great data, and where the gaps "
                "still are.\n\n"
                "I'm curious: what does the handoff look like between enriched "
                "leads and your sales team? The Sales Directors I work with "
                "consistently say that gap - from data to action - is where "
                "pipeline velocity gets lost.\n\n"
                "We're helping SaaS sales teams automate that orchestration "
                "layer: AI agents that handle ICP scoring, personalized "
                "multi-channel outreach, and pipeline coaching so reps spend "
                "time selling, not researching.\n\n"
                "Happy to share what's working if useful. No pitch.\n\n"
                "Best,\n"
                "Chris Daigle\n"
                "CEO, Chiefaiofficer.com"
            ),
        },
    },
    {
        "email": "garris.yeung@apollo.io",
        "first_name": "Garris",
        "last_name": "Yeung",
        "company_name": "Apollo.io",
        "custom_variables": {
            "personalized_subject": "Scaling mid-market without scaling headcount",
            "personalized_body": (
                "Hi Garris,\n\n"
                "Scaling a mid-market book is interesting - the deal complexity "
                "needs enterprise-level research, but the volume demands "
                "SMB-level efficiency.\n\n"
                "A mid-market sales leader I worked with was facing the same "
                "challenge: great data pipeline, but reps were spending 3+ "
                "hours daily on research before actual selling. After deploying "
                "AI agents to handle ICP scoring and personalized outreach:\n\n"
                "- Lead research time: 3 hours to 20 minutes\n"
                "- Cost per qualified lead: down 60%\n"
                "- Pipeline coverage: 2x without adding headcount\n\n"
                "Worth a 10-minute call to explore whether something similar "
                "fits your mid-market motion?\n\n"
                "Best,\n"
                "Chris Daigle\n"
                "CEO, Chiefaiofficer.com"
            ),
        },
    },
    {
        "email": "paulaurrutia@apollo.io",
        "first_name": "Paula",
        "last_name": "Urrutia",
        "company_name": "Apollo.io",
        "custom_variables": {
            "personalized_subject": "How a SaaS team cut lead research by 80%",
            "personalized_body": (
                "Hi Paula,\n\n"
                "Thought you might find this relevant:\n\n"
                "A SaaS sales team similar to yours came to us with a familiar "
                "challenge - their SDRs were spending 3+ hours daily on manual "
                "research before any actual selling, even with solid enrichment "
                "tools in place.\n\n"
                "After implementing autonomous AI agents:\n"
                "- Lead enrichment time: 3 hours to 20 minutes\n"
                "- Data accuracy: 67% to 94%\n"
                "- Cost per qualified lead: down 60%\n\n"
                "The system gets smarter over time - it learns what makes a "
                "good lead for their specific business.\n\n"
                "If you're seeing similar gaps between data and action on "
                "your team, I can walk you through exactly how they set it "
                "up. Takes about 15 minutes.\n\n"
                "Worth a conversation?\n\n"
                "Best,\n"
                "Chris Daigle\n"
                "CEO, Chiefaiofficer.com"
            ),
        },
    },
]


async def main(dry_run: bool = True):
    from mcp_servers_instantly_mcp_server import AsyncInstantlyClient

    client = AsyncInstantlyClient()  # reads INSTANTLY_API_KEY from env

    try:
        # ── Step 1: Delete old campaign ──────────────────────────────
        print(f"\n{'[DRY RUN] ' if dry_run else ''}Step 1: Delete old campaign {OLD_CAMPAIGN_ID}")
        if not dry_run:
            result = await client.delete_campaign(OLD_CAMPAIGN_ID)
            if result.get("success"):
                print(f"  Deleted: {OLD_CAMPAIGN_NAME}")
            else:
                print(f"  WARNING: Delete returned: {result}")
                print("  Continuing anyway (campaign may already be deleted)...")
        else:
            print(f"  Would delete: {OLD_CAMPAIGN_NAME} ({OLD_CAMPAIGN_ID})")

        # ── Step 2: Create new campaign with merge variable template ─
        print(f"\n{'[DRY RUN] ' if dry_run else ''}Step 2: Create new campaign {NEW_CAMPAIGN_NAME}")

        schedule = {
            "timezone": "America/Detroit",
            "days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
            "startHour": 8,
            "endHour": 18,
        }

        if not dry_run:
            result = await client.create_campaign(
                name=NEW_CAMPAIGN_NAME,
                from_email=SENDING_ACCOUNTS[0],
                subject="{{personalized_subject}}",
                body="{{personalized_body}}",
                schedule=schedule,
                email_list=SENDING_ACCOUNTS,
            )
            if not result.get("success"):
                print(f"  ERROR: Campaign creation failed: {result.get('error')}")
                return
            new_campaign_id = result.get("data", {}).get("id")
            print(f"  Created: {NEW_CAMPAIGN_NAME} ({new_campaign_id})")
        else:
            new_campaign_id = "<new-campaign-id>"
            print(f"  Would create: {NEW_CAMPAIGN_NAME}")
            print(f"  Subject template: {{{{personalized_subject}}}}")
            print(f"  Body template: {{{{personalized_body}}}}")
            print(f"  Sending accounts: {len(SENDING_ACCOUNTS)}")

        # ── Step 3: Add leads with personalized custom variables ─────
        print(f"\n{'[DRY RUN] ' if dry_run else ''}Step 3: Add {len(LEADS)} leads with personalized copy")

        for i, lead in enumerate(LEADS, 1):
            subj = lead["custom_variables"]["personalized_subject"]
            print(f"\n  Lead {i}/{len(LEADS)}: {lead['first_name']} {lead['last_name']}")
            print(f"    Email: {lead['email']}")
            print(f"    Subject: {subj}")
            body_preview = lead["custom_variables"]["personalized_body"][:80] + "..."
            print(f"    Body preview: {body_preview}")

            if not dry_run:
                result = await client.add_leads(
                    new_campaign_id,
                    [lead],
                    skip_duplicates=False,
                )
                added = result.get("added", 0)
                errors = result.get("errors", [])
                if added > 0:
                    print(f"    Added successfully (ID: {result.get('lead_ids', ['?'])[0]})")
                elif errors:
                    print(f"    ERROR: {errors}")
                else:
                    print(f"    Skipped (may already exist)")

        # ── Summary ──────────────────────────────────────────────────
        print(f"\n{'=' * 60}")
        if dry_run:
            print("[DRY RUN] No changes made. Run with --live to execute.")
        else:
            print(f"DONE: Campaign {NEW_CAMPAIGN_NAME} ({new_campaign_id})")
            print(f"  Status: DRAFTED (not sending)")
            print(f"  Leads: {len(LEADS)}")
            print(f"  Next: Activate via Instantly UI or API when ready")

            # Save new campaign ID for reference
            ref = {
                "old_campaign_id": OLD_CAMPAIGN_ID,
                "old_campaign_name": OLD_CAMPAIGN_NAME,
                "new_campaign_id": new_campaign_id,
                "new_campaign_name": NEW_CAMPAIGN_NAME,
                "leads": len(LEADS),
                "action": "email_copy_fix",
            }
            ref_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                ".hive-mind", "campaign_fix_ref.json",
            )
            with open(ref_path, "w") as f:
                json.dump(ref, f, indent=2)
            print(f"  Reference saved: {ref_path}")

    finally:
        await client.close()


# ── Import helper: resolve the MCP server module ────────────────────
# The Instantly client lives in mcp-servers/instantly-mcp/server.py
# which isn't a standard Python package path
def _setup_import():
    mcp_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "mcp-servers", "instantly-mcp",
    )
    sys.path.insert(0, mcp_dir)
    # The module file is server.py — import it as a custom name
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "mcp_servers_instantly_mcp_server",
        os.path.join(mcp_dir, "server.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["mcp_servers_instantly_mcp_server"] = mod
    spec.loader.exec_module(mod)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fix email copy in Instantly campaign")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Preview changes without executing (default)")
    parser.add_argument("--live", action="store_true",
                        help="Execute changes against Instantly API")
    args = parser.parse_args()

    _setup_import()
    asyncio.run(main(dry_run=not args.live))
