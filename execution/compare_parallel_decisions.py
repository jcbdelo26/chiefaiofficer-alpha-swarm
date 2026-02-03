#!/usr/bin/env python3
"""
Parallel Mode Decision Comparison
==================================
Compares AI recommendations vs AE (human) decisions to validate alignment.

Usage:
    python execution/compare_parallel_decisions.py
    python execution/compare_parallel_decisions.py --ai-decisions FILE --ae-decisions FILE
    python execution/compare_parallel_decisions.py --json
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from collections import Counter

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
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None


# =============================================================================
# CONFIGURATION
# =============================================================================

HIVE_MIND_DIR = PROJECT_ROOT / ".hive-mind"
CAMPAIGNS_DIR = HIVE_MIND_DIR / "campaigns"
GATEKEEPER_DIR = HIVE_MIND_DIR / "gatekeeper"

# Exit criteria thresholds
MIN_AGREEMENT_RATE = 0.70
MAX_FALSE_POSITIVE_RATE = 0.15
MAX_FALSE_NEGATIVE_RATE = 0.10


@dataclass
class Decision:
    """A single decision (AI or human)."""
    lead_id: str
    approved: bool
    tier: Optional[str] = None
    confidence: Optional[float] = None
    reason: Optional[str] = None


@dataclass
class ComparisonResult:
    """Result of comparing AI vs human decisions."""
    lead_id: str
    ai_approved: bool
    ae_approved: bool
    agreement: bool
    decision_type: str  # "true_positive", "true_negative", "false_positive", "false_negative"
    ai_tier: Optional[str] = None
    ae_tier: Optional[str] = None


@dataclass
class ParallelModeReport:
    """Full parallel mode comparison report."""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_leads: int = 0
    ai_approved: int = 0
    ae_approved: int = 0
    agreements: int = 0
    disagreements: int = 0
    agreement_rate: float = 0.0
    true_positives: int = 0
    true_negatives: int = 0
    false_positives: int = 0  # AI approved, AE rejected
    false_negatives: int = 0  # AI rejected, AE approved
    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0
    comparisons: List[ComparisonResult] = field(default_factory=list)
    tier_accuracy: Dict[str, float] = field(default_factory=dict)
    ready_for_assisted: bool = False
    blocking_issues: List[str] = field(default_factory=list)


# =============================================================================
# DATA LOADING
# =============================================================================

def load_decisions(filepath: Path) -> List[Decision]:
    """Load decisions from a JSON file."""
    if not filepath.exists():
        return []
    
    try:
        with open(filepath) as f:
            data = json.load(f)
        
        decisions = []
        if isinstance(data, list):
            for item in data:
                decisions.append(Decision(
                    lead_id=item.get("lead_id") or item.get("id") or item.get("contact_id", "unknown"),
                    approved=item.get("approved") or item.get("ae_approved", False),
                    tier=item.get("tier") or item.get("icp_tier"),
                    confidence=item.get("confidence"),
                    reason=item.get("reason") or item.get("notes")
                ))
        elif isinstance(data, dict):
            for lead_id, item in data.items():
                if isinstance(item, dict):
                    decisions.append(Decision(
                        lead_id=lead_id,
                        approved=item.get("approved", False),
                        tier=item.get("tier"),
                        confidence=item.get("confidence"),
                        reason=item.get("reason")
                    ))
        
        return decisions
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return []


def find_decision_files() -> Tuple[Optional[Path], Optional[Path]]:
    """Find the most recent AI and AE decision files."""
    ai_file = None
    ae_file = None
    
    # Look for AI recommendations
    ai_patterns = [
        CAMPAIGNS_DIR / "ai_recommendations.json",
        CAMPAIGNS_DIR / "latest_recommendations.json",
        HIVE_MIND_DIR / "campaigns" / "*recommendations*.json",
    ]
    
    for pattern in ai_patterns:
        if "*" in str(pattern):
            matches = list(pattern.parent.glob(pattern.name))
            if matches:
                ai_file = max(matches, key=lambda p: p.stat().st_mtime)
                break
        elif pattern.exists():
            ai_file = pattern
            break
    
    # Look for AE decisions
    ae_patterns = [
        GATEKEEPER_DIR / "ae_decisions.json",
        GATEKEEPER_DIR / "approved" / "*.json",
        Path(".tmp") / "ae_review_sample.json",
    ]
    
    for pattern in ae_patterns:
        if "*" in str(pattern):
            if pattern.parent.exists():
                matches = list(pattern.parent.glob(pattern.name))
                if matches:
                    ae_file = max(matches, key=lambda p: p.stat().st_mtime)
                    break
        elif pattern.exists():
            ae_file = pattern
            break
    
    return ai_file, ae_file


# =============================================================================
# COMPARISON LOGIC
# =============================================================================

def compare_decisions(ai_decisions: List[Decision], ae_decisions: List[Decision]) -> ParallelModeReport:
    """Compare AI and AE decisions."""
    report = ParallelModeReport()
    
    # Create lookup by lead_id
    ai_by_id = {d.lead_id: d for d in ai_decisions}
    ae_by_id = {d.lead_id: d for d in ae_decisions}
    
    # Find common leads
    common_ids = set(ai_by_id.keys()) & set(ae_by_id.keys())
    
    if not common_ids:
        report.blocking_issues.append("No common leads found between AI and AE decisions")
        return report
    
    report.total_leads = len(common_ids)
    tier_correct = Counter()
    tier_total = Counter()
    
    for lead_id in common_ids:
        ai = ai_by_id[lead_id]
        ae = ae_by_id[lead_id]
        
        if ai.approved:
            report.ai_approved += 1
        if ae.approved:
            report.ae_approved += 1
        
        # Determine decision type
        if ai.approved and ae.approved:
            decision_type = "true_positive"
            report.true_positives += 1
            report.agreements += 1
        elif not ai.approved and not ae.approved:
            decision_type = "true_negative"
            report.true_negatives += 1
            report.agreements += 1
        elif ai.approved and not ae.approved:
            decision_type = "false_positive"
            report.false_positives += 1
            report.disagreements += 1
        else:  # not ai.approved and ae.approved
            decision_type = "false_negative"
            report.false_negatives += 1
            report.disagreements += 1
        
        # Track tier accuracy
        if ai.tier and ae.tier:
            tier_total[ai.tier] += 1
            if ai.tier == ae.tier:
                tier_correct[ai.tier] += 1
        
        report.comparisons.append(ComparisonResult(
            lead_id=lead_id,
            ai_approved=ai.approved,
            ae_approved=ae.approved,
            agreement=decision_type in ["true_positive", "true_negative"],
            decision_type=decision_type,
            ai_tier=ai.tier,
            ae_tier=ae.tier
        ))
    
    # Calculate rates
    if report.total_leads > 0:
        report.agreement_rate = report.agreements / report.total_leads
    
    if report.ai_approved > 0:
        report.false_positive_rate = report.false_positives / report.ai_approved
    
    ai_rejected = report.total_leads - report.ai_approved
    if ai_rejected > 0:
        report.false_negative_rate = report.false_negatives / ai_rejected
    
    # Calculate tier accuracy
    for tier in tier_total:
        if tier_total[tier] > 0:
            report.tier_accuracy[tier] = tier_correct[tier] / tier_total[tier]
    
    # Check exit criteria
    if report.agreement_rate < MIN_AGREEMENT_RATE:
        report.blocking_issues.append(
            f"Agreement rate {report.agreement_rate:.0%} < {MIN_AGREEMENT_RATE:.0%}"
        )
    if report.false_positive_rate > MAX_FALSE_POSITIVE_RATE:
        report.blocking_issues.append(
            f"False positive rate {report.false_positive_rate:.0%} > {MAX_FALSE_POSITIVE_RATE:.0%}"
        )
    if report.false_negative_rate > MAX_FALSE_NEGATIVE_RATE:
        report.blocking_issues.append(
            f"False negative rate {report.false_negative_rate:.0%} > {MAX_FALSE_NEGATIVE_RATE:.0%}"
        )
    
    report.ready_for_assisted = len(report.blocking_issues) == 0
    
    return report


# =============================================================================
# OUTPUT
# =============================================================================

def print_report_rich(report: ParallelModeReport):
    """Print report using rich library."""
    # Summary table
    table = Table(title="Parallel Mode Comparison Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="bold")
    table.add_column("Status")
    
    # Agreement rate
    agreement_status = "✅" if report.agreement_rate >= MIN_AGREEMENT_RATE else "❌"
    table.add_row(
        "Agreement Rate",
        f"{report.agreement_rate:.0%}",
        f"{agreement_status} (threshold: {MIN_AGREEMENT_RATE:.0%})"
    )
    
    # False positive rate
    fp_status = "✅" if report.false_positive_rate <= MAX_FALSE_POSITIVE_RATE else "❌"
    table.add_row(
        "False Positive Rate",
        f"{report.false_positive_rate:.0%}",
        f"{fp_status} (max: {MAX_FALSE_POSITIVE_RATE:.0%})"
    )
    
    # False negative rate
    fn_status = "✅" if report.false_negative_rate <= MAX_FALSE_NEGATIVE_RATE else "❌"
    table.add_row(
        "False Negative Rate",
        f"{report.false_negative_rate:.0%}",
        f"{fn_status} (max: {MAX_FALSE_NEGATIVE_RATE:.0%})"
    )
    
    console.print(table)
    console.print()
    
    # Decision breakdown
    table2 = Table(title="Decision Breakdown")
    table2.add_column("Category", style="cyan")
    table2.add_column("Count")
    table2.add_column("Description")
    
    table2.add_row("Total Leads", str(report.total_leads), "Leads compared")
    table2.add_row("AI Approved", str(report.ai_approved), "AI recommended approval")
    table2.add_row("AE Approved", str(report.ae_approved), "Human approved")
    table2.add_row("True Positives", str(report.true_positives), "[green]Both approved[/green]")
    table2.add_row("True Negatives", str(report.true_negatives), "[green]Both rejected[/green]")
    table2.add_row("False Positives", str(report.false_positives), "[yellow]AI approved, AE rejected[/yellow]")
    table2.add_row("False Negatives", str(report.false_negatives), "[red]AI rejected, AE approved[/red]")
    
    console.print(table2)
    console.print()
    
    # Tier accuracy if available
    if report.tier_accuracy:
        table3 = Table(title="Tier Accuracy")
        table3.add_column("Tier", style="cyan")
        table3.add_column("Accuracy")
        
        for tier, accuracy in sorted(report.tier_accuracy.items()):
            table3.add_row(tier, f"{accuracy:.0%}")
        
        console.print(table3)
        console.print()
    
    # Result
    if report.ready_for_assisted:
        console.print(Panel(
            "[green bold]✅ READY FOR ASSISTED MODE[/green bold]\n\n"
            "All parallel mode criteria passed. You can proceed to Assisted Mode by updating:\n"
            "[cyan]config/production.json[/cyan]: rollout_phase.current = \"assisted\"",
            title="Validation Result",
            style="green"
        ))
    else:
        blocking = "\n".join(f"• {issue}" for issue in report.blocking_issues)
        console.print(Panel(
            f"[red bold]❌ NOT READY FOR ASSISTED MODE[/red bold]\n\n"
            f"[yellow]Blocking Issues:[/yellow]\n{blocking}",
            title="Validation Result",
            style="red"
        ))


def print_report_plain(report: ParallelModeReport):
    """Print report without rich library."""
    print("\n" + "=" * 60)
    print("PARALLEL MODE COMPARISON SUMMARY")
    print("=" * 60)
    
    print(f"\nTotal Leads Compared: {report.total_leads}")
    print(f"AI Approved: {report.ai_approved}")
    print(f"AE Approved: {report.ae_approved}")
    
    print(f"\nAgreement Rate: {report.agreement_rate:.0%} (threshold: >= {MIN_AGREEMENT_RATE:.0%})")
    print(f"False Positive Rate: {report.false_positive_rate:.0%} (max: {MAX_FALSE_POSITIVE_RATE:.0%})")
    print(f"False Negative Rate: {report.false_negative_rate:.0%} (max: {MAX_FALSE_NEGATIVE_RATE:.0%})")
    
    print("\nDecision Breakdown:")
    print(f"  True Positives: {report.true_positives} (both approved)")
    print(f"  True Negatives: {report.true_negatives} (both rejected)")
    print(f"  False Positives: {report.false_positives} (AI approved, AE rejected)")
    print(f"  False Negatives: {report.false_negatives} (AI rejected, AE approved)")
    
    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    
    if report.ready_for_assisted:
        print("\n✅ READY FOR ASSISTED MODE")
        print("\nAll criteria passed. Update config/production.json:")
        print('   rollout_phase.current = "assisted"')
    else:
        print("\n❌ NOT READY FOR ASSISTED MODE")
        print("\nBlocking Issues:")
        for issue in report.blocking_issues:
            print(f"  • {issue}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Compare Parallel Mode Decisions")
    parser.add_argument("--ai-decisions", type=Path, help="Path to AI decisions JSON")
    parser.add_argument("--ae-decisions", type=Path, help="Path to AE decisions JSON")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show individual comparisons")
    args = parser.parse_args()
    
    # Find or use provided files
    if args.ai_decisions and args.ae_decisions:
        ai_file = args.ai_decisions
        ae_file = args.ae_decisions
    else:
        ai_file, ae_file = find_decision_files()
    
    if not ai_file or not ai_file.exists():
        print("❌ AI decisions file not found.")
        print("\nTo generate AI recommendations, run:")
        print("  python execution/crafter_campaign.py --input .hive-mind/enriched/latest.json")
        sys.exit(1)
    
    if not ae_file or not ae_file.exists():
        print("❌ AE decisions file not found.")
        print("\nTo collect AE decisions:")
        print("  1. Run: python execution/gatekeeper_queue.py --serve")
        print("  2. Have AE review and approve/reject leads")
        sys.exit(1)
    
    print(f"Loading AI decisions from: {ai_file}")
    print(f"Loading AE decisions from: {ae_file}")
    
    ai_decisions = load_decisions(ai_file)
    ae_decisions = load_decisions(ae_file)
    
    print(f"Found {len(ai_decisions)} AI decisions, {len(ae_decisions)} AE decisions")
    
    report = compare_decisions(ai_decisions, ae_decisions)
    
    if args.json:
        output = asdict(report)
        # Convert comparisons to serializable format
        output["comparisons"] = [asdict(c) for c in report.comparisons]
        print(json.dumps(output, indent=2))
    elif RICH_AVAILABLE:
        print_report_rich(report)
    else:
        print_report_plain(report)
    
    sys.exit(0 if report.ready_for_assisted else 1)


if __name__ == "__main__":
    main()
