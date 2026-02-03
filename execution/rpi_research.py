#!/usr/bin/env python3
"""
RPI Research Phase - Frequent Intentional Compaction
=====================================================
Phase 1 of Research → Plan → Implement workflow.

Analyzes segmented leads to understand context for campaign creation
BEFORE generating campaigns. Based on Dex Horthy's FIC pattern.

Usage:
    python execution/rpi_research.py --input .hive-mind/segmented/segmented_2026-01-15.json
"""

import json
import argparse
import uuid
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import Counter
from dataclasses import dataclass, field, asdict
import sys

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

from core.event_log import log_event, EventType
from core.context import (
    EventThread, EventType as ContextEventType, 
    estimate_tokens, check_context_budget, trigger_compaction,
    create_phase_summary, ContextManager, serialize_thread
)

console = Console(force_terminal=True, legacy_windows=False)

# Global event thread for progress tracking
_event_thread: Optional[EventThread] = None


@dataclass
class TierFindings:
    """Research findings for a single tier."""
    lead_count: int
    common_titles: List[str]
    industries: Dict[str, int]
    top_sources: List[str]
    personalization_opportunities: List[str]
    recommended_angles: List[str]
    key_insight: str
    avg_icp_score: float = 0.0
    company_size_range: str = ""


@dataclass
class ResearchOutput:
    """Complete research output structure."""
    research_id: str
    created_at: str
    input_file: str
    segments_analyzed: int
    findings: Dict[str, Dict[str, Any]]
    cross_segment_insights: str
    recommended_campaign_strategy: str


def analyze_tier(leads: List[Dict], tier_name: str) -> TierFindings:
    """Analyze leads within a single tier."""
    if not leads:
        return TierFindings(
            lead_count=0,
            common_titles=[],
            industries={},
            top_sources=[],
            personalization_opportunities=[],
            recommended_angles=[],
            key_insight="No leads in this tier"
        )

    titles = Counter(lead.get("title", "Unknown") for lead in leads)
    industries = Counter(lead.get("industry", "Unknown") for lead in leads)
    sources = Counter(lead.get("source", "unknown") for lead in leads)
    
    company_sizes = [lead.get("company_size", 0) for lead in leads]
    min_size = min(company_sizes) if company_sizes else 0
    max_size = max(company_sizes) if company_sizes else 0
    
    icp_scores = [lead.get("icp_score", 0) for lead in leads]
    avg_score = sum(icp_scores) / len(icp_scores) if icp_scores else 0
    
    personalization_opps = _identify_personalization_opportunities(leads, sources)
    recommended_angles = _identify_recommended_angles(leads, sources, tier_name)
    key_insight = _generate_key_insight(leads, titles, sources, tier_name)
    
    return TierFindings(
        lead_count=len(leads),
        common_titles=[t for t, _ in titles.most_common(5)],
        industries=dict(industries.most_common(10)),
        top_sources=[s for s, _ in sources.most_common(3)],
        personalization_opportunities=personalization_opps,
        recommended_angles=recommended_angles,
        key_insight=key_insight,
        avg_icp_score=round(avg_score, 1),
        company_size_range=f"{min_size}-{max_size} employees"
    )


def _identify_personalization_opportunities(leads: List[Dict], sources: Counter) -> List[str]:
    """Identify personalization opportunities based on lead data."""
    opportunities = []
    
    has_company_size = sum(1 for l in leads if l.get("company_size", 0) > 0)
    if has_company_size > len(leads) * 0.5:
        opportunities.append("company_size_messaging")
    
    has_industry = sum(1 for l in leads if l.get("industry"))
    if has_industry > len(leads) * 0.5:
        opportunities.append("industry_specific_content")
    
    if "competitor_follower" in sources:
        opportunities.append("competitor_displacement")
    
    if "event_attendee" in sources:
        opportunities.append("event_reference")
    
    if "post_engager" in sources:
        opportunities.append("content_engagement_reference")
    
    if "group_member" in sources:
        opportunities.append("community_connection")
    
    title_keywords = set()
    for lead in leads:
        title = lead.get("title", "").lower()
        if "cro" in title or "chief revenue" in title:
            title_keywords.add("executive_level_messaging")
        if "vp" in title or "vice president" in title:
            title_keywords.add("leadership_value_props")
        if "director" in title:
            title_keywords.add("operational_efficiency_focus")
    
    opportunities.extend(list(title_keywords))
    return opportunities[:6]


