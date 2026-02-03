#!/usr/bin/env python3
"""
Priority #3: AI vs Human Decision Comparison
==============================================
Compare AI swarm decisions against human AE decisions to build trust.

Features:
- Log AI decisions with full reasoning
- Create approval queue for AE review
- Track agreement rate between AI and human
- Generate comparison analytics

Usage:
    python execution/priority_3_ai_vs_human_comparison.py --generate-queue 100
    python execution/priority_3_ai_vs_human_comparison.py --review
    python execution/priority_3_ai_vs_human_comparison.py --analyze
"""

import os
import sys
import json
import asyncio
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.progress import Progress

console = Console()


class AIDecisionType(Enum):
    """Types of AI decisions to compare."""
    QUALIFICATION = "qualification"  # Tier assignment
    OUTREACH = "outreach"           # Send email or not
    PERSONALIZATION = "personalization"  # Email content
    PRIORITY = "priority"           # Lead priority ranking


class HumanVerdict(Enum):
    """Human verdict on AI decision."""
    AGREE = "agree"
    DISAGREE = "disagree"
    PARTIAL = "partial"
    NOT_REVIEWED = "not_reviewed"


@dataclass
class AIDecision:
    """A single AI decision awaiting human review."""
    decision_id: str
    decision_type: AIDecisionType
    lead_id: str
    lead_name: str
    lead_company: str
    lead_tier: str
    
    # AI's decision
    ai_recommendation: str
    ai_confidence: float
    ai_reasoning: str
    ai_factors: Dict[str, Any]
    
    # Human review
    human_verdict: HumanVerdict = HumanVerdict.NOT_REVIEWED
    human_decision: Optional[str] = None
    human_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    priority: int = 2  # 1=high, 2=medium, 3=low
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "decision_type": self.decision_type.value,
            "human_verdict": self.human_verdict.value
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AIDecision':
        data["decision_type"] = AIDecisionType(data["decision_type"])
        data["human_verdict"] = HumanVerdict(data["human_verdict"])
        return cls(**data)


@dataclass
class ComparisonMetrics:
    """Metrics comparing AI vs human decisions."""
    total_decisions: int = 0
    reviewed: int = 0
    agree: int = 0
    disagree: int = 0
    partial: int = 0
    
    # By decision type
    by_type: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
    # By tier
    by_tier: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
    # Confidence analysis
    avg_confidence_agree: float = 0
    avg_confidence_disagree: float = 0
    
    def agreement_rate(self) -> float:
        """Calculate overall agreement rate."""
        if self.reviewed == 0:
            return 0
        return (self.agree + self.partial * 0.5) / self.reviewed * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "agreement_rate": self.agreement_rate()
        }


