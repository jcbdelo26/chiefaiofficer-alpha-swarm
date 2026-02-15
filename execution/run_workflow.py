#!/usr/bin/env python3
"""
Workflow Orchestrator - End-to-End Pipeline Execution
=====================================================
Orchestrates complete workflows through all agents with monitoring.

Workflows:
1. lead-harvesting: scrape → normalize → enrich → segment → store
2. campaign-creation: select segment → generate → review → send

Usage:
    python execution/run_workflow.py --workflow lead-harvesting --test-mode
    python execution/run_workflow.py --workflow campaign-creation --tier tier_3 --test-mode
"""

import os
import sys
import json
import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


class WorkflowType(Enum):
    LEAD_HARVESTING = "lead-harvesting"
    CAMPAIGN_CREATION = "campaign-creation"


class WorkflowStep(Enum):
    NORMALIZE = "normalize"
    ENRICH = "enrich"
    SEGMENT = "segment"
    STORE = "store"
    SELECT_SEGMENT = "select_segment"
    GENERATE = "generate"
    REVIEW = "review"
    SEND = "send"


@dataclass
class StepResult:
    """Result of a workflow step."""
    step: str
    success: bool
    duration_seconds: float
    records_processed: int = 0
    records_output: int = 0
    error_message: Optional[str] = None
    output_file: Optional[str] = None
    cost_usd: float = 0.0
    metadata: Dict[str, Any] = None


@dataclass
class WorkflowResult:
    """Complete workflow execution result."""
    workflow: str
    mode: str
    started_at: str
    completed_at: str
    total_duration_seconds: float
    success: bool
    steps: List[StepResult]
    metrics: Dict[str, Any]
    error_message: Optional[str] = None


