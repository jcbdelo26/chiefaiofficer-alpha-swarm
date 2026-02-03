#!/usr/bin/env python3
"""
RPI Implement Phase - Execute from Clean Plan
==============================================
Phase 3 of Research → Plan → Implement workflow.

Executes campaign generation from approved plan with fresh context.
This agent reads ONLY the plan - not raw research, not raw leads.

Based on Dex Horthy's Context Engineering methodology.

Usage:
    python execution/rpi_implement.py --plan .hive-mind/plans/plan_20260115.json
"""

import json
import argparse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress

from core.event_log import log_event, EventType
from core.context import (
    estimate_tokens, get_context_zone, ContextZone, compact_lead_batch,
    EventThread, EventType as ContextEventType,
    trigger_compaction, create_phase_summary, ContextManager
)

console = Console()

# Global event thread for progress tracking
_event_thread: Optional[EventThread] = None

# Dumb Zone protection settings
SMART_ZONE_BATCH_SIZE = 25


@dataclass
class GeneratedEmail:
    """A generated email in a sequence."""
    step: int
    delay_days: int
    subject_a: str
    subject_b: str
    body: str
    personalization_level: str


@dataclass
class GeneratedCampaign:
    """A generated campaign from the plan."""
    campaign_id: str
    tier: str
    template: str
    lead_count: int
    sequence: List[Dict[str, Any]]
    status: str
    created_at: str
    plan_id: str
    semantic_anchors: List[str]


# Email templates (simplified for implementation)
TEMPLATES = {
    "competitor_displacement": {
        "subject_a": "{first_name}, what {source} isn't showing you",
        "subject_b": "Beyond {source} for {company}",
        "body": """Hi {first_name},

I noticed you follow {source}'s updates on LinkedIn - smart move staying current on revenue intelligence.

Here's what I've been hearing from {title}s like yourself at companies your size:

"{source} shows us what happened... but we still can't predict what's going to happen next quarter."

At Chiefaiofficer.com, we're building the layer ABOVE traditional tools.

Worth a 15-min look?

Best,
Chris"""
    },
    "event_followup": {
        "subject_a": "Quick follow-up from {source}",
        "subject_b": "{first_name}, loved the {source} discussion",
        "body": """Hi {first_name},

I saw you attended {source} - great session.

Would love to share how {company} could apply some of these concepts.

15 minutes this week?

Chris"""
    },
    "thought_leadership": {
        "subject_a": "Your take on revenue operations",
        "subject_b": "{first_name}, re: your LinkedIn comment",
        "body": """Hi {first_name},

I came across your perspective on LinkedIn. Couldn't agree more.

We're working with companies like {company} on exactly this.

Quick 15-min chat?

Chris"""
    },
    "community_outreach": {
        "subject_a": "Fellow {source} member",
        "subject_b": "{first_name}, connecting from {source}",
        "body": """Hi {first_name},

I noticed we're both members of {source} - great community.

Given your role as {title} at {company}, thought you might be interested in what we're building.

Open to a quick 15-min call?

Chris"""
    },
    "website_visitor": {
        "subject_a": "You were on our site earlier",
        "subject_b": "Following up, {first_name}",
        "body": """Hi {first_name},

I noticed you were exploring Chiefaiofficer.com earlier.

I'd love to give you a personalized walkthrough.

Worth 15 minutes?

Chris"""
    }
}

FOLLOWUP_TEMPLATES = [
    {
        "delay_days": 3,
        "subject": "Quick follow-up, {first_name}",
        "body": """Hi {first_name},

Just bumping this up.

Here's a quick case study: [Case Study Link]

Still open to that 15-min conversation?

Chris"""
    },
    {
        "delay_days": 7,
        "subject": "{company} + Chiefaiofficer.com",
        "body": """Hi {first_name},

Companies like {company} are seeing 40% improvement in forecast accuracy.

Last ask: calendly.com/chiefaiofficer/intro

Chris"""
    },
    {
        "delay_days": 14,
        "subject": "Should I close the loop?",
        "body": """Hi {first_name},

I haven't heard back, so I'm guessing timing isn't right.

Feel free to reach out anytime.

Chris"""
    }
]


def load_leads_for_tier(plan: Dict[str, Any], tier: str) -> List[Dict[str, Any]]:
    """Load leads for a specific tier from the original segmented file."""
    
    segmented_dir = Path(__file__).parent.parent / ".hive-mind" / "segmented"
    if not segmented_dir.exists():
        return []
    
    segmented_files = sorted(segmented_dir.glob("*.json"), reverse=True)
    if not segmented_files:
        return []
    
    with open(segmented_files[0]) as f:
        data = json.load(f)
    
    leads = data.get("leads", [])
    tier_leads = [l for l in leads if l.get("icp_tier", "").lower() == tier.lower()]
    
    return tier_leads


