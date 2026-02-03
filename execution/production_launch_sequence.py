#!/usr/bin/env python3
"""
Production Launch Sequence - Master Controller
===============================================
Orchestrates the 4-priority launch sequence for ChiefAIOfficer-beta-swarm.

Sequence:
1. Priority #1: Run 1000 leads through simulation
2. Priority #2: Verify all API connections
3. Priority #3: Compare AI vs Human decisions
4. Priority #4: Go live in Parallel Mode

Usage:
    python execution/production_launch_sequence.py --status
    python execution/production_launch_sequence.py --run-all
    python execution/production_launch_sequence.py --priority 1
"""

import os
import sys
import json
import asyncio
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress

console = Console()


@dataclass
class LaunchStatus:
    """Status of the launch sequence."""
    priority_1_complete: bool = False
    priority_1_leads_processed: int = 0
    priority_1_success_rate: float = 0.0
    
    priority_2_complete: bool = False
    priority_2_keys_configured: int = 0
    priority_2_keys_required: int = 0
    priority_2_connections_ok: int = 0
    
    priority_3_complete: bool = False
    priority_3_decisions_reviewed: int = 0
    priority_3_agreement_rate: float = 0.0
    
    priority_4_active: bool = False
    priority_4_autonomy_level: str = "parallel"
    priority_4_approval_rate: float = 0.0
    
    last_updated: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LaunchSequenceController:
    """Controls the production launch sequence."""
    
    def __init__(self):
        self.status_file = Path(".hive-mind/launch_status.json")
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        self.status = self._load_status()
    
    def _load_status(self) -> LaunchStatus:
        """Load status from disk."""
        if self.status_file.exists():
            with open(self.status_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return LaunchStatus(**data)
        return LaunchStatus()
    
    def _save_status(self):
        """Save status to disk."""
        self.status.last_updated = datetime.now(timezone.utc).isoformat()
        with open(self.status_file, 'w', encoding='utf-8') as f:
            json.dump(self.status.to_dict(), f, indent=2)
    
    async def run_priority_1(self, lead_count: int = 1000) -> bool:
        """Run Priority #1: Simulation Harness."""
        console.print(Panel("[bold blue]PRIORITY #1: SIMULATION HARNESS[/bold blue]"))
        
        try:
            from execution.priority_1_simulation_harness import SimulationEngine, generate_lead_batch
            
            leads = generate_lead_batch(lead_count)
            engine = SimulationEngine()
            result = await engine.run_simulation(leads)
            engine.print_report()
            
            metrics = result["metrics"]
            self.status.priority_1_complete = metrics["success_rate"] >= 90
            self.status.priority_1_leads_processed = metrics["processed_leads"]
            self.status.priority_1_success_rate = metrics["success_rate"]
            self._save_status()
            
            if self.status.priority_1_complete:
                console.print("\n[green]✅ Priority #1 COMPLETE[/green]")
                return True
            else:
                console.print(f"\n[yellow]⚠️ Success rate {metrics['success_rate']:.1f}% below 90% threshold[/yellow]")
                return False
                
        except Exception as e:
            console.print(f"\n[red]❌ Priority #1 FAILED: {e}[/red]")
            return False
    
    async def run_priority_2(self, test_connections: bool = True) -> bool:
        """Run Priority #2: API Key Verification."""
        console.print(Panel("[bold blue]PRIORITY #2: API KEY VERIFICATION[/bold blue]"))
        
        try:
            from execution.priority_2_api_key_setup import APIKeyChecker
            
            checker = APIKeyChecker()
            env_results = checker.check_environment_variables()
            
            connection_results = None
            if test_connections:
                connection_results = await checker.test_all_connections()
            
            checker.print_report(env_results, connection_results)
            
            self.status.priority_2_keys_configured = env_results["set"]
            self.status.priority_2_keys_required = len(env_results["missing_required"])
            
            if connection_results:
                self.status.priority_2_connections_ok = connection_results["connected"]
            
            self.status.priority_2_complete = len(env_results["missing_required"]) == 0
            self._save_status()
            
            if self.status.priority_2_complete:
                console.print("\n[green]✅ Priority #2 COMPLETE[/green]")
                return True
            else:
                console.print(f"\n[yellow]⚠️ Missing required API keys[/yellow]")
                checker.generate_setup_instructions()
                return False
                
        except Exception as e:
            console.print(f"\n[red]❌ Priority #2 FAILED: {e}[/red]")
            return False
    
    async def run_priority_3(self, generate_count: int = 100) -> bool:
        """Run Priority #3: AI vs Human Comparison."""
        console.print(Panel("[bold blue]PRIORITY #3: AI vs HUMAN COMPARISON[/bold blue]"))
        
        try:
            from execution.priority_3_ai_vs_human_comparison import (
                ComparisonQueue, 
                generate_sample_decisions,
                print_metrics
            )
            
            queue = ComparisonQueue()
            
            # Generate decisions if queue is empty
            pending = len([d for d in queue.decisions if d.human_verdict.value == "not_reviewed"])
            if pending == 0:
                console.print(f"[yellow]Generating {generate_count} sample decisions for review...[/yellow]")
                decisions = generate_sample_decisions(generate_count)
                for d in decisions:
                    queue.add_decision(d)
                console.print(f"[green]Added {len(decisions)} decisions to queue[/green]")
            
            # Show metrics
            print_metrics(queue)
            
            metrics = queue.calculate_metrics()
            self.status.priority_3_decisions_reviewed = metrics.reviewed
            self.status.priority_3_agreement_rate = metrics.agreement_rate()
            
            # Need at least 50 reviews with 75% agreement
            self.status.priority_3_complete = (
                metrics.reviewed >= 50 and 
                metrics.agreement_rate() >= 75
            )
            self._save_status()
            
            if self.status.priority_3_complete:
                console.print("\n[green]✅ Priority #3 COMPLETE[/green]")
                return True
            else:
                console.print("\n[yellow]⚠️ Need more reviews or higher agreement rate[/yellow]")
                console.print(f"   Reviewed: {metrics.reviewed}/50 required")
                console.print(f"   Agreement: {metrics.agreement_rate():.1f}%/75% required")
                console.print("\n[dim]Run: python execution/priority_3_ai_vs_human_comparison.py --review[/dim]")
                return False
                
        except Exception as e:
            console.print(f"\n[red]❌ Priority #3 FAILED: {e}[/red]")
            return False
    
    async def run_priority_4(self, generate_count: int = 50) -> bool:
        """Run Priority #4: Parallel Mode."""
        console.print(Panel("[bold blue]PRIORITY #4: PARALLEL MODE[/bold blue]"))
        
        try:
            from execution.priority_4_parallel_mode import (
                ParallelModeQueue,
                generate_sample_actions,
                print_dashboard
            )
            
            queue = ParallelModeQueue()
            
            # Generate actions if queue is empty
            pending = len(queue.get_pending_approvals(limit=1000))
            if pending == 0:
                console.print(f"[yellow]Generating {generate_count} sample actions...[/yellow]")
                queued = generate_sample_actions(queue, generate_count)
                console.print(f"[green]Queued {queued} actions for approval[/green]")
            
            # Show dashboard
            print_dashboard(queue)
            
            metrics = queue.calculate_metrics()
            self.status.priority_4_active = True
            self.status.priority_4_autonomy_level = queue.config.autonomy_level.value
            self.status.priority_4_approval_rate = metrics.approval_rate
            self._save_status()
            
            console.print("\n[green]✅ Priority #4 ACTIVE - Parallel Mode Running[/green]")
            console.print("\n[dim]Run: python execution/priority_4_parallel_mode.py --approve[/dim]")
            return True
                
        except Exception as e:
            console.print(f"\n[red]❌ Priority #4 FAILED: {e}[/red]")
            return False
    
    def print_status(self):
        """Print overall launch status."""
        console.print("\n")
        console.print(Panel("[bold blue]PRODUCTION LAUNCH STATUS[/bold blue]", expand=False))
        
        table = Table(show_header=True)
        table.add_column("Priority", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details", style="dim")
        table.add_column("Command", style="yellow")
        
        # Priority 1
        p1_status = "✅ Complete" if self.status.priority_1_complete else "⏳ Pending"
        p1_details = f"{self.status.priority_1_leads_processed} leads, {self.status.priority_1_success_rate:.1f}% success"
        table.add_row(
            "#1 Simulation",
            p1_status,
            p1_details,
            "--priority 1"
        )
        
        # Priority 2
        p2_status = "✅ Complete" if self.status.priority_2_complete else "⏳ Pending"
        p2_details = f"{self.status.priority_2_keys_configured} keys configured"
        if self.status.priority_2_keys_required > 0:
            p2_details += f", {self.status.priority_2_keys_required} missing"
        table.add_row(
            "#2 API Keys",
            p2_status,
            p2_details,
            "--priority 2"
        )
        
        # Priority 3
        p3_status = "✅ Complete" if self.status.priority_3_complete else "⏳ Pending"
        p3_details = f"{self.status.priority_3_decisions_reviewed} reviewed, {self.status.priority_3_agreement_rate:.1f}% agreement"
        table.add_row(
            "#3 AI vs Human",
            p3_status,
            p3_details,
            "--priority 3"
        )
        
        # Priority 4
        p4_status = "🟢 Active" if self.status.priority_4_active else "⏳ Pending"
        p4_details = f"{self.status.priority_4_autonomy_level.upper()}, {self.status.priority_4_approval_rate:.1f}% approval"
        table.add_row(
            "#4 Parallel Mode",
            p4_status,
            p4_details,
            "--priority 4"
        )
        
        console.print(table)
        
        # Overall readiness
        all_complete = (
            self.status.priority_1_complete and
            self.status.priority_2_complete and
            self.status.priority_3_complete and
            self.status.priority_4_active
        )
        
        if all_complete:
            console.print("\n[bold green]🚀 PRODUCTION READY[/bold green]")
            console.print("All priorities complete. Swarm is operational in Parallel Mode.")
        else:
            pending = []
            if not self.status.priority_1_complete:
                pending.append("#1 Simulation")
            if not self.status.priority_2_complete:
                pending.append("#2 API Keys")
            if not self.status.priority_3_complete:
                pending.append("#3 AI vs Human")
            if not self.status.priority_4_active:
                pending.append("#4 Parallel Mode")
            
            console.print(f"\n[yellow]⏳ Pending: {', '.join(pending)}[/yellow]")
        
        if self.status.last_updated:
            console.print(f"\n[dim]Last updated: {self.status.last_updated}[/dim]")


# =============================================================================
# CLI
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Production Launch Sequence Controller")
    parser.add_argument("--status", action="store_true", help="Show launch status")
    parser.add_argument("--run-all", action="store_true", help="Run all priorities sequentially")
    parser.add_argument("--priority", type=int, choices=[1, 2, 3, 4], help="Run specific priority")
    parser.add_argument("--leads", type=int, default=100, help="Number of leads for simulation")
    
    args = parser.parse_args()
    
    controller = LaunchSequenceController()
    
    if args.run_all:
        console.print(Panel(
            "[bold blue]PRODUCTION LAUNCH SEQUENCE[/bold blue]\n"
            "Running all 4 priorities sequentially...",
            expand=False
        ))
        
        # Priority 1
        if not await controller.run_priority_1(args.leads):
            console.print("\n[red]Stopping: Priority #1 not passed[/red]")
            controller.print_status()
            return
        
        # Priority 2
        if not await controller.run_priority_2():
            console.print("\n[red]Stopping: Priority #2 not passed - configure API keys[/red]")
            controller.print_status()
            return
        
        # Priority 3
        if not await controller.run_priority_3():
            console.print("\n[yellow]Priority #3 needs human review. Continuing to #4...[/yellow]")
        
        # Priority 4
        await controller.run_priority_4()
        
        controller.print_status()
    
    elif args.priority:
        if args.priority == 1:
            await controller.run_priority_1(args.leads)
        elif args.priority == 2:
            await controller.run_priority_2()
        elif args.priority == 3:
            await controller.run_priority_3()
        elif args.priority == 4:
            await controller.run_priority_4()
        
        controller.print_status()
    
    else:
        controller.print_status()
        console.print("\n[dim]Options: --run-all, --priority N, --status[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