def _identify_recommended_angles(leads: List[Dict], sources: Counter, tier_name: str) -> List[str]:
    """Identify recommended campaign angles."""
    angles = []
    
    if "competitor_follower" in sources:
        angles.append("competitor_displacement")
    
    if "event_attendee" in sources:
        angles.append("thought_leadership_followup")
    
    if "post_engager" in sources:
        angles.append("content_engagement_nurture")
    
    if "tier1" in tier_name.lower() or "vip" in tier_name.lower():
        angles.append("high_touch_personalized")
        angles.append("executive_briefing")
    
    if "tier2" in tier_name.lower():
        angles.append("value_proposition_focus")
        angles.append("case_study_led")
    
    if "tier3" in tier_name.lower():
        angles.append("educational_content")
        angles.append("automated_nurture")
    
    avg_company_size = sum(l.get("company_size", 0) for l in leads) / len(leads) if leads else 0
    if avg_company_size > 200:
        angles.append("enterprise_messaging")
    elif avg_company_size > 100:
        angles.append("mid_market_focus")
    else:
        angles.append("growth_stage_messaging")
    
    return list(set(angles))[:5]


def _generate_key_insight(leads: List[Dict], titles: Counter, sources: Counter, tier_name: str) -> str:
    """Generate a key insight summary for the tier."""
    top_title = titles.most_common(1)[0][0] if titles else "Unknown"
    top_source = sources.most_common(1)[0][0] if sources else "unknown"
    
    industries = Counter(lead.get("industry", "Unknown") for lead in leads)
    top_industry = industries.most_common(1)[0][0] if industries else "Unknown"
    
    insight_parts = [
        f"High concentration of {top_title} roles",
        f"primarily from {top_source} source",
        f"in {top_industry} industry."
    ]
    
    if "competitor_follower" in sources:
        insight_parts.append("Strong displacement opportunity exists.")
    elif "event_attendee" in sources:
        insight_parts.append("Event-driven engagement warrants timely follow-up.")
    
    return " ".join(insight_parts)


def generate_cross_segment_insights(tier_findings: Dict[str, TierFindings]) -> str:
    """Generate insights that span across all segments."""
    insights = []
    
    total_leads = sum(tf.lead_count for tf in tier_findings.values())
    tier1_count = sum(tf.lead_count for k, tf in tier_findings.items() if "tier1" in k.lower() or "vip" in k.lower())
    tier2_count = sum(tf.lead_count for k, tf in tier_findings.items() if "tier2" in k.lower())
    
    if tier1_count > 0:
        tier1_pct = (tier1_count / total_leads) * 100
        insights.append(f"VIP/Tier 1 leads represent {tier1_pct:.1f}% of the batch - prioritize for AE review.")
    
    all_sources = Counter()
    for tf in tier_findings.values():
        for source in tf.top_sources:
            all_sources[source] += 1
    
    if all_sources:
        dominant_source = all_sources.most_common(1)[0][0]
        insights.append(f"'{dominant_source}' is the dominant lead source across tiers.")
    
    all_industries = Counter()
    for tf in tier_findings.values():
        for ind, count in tf.industries.items():
            all_industries[ind] += count
    
    if all_industries:
        top_industries = [ind for ind, _ in all_industries.most_common(3)]
        insights.append(f"Top industries across segments: {', '.join(top_industries)}.")
    
    all_angles = set()
    for tf in tier_findings.values():
        all_angles.update(tf.recommended_angles)
    
    if "competitor_displacement" in all_angles:
        insights.append("Competitor displacement is viable across multiple tiers.")
    
    return " ".join(insights)