def generate_email_sequence(
    tier_plan: Dict[str, Any], 
    lead: Dict[str, Any]
) -> List[GeneratedEmail]:
    """Generate email sequence for a single lead based on tier plan."""
    
    template_name = tier_plan.get("template_selection", "competitor_displacement")
    template = TEMPLATES.get(template_name, TEMPLATES["competitor_displacement"])
    
    vars = {
        "first_name": lead.get("name", "").split()[0] if lead.get("name") else "there",
        "company": lead.get("company", "your company"),
        "title": lead.get("title", "leader"),
        "source": lead.get("source_name", "the industry"),
    }
    
    sequence = []
    
    sequence.append(GeneratedEmail(
        step=1,
        delay_days=0,
        subject_a=template["subject_a"].format(**vars),
        subject_b=template["subject_b"].format(**vars),
        body=template["body"].format(**vars),
        personalization_level=tier_plan.get("personalization_depth", "medium")
    ))
    
    seq_length = tier_plan.get("sequence_length", 4)
    seq_timing = tier_plan.get("sequence_timing", [0, 3, 7, 14])
    
    for i, followup in enumerate(FOLLOWUP_TEMPLATES[:seq_length-1], start=2):
        delay = seq_timing[i-1] if i-1 < len(seq_timing) else followup["delay_days"]
        sequence.append(GeneratedEmail(
            step=i,
            delay_days=delay,
            subject_a=followup["subject"].format(**vars),
            subject_b=followup["subject"].format(**vars),
            body=followup["body"].format(**vars),
            personalization_level="light"
        ))
    
    return sequence


def generate_semantic_anchors(tier_plan: Dict[str, Any], lead_count: int) -> List[str]:
    """Generate semantic anchors for this campaign."""
    
    anchors = []
    
    anchors.append(
        f"TEMPLATE: {tier_plan.get('template_selection')} - {tier_plan.get('template_rationale')}"
    )
    
    hooks = tier_plan.get("personalization_hooks", [])
    if hooks:
        anchors.append(f"PERSONALIZATION: {tier_plan.get('personalization_depth')} depth using hooks: {', '.join(hooks[:3])}")
    
    anchors.append(f"A/B TEST: {tier_plan.get('ab_test_hypothesis')}")
    
    if tier_plan.get("requires_ae_review"):
        anchors.append(f"REVIEW: AE approval required for {lead_count} leads")
    
    return anchors


def generate_campaign_from_plan(
    plan: Dict[str, Any], 
    tier: str, 
    tier_plan: Dict[str, Any]
) -> Optional[GeneratedCampaign]:
    """Generate a campaign for a single tier based on the plan."""
    
    console.print(f"[dim]  Generating campaign for {tier}...[/dim]")
    
    leads = load_leads_for_tier(plan, tier)
    
    if not leads:
        leads = [{"name": "Sample Lead", "company": "Sample Co", "title": "VP Sales"}]
        console.print(f"[yellow]  Warning: No leads found for {tier}, using placeholder[/yellow]")
    
    lead_count = tier_plan.get("lead_count", len(leads))
    
    sample_sequence = generate_email_sequence(tier_plan, leads[0] if leads else {})
    anchors = generate_semantic_anchors(tier_plan, lead_count)
    
    campaign_id = str(uuid.uuid4())
    
    return GeneratedCampaign(
        campaign_id=campaign_id,
        tier=tier,
        template=tier_plan.get("template_selection", "competitor_displacement"),
        lead_count=lead_count,
        sequence=[asdict(e) for e in sample_sequence],
        status="pending_review" if tier_plan.get("requires_ae_review") else "ready",
        created_at=datetime.now(timezone.utc).isoformat(),
        plan_id=plan.get("plan_id", "unknown"),
        semantic_anchors=anchors
    )


def implement_plan(plan: Dict[str, Any]) -> List[GeneratedCampaign]:
    """Implement the approved plan by generating campaigns."""
    global _event_thread
    
    console.print(f"\n[bold green]🚀 RPI IMPLEMENT PHASE: Executing Plan[/bold green]")
    console.print(f"[dim]Plan ID: {plan.get('plan_id')}[/dim]")
    
    # Initialize event thread for progress tracking
    _event_thread = EventThread(f"implement_{plan.get('plan_id', 'unknown')[:8]}")
    _event_thread.add_event(ContextEventType.PHASE_STARTED, {
        'phase': 'implement',
        'plan_id': plan.get('plan_id', 'unknown')
    }, phase='implement')
    
    tokens = estimate_tokens(plan)
    zone = get_context_zone(tokens)
    
    if zone == ContextZone.SMART:
        console.print(f"[dim]Context zone: SMART ({tokens:,} tokens) - excellent[/dim]")
    else:
        console.print(f"[yellow]⚠️ Context zone: {zone.value} ({tokens:,} tokens)[/yellow]")
        _event_thread.add_event(ContextEventType.COMPACTION, {
            'reason': 'context_zone_warning',
            'zone': zone.value,
            'tokens': tokens
        })
    
    tier_plans = plan.get("tier_plans", {})
    campaigns = []
    
    with Progress() as progress:
        task = progress.add_task("Implementing plan...", total=len(tier_plans))
        
        for tier, tier_plan in tier_plans.items():
            try:
                campaign = generate_campaign_from_plan(plan, tier, tier_plan)
                if campaign:
                    campaigns.append(campaign)
                    
                    log_event(EventType.CAMPAIGN_CREATED, {
                        "campaign_id": campaign.campaign_id,
                        "tier": tier,
                        "template": campaign.template,
                        "lead_count": campaign.lead_count,
                        "plan_id": plan.get("plan_id"),
                        "rpi_phase": "implement"
                    })
                    
            except Exception as e:
                console.print(f"[red]Error generating campaign for {tier}: {e}[/red]")
            
            progress.update(task, advance=1)
    
    # Add phase complete event
    _event_thread.add_event(ContextEventType.PHASE_COMPLETE, {
        'phase': 'implement',
        'campaigns_generated': len(campaigns),
        'total_leads': sum(c.lead_count for c in campaigns)
    }, phase='implement')
    
    # Trigger compaction if needed
    trigger_compaction(_event_thread)
    
    console.print(f"\n[green]✅ Generated {len(campaigns)} campaigns from plan[/green]")
    
    return campaigns


