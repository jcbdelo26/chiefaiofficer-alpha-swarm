#!/usr/bin/env python3
"""
Priority #4: Parallel Mode - AE Reviews Every AI Decision
==========================================================
Production deployment where AI makes decisions but AE must approve before execution.

Features:
- AI processes leads through full pipeline
- All outreach actions require explicit AE approval
- Dashboard for reviewing and approving/rejecting
- Metrics tracking for production monitoring
- Gradual autonomy increase based on agreement rate

Usage:
    python execution/priority_4_parallel_mode.py --start
    python execution/priority_4_parallel_mode.py --dashboard
    python execution/priority_4_parallel_mode.py --process-lead "lead_id"
    python execution/priority_4_parallel_mode.py --status
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
from rich.live import Live
from rich.layout import Layout

console = Console()


class ParallelModeStatus(Enum):
    """Status of parallel mode operations."""
    PENDING_AI = "pending_ai"
    AI_COMPLETE = "ai_complete"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


class AutonomyLevel(Enum):
    """Levels of AI autonomy."""
    SHADOW = "shadow"       # AI decides, no action taken
    PARALLEL = "parallel"   # AI decides, AE must approve
    ASSISTED = "assisted"   # AI decides, AE can override (auto-approve after timeout)
    AUTONOMOUS = "autonomous"  # AI decides and executes


@dataclass
class ParallelModeConfig:
    """Configuration for parallel mode."""
    autonomy_level: AutonomyLevel = AutonomyLevel.PARALLEL
    approval_timeout_hours: int = 24
    auto_approve_confidence_threshold: float = 0.95
    require_approval_for: List[str] = field(default_factory=lambda: [
        "send_email",
        "send_sms",
        "bulk_send",
        "campaign_launch"
    ])
    exempt_from_approval: List[str] = field(default_factory=lambda: [
        "read_contact",
        "search_contacts",
        "enrich_contact"
    ])
    min_agreement_rate_for_promotion: float = 90.0
    min_reviews_for_promotion: int = 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "autonomy_level": self.autonomy_level.value
        }


@dataclass
class QueuedAction:
    """An action queued for AE approval in parallel mode."""
    action_id: str
    lead_id: str
    lead_name: str
    lead_company: str
    lead_email: Optional[str]
    lead_tier: str
    
    # Action details
    action_type: str  # send_email, send_sms, etc.
    action_payload: Dict[str, Any]
    
    # AI decision
    ai_confidence: float
    ai_reasoning: str
    qualification_details: Dict[str, Any]
    
    # Status tracking
    status: ParallelModeStatus = ParallelModeStatus.PENDING_APPROVAL
    
    # Approval tracking
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None
    modifications: Optional[Dict[str, Any]] = None
    
    # Execution tracking
    executed_at: Optional[str] = None
    execution_result: Optional[Dict[str, Any]] = None
    
    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    deadline: str = field(default_factory=lambda: (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat())
    
    # Priority (1=highest)
    priority: int = 2
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "status": self.status.value
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueuedAction':
        data["status"] = ParallelModeStatus(data["status"])
        return cls(**data)
    
    def is_expired(self) -> bool:
        """Check if action has passed its deadline."""
        deadline = datetime.fromisoformat(self.deadline.replace('Z', '+00:00'))
        return datetime.now(timezone.utc) > deadline


@dataclass
class ParallelModeMetrics:
    """Metrics for parallel mode operation."""
    total_actions: int = 0
    pending_approval: int = 0
    approved: int = 0
    rejected: int = 0
    executed: int = 0
    expired: int = 0
    
    # Timing
    avg_approval_time_hours: float = 0
    
    # By action type
    by_action_type: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
    # By tier
    by_tier: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
    # Trend
    approval_rate: float = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ParallelModeQueue:
    """
    Queue for managing actions in Parallel Mode.
    
    All AI-initiated actions go through this queue for AE approval
    before execution.
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or Path(".hive-mind/parallel_mode")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.config_file = self.storage_dir / "config.json"
        self.queue_file = self.storage_dir / "action_queue.json"
        self.history_dir = self.storage_dir / "history"
        self.history_dir.mkdir(exist_ok=True)
        
        self.config = self._load_config()
        self.actions: List[QueuedAction] = []
        self._load_queue()
    
    def _load_config(self) -> ParallelModeConfig:
        """Load configuration."""
        if self.config_file.exists():
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data["autonomy_level"] = AutonomyLevel(data["autonomy_level"])
                return ParallelModeConfig(**data)
        return ParallelModeConfig()
    
    def _save_config(self):
        """Save configuration."""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config.to_dict(), f, indent=2)
    
    def _load_queue(self):
        """Load queue from disk."""
        if self.queue_file.exists():
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.actions = [QueuedAction.from_dict(a) for a in data]
    
    def _save_queue(self):
        """Save queue to disk."""
        with open(self.queue_file, 'w', encoding='utf-8') as f:
            json.dump([a.to_dict() for a in self.actions], f, indent=2)
    
    def queue_action(
        self,
        lead: Dict[str, Any],
        action_type: str,
        action_payload: Dict[str, Any],
        ai_confidence: float,
        ai_reasoning: str,
        qualification_details: Dict[str, Any]
    ) -> QueuedAction:
        """
        Queue an action for AE approval.
        
        Returns the queued action (or auto-approved if confidence is high enough).
        """
        action = QueuedAction(
            action_id=f"act_{uuid.uuid4().hex[:8]}",
            lead_id=lead.get("lead_id", "unknown"),
            lead_name=lead.get("name", "Unknown"),
            lead_company=lead.get("company", {}).get("name", "Unknown"),
            lead_email=lead.get("email"),
            lead_tier=lead.get("tier", "tier_3"),
            action_type=action_type,
            action_payload=action_payload,
            ai_confidence=ai_confidence,
            ai_reasoning=ai_reasoning,
            qualification_details=qualification_details,
            priority=1 if lead.get("tier") == "tier_1" else 2 if lead.get("tier") == "tier_2" else 3
        )
        
        # Check if action requires approval
        if action_type in self.config.exempt_from_approval:
            action.status = ParallelModeStatus.APPROVED
            action.approved_by = "SYSTEM"
            action.approved_at = datetime.now(timezone.utc).isoformat()
        
        # Check for auto-approval based on confidence
        elif (self.config.autonomy_level == AutonomyLevel.ASSISTED and 
              ai_confidence >= self.config.auto_approve_confidence_threshold):
            action.status = ParallelModeStatus.APPROVED
            action.approved_by = "AUTO_CONFIDENCE"
            action.approved_at = datetime.now(timezone.utc).isoformat()
        
        self.actions.append(action)
        self._save_queue()
        
        return action
    
    def get_pending_approvals(self, limit: int = 20) -> List[QueuedAction]:
        """Get actions pending approval."""
        pending = [a for a in self.actions if a.status == ParallelModeStatus.PENDING_APPROVAL]
        # Sort by priority, then deadline
        pending.sort(key=lambda x: (x.priority, x.deadline))
        return pending[:limit]
    
    def approve_action(
        self,
        action_id: str,
        approver: str = "AE",
        modifications: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Approve an action for execution."""
        for action in self.actions:
            if action.action_id == action_id:
                action.status = ParallelModeStatus.APPROVED
                action.approved_by = approver
                action.approved_at = datetime.now(timezone.utc).isoformat()
                if modifications:
                    action.modifications = modifications
                    action.action_payload.update(modifications)
                self._save_queue()
                return True
        return False
    
    def reject_action(
        self,
        action_id: str,
        reason: str,
        rejector: str = "AE"
    ) -> bool:
        """Reject an action."""
        for action in self.actions:
            if action.action_id == action_id:
                action.status = ParallelModeStatus.REJECTED
                action.approved_by = rejector
                action.approved_at = datetime.now(timezone.utc).isoformat()
                action.rejection_reason = reason
                self._save_queue()
                return True
        return False
    
    def mark_executed(
        self,
        action_id: str,
        result: Dict[str, Any]
    ) -> bool:
        """Mark an action as executed."""
        for action in self.actions:
            if action.action_id == action_id:
                action.status = ParallelModeStatus.EXECUTED
                action.executed_at = datetime.now(timezone.utc).isoformat()
                action.execution_result = result
                self._save_queue()
                return True
        return False
    
    def process_expired(self):
        """Handle expired actions based on autonomy level."""
        expired_count = 0
        
        for action in self.actions:
            if action.status == ParallelModeStatus.PENDING_APPROVAL and action.is_expired():
                if self.config.autonomy_level == AutonomyLevel.ASSISTED:
                    # Auto-approve in assisted mode
                    action.status = ParallelModeStatus.APPROVED
                    action.approved_by = "AUTO_TIMEOUT"
                    action.approved_at = datetime.now(timezone.utc).isoformat()
                else:
                    # Mark as expired in parallel mode
                    action.status = ParallelModeStatus.FAILED
                    action.rejection_reason = "Approval deadline expired"
                
                expired_count += 1
        
        if expired_count > 0:
            self._save_queue()
        
        return expired_count
    
    def get_approved_for_execution(self) -> List[QueuedAction]:
        """Get actions that are approved and ready for execution."""
        return [a for a in self.actions if a.status == ParallelModeStatus.APPROVED]
    
    def calculate_metrics(self) -> ParallelModeMetrics:
        """Calculate metrics for parallel mode."""
        metrics = ParallelModeMetrics()
        metrics.total_actions = len(self.actions)
        
        approval_times = []
        
        for action in self.actions:
            # Count by status
            if action.status == ParallelModeStatus.PENDING_APPROVAL:
                metrics.pending_approval += 1
            elif action.status == ParallelModeStatus.APPROVED:
                metrics.approved += 1
            elif action.status == ParallelModeStatus.REJECTED:
                metrics.rejected += 1
            elif action.status == ParallelModeStatus.EXECUTED:
                metrics.executed += 1
            
            # Track approval time
            if action.approved_at and action.created_at:
                created = datetime.fromisoformat(action.created_at.replace('Z', '+00:00'))
                approved = datetime.fromisoformat(action.approved_at.replace('Z', '+00:00'))
                hours = (approved - created).total_seconds() / 3600
                approval_times.append(hours)
            
            # By action type
            atype = action.action_type
            if atype not in metrics.by_action_type:
                metrics.by_action_type[atype] = {"pending": 0, "approved": 0, "rejected": 0, "executed": 0}
            
            if action.status == ParallelModeStatus.PENDING_APPROVAL:
                metrics.by_action_type[atype]["pending"] += 1
            elif action.status in [ParallelModeStatus.APPROVED, ParallelModeStatus.EXECUTED]:
                metrics.by_action_type[atype]["approved"] += 1
            elif action.status == ParallelModeStatus.REJECTED:
                metrics.by_action_type[atype]["rejected"] += 1
            
            # By tier
            tier = action.lead_tier
            if tier not in metrics.by_tier:
                metrics.by_tier[tier] = {"pending": 0, "approved": 0, "rejected": 0}
            
            if action.status == ParallelModeStatus.PENDING_APPROVAL:
                metrics.by_tier[tier]["pending"] += 1
            elif action.status in [ParallelModeStatus.APPROVED, ParallelModeStatus.EXECUTED]:
                metrics.by_tier[tier]["approved"] += 1
            elif action.status == ParallelModeStatus.REJECTED:
                metrics.by_tier[tier]["rejected"] += 1
        
        if approval_times:
            metrics.avg_approval_time_hours = sum(approval_times) / len(approval_times)
        
        # Calculate approval rate
        total_decided = metrics.approved + metrics.rejected + metrics.executed
        if total_decided > 0:
            metrics.approval_rate = (metrics.approved + metrics.executed) / total_decided * 100
        
        return metrics
    
    def check_promotion_eligibility(self) -> Tuple[bool, str]:
        """Check if ready to promote to higher autonomy level."""
        metrics = self.calculate_metrics()
        
        total_reviewed = metrics.approved + metrics.rejected + metrics.executed
        
        if total_reviewed < self.config.min_reviews_for_promotion:
            return False, f"Need {self.config.min_reviews_for_promotion} reviews, have {total_reviewed}"
        
        if metrics.approval_rate < self.config.min_agreement_rate_for_promotion:
            return False, f"Need {self.config.min_agreement_rate_for_promotion}% approval rate, have {metrics.approval_rate:.1f}%"
        
        return True, "Ready for promotion to next autonomy level"
    
    def promote_autonomy(self) -> bool:
        """Promote to next autonomy level."""
        levels = list(AutonomyLevel)
        current_idx = levels.index(self.config.autonomy_level)
        
        if current_idx < len(levels) - 1:
            self.config.autonomy_level = levels[current_idx + 1]
            self._save_config()
            return True
        return False
    
    def archive_completed(self):
        """Archive completed actions."""
        completed = [a for a in self.actions if a.status in [
            ParallelModeStatus.EXECUTED,
            ParallelModeStatus.REJECTED,
            ParallelModeStatus.FAILED
        ]]
        
        if completed:
            archive_file = self.history_dir / f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(archive_file, 'w', encoding='utf-8') as f:
                json.dump([a.to_dict() for a in completed], f, indent=2)
            
            self.actions = [a for a in self.actions if a not in completed]
            self._save_queue()
            
            return len(completed)
        return 0


def print_dashboard(queue: ParallelModeQueue):
    """Print parallel mode dashboard."""
    metrics = queue.calculate_metrics()
    
    console.print("\n")
    console.print(Panel(
        f"[bold blue]PARALLEL MODE DASHBOARD[/bold blue]\n"
        f"Autonomy Level: [yellow]{queue.config.autonomy_level.value.upper()}[/yellow]",
        expand=False
    ))
    
    # Status overview
    status_table = Table(title="Queue Status", show_header=True)
    status_table.add_column("Status", style="cyan")
    status_table.add_column("Count", style="green")
    
    status_table.add_row("Pending Approval", f"[yellow]{metrics.pending_approval}[/yellow]")
    status_table.add_row("Approved", f"[green]{metrics.approved}[/green]")
    status_table.add_row("Rejected", f"[red]{metrics.rejected}[/red]")
    status_table.add_row("Executed", f"[blue]{metrics.executed}[/blue]")
    status_table.add_row("", "")
    status_table.add_row("[bold]Total[/bold]", f"[bold]{metrics.total_actions}[/bold]")
    
    console.print(status_table)
    
    # Performance metrics
    perf_table = Table(title="Performance Metrics", show_header=True)
    perf_table.add_column("Metric", style="cyan")
    perf_table.add_column("Value", style="green")
    
    perf_table.add_row("Approval Rate", f"{metrics.approval_rate:.1f}%")
    perf_table.add_row("Avg Approval Time", f"{metrics.avg_approval_time_hours:.1f} hours")
    
    console.print(perf_table)
    
    # Pending actions preview
    pending = queue.get_pending_approvals(limit=5)
    if pending:
        pending_table = Table(title="Pending Approvals (Next 5)", show_header=True)
        pending_table.add_column("ID", style="dim")
        pending_table.add_column("Lead", style="cyan")
        pending_table.add_column("Action", style="yellow")
        pending_table.add_column("Confidence", style="green")
        pending_table.add_column("Priority", style="red")
        
        for action in pending:
            pending_table.add_row(
                action.action_id[:12],
                f"{action.lead_name[:15]}... ({action.lead_company[:10]}...)",
                action.action_type,
                f"{action.ai_confidence:.0%}",
                f"P{action.priority}"
            )
        
        console.print(pending_table)
    
    # Promotion eligibility
    eligible, reason = queue.check_promotion_eligibility()
    if eligible:
        console.print(f"\n[bold green]✅ ELIGIBLE FOR PROMOTION[/bold green]: {reason}")
    else:
        console.print(f"\n[yellow]⏳ Not ready for promotion[/yellow]: {reason}")


def interactive_approval(queue: ParallelModeQueue):
    """Interactive approval session."""
    pending = queue.get_pending_approvals(limit=10)
    
    if not pending:
        console.print("[yellow]No pending actions to approve.[/yellow]")
        return
    
    console.print(Panel(
        f"[bold blue]Action Approval Queue[/bold blue]\n"
        f"Pending: {len(pending)} actions"
    ))
    
    for i, action in enumerate(pending, 1):
        console.print(f"\n{'='*60}")
        console.print(f"[bold]Action {i}/{len(pending)}[/bold] - {action.action_id}")
        console.print(f"{'='*60}")
        
        # Lead info
        info_table = Table(show_header=False, box=None)
        info_table.add_column("Field", style="cyan")
        info_table.add_column("Value", style="white")
        
        info_table.add_row("Lead", action.lead_name)
        info_table.add_row("Company", action.lead_company)
        info_table.add_row("Email", action.lead_email or "[red]Missing[/red]")
        info_table.add_row("Tier", action.lead_tier.upper())
        
        console.print(info_table)
        
        # Action details
        console.print(f"\n[bold yellow]Action:[/bold yellow] {action.action_type}")
        console.print(f"[bold yellow]AI Confidence:[/bold yellow] {action.ai_confidence:.0%}")
        console.print(f"\n[bold yellow]AI Reasoning:[/bold yellow]")
        console.print(f"  {action.ai_reasoning}")
        
        # Email preview (if email action)
        if action.action_type == "send_email" and action.action_payload.get("subject"):
            console.print(f"\n[bold yellow]Email Preview:[/bold yellow]")
            console.print(f"  Subject: {action.action_payload.get('subject')}")
            body_preview = action.action_payload.get('body', '')[:200]
            console.print(f"  Body: {body_preview}...")
        
        # Decision
        console.print("\n[bold green]Your decision:[/bold green]")
        console.print("  1. Approve - Execute this action")
        console.print("  2. Reject - Do not execute")
        console.print("  3. Modify - Approve with changes")
        console.print("  4. Skip - Review later")
        console.print("  5. Quit - Exit approval session")
        
        choice = Prompt.ask("Enter choice", choices=["1", "2", "3", "4", "5"], default="1")
        
        if choice == "5":
            console.print("[yellow]Exiting approval session.[/yellow]")
            break
        
        if choice == "4":
            continue
        
        if choice == "1":
            queue.approve_action(action.action_id, approver="AE")
            console.print(f"[green]✅ Action approved[/green]")
        
        elif choice == "2":
            reason = Prompt.ask("Rejection reason")
            queue.reject_action(action.action_id, reason=reason, rejector="AE")
            console.print(f"[red]❌ Action rejected[/red]")
        
        elif choice == "3":
            console.print("[yellow]Enter modifications (JSON format):[/yellow]")
            mod_str = Prompt.ask("Modifications", default="{}")
            try:
                modifications = json.loads(mod_str)
                queue.approve_action(action.action_id, approver="AE", modifications=modifications)
                console.print(f"[green]✅ Action approved with modifications[/green]")
            except json.JSONDecodeError:
                console.print("[red]Invalid JSON, action skipped[/red]")
    
    print_dashboard(queue)


def generate_sample_actions(queue: ParallelModeQueue, count: int):
    """Generate sample actions for testing."""
    from execution.priority_1_simulation_harness import generate_lead_batch
    
    leads = generate_lead_batch(count)
    
    for lead in leads:
        # Only queue actions for tier 1 and tier 2
        tier = "tier_1" if lead.get("title_score", 0) > 20 else "tier_2" if lead.get("title_score", 0) > 10 else "tier_3"
        
        if tier in ["tier_1", "tier_2"]:
            lead["tier"] = tier
            
            queue.queue_action(
                lead=lead,
                action_type="send_email",
                action_payload={
                    "subject": f"Quick question about AI for {lead.get('company', {}).get('name', 'your company')}",
                    "body": f"Hi {lead.get('first_name', 'there')},\n\nI noticed you're at {lead.get('company', {}).get('name')}...",
                    "template_id": f"template_{tier}"
                },
                ai_confidence=0.75 + (lead.get("title_score", 0) / 100),
                ai_reasoning=f"Tier {tier[-1]} lead with strong ICP fit. Title: {lead.get('title')}.",
                qualification_details={
                    "icp_score": lead.get("title_score", 0) * 3,
                    "source": lead.get("source_type")
                }
            )
    
    return len([l for l in leads if l.get("title_score", 0) > 10])


# =============================================================================
# CLI
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Parallel Mode - AE approval workflow")
    parser.add_argument("--start", action="store_true", help="Start parallel mode (show dashboard)")
    parser.add_argument("--dashboard", action="store_true", help="Show dashboard")
    parser.add_argument("--approve", action="store_true", help="Start approval session")
    parser.add_argument("--generate", type=int, help="Generate N sample actions")
    parser.add_argument("--execute", action="store_true", help="Execute approved actions")
    parser.add_argument("--promote", action="store_true", help="Promote to next autonomy level")
    parser.add_argument("--status", action="store_true", help="Show current status")
    
    args = parser.parse_args()
    
    queue = ParallelModeQueue()
    
    if args.generate:
        console.print(f"\n[bold]Generating {args.generate} sample actions...[/bold]")
        queued = generate_sample_actions(queue, args.generate)
        console.print(f"[green]✅ Queued {queued} actions for approval[/green]")
    
    elif args.approve:
        interactive_approval(queue)
    
    elif args.execute:
        approved = queue.get_approved_for_execution()
        if not approved:
            console.print("[yellow]No approved actions to execute.[/yellow]")
        else:
            console.print(f"\n[bold]Executing {len(approved)} approved actions...[/bold]")
            for action in approved:
                # Simulate execution
                console.print(f"  Executing: {action.action_type} for {action.lead_name}...")
                await asyncio.sleep(0.1)  # Simulate
                queue.mark_executed(action.action_id, {"status": "simulated_success"})
            console.print(f"[green]✅ Executed {len(approved)} actions[/green]")
    
    elif args.promote:
        eligible, reason = queue.check_promotion_eligibility()
        if eligible:
            if Confirm.ask(f"Promote from {queue.config.autonomy_level.value} to next level?"):
                old_level = queue.config.autonomy_level.value
                if queue.promote_autonomy():
                    console.print(f"[green]✅ Promoted from {old_level} to {queue.config.autonomy_level.value}[/green]")
                else:
                    console.print("[yellow]Already at maximum autonomy level[/yellow]")
        else:
            console.print(f"[red]Not eligible for promotion: {reason}[/red]")
    
    elif args.dashboard or args.start or args.status:
        # Process expired actions first
        expired = queue.process_expired()
        if expired:
            console.print(f"[yellow]Processed {expired} expired actions[/yellow]")
        
        print_dashboard(queue)
    
    else:
        # Default: show help
        console.print(Panel(
            "[bold blue]PARALLEL MODE[/bold blue]\n\n"
            "AI makes decisions, AE must approve before execution.\n\n"
            "[bold]Commands:[/bold]\n"
            "  --dashboard    Show status dashboard\n"
            "  --approve      Start approval session\n"
            "  --generate N   Generate N sample actions\n"
            "  --execute      Execute approved actions\n"
            "  --promote      Promote to next autonomy level\n"
        ))


if __name__ == "__main__":
    asyncio.run(main())