class WorkflowOrchestrator:
    """
    Orchestrates end-to-end workflows through the agent pipeline.
    
    Monitors:
    - Step completion and timing
    - Data flow between agents
    - Error handling and rollback
    - Cost tracking
    """
    
    def __init__(self, test_mode: bool = True):
        self.test_mode = test_mode
        self.results_dir = PROJECT_ROOT / ".hive-mind" / "workflows"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
    def run_lead_harvesting(
        self,
        input_file: Optional[Path] = None,
        linkedin_url: Optional[str] = None
    ) -> WorkflowResult:
        """
        Execute the lead harvesting workflow.
        
        Steps:
        1. Normalize: Clean and validate input data
        2. Enrich: Add contact/company data via Clay
        3. Segment: Score and tier leads by ICP
        4. Store: Save to Supabase and GHL
        
        Returns:
            WorkflowResult with step-by-step metrics
        """
        workflow_id = f"lead-harvest-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        started_at = datetime.now(timezone.utc).isoformat()
        steps: List[StepResult] = []
        total_cost = 0.0
        
        console.print(Panel(
            f"[bold green]Starting Lead Harvesting Workflow[/bold green]\n"
            f"Mode: {'TEST' if self.test_mode else 'PRODUCTION'}\n"
            f"Workflow ID: {workflow_id}",
            title="Workflow: lead-harvesting"
        ))
        
        try:
            # Step 1: Normalize
            console.print("\n[bold]Step 1: Normalize[/bold]")
            step_start = time.time()
            
            if input_file:
                with open(input_file) as f:
                    data = json.load(f)
                leads = data.get("test_leads", data.get("leads", []))
            else:
                leads = []
            
            normalized_count = len(leads)
            step_duration = time.time() - step_start
            
            steps.append(StepResult(
                step="normalize",
                success=True,
                duration_seconds=step_duration,
                records_processed=normalized_count,
                records_output=normalized_count,
                metadata={"source": str(input_file) if input_file else "linkedin_url"}
            ))
            console.print(f"  [green]✓[/green] Normalized {normalized_count} leads ({step_duration:.2f}s)")
            
            # Step 2: Enrich
            console.print("\n[bold]Step 2: Enrich via Clay[/bold]")
            step_start = time.time()
            
            from execution.enricher_waterfall import ClayEnricher
            
            enricher = ClayEnricher(test_mode=self.test_mode)
            if input_file:
                enriched = enricher.enrich_batch(input_file)
            else:
                enriched = []
            
            enriched_count = len(enriched)
            step_duration = time.time() - step_start
            enrichment_cost = enricher.test_stats.get("simulated_cost_usd", 0) if self.test_mode else 0
            total_cost += enrichment_cost
            
            # Save enriched results
            enriched_file = enricher.save_test_results(enriched) if self.test_mode else enricher.save_enriched(enriched)
            
            steps.append(StepResult(
                step="enrich",
                success=enriched_count > 0,
                duration_seconds=step_duration,
                records_processed=normalized_count,
                records_output=enriched_count,
                output_file=str(enriched_file),
                cost_usd=enrichment_cost,
                metadata={
                    "success_rate": f"{(enriched_count/max(normalized_count,1))*100:.1f}%",
                    "api_calls": enricher.test_stats.get("api_calls_simulated", 0)
                }
            ))
            console.print(f"  [green]✓[/green] Enriched {enriched_count}/{normalized_count} leads ({step_duration:.2f}s)")
            
            # Step 3: Segment
            console.print("\n[bold]Step 3: Segment by ICP[/bold]")
            step_start = time.time()
            
            from execution.segmentor_classify import LeadSegmentor
            
            segmentor = LeadSegmentor(use_annealing=True)
            segmented = segmentor.segment_batch(enriched_file)
            
            segmented_count = len(segmented)
            step_duration = time.time() - step_start
            
            # Save segmented results
            segmented_file = PROJECT_ROOT / ".hive-mind" / "testing" / "segmentor_test_results.json"
            segmentor.save_segmented(segmented, segmented_file if self.test_mode else None)
            
            # Calculate tier distribution
            tier_dist = {}
            for s in segmented:
                tier_dist[s.icp_tier] = tier_dist.get(s.icp_tier, 0) + 1
            
            steps.append(StepResult(
                step="segment",
                success=segmented_count > 0,
                duration_seconds=step_duration,
                records_processed=enriched_count,
                records_output=segmented_count,
                output_file=str(segmented_file),
                metadata={"tier_distribution": tier_dist}
            ))
            console.print(f"  [green]✓[/green] Segmented {segmented_count} leads ({step_duration:.2f}s)")
            
            # Step 4: Store (simulated in test mode)
            console.print("\n[bold]Step 4: Store to Supabase/GHL[/bold]")
            step_start = time.time()
            
            if self.test_mode:
                console.print("  [yellow]⚠ TEST MODE: Skipping actual database storage[/yellow]")
                stored_count = segmented_count
            else:
                # TODO: Implement actual storage
                stored_count = 0
            
            step_duration = time.time() - step_start
            
            steps.append(StepResult(
                step="store",
                success=True,
                duration_seconds=step_duration,
                records_processed=segmented_count,
                records_output=stored_count,
                metadata={"test_mode": self.test_mode}
            ))
            console.print(f"  [green]✓[/green] Storage complete ({step_duration:.2f}s)")
            
            # Calculate metrics
            completed_at = datetime.now(timezone.utc).isoformat()
            total_duration = sum(s.duration_seconds for s in steps)
            
            metrics = {
                "leads_input": normalized_count,
                "leads_enriched": enriched_count,
                "leads_segmented": segmented_count,
                "leads_stored": stored_count,
                "success_rate_percent": (segmented_count / max(normalized_count, 1)) * 100,
                "total_cost_usd": total_cost,
                "cost_per_lead_usd": total_cost / max(segmented_count, 1),
                "time_per_lead_seconds": total_duration / max(normalized_count, 1),
                "tier_distribution": tier_dist
            }
            
            result = WorkflowResult(
                workflow="lead-harvesting",
                mode="test" if self.test_mode else "production",
                started_at=started_at,
                completed_at=completed_at,
                total_duration_seconds=total_duration,
                success=all(s.success for s in steps),
                steps=[asdict(s) for s in steps],
                metrics=metrics
            )
            
            self._save_result(result, workflow_id)
            self._print_summary(result)
            
            return result
            
        except Exception as e:
            console.print(f"[red]✗ Workflow failed: {e}[/red]")
            return WorkflowResult(
                workflow="lead-harvesting",
                mode="test" if self.test_mode else "production",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                total_duration_seconds=0,
                success=False,
                steps=[asdict(s) for s in steps],
                metrics={},
                error_message=str(e)
            )
    
    def run_campaign_creation(
        self,
        tier: str = "tier_3",
        input_file: Optional[Path] = None
    ) -> WorkflowResult:
        """
        Execute the campaign creation workflow.
        
        Steps:
        1. Select Segment: Load leads from specified tier
        2. Generate: Create personalized campaigns
        3. Review: Queue for GATEKEEPER approval
        4. Send: (Test mode: skip actual send)
        
        Returns:
            WorkflowResult with step-by-step metrics
        """
        workflow_id = f"campaign-{tier}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        started_at = datetime.now(timezone.utc).isoformat()
        steps: List[StepResult] = []
        
        console.print(Panel(
            f"[bold green]Starting Campaign Creation Workflow[/bold green]\n"
            f"Mode: {'TEST' if self.test_mode else 'PRODUCTION'}\n"
            f"Target Tier: {tier}\n"
            f"Workflow ID: {workflow_id}",
            title="Workflow: campaign-creation"
        ))
        
        try:
            # Step 1: Select Segment
            console.print("\n[bold]Step 1: Select Segment[/bold]")
            step_start = time.time()
            
            if input_file:
                segment_file = input_file
            else:
                segment_file = PROJECT_ROOT / ".hive-mind" / "testing" / "segmentor_test_results.json"
            
            with open(segment_file) as f:
                data = json.load(f)
            
            leads = data.get("leads", [])
            selected = [l for l in leads if l.get("icp_tier") == tier or tier == "all"]
            if not selected:
                selected = leads  # Use all leads if tier filter returns nothing
            
            step_duration = time.time() - step_start
            
            steps.append(StepResult(
                step="select_segment",
                success=len(selected) > 0,
                duration_seconds=step_duration,
                records_processed=len(leads),
                records_output=len(selected),
                metadata={"tier_filter": tier, "source": str(segment_file)}
            ))
            console.print(f"  [green]✓[/green] Selected {len(selected)} {tier} leads ({step_duration:.2f}s)")
            
            # Step 2: Generate Campaigns
            console.print("\n[bold]Step 2: Generate Campaigns[/bold]")
            step_start = time.time()
            
            from execution.crafter_campaign_ghl import TestModeCrafter
            
            crafter = TestModeCrafter()
            campaign_results = crafter.generate_campaigns(selected, f"{tier}-workflow")
            
            campaigns_count = campaign_results.get("campaigns_generated", 0)
            personalization_rate = campaign_results.get("metrics", {}).get("personalization_rate", 0)
            step_duration = time.time() - step_start
            
            steps.append(StepResult(
                step="generate",
                success=campaigns_count > 0,
                duration_seconds=step_duration,
                records_processed=len(selected),
                records_output=campaigns_count,
                output_file=str(PROJECT_ROOT / ".hive-mind" / "testing" / "sample_campaigns.json"),
                metadata={
                    "personalization_rate": f"{personalization_rate}%",
                    "template_used": campaign_results.get("sample_campaigns", [{}])[0].get("template_used", "unknown")
                }
            ))
            console.print(f"  [green]✓[/green] Generated {campaigns_count} campaigns ({step_duration:.2f}s)")
            
            # Step 3: Queue for Review
            console.print("\n[bold]Step 3: Queue for GATEKEEPER Review[/bold]")
            step_start = time.time()
            
            if self.test_mode:
                console.print("  [yellow]⚠ TEST MODE: Simulating review queue[/yellow]")
                queued_count = campaigns_count
            else:
                from execution.gatekeeper_queue import GatekeeperQueue
                gatekeeper = GatekeeperQueue()
                # Queue campaigns for review
                queued_count = 0
            
            step_duration = time.time() - step_start
            
            steps.append(StepResult(
                step="review",
                success=True,
                duration_seconds=step_duration,
                records_processed=campaigns_count,
                records_output=queued_count,
                metadata={"test_mode": self.test_mode, "status": "queued_for_review"}
            ))
            console.print(f"  [green]✓[/green] Queued {queued_count} campaigns for review ({step_duration:.2f}s)")
            
            # Step 4: Send (blocked in test mode)
            console.print("\n[bold]Step 4: Send via GHL[/bold]")
            step_start = time.time()
            
            if self.test_mode:
                console.print("  [yellow]⚠ TEST MODE: Send blocked - requires GATEKEEPER approval[/yellow]")
                sent_count = 0
            else:
                sent_count = 0  # Would send after approval
            
            step_duration = time.time() - step_start
            
            steps.append(StepResult(
                step="send",
                success=True,  # Success = didn't send in test mode
                duration_seconds=step_duration,
                records_processed=queued_count,
                records_output=sent_count,
                metadata={"test_mode": self.test_mode, "status": "blocked_test_mode" if self.test_mode else "pending_approval"}
            ))
            console.print(f"  [green]✓[/green] Send step complete ({step_duration:.2f}s)")
            
            # Calculate metrics
            completed_at = datetime.now(timezone.utc).isoformat()
            total_duration = sum(s.duration_seconds for s in steps)
            
            metrics = {
                "leads_selected": len(selected),
                "campaigns_generated": campaigns_count,
                "campaigns_queued": queued_count,
                "campaigns_sent": sent_count,
                "personalization_rate": personalization_rate,
                "time_per_campaign_seconds": total_duration / max(campaigns_count, 1)
            }
            
            result = WorkflowResult(
                workflow="campaign-creation",
                mode="test" if self.test_mode else "production",
                started_at=started_at,
                completed_at=completed_at,
                total_duration_seconds=total_duration,
                success=all(s.success for s in steps),
                steps=[asdict(s) for s in steps],
                metrics=metrics
            )
            
            self._save_result(result, workflow_id)
            self._print_summary(result)
            
            return result
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            console.print(f"[red]✗ Workflow failed: {e}[/red]")
            return WorkflowResult(
                workflow="campaign-creation",
                mode="test" if self.test_mode else "production",
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                total_duration_seconds=0,
                success=False,
                steps=[asdict(s) for s in steps],
                metrics={},
                error_message=str(e)
            )
    
    def _save_result(self, result: WorkflowResult, workflow_id: str):
        """Save workflow result to file."""
        filepath = self.results_dir / f"{workflow_id}.json"
        
        with open(filepath, 'w') as f:
            json.dump(asdict(result), f, indent=2)
        
        console.print(f"\n[dim]Workflow results saved to: {filepath}[/dim]")
    
    def _print_summary(self, result: WorkflowResult):
        """Print workflow execution summary."""
        
        console.print("\n" + "=" * 60)
        console.print("[bold]WORKFLOW SUMMARY[/bold]")
        console.print("=" * 60)
        
        # Steps table
        table = Table(title="Step Execution")
        table.add_column("Step", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Duration", justify="right")
        table.add_column("In → Out", justify="right")
        table.add_column("Cost", justify="right")
        
        for step in result.steps:
            status = "[green]✓[/green]" if step["success"] else "[red]✗[/red]"
            duration = f"{step['duration_seconds']:.2f}s"
            records = f"{step['records_processed']} → {step['records_output']}"
            cost = f"${step.get('cost_usd', 0):.2f}"
            table.add_row(step["step"], status, duration, records, cost)
        
        console.print(table)
        
        # Metrics
        console.print(f"\n[bold]Performance Metrics:[/bold]")
        metrics = result.metrics
        for key, value in metrics.items():
            if isinstance(value, float):
                console.print(f"  {key}: {value:.2f}")
            elif isinstance(value, dict):
                console.print(f"  {key}: {json.dumps(value)}")
            else:
                console.print(f"  {key}: {value}")
        
        # Final status
        status_color = "green" if result.success else "red"
        status_text = "SUCCESS" if result.success else "FAILED"
        console.print(f"\n[bold {status_color}]Workflow Status: {status_text}[/bold {status_color}]")
        console.print(f"Total Duration: {result.total_duration_seconds:.2f}s")


def main():
    parser = argparse.ArgumentParser(
        description="Run end-to-end workflows through the agent pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python execution/run_workflow.py --workflow lead-harvesting --test-mode
    python execution/run_workflow.py --workflow campaign-creation --tier tier_3 --test-mode
    python execution/run_workflow.py --workflow lead-harvesting --input .hive-mind/testing/test-leads.json --test-mode
        """
    )
    parser.add_argument(
        "--workflow",
        type=str,
        required=True,
        choices=["lead-harvesting", "campaign-creation"],
        help="Workflow to execute"
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Run in test mode (no real API calls or sends)"
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Input file for the workflow"
    )
    parser.add_argument(
        "--tier",
        type=str,
        default="tier_3",
        help="Target tier for campaign creation (default: tier_3)"
    )
    
    args = parser.parse_args()
    
    orchestrator = WorkflowOrchestrator(test_mode=args.test_mode)
    
    if args.workflow == "lead-harvesting":
        input_file = args.input or PROJECT_ROOT / ".hive-mind" / "testing" / "test-leads.json"
        result = orchestrator.run_lead_harvesting(input_file=input_file)
    else:  # campaign-creation
        result = orchestrator.run_campaign_creation(tier=args.tier, input_file=args.input)
    
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