def print_implementation_summary(campaigns: List[GeneratedCampaign], plan: Dict[str, Any]):
    """Print summary of implemented campaigns."""
    
    console.print("\n")
    console.print(Panel.fit(
        f"[bold green]🚀 RPI IMPLEMENTATION COMPLETE[/bold green]\n"
        f"Plan ID: {plan.get('plan_id')}\n"
        f"Campaigns Generated: {len(campaigns)}",
        title="Phase 3: Implement"
    ))
    
    table = Table(title="Generated Campaigns")
    table.add_column("Tier", style="cyan")
    table.add_column("Template", style="yellow")
    table.add_column("Leads", style="green", justify="right")
    table.add_column("Sequence", style="blue", justify="right")
    table.add_column("Status", style="magenta")
    
    for campaign in campaigns:
        status_style = "yellow" if campaign.status == "pending_review" else "green"
        table.add_row(
            campaign.tier,
            campaign.template,
            str(campaign.lead_count),
            f"{len(campaign.sequence)} emails",
            f"[{status_style}]{campaign.status}[/{status_style}]"
        )
    
    console.print(table)
    
    console.print("\n[bold]🔗 Semantic Anchors (for GATEKEEPER)[/bold]")
    for campaign in campaigns:
        console.print(f"\n  [cyan]{campaign.tier}[/cyan]:")
        for anchor in campaign.semantic_anchors:
            console.print(f"    • {anchor}")
    
    pending = [c for c in campaigns if c.status == "pending_review"]
    if pending:
        console.print(f"\n[yellow]⚠️ {len(pending)} campaign(s) require AE review[/yellow]")


def save_campaigns(campaigns: List[GeneratedCampaign], plan_id: str, output_dir: Optional[Path] = None) -> Path:
    """Save generated campaigns to JSON file."""
    
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / ".hive-mind" / "campaigns"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"campaigns_rpi_{timestamp}.json"
    
    campaigns_data = [asdict(c) for c in campaigns]
    
    with open(output_path, "w") as f:
        json.dump({
            "created_at": datetime.now(timezone.utc).isoformat(),
            "plan_id": plan_id,
            "campaign_count": len(campaigns),
            "total_leads": sum(c.lead_count for c in campaigns),
            "pending_review": sum(1 for c in campaigns if c.status == "pending_review"),
            "rpi_workflow": True,
            "campaigns": campaigns_data
        }, f, indent=2)
    
    return output_path


def main():
    parser = argparse.ArgumentParser(description="RPI Implement Phase - Execute approved plan")
    parser.add_argument("--plan", type=Path, required=True, help="Approved plan JSON file")
    parser.add_argument("--output", type=Path, default=None, help="Output directory")
    
    args = parser.parse_args()
    
    if not args.plan.exists():
        console.print(f"[red]Error: Plan file not found: {args.plan}[/red]")
        sys.exit(1)
    
    with open(args.plan) as f:
        plan = json.load(f)
    
    campaigns = implement_plan(plan)
    print_implementation_summary(campaigns, plan)
    
    output_path = save_campaigns(campaigns, plan.get("plan_id", "unknown"), args.output)
    console.print(f"\n[green]✅ Campaigns saved to {output_path}[/green]")
    
    pending = [c for c in campaigns if c.status == "pending_review"]
    
    console.print("\n" + "=" * 60)
    console.print("[bold green]✅ RPI WORKFLOW COMPLETE[/bold green]")
    console.print("=" * 60)
    
    if pending:
        console.print(f"\n[yellow]Next: Queue {len(pending)} campaign(s) for AE review:[/yellow]")
        console.print(f"  [cyan]python execution/gatekeeper_queue.py --input {output_path}[/cyan]")
    
    console.print("\nRPI Workflow Summary:")
    console.print("  ✓ Research: Compressed truth about lead batch")
    console.print("  ✓ Plan: Compressed intent into detailed strategy")
    console.print("  ✓ Implement: Executed plan with fresh context\n")


if __name__ == "__main__":
    main()
