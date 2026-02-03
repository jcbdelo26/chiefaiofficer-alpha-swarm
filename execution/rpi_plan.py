#!/usr/bin/env python3
"""
RPI Plan Phase - Compress Intent
================================
Phase 2 of Research → Plan → Implement workflow.

Creates detailed implementation plan from research summary.
This is the HIGH LEVERAGE POINT for human review.

Based on Dex Horthy's Context Engineering methodology.

Usage:
    python execution/rpi_plan.py --research .hive-mind/research/research_20260115.json
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
from rich.markdown import Markdown

from core.event_log import log_event, EventType
from core.context import (
    estimate_tokens, get_context_zone, ContextZone,
    EventThread, EventType as ContextEventType,
    trigger_compaction, create_phase_summary, ContextManager
)

console = Console()

# Global event thread for progress tracking
_event_thread: Optional[EventThread] = None


@dataclass
class TierPlan:
    """Plan for a single tier."""
    tier: str
    lead_count: int
    template_selection: str
    template_rationale: str
    personalization_depth: str  # deep, medium, light, minimal
    personalization_hooks: List[str]
    sequence_length: int
    sequence_timing: List[int]  # days between emails
    ab_test_hypothesis: str
    expected_open_rate: float
    expected_reply_rate: float
    requires_ae_review: bool
    special_instructions: List[str] = field(default_factory=list)


@dataclass
class CampaignPlan:
    """Complete campaign plan output."""
    plan_id: str
    created_at: str
    research_id: str
    research_file: str
    
    # Overall strategy
    total_leads: int
    campaign_strategy: str
    primary_angle: str
    
    # Tier-specific plans
    tier_plans: Dict[str, Dict[str, Any]]
    
    # Compliance
    compliance_checks: List[str]
    compliance_flags: List[str]
    
    # A/B Testing
    ab_test_strategy: str
    
    # Timing
    recommended_send_window: str
    sequence_overview: str
    
    # Review requirements
    requires_human_review: bool
    review_priority: str  # critical, high, medium, low
    review_focus_areas: List[str]
    
    # Metrics predictions
    predicted_metrics: Dict[str, float]


def select_template(tier: str, sources: List[str], angles: List[str]) -> tuple:
    """Select optimal template based on tier and available data."""
    
    templates = {
        "competitor_displacement": {
            "triggers": ["competitor_follower", "competitor_displacement"],
            "priority": 1
        },
        "event_followup": {
            "triggers": ["event_attendee", "thought_leadership_followup"],
            "priority": 2
        },
        "thought_leadership": {
            "triggers": ["post_engager", "content_engagement_nurture"],
            "priority": 3
        },
        "community_outreach": {
            "triggers": ["group_member", "community_connection"],
            "priority": 4
        },
        "website_visitor": {
            "triggers": ["website_visitor"],
            "priority": 5
        }
    }
    
    all_signals = sources + angles
    for template_name, config in templates.items():
        for trigger in config["triggers"]:
            if trigger in all_signals:
                rationale = f"Selected '{template_name}' because source/angle includes '{trigger}'"
                return template_name, rationale
    
    return "competitor_displacement", "Default template - no specific source match"


def determine_personalization_depth(tier: str, opportunities: List[str]) -> tuple:
    """Determine personalization depth based on tier and opportunities."""
    
    if "tier1" in tier.lower() or "vip" in tier.lower():
        depth = "deep"
        hooks = opportunities[:6]
    elif "tier2" in tier.lower():
        depth = "medium"
        hooks = opportunities[:4]
    elif "tier3" in tier.lower():
        depth = "light"
        hooks = opportunities[:2]
    else:
        depth = "minimal"
        hooks = opportunities[:1] if opportunities else []
    
    return depth, hooks


def generate_sequence_timing(tier: str, depth: str) -> tuple:
    """Generate email sequence timing based on tier."""
    
    if depth == "deep":
        return 4, [0, 4, 7, 14]
    elif depth == "medium":
        return 4, [0, 3, 7, 14]
    elif depth == "light":
        return 3, [0, 3, 10]
    else:
        return 2, [0, 7]


def generate_ab_hypothesis(tier: str, template: str, hooks: List[str]) -> str:
    """Generate A/B test hypothesis for the campaign."""
    
    hypotheses = {
        "competitor_displacement": [
            "Subject A (pain point) vs Subject B (transformation) - expect A higher open rate",
        ],
        "event_followup": [
            "Event name in subject vs event topic in subject - measure recognition",
        ],
        "thought_leadership": [
            "Quote their comment vs ask follow-up question - measure engagement",
        ],
        "community_outreach": [
            "Community connection vs professional value - measure trust building",
        ]
    }
    
    template_hypotheses = hypotheses.get(template, ["Standard A/B on subject line length"])
    return template_hypotheses[0]


def predict_metrics(tier: str, template: str, depth: str) -> Dict[str, float]:
    """Predict campaign performance metrics."""
    
    base_rates = {
        "tier_1": {"open": 0.55, "reply": 0.12, "meeting": 0.20},
        "tier_2": {"open": 0.50, "reply": 0.08, "meeting": 0.15},
        "tier_3": {"open": 0.45, "reply": 0.05, "meeting": 0.10},
        "tier_4": {"open": 0.40, "reply": 0.03, "meeting": 0.05},
    }
    
    tier_key = tier.lower().replace("_", "_")
    rates = base_rates.get("tier_3")
    for key in base_rates:
        if key in tier_key:
            rates = base_rates[key]
            break
    
    depth_multipliers = {"deep": 1.2, "medium": 1.0, "light": 0.9, "minimal": 0.8}
    multiplier = depth_multipliers.get(depth, 1.0)
    
    return {
        "predicted_open_rate": round(rates["open"] * multiplier, 2),
        "predicted_reply_rate": round(rates["reply"] * multiplier, 2),
        "predicted_meeting_rate": round(rates["meeting"] * multiplier, 2)
    }


def create_tier_plan(tier: str, findings: Dict[str, Any]) -> TierPlan:
    """Create a plan for a single tier."""
    
    lead_count = findings.get("lead_count", 0)
    sources = findings.get("top_sources", [])
    angles = findings.get("recommended_angles", [])
    opportunities = findings.get("personalization_opportunities", [])
    
    template, rationale = select_template(tier, sources, angles)
    depth, hooks = determine_personalization_depth(tier, opportunities)
    seq_length, seq_timing = generate_sequence_timing(tier, depth)
    ab_hypothesis = generate_ab_hypothesis(tier, template, hooks)
    metrics = predict_metrics(tier, template, depth)
    
    requires_review = "tier1" in tier.lower() or "tier2" in tier.lower()
    
    special = []
    if "enterprise_messaging" in angles:
        special.append("Use enterprise-level language and case studies")
    if "competitor_displacement" in angles:
        special.append("Reference competitor limitations without disparagement")
    if "high_touch_personalized" in angles:
        special.append("Each email should feel unique")
    
    return TierPlan(
        tier=tier,
        lead_count=lead_count,
        template_selection=template,
        template_rationale=rationale,
        personalization_depth=depth,
        personalization_hooks=hooks,
        sequence_length=seq_length,
        sequence_timing=seq_timing,
        ab_test_hypothesis=ab_hypothesis,
        expected_open_rate=metrics["predicted_open_rate"],
        expected_reply_rate=metrics["predicted_reply_rate"],
        requires_ae_review=requires_review,
        special_instructions=special
    )


def generate_compliance_checks(tier_plans: Dict[str, TierPlan]) -> tuple:
    """Generate compliance checklist and any flags."""
    
    checks = [
        "CAN-SPAM: Physical address included",
        "CAN-SPAM: Unsubscribe mechanism verified",
        "CAN-SPAM: Non-deceptive subject lines",
        "GDPR: Legitimate interest documented",
        "Brand Safety: No competitor disparagement",
    ]
    
    flags = []
    
    total_enterprise = 0
    for plan in tier_plans.values():
        if "enterprise" in str(plan.special_instructions).lower():
            total_enterprise += plan.lead_count
    
    if total_enterprise > 0:
        flags.append(f"⚠️ {total_enterprise} enterprise accounts - senior AE review needed")
    
    deep_count = sum(1 for p in tier_plans.values() if p.personalization_depth == "deep")
    if deep_count > 0:
        flags.append(f"⚠️ {deep_count} tier(s) require deep personalization")
    
    return checks, flags


def generate_campaign_plan(research: Dict[str, Any]) -> CampaignPlan:
    """Generate complete campaign plan from research."""
    global _event_thread
    
    # Initialize event thread for progress tracking
    plan_id = str(uuid.uuid4())
    _event_thread = EventThread(f"plan_{plan_id[:8]}")
    _event_thread.add_event(ContextEventType.PHASE_STARTED, {
        'phase': 'plan',
        'research_id': research.get('research_id', 'unknown')
    }, phase='plan')
    
    console.print("[dim]Generating tier-specific plans...[/dim]")
    
    tier_plans = {}
    findings = research.get("findings", {})
    
    for tier, tier_findings in findings.items():
        if tier_findings.get("lead_count", 0) > 0:
            plan = create_tier_plan(tier, tier_findings)
            tier_plans[tier] = asdict(plan)
    
    total_leads = sum(f.get("lead_count", 0) for f in findings.values())
    
    cross_insights = research.get("cross_segment_insights", "")
    if "competitor" in cross_insights.lower():
        primary_angle = "competitor_displacement"
    elif "event" in cross_insights.lower():
        primary_angle = "event_followup"
    else:
        primary_angle = "thought_leadership"
    
    tier_plan_objects = {k: TierPlan(**v) for k, v in tier_plans.items()}
    compliance_checks, compliance_flags = generate_compliance_checks(tier_plan_objects)
    
    ab_strategy = "Multi-variant testing: Tier 1 (messaging), Tier 2 (depth), Tier 3 (length)"
    send_window = "Tuesday-Thursday, 8:00-10:00 AM recipient local time"
    
    tier1_count = sum(1 for t in tier_plans if "tier1" in t.lower())
    tier2_count = sum(1 for t in tier_plans if "tier2" in t.lower())
    
    sequence_overview = f"Total tiers: {len(tier_plans)}, Tier 1: {tier1_count}, Tier 2: {tier2_count}"
    
    requires_review = any(p.get("requires_ae_review", False) for p in tier_plans.values())
    review_priority = "critical" if tier1_count > 0 else "high" if tier2_count > 0 else "medium"
    
    review_focus = [
        "Template selection matches lead source",
        "Personalization hooks are accurate",
        "Sequence timing aligns with tier",
        "A/B test hypotheses are valid",
        "No compliance concerns"
    ]
    
    # Add plan created event
    _event_thread.add_event(ContextEventType.PLAN_CREATED, {
        'plan_id': plan_id,
        'total_leads': total_leads,
        'tier_count': len(tier_plans),
        'requires_review': requires_review
    }, phase='plan')
    
    # Trigger compaction if needed
    trigger_compaction(_event_thread)
    
    predicted = {
        "avg_open_rate": round(
            sum(p.get("expected_open_rate", 0) * p.get("lead_count", 0) for p in tier_plans.values()) / 
            max(total_leads, 1), 2
        ),
        "avg_reply_rate": round(
            sum(p.get("expected_reply_rate", 0) * p.get("lead_count", 0) for p in tier_plans.values()) / 
            max(total_leads, 1), 2
        ),
        "total_expected_replies": round(
            sum(p.get("expected_reply_rate", 0) * p.get("lead_count", 0) for p in tier_plans.values())
        )
    }
    
    return CampaignPlan(
        plan_id=plan_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        research_id=research.get("research_id", "unknown"),
        research_file=research.get("input_file", ""),
        total_leads=total_leads,
        campaign_strategy=research.get("recommended_campaign_strategy", ""),
        primary_angle=primary_angle,
        tier_plans=tier_plans,
        compliance_checks=compliance_checks,
        compliance_flags=compliance_flags,
        ab_test_strategy=ab_strategy,
        recommended_send_window=send_window,
        sequence_overview=sequence_overview,
        requires_human_review=requires_review,
        review_priority=review_priority,
        review_focus_areas=review_focus,
        predicted_metrics=predicted
    )


def print_plan_summary(plan: CampaignPlan):
    """Print human-readable plan summary for review."""
    
    console.print("\n")
    console.print(Panel.fit(
        f"[bold yellow]📋 RPI PLAN PHASE - HIGH LEVERAGE REVIEW POINT[/bold yellow]\n"
        f"Plan ID: {plan.plan_id}\n"
        f"Total Leads: {plan.total_leads}\n"
        f"Review Priority: [bold]{plan.review_priority.upper()}[/bold]",
        title="Phase 2: Plan (REVIEW BEFORE IMPLEMENTING)"
    ))
    
    console.print("\n[bold]🎯 Campaign Strategy[/bold]")
    console.print(Markdown(plan.campaign_strategy[:500] if plan.campaign_strategy else "No strategy defined"))
    
    tier_table = Table(title="Tier-Specific Plans")
    tier_table.add_column("Tier", style="cyan")
    tier_table.add_column("Leads", style="green", justify="right")
    tier_table.add_column("Template", style="yellow")
    tier_table.add_column("Depth", style="magenta")
    tier_table.add_column("Open Rate", style="blue", justify="right")
    tier_table.add_column("AE Review", style="red")
    
    for tier, plan_data in sorted(plan.tier_plans.items()):
        tier_table.add_row(
            tier,
            str(plan_data.get("lead_count", 0)),
            plan_data.get("template_selection", "-"),
            plan_data.get("personalization_depth", "-"),
            f"{plan_data.get('expected_open_rate', 0):.0%}",
            "✓" if plan_data.get("requires_ae_review") else "-"
        )
    
    console.print(tier_table)
    
    console.print("\n[bold]📝 Template Rationale[/bold]")
    for tier, plan_data in sorted(plan.tier_plans.items()):
        console.print(f"  [cyan]{tier}[/cyan]: {plan_data.get('template_rationale', 'N/A')}")
    
    if plan.compliance_flags:
        console.print("\n[bold red]⚠️ Compliance Flags[/bold red]")
        for flag in plan.compliance_flags:
            console.print(f"  {flag}")
    
    console.print("\n[bold]📊 Predicted Metrics[/bold]")
    console.print(f"  Average Open Rate: {plan.predicted_metrics.get('avg_open_rate', 0):.0%}")
    console.print(f"  Average Reply Rate: {plan.predicted_metrics.get('avg_reply_rate', 0):.0%}")
    console.print(f"  Expected Replies: {plan.predicted_metrics.get('total_expected_replies', 0)}")


def save_plan(plan: CampaignPlan, output_dir: Optional[Path] = None) -> Path:
    """Save plan to JSON file."""
    
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / ".hive-mind" / "plans"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"plan_{timestamp}.json"
    
    with open(output_path, "w") as f:
        json.dump(asdict(plan), f, indent=2)
    
    return output_path


def main():
    parser = argparse.ArgumentParser(description="RPI Plan Phase - Create implementation plan")
    parser.add_argument("--research", type=Path, required=True, help="Research JSON file")
    parser.add_argument("--output", type=Path, default=None, help="Output directory")
    
    args = parser.parse_args()
    
    console.print("\n[bold yellow]📋 RPI PLAN PHASE: Compressing Intent[/bold yellow]")
    
    if not args.research.exists():
        console.print(f"[red]Error: Research file not found: {args.research}[/red]")
        sys.exit(1)
    
    with open(args.research) as f:
        research = json.load(f)
    
    tokens = estimate_tokens(research)
    zone = get_context_zone(tokens)
    console.print(f"[dim]Context zone: {zone.value} ({tokens:,} tokens)[/dim]")
    
    plan = generate_campaign_plan(research)
    print_plan_summary(plan)
    
    output_path = save_plan(plan, args.output)
    console.print(f"\n[green]✅ Plan saved to {output_path}[/green]")
    
    try:
        log_event(EventType.PLAN_CREATED, {"plan_id": plan.plan_id, "total_leads": plan.total_leads})
    except AttributeError:
        log_event(EventType.CAMPAIGN_CREATED, {"plan_id": plan.plan_id, "operation": "rpi_plan"})
    
    console.print("\n" + "=" * 70)
    console.print("[bold yellow]⏸️  HIGH LEVERAGE CHECKPOINT: Review Plan[/bold yellow]")
    console.print("=" * 70)
    console.print("\nAfter approval, proceed to IMPLEMENT:")
    console.print(f"  [cyan]python execution/rpi_implement.py --plan {output_path}[/cyan]\n")


if __name__ == "__main__":
    main()