def generate_campaign_strategy(tier_findings: Dict[str, TierFindings], total_leads: int) -> str:
    """Generate recommended campaign strategy based on research."""
    strategies = []
    
    tier1_findings = {k: v for k, v in tier_findings.items() if "tier1" in k.lower() or "vip" in k.lower()}
    tier2_findings = {k: v for k, v in tier_findings.items() if "tier2" in k.lower()}
    tier3_findings = {k: v for k, v in tier_findings.items() if "tier3" in k.lower()}
    
    if tier1_findings:
        tier1_count = sum(tf.lead_count for tf in tier1_findings.values())
        strategies.append(f"TIER 1 ({tier1_count} leads): High-touch personalized sequences with AE involvement. "
                         "Each email should reference specific company/role context.")
    
    if tier2_findings:
        tier2_count = sum(tf.lead_count for tf in tier2_findings.values())
        strategies.append(f"TIER 2 ({tier2_count} leads): Value-proposition focused sequences with case studies. "
                         "Moderate personalization with source-based hooks.")
    
    if tier3_findings:
        tier3_count = sum(tf.lead_count for tf in tier3_findings.values())
        strategies.append(f"TIER 3 ({tier3_count} leads): Educational nurture sequences. "
                         "Template-based with minimal personalization, focus on volume.")
    
    all_sources = set()
    for tf in tier_findings.values():
        all_sources.update(tf.top_sources)
    
    if "competitor_follower" in all_sources:
        strategies.append("ANGLE: Create displacement-focused variant for competitor followers.")
    
    if "event_attendee" in all_sources:
        strategies.append("TIMING: Prioritize event attendees for immediate outreach while context is fresh.")
    
    return " | ".join(strategies)


def run_research(input_path: Path, context_manager: Optional[ContextManager] = None) -> ResearchOutput:
    """Run research analysis on segmented leads."""
    global _event_thread
    
    console.print(f"\n[bold blue][RESEARCH] RPI RESEARCH PHASE[/bold blue]")
    console.print(f"[dim]Analyzing: {input_path}[/dim]\n")
    
    # Initialize event thread for progress tracking
    research_id = str(uuid.uuid4())
    _event_thread = EventThread(f"research_{research_id[:8]}")
    _event_thread.add_event(ContextEventType.PHASE_STARTED, {
        'phase': 'research',
        'input_file': str(input_path)
    }, phase='research')
    
    with open(input_path) as f:
        data = json.load(f)
    
    # Check context budget before processing
    input_tokens = estimate_tokens(data)
    if not check_context_budget(input_tokens, max_budget=0.6):
        console.print(f"[yellow]⚠️ Large input detected ({input_tokens:,} tokens) - will compact results[/yellow]")
        _event_thread.add_event(ContextEventType.COMPACTION, {
            'reason': 'large_input',
            'input_tokens': input_tokens
        })
    
    if isinstance(data, list):
        leads = data
    else:
        leads = data.get("leads", data.get("data", []))
    
    console.print(f"[dim]Loaded {len(leads)} leads for analysis[/dim]")
    
    tiers_grouped: Dict[str, List[Dict]] = {}
    for lead in leads:
        tier = lead.get("icp_tier", "unknown")
        if tier not in tiers_grouped:
            tiers_grouped[tier] = []
        tiers_grouped[tier].append(lead)
    
    console.print(f"[dim]Found {len(tiers_grouped)} segments/tiers[/dim]")
    
    tier_findings: Dict[str, TierFindings] = {}
    findings_dict: Dict[str, Dict[str, Any]] = {}
    
    for tier_name, tier_leads in sorted(tiers_grouped.items()):
        console.print(f"[dim]  Analyzing {tier_name}: {len(tier_leads)} leads...[/dim]")
        findings = analyze_tier(tier_leads, tier_name)
        tier_findings[tier_name] = findings
        findings_dict[tier_name] = asdict(findings)
    
    cross_insights = generate_cross_segment_insights(tier_findings)
    campaign_strategy = generate_campaign_strategy(tier_findings, len(leads))
    
    output = ResearchOutput(
        research_id=research_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        input_file=str(input_path),
        segments_analyzed=len(tiers_grouped),
        findings=findings_dict,
        cross_segment_insights=cross_insights,
        recommended_campaign_strategy=campaign_strategy
    )
    
    # Add phase complete event
    _event_thread.add_event(ContextEventType.RESEARCH_COMPLETE, {
        'research_id': research_id,
        'segments_analyzed': len(tiers_grouped),
        'total_leads': len(leads)
    }, phase='research')
    
    # Trigger compaction if needed
    trigger_compaction(_event_thread)
    
    # Log context utilization
    output_tokens = estimate_tokens(asdict(output))
    console.print(f"[dim]Output tokens: {output_tokens:,} (compacted from {input_tokens:,} input tokens)[/dim]")
    
    return output