class ComparisonQueue:
    """
    Queue of AI decisions awaiting human review.
    
    Enables side-by-side comparison of AI vs AE decisions.
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or Path(".hive-mind/comparisons")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.queue_file = self.storage_dir / "review_queue.json"
        self.archive_dir = self.storage_dir / "archive"
        self.archive_dir.mkdir(exist_ok=True)
        
        self.decisions: List[AIDecision] = []
        self._load_queue()
    
    def _load_queue(self):
        """Load queue from disk."""
        if self.queue_file.exists():
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.decisions = [AIDecision.from_dict(d) for d in data]
    
    def _save_queue(self):
        """Save queue to disk."""
        with open(self.queue_file, 'w', encoding='utf-8') as f:
            json.dump([d.to_dict() for d in self.decisions], f, indent=2)
    
    def add_decision(self, decision: AIDecision):
        """Add a decision to the review queue."""
        self.decisions.append(decision)
        self._save_queue()
    
    def get_pending(self, limit: int = 10) -> List[AIDecision]:
        """Get pending decisions for review."""
        pending = [d for d in self.decisions if d.human_verdict == HumanVerdict.NOT_REVIEWED]
        # Sort by priority, then by creation time
        pending.sort(key=lambda x: (x.priority, x.created_at))
        return pending[:limit]
    
    def submit_review(
        self,
        decision_id: str,
        verdict: HumanVerdict,
        human_decision: str,
        notes: str = "",
        reviewer: str = "AE"
    ) -> bool:
        """Submit a human review for a decision."""
        for decision in self.decisions:
            if decision.decision_id == decision_id:
                decision.human_verdict = verdict
                decision.human_decision = human_decision
                decision.human_notes = notes
                decision.reviewed_by = reviewer
                decision.reviewed_at = datetime.now(timezone.utc).isoformat()
                self._save_queue()
                return True
        return False
    
    def calculate_metrics(self) -> ComparisonMetrics:
        """Calculate comparison metrics."""
        metrics = ComparisonMetrics()
        metrics.total_decisions = len(self.decisions)
        
        confidence_agree = []
        confidence_disagree = []
        
        for d in self.decisions:
            if d.human_verdict != HumanVerdict.NOT_REVIEWED:
                metrics.reviewed += 1
                
                if d.human_verdict == HumanVerdict.AGREE:
                    metrics.agree += 1
                    confidence_agree.append(d.ai_confidence)
                elif d.human_verdict == HumanVerdict.DISAGREE:
                    metrics.disagree += 1
                    confidence_disagree.append(d.ai_confidence)
                elif d.human_verdict == HumanVerdict.PARTIAL:
                    metrics.partial += 1
                
                # By type
                dtype = d.decision_type.value
                if dtype not in metrics.by_type:
                    metrics.by_type[dtype] = {"agree": 0, "disagree": 0, "partial": 0}
                if d.human_verdict == HumanVerdict.AGREE:
                    metrics.by_type[dtype]["agree"] += 1
                elif d.human_verdict == HumanVerdict.DISAGREE:
                    metrics.by_type[dtype]["disagree"] += 1
                else:
                    metrics.by_type[dtype]["partial"] += 1
                
                # By tier
                tier = d.lead_tier
                if tier not in metrics.by_tier:
                    metrics.by_tier[tier] = {"agree": 0, "disagree": 0, "partial": 0}
                if d.human_verdict == HumanVerdict.AGREE:
                    metrics.by_tier[tier]["agree"] += 1
                elif d.human_verdict == HumanVerdict.DISAGREE:
                    metrics.by_tier[tier]["disagree"] += 1
                else:
                    metrics.by_tier[tier]["partial"] += 1
        
        if confidence_agree:
            metrics.avg_confidence_agree = sum(confidence_agree) / len(confidence_agree)
        if confidence_disagree:
            metrics.avg_confidence_disagree = sum(confidence_disagree) / len(confidence_disagree)
        
        return metrics
    
    def archive_reviewed(self):
        """Archive all reviewed decisions."""
        reviewed = [d for d in self.decisions if d.human_verdict != HumanVerdict.NOT_REVIEWED]
        
        if reviewed:
            archive_file = self.archive_dir / f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(archive_file, 'w', encoding='utf-8') as f:
                json.dump([d.to_dict() for d in reviewed], f, indent=2)
            
            # Remove from active queue
            self.decisions = [d for d in self.decisions if d.human_verdict == HumanVerdict.NOT_REVIEWED]
            self._save_queue()
            
            return len(reviewed)
        return 0


def generate_sample_decisions(count: int) -> List[AIDecision]:
    """Generate sample AI decisions for testing."""
    from execution.priority_1_simulation_harness import generate_lead_batch
    
    leads = generate_lead_batch(count)
    decisions = []
    
    for lead in leads:
        # Simulate AI qualification decision
        icp_score = lead.get("title_score", 10) * 2 + (20 if lead.get("company", {}).get("employee_count", 0) > 50 else 5)
        tier = "tier_1" if icp_score >= 80 else "tier_2" if icp_score >= 60 else "tier_3" if icp_score >= 40 else "tier_4"
        
        confidence = 0.65 + (icp_score / 100 * 0.30)
        
        decision = AIDecision(
            decision_id=f"dec_{uuid.uuid4().hex[:8]}",
            decision_type=AIDecisionType.QUALIFICATION,
            lead_id=lead.get("lead_id"),
            lead_name=lead.get("name"),
            lead_company=lead.get("company", {}).get("name", "Unknown"),
            lead_tier=tier,
            ai_recommendation=f"Assign to {tier.upper()}" + (" - Prioritize for outreach" if tier == "tier_1" else ""),
            ai_confidence=min(confidence, 0.98),
            ai_reasoning=generate_reasoning(lead, tier, icp_score),
            ai_factors={
                "icp_score": icp_score,
                "title_level": lead.get("title_level"),
                "company_size": lead.get("company", {}).get("employee_count"),
                "source_type": lead.get("source_type"),
                "has_email": lead.get("email") is not None
            },
            priority=1 if tier == "tier_1" else 2 if tier == "tier_2" else 3
        )
        decisions.append(decision)
    
    return decisions


def generate_reasoning(lead: Dict, tier: str, score: int) -> str:
    """Generate AI reasoning explanation."""
    reasons = []
    
    title = lead.get("title", "")
    if "VP" in title or "C" in title[:2]:
        reasons.append(f"Senior title ({title}) indicates decision-making authority")
    
    size = lead.get("company", {}).get("employee_count", 0)
    if 51 <= size <= 500:
        reasons.append(f"Company size ({size}) is ideal for our solution")
    elif size > 500:
        reasons.append(f"Enterprise company ({size} employees) - larger deal potential")
    
    source = lead.get("source_type", "")
    if source == "competitor_follower":
        reasons.append("Following competitor suggests active interest in solutions")
    elif source == "demo_requester":
        reasons.append("Demo request shows high intent")
    
    if lead.get("email"):
        reasons.append("Valid email available for outreach")
    else:
        reasons.append("Missing email - needs enrichment")
    
    return f"ICP Score: {score}. " + " | ".join(reasons) if reasons else f"ICP Score: {score}. Standard qualification."


def interactive_review(queue: ComparisonQueue):
    """Interactive review session for AE."""
    pending = queue.get_pending(limit=5)
    
    if not pending:
        console.print("[yellow]No pending decisions to review.[/yellow]")
        return
    
    console.print(Panel(
        f"[bold blue]AI Decision Review Queue[/bold blue]\n"
        f"Pending reviews: {len([d for d in queue.decisions if d.human_verdict == HumanVerdict.NOT_REVIEWED])}"
    ))
    
    for i, decision in enumerate(pending, 1):
        console.print(f"\n{'='*60}")
        console.print(f"[bold]Decision {i}/{len(pending)}[/bold]")
        console.print(f"{'='*60}")
        
        # Show lead info
        info_table = Table(show_header=False, box=None)
        info_table.add_column("Field", style="cyan")
        info_table.add_column("Value", style="white")
        
        info_table.add_row("Lead", decision.lead_name)
        info_table.add_row("Company", decision.lead_company)
        info_table.add_row("Lead ID", decision.lead_id)
        
        console.print(info_table)
        
        # Show AI decision
        console.print(f"\n[bold yellow]AI Recommendation:[/bold yellow]")
        console.print(f"  {decision.ai_recommendation}")
        console.print(f"\n[bold yellow]AI Confidence:[/bold yellow] {decision.ai_confidence:.0%}")
        console.print(f"\n[bold yellow]AI Reasoning:[/bold yellow]")
        console.print(f"  {decision.ai_reasoning}")
        
        # Show factors
        console.print(f"\n[bold yellow]Factors:[/bold yellow]")
        for factor, value in decision.ai_factors.items():
            console.print(f"  • {factor}: {value}")
        
        # Get human verdict
        console.print("\n[bold green]Your verdict:[/bold green]")
        console.print("  1. Agree - AI decision is correct")
        console.print("  2. Disagree - AI decision is wrong")
        console.print("  3. Partial - Somewhat correct but needs adjustment")
        console.print("  4. Skip - Review later")
        console.print("  5. Quit - Exit review session")
        
        choice = Prompt.ask("Enter choice", choices=["1", "2", "3", "4", "5"], default="1")
        
        if choice == "5":
            console.print("[yellow]Exiting review session.[/yellow]")
            break
        
        if choice == "4":
            continue
        
        verdict_map = {
            "1": HumanVerdict.AGREE,
            "2": HumanVerdict.DISAGREE,
            "3": HumanVerdict.PARTIAL
        }
        
        verdict = verdict_map[choice]
        
        human_decision = ""
        if verdict != HumanVerdict.AGREE:
            human_decision = Prompt.ask("What should the decision be?")
        else:
            human_decision = decision.ai_recommendation
        
        notes = Prompt.ask("Any notes? (optional)", default="")
        
        queue.submit_review(
            decision_id=decision.decision_id,
            verdict=verdict,
            human_decision=human_decision,
            notes=notes,
            reviewer="AE"
        )
        
        console.print(f"[green]✅ Review submitted[/green]")
    
    # Show updated metrics
    print_metrics(queue)


def print_metrics(queue: ComparisonQueue):
    """Print comparison metrics."""
    metrics = queue.calculate_metrics()
    
    console.print("\n")
    console.print(Panel("[bold blue]AI vs Human Comparison Metrics[/bold blue]", expand=False))
    
    # Summary table
    summary_table = Table(title="Overall Summary", show_header=True)
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")
    
    summary_table.add_row("Total Decisions", str(metrics.total_decisions))
    summary_table.add_row("Reviewed", str(metrics.reviewed))
    summary_table.add_row("Pending", str(metrics.total_decisions - metrics.reviewed))
    summary_table.add_row("", "")
    summary_table.add_row("[bold]Agreement Rate[/bold]", f"[bold]{metrics.agreement_rate():.1f}%[/bold]")
    summary_table.add_row("  Agree", str(metrics.agree))
    summary_table.add_row("  Disagree", str(metrics.disagree))
    summary_table.add_row("  Partial", str(metrics.partial))
    
    console.print(summary_table)
    
    # Confidence analysis
    if metrics.avg_confidence_agree or metrics.avg_confidence_disagree:
        conf_table = Table(title="Confidence Analysis", show_header=True)
        conf_table.add_column("Verdict", style="cyan")
        conf_table.add_column("Avg AI Confidence", style="green")
        
        conf_table.add_row("When Human Agrees", f"{metrics.avg_confidence_agree:.1%}")
        conf_table.add_row("When Human Disagrees", f"{metrics.avg_confidence_disagree:.1%}")
        
        console.print(conf_table)
    
    # By tier
    if metrics.by_tier:
        tier_table = Table(title="Agreement by Tier", show_header=True)
        tier_table.add_column("Tier", style="cyan")
        tier_table.add_column("Agree", style="green")
        tier_table.add_column("Disagree", style="red")
        tier_table.add_column("Partial", style="yellow")
        
        for tier, counts in sorted(metrics.by_tier.items()):
            tier_table.add_row(
                tier,
                str(counts["agree"]),
                str(counts["disagree"]),
                str(counts["partial"])
            )
        
        console.print(tier_table)
    
    # Production readiness assessment
    agreement_rate = metrics.agreement_rate()
    if agreement_rate >= 90:
        console.print("\n[bold green]✅ HIGH AGREEMENT (≥90%)[/bold green]")
        console.print("AI decisions are highly aligned with human judgment. Ready for increased autonomy.")
    elif agreement_rate >= 75:
        console.print("\n[bold yellow]⚠️ MODERATE AGREEMENT (75-90%)[/bold yellow]")
        console.print("AI decisions are mostly correct. Continue with Parallel Mode before Full Autonomy.")
    elif agreement_rate >= 50:
        console.print("\n[bold orange]⚠️ LOW AGREEMENT (50-75%)[/bold orange]")
        console.print("AI needs more training data. Review disagreements and update prompts/thresholds.")
    else:
        console.print("\n[bold red]❌ POOR AGREEMENT (<50%)[/bold red]")
        console.print("AI decisions diverge significantly from human judgment. Do not proceed to production.")


# =============================================================================
# CLI
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Compare AI vs Human decisions")
    parser.add_argument("--generate-queue", type=int, help="Generate N sample decisions for review")
    parser.add_argument("--review", action="store_true", help="Start interactive review session")
    parser.add_argument("--analyze", action="store_true", help="Analyze comparison metrics")
    parser.add_argument("--archive", action="store_true", help="Archive reviewed decisions")
    
    args = parser.parse_args()
    
    queue = ComparisonQueue()
    
    if args.generate_queue:
        console.print(f"\n[bold]Generating {args.generate_queue} sample decisions...[/bold]")
        decisions = generate_sample_decisions(args.generate_queue)
        
        for decision in decisions:
            queue.add_decision(decision)
        
        console.print(f"[green]✅ Added {len(decisions)} decisions to review queue[/green]")
        console.print(f"\n[yellow]Next step:[/yellow] Run with --review to start reviewing")
    
    elif args.review:
        interactive_review(queue)
    
    elif args.analyze:
        print_metrics(queue)
    
    elif args.archive:
        archived = queue.archive_reviewed()
        console.print(f"[green]✅ Archived {archived} reviewed decisions[/green]")
    
    else:
        # Default: show current status
        pending = len([d for d in queue.decisions if d.human_verdict == HumanVerdict.NOT_REVIEWED])
        reviewed = len([d for d in queue.decisions if d.human_verdict != HumanVerdict.NOT_REVIEWED])
        
        console.print(Panel(
            f"[bold blue]AI vs Human Comparison Queue[/bold blue]\n\n"
            f"Pending reviews: {pending}\n"
            f"Completed reviews: {reviewed}\n"
            f"Total: {len(queue.decisions)}"
        ))
        
        if pending > 0:
            console.print("\n[yellow]Run with --review to start reviewing decisions[/yellow]")
        
        if reviewed > 0:
            console.print("[yellow]Run with --analyze to see comparison metrics[/yellow]")
        
        console.print("\n[dim]Options: --generate-queue N, --review, --analyze, --archive[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