def print_research_summary(research: ResearchOutput):
    """Print human-readable research summary for review."""
    console.print("\n")
    console.print(Panel.fit(
        f"[bold blue][RESEARCH] COMPLETE - REVIEW BEFORE PLANNING[/bold blue]\n"
        f"Research ID: {research.research_id}\n"
        f"Segments Analyzed: {research.segments_analyzed}",
        title="Phase 1: Research"
    ))
    
    tier_table = Table(title="Segment Analysis Summary")
    tier_table.add_column("Tier", style="cyan")
    tier_table.add_column("Leads", style="green", justify="right")
    tier_table.add_column("Avg ICP", style="yellow", justify="right")
    tier_table.add_column("Top Titles", style="white")
    tier_table.add_column("Top Sources", style="magenta")
    
    for tier_name, findings in sorted(research.findings.items()):
        tier_table.add_row(
            tier_name,
            str(findings["lead_count"]),
            str(findings.get("avg_icp_score", "N/A")),
            ", ".join(findings["common_titles"][:2]) if findings["common_titles"] else "-",
            ", ".join(findings["top_sources"][:2]) if findings["top_sources"] else "-"
        )
    
    console.print(tier_table)
    
    console.print("\n[bold][PERSONALIZATION] Opportunities by Tier[/bold]")
    for tier_name, findings in sorted(research.findings.items()):
        opps = findings.get("personalization_opportunities", [])
        if opps:
            console.print(f"  [cyan]{tier_name}[/cyan]: {', '.join(opps[:4])}")
    
    console.print("\n[bold][ANGLES] Recommended by Tier[/bold]")
    for tier_name, findings in sorted(research.findings.items()):
        angles = findings.get("recommended_angles", [])
        if angles:
            console.print(f"  [cyan]{tier_name}[/cyan]: {', '.join(angles[:3])}")
    
    console.print("\n[bold][INSIGHTS] Key Findings[/bold]")
    for tier_name, findings in sorted(research.findings.items()):
        insight = findings.get("key_insight", "")
        if insight:
            console.print(f"  [cyan]{tier_name}[/cyan]: {insight}")
    
    console.print("\n[bold][CROSS-SEGMENT] Insights[/bold]")
    console.print(Markdown(research.cross_segment_insights))
    
    console.print("\n[bold][STRATEGY] Recommended Campaign Strategy[/bold]")
    for strategy in research.recommended_campaign_strategy.split(" | "):
        console.print(f"  • {strategy}")


def save_research(research: ResearchOutput, output_dir: Optional[Path] = None) -> Path:
    """Save research output to JSON file."""
    if output_dir is None:
        output_dir = Path(__file__).parent.parent / ".hive-mind" / "research"
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"research_{timestamp}.json"
    
    with open(output_path, "w") as f:
        json.dump(asdict(research), f, indent=2)
    
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="RPI Research Phase - Analyze segmented leads before campaign creation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python execution/rpi_research.py --input .hive-mind/segmented/segmented_2026-01-15.json
    python execution/rpi_research.py --input .hive-mind/segmented/latest.json --output .hive-mind/research/
        """
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to segmented leads JSON file"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: .hive-mind/research/)"
    )
    
    args = parser.parse_args()
    
    if not args.input.exists():
        console.print(f"[red]Error: Input file not found: {args.input}[/red]")
        sys.exit(1)
    
    research = run_research(args.input)
    
    print_research_summary(research)
    
    output_path = save_research(research, args.output)
    console.print(f"\n[green][OK] Research saved to {output_path}[/green]")
    
    try:
        log_event(EventType.RESEARCH_COMPLETED, {
            "research_id": research.research_id,
            "input_file": str(args.input),
            "segments_analyzed": research.segments_analyzed,
            "total_leads": sum(f["lead_count"] for f in research.findings.values())
        })
    except AttributeError:
        log_event(EventType.ENRICHMENT_COMPLETED, {
            "research_id": research.research_id,
            "input_file": str(args.input),
            "segments_analyzed": research.segments_analyzed,
            "operation": "rpi_research"
        })
    
    console.print("\n" + "=" * 60)
    console.print("[bold yellow][CHECKPOINT] Review Research Before Planning[/bold yellow]")
    console.print("=" * 60)
    console.print("""
Verify the research findings above before proceeding:

  ✓ Tier distribution makes sense
  ✓ Personalization opportunities are valid
  ✓ Recommended angles align with campaign goals
  ✓ Cross-segment insights are accurate

After review, proceed to PLAN phase:
""")
    console.print(f"  [cyan]python execution/rpi_plan.py --research {output_path}[/cyan]")
    console.print()


if __name__ == "__main__":
    main()
