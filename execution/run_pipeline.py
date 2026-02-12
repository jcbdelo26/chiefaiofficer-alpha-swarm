#!/usr/bin/env python3
"""
Unified Pipeline Runner
=======================
End-to-end pipeline that runs all agents in sequence:
    HUNTER (scrape) -> ENRICHER (enrich) -> SEGMENTOR (classify) 
    -> CRAFTER (campaign) -> GATEKEEPER (approve) -> OUTBOX (send)

Modes:
- dry_run: Log only, no external API calls
- sandbox: Mock responses, safe testing
- staging: Real APIs, test data only
- production: Full live execution

Usage:
    python execution/run_pipeline.py --mode sandbox --source competitor_gong
    python execution/run_pipeline.py --mode staging --input leads.json
    python execution/run_pipeline.py --mode production --segment tier_1 --limit 10
"""

import os
import sys
import json
import uuid
import argparse
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field
from enum import Enum

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel

console = Console()

try:
    from execution.sandbox_manager import SandboxManager, SandboxMode
    SANDBOX_AVAILABLE = True
except ImportError:
    SANDBOX_AVAILABLE = False

try:
    from core.self_annealing import SelfAnnealingEngine
    ANNEALING_AVAILABLE = True
except ImportError:
    ANNEALING_AVAILABLE = False

try:
    from core.context import ContextManager, EventType
    CONTEXT_AVAILABLE = True
except ImportError:
    CONTEXT_AVAILABLE = False


class PipelineMode(Enum):
    DRY_RUN = "dry_run"
    SANDBOX = "sandbox"
    STAGING = "staging"
    PRODUCTION = "production"


class PipelineStage(Enum):
    SCRAPE = "scrape"
    ENRICH = "enrich"
    SEGMENT = "segment"
    CRAFT = "craft"
    APPROVE = "approve"
    SEND = "send"


@dataclass
class StageResult:
    stage: PipelineStage
    success: bool
    duration_ms: float
    input_count: int
    output_count: int
    errors: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineRun:
    run_id: str
    mode: PipelineMode
    started_at: str
    completed_at: Optional[str] = None
    stages: List[StageResult] = field(default_factory=list)
    total_leads_processed: int = 0
    total_campaigns_created: int = 0
    total_errors: int = 0
    cost_estimate: float = 0.0


class UnifiedPipeline:
    """
    Orchestrates the full lead-to-campaign pipeline.
    
    Flow:
    1. HUNTER: Scrape leads from LinkedIn (competitor followers, event attendees)
    2. ENRICHER: Enrich with contact/company data via Clay
    3. SEGMENTOR: Score ICP fit, assign tiers, route to campaigns
    4. CRAFTER: Generate personalized email sequences
    5. GATEKEEPER: Queue for human approval (Tier 1) or auto-approve
    6. OUTBOX: Push to Instantly for sending
    """
    
    def __init__(self, mode: PipelineMode = PipelineMode.SANDBOX):
        self.mode = mode
        self.run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        
        self.hive_mind = PROJECT_ROOT / ".hive-mind"
        self.hive_mind.mkdir(parents=True, exist_ok=True)
        
        if ANNEALING_AVAILABLE:
            self.annealing = SelfAnnealingEngine()
        else:
            self.annealing = None
        
        if CONTEXT_AVAILABLE:
            self.context = ContextManager(workflow_id=self.run_id)
        else:
            self.context = None
        
        self.current_run: Optional[PipelineRun] = None
        self.leads: List[Dict] = []
        self.enriched: List[Dict] = []
        self.segmented: List[Dict] = []
        self.campaigns: List[Dict] = []
    
    def _is_safe_mode(self) -> bool:
        return self.mode in [PipelineMode.DRY_RUN, PipelineMode.SANDBOX]
    
    async def run_full_pipeline(
        self,
        source: Optional[str] = None,
        input_file: Optional[Path] = None,
        segment_filter: Optional[str] = None,
        limit: int = 100
    ) -> PipelineRun:
        """Run the complete pipeline end-to-end."""
        
        self.current_run = PipelineRun(
            run_id=self.run_id,
            mode=self.mode,
            started_at=datetime.utcnow().isoformat()
        )
        
        console.print(Panel(
            f"[bold]Pipeline Run: {self.run_id}[/bold]\n"
            f"Mode: {self.mode.value}\n"
            f"Source: {source or input_file or 'default'}",
            title="Starting Pipeline"
        ))
        
        stages = [
            ("Scraping", PipelineStage.SCRAPE, lambda: self._stage_scrape(source, input_file, limit)),
            ("Enriching", PipelineStage.ENRICH, lambda: self._stage_enrich()),
            ("Segmenting", PipelineStage.SEGMENT, lambda: self._stage_segment(segment_filter)),
            ("Crafting", PipelineStage.CRAFT, lambda: self._stage_craft()),
            ("Approving", PipelineStage.APPROVE, lambda: self._stage_approve()),
            ("Sending", PipelineStage.SEND, lambda: self._stage_send()),
        ]
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console
        ) as progress:
            task = progress.add_task("Running pipeline...", total=len(stages))
            
            for name, stage, executor in stages:
                progress.update(task, description=f"[cyan]{name}...")
                
                try:
                    result = await executor()
                    self.current_run.stages.append(result)
                    
                    if not result.success:
                        console.print(f"[red]Stage {name} failed: {result.errors}[/red]")
                        if self.mode == PipelineMode.PRODUCTION:
                            break
                    
                except Exception as e:
                    error_result = StageResult(
                        stage=stage,
                        success=False,
                        duration_ms=0,
                        input_count=0,
                        output_count=0,
                        errors=[str(e)]
                    )
                    self.current_run.stages.append(error_result)
                    console.print(f"[red]Stage {name} error: {e}[/red]")
                
                progress.advance(task)
        
        self.current_run.completed_at = datetime.utcnow().isoformat()
        self.current_run.total_leads_processed = len(self.segmented)
        self.current_run.total_campaigns_created = len(self.campaigns)
        self.current_run.total_errors = sum(len(s.errors) for s in self.current_run.stages)
        
        self._save_run_report()
        self._print_summary()
        
        return self.current_run
    
    async def _stage_scrape(
        self, 
        source: Optional[str], 
        input_file: Optional[Path],
        limit: int
    ) -> StageResult:
        """Stage 1: Scrape or load leads."""
        import time
        start = time.time()
        errors = []
        
        if input_file and input_file.exists():
            with open(input_file) as f:
                self.leads = json.load(f)[:limit]
        elif self._is_safe_mode():
            from execution.generate_test_data import generate_test_batch
            scenario = "competitor_displacement" if source and "competitor" in source else "event_followup"
            self.leads = generate_test_batch(min(limit, 20), scenario)
        else:
            try:
                from execution.hunter_scrape_followers import LinkedInFollowerScraper
                scraper = LinkedInFollowerScraper()
                
                if source and source.startswith("competitor_"):
                    company = source.replace("competitor_", "")
                    self.leads = [vars(l) if hasattr(l, '__dict__') else l for l in scraper.fetch_followers(f"https://www.linkedin.com/company/{company}", company, limit=limit)]
                else:
                    self.leads = [vars(l) if hasattr(l, '__dict__') else l for l in scraper.fetch_followers("https://www.linkedin.com/company/gong", "gong", limit=limit)]
                    
            except Exception as e:
                errors.append(f"Scraper error: {e}")
                from execution.generate_test_data import generate_test_batch
                self.leads = generate_test_batch(20, "competitor_displacement")
        
        duration = (time.time() - start) * 1000
        
        return StageResult(
            stage=PipelineStage.SCRAPE,
            success=len(errors) == 0,
            duration_ms=duration,
            input_count=0,
            output_count=len(self.leads),
            errors=errors,
            metrics={"source": source or "test_data"}
        )
    
    async def _stage_enrich(self) -> StageResult:
        """Stage 2: Enrich leads with contact/company data."""
        import time
        start = time.time()
        errors = []
        
        if self._is_safe_mode():
            from execution.generate_test_data import generate_enrichment_data
            self.enriched = []
            for lead in self.leads:
                enrichment = generate_enrichment_data(lead)
                enriched_lead = {**lead, **enrichment}
                enriched_lead["enriched"] = True
                self.enriched.append(enriched_lead)
        else:
            try:
                from execution.enricher_clay_waterfall import ClayEnricher
                enricher = ClayEnricher()
                self.enriched = []
                
                for lead in self.leads:
                    try:
                        result = enricher.enrich_lead(
                            lead_id=lead.get("lead_id", lead.get("email", "")),
                            linkedin_url=lead.get("linkedin_url", lead.get("profile_url", "")),
                            name=lead.get("name", ""),
                            company=lead.get("company", "")
                        )
                        self.enriched.append(result)
                    except Exception as e:
                        errors.append(f"Enrich failed for {lead.get('email', 'unknown')}: {e}")
                        self.enriched.append({**lead, "enriched": False, "enrich_error": str(e)})
                        
            except ImportError as e:
                errors.append(f"Enricher import error: {e}")
                self.enriched = [{**l, "enriched": False} for l in self.leads]
        
        duration = (time.time() - start) * 1000
        
        return StageResult(
            stage=PipelineStage.ENRICH,
            success=len([e for e in self.enriched if e.get("enriched")]) > 0,
            duration_ms=duration,
            input_count=len(self.leads),
            output_count=len(self.enriched),
            errors=errors[:5],
            metrics={
                "enriched_count": len([e for e in self.enriched if e.get("enriched")]),
                "failed_count": len([e for e in self.enriched if not e.get("enriched")])
            }
        )
    
    async def _stage_segment(self, segment_filter: Optional[str] = None) -> StageResult:
        """Stage 3: Score and segment leads."""
        import time
        start = time.time()
        errors = []
        
        try:
            from execution.segmentor_classify import LeadSegmentor
            segmentor = LeadSegmentor()
            
            segmented_results = []
            for lead in self.enriched:
                result = segmentor.segment_lead(lead)
                if hasattr(result, '__dataclass_fields__'):
                    segmented_results.append(asdict(result))
                elif hasattr(result, 'to_dict'):
                    segmented_results.append(result.to_dict())
                else:
                    segmented_results.append(result)
            
            self.segmented = segmented_results
            
            if segment_filter:
                self.segmented = [l for l in self.segmented if l.get("icp_tier") == segment_filter]
                
        except (ImportError, AttributeError) as e:
            console.print(f"[yellow]Using fallback segmentor: {e}[/yellow]")
            self.segmented = []
            for lead in self.enriched:
                score = lead.get("icp_score", 50)
                if score >= 80:
                    tier = "tier_1"
                elif score >= 60:
                    tier = "tier_2"
                elif score >= 40:
                    tier = "tier_3"
                else:
                    tier = "tier_4"
                
                segmented_lead = {
                    **lead,
                    "icp_tier": tier,
                    "icp_score": score,
                    "recommended_campaign": self._get_campaign(tier, lead.get("source", "unknown"))
                }
                self.segmented.append(segmented_lead)
            
            if segment_filter:
                self.segmented = [l for l in self.segmented if l.get("icp_tier") == segment_filter]
        
        if self.annealing:
            for lead in self.segmented:
                self.annealing.learn_from_outcome(
                    workflow=f"segment_{lead.get('id', 'unknown')}",
                    outcome={"segmented": True, "tier": lead.get("icp_tier")},
                    success=True
                )
        
        duration = (time.time() - start) * 1000
        
        tier_counts = {}
        for lead in self.segmented:
            tier = lead.get("icp_tier", "unknown")
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        return StageResult(
            stage=PipelineStage.SEGMENT,
            success=len(self.segmented) > 0,
            duration_ms=duration,
            input_count=len(self.enriched),
            output_count=len(self.segmented),
            errors=errors,
            metrics={"tier_distribution": tier_counts}
        )
    
    def _get_campaign(self, tier: str, source: str) -> str:
        """Get campaign recommendation based on tier and source."""
        if "competitor" in source:
            return "competitor_displacement"
        elif "event" in source:
            return "event_followup"
        elif "website" in source or "visitor" in source:
            return "intent_based"
        elif tier == "tier_1":
            return "high_touch_personalized"
        elif tier == "tier_2":
            return "mid_touch_segmented"
        else:
            return "nurture_sequence"
    
    async def _stage_craft(self) -> StageResult:
        """Stage 4: Generate campaigns."""
        import time
        start = time.time()
        errors = []
        
        campaign_groups = {}
        for lead in self.segmented:
            campaign_type = lead.get("recommended_campaign", "nurture_sequence")
            if campaign_type not in campaign_groups:
                campaign_groups[campaign_type] = []
            campaign_groups[campaign_type].append(lead)
        
        self.campaigns = []
        
        for campaign_type, leads in campaign_groups.items():
            if self._is_safe_mode():
                campaign = {
                    "campaign_id": f"camp_{campaign_type}_{uuid.uuid4().hex[:8]}",
                    "campaign_type": campaign_type,
                    "lead_count": len(leads),
                    "leads": leads,
                    "status": "draft",
                    "created_at": datetime.utcnow().isoformat(),
                    "subject_line": f"[{campaign_type.replace('_', ' ').title()}] Personalized outreach",
                    "sequence_steps": 3
                }
                self.campaigns.append(campaign)
            else:
                try:
                    from execution.crafter_campaign import CampaignCrafter
                    crafter = CampaignCrafter()
                    campaign = crafter.create_campaign(leads, campaign_type)
                    self.campaigns.append(asdict(campaign) if hasattr(campaign, '__dataclass_fields__') else campaign)
                except Exception as e:
                    errors.append(f"Crafter error for {campaign_type}: {e}")
        
        duration = (time.time() - start) * 1000
        
        return StageResult(
            stage=PipelineStage.CRAFT,
            success=len(self.campaigns) > 0,
            duration_ms=duration,
            input_count=len(self.segmented),
            output_count=len(self.campaigns),
            errors=errors,
            metrics={
                "campaigns_by_type": {c["campaign_type"]: c["lead_count"] for c in self.campaigns}
            }
        )
    
    async def _stage_approve(self) -> StageResult:
        """Stage 5: Queue for approval or auto-approve."""
        import time
        start = time.time()
        
        for campaign in self.campaigns:
            has_tier_1 = any(
                l.get("icp_tier") == "tier_1" 
                for l in campaign.get("leads", [])
            )
            
            if has_tier_1:
                campaign["status"] = "pending_review"
                campaign["requires_approval"] = True
            else:
                if self.mode == PipelineMode.PRODUCTION:
                    campaign["status"] = "approved"
                else:
                    campaign["status"] = "approved_sandbox"
                campaign["requires_approval"] = False
        
        pending = len([c for c in self.campaigns if c.get("requires_approval")])
        approved = len([c for c in self.campaigns if not c.get("requires_approval")])
        
        duration = (time.time() - start) * 1000
        
        return StageResult(
            stage=PipelineStage.APPROVE,
            success=True,
            duration_ms=duration,
            input_count=len(self.campaigns),
            output_count=len(self.campaigns),
            errors=[],
            metrics={"pending_review": pending, "auto_approved": approved}
        )
    
    async def _stage_send(self) -> StageResult:
        """Stage 6: Push to outbox (Instantly)."""
        import time
        start = time.time()
        errors = []
        sent = 0
        
        approved_campaigns = [c for c in self.campaigns if c.get("status") in ["approved", "approved_sandbox"]]
        
        if self._is_safe_mode():
            for campaign in approved_campaigns:
                campaign["sent_to_instantly"] = True
                campaign["instantly_campaign_id"] = f"mock_{uuid.uuid4().hex[:8]}"
                sent += campaign.get("lead_count", 0)
        elif self.mode == PipelineMode.PRODUCTION:
            try:
                from execution.ingest_instantly_templates import push_campaign_to_instantly
                
                for campaign in approved_campaigns:
                    try:
                        result = push_campaign_to_instantly(campaign)
                        campaign["sent_to_instantly"] = True
                        campaign["instantly_campaign_id"] = result.get("campaign_id")
                        sent += campaign.get("lead_count", 0)
                    except Exception as e:
                        errors.append(f"Instantly push failed: {e}")
                        campaign["sent_to_instantly"] = False
                        
            except ImportError:
                errors.append("Instantly integration not available")
        
        duration = (time.time() - start) * 1000
        
        return StageResult(
            stage=PipelineStage.SEND,
            success=sent > 0 or len(approved_campaigns) == 0,
            duration_ms=duration,
            input_count=len(approved_campaigns),
            output_count=sent,
            errors=errors,
            metrics={"leads_queued": sent, "campaigns_pushed": len(approved_campaigns)}
        )
    
    def _save_run_report(self):
        """Save pipeline run report."""
        report_dir = self.hive_mind / "pipeline_runs"
        report_dir.mkdir(parents=True, exist_ok=True)
        
        report = {
            "run_id": self.current_run.run_id,
            "mode": self.current_run.mode.value,
            "started_at": self.current_run.started_at,
            "completed_at": self.current_run.completed_at,
            "total_leads_processed": self.current_run.total_leads_processed,
            "total_campaigns_created": self.current_run.total_campaigns_created,
            "total_errors": self.current_run.total_errors,
            "stages": [
                {
                    "stage": s.stage.value,
                    "success": s.success,
                    "duration_ms": s.duration_ms,
                    "input_count": s.input_count,
                    "output_count": s.output_count,
                    "errors": s.errors,
                    "metrics": s.metrics
                }
                for s in self.current_run.stages
            ]
        }
        
        report_path = report_dir / f"{self.run_id}.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        
        campaigns_path = report_dir / f"{self.run_id}_campaigns.json"
        with open(campaigns_path, "w") as f:
            campaigns_safe = []
            for c in self.campaigns:
                safe_c = {k: v for k, v in c.items() if k != "leads"}
                safe_c["lead_count"] = len(c.get("leads", []))
                campaigns_safe.append(safe_c)
            json.dump(campaigns_safe, f, indent=2)
    
    def _print_summary(self):
        """Print pipeline run summary."""
        console.print("\n")
        
        table = Table(title=f"Pipeline Run: {self.run_id}")
        table.add_column("Stage", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Duration", justify="right")
        table.add_column("In", justify="right")
        table.add_column("Out", justify="right")
        table.add_column("Errors", justify="right")
        
        for stage in self.current_run.stages:
            status = "[green]PASS[/green]" if stage.success else "[red]FAIL[/red]"
            table.add_row(
                stage.stage.value,
                status,
                f"{stage.duration_ms:.0f}ms",
                str(stage.input_count),
                str(stage.output_count),
                str(len(stage.errors))
            )
        
        console.print(table)
        
        total_duration = sum(s.duration_ms for s in self.current_run.stages)
        all_passed = all(s.success for s in self.current_run.stages)
        
        summary = Panel(
            f"[bold]Total Duration:[/bold] {total_duration:.0f}ms\n"
            f"[bold]Leads Processed:[/bold] {self.current_run.total_leads_processed}\n"
            f"[bold]Campaigns Created:[/bold] {self.current_run.total_campaigns_created}\n"
            f"[bold]Errors:[/bold] {self.current_run.total_errors}\n"
            f"[bold]Status:[/bold] {'[green]SUCCESS[/green]' if all_passed else '[red]FAILED[/red]'}",
            title="Summary"
        )
        console.print(summary)


async def main():
    parser = argparse.ArgumentParser(description="Unified Pipeline Runner")
    parser.add_argument("--mode", choices=["dry_run", "sandbox", "staging", "production"], default="sandbox")
    parser.add_argument("--source", type=str, help="Lead source (e.g., competitor_gong, event_saastr)")
    parser.add_argument("--input", type=str, help="Input JSON file with leads")
    parser.add_argument("--segment", type=str, help="Filter to specific segment (tier_1, tier_2, etc.)")
    parser.add_argument("--limit", type=int, default=100, help="Max leads to process")
    args = parser.parse_args()
    
    mode = PipelineMode(args.mode)
    
    if mode == PipelineMode.PRODUCTION:
        console.print("[yellow]WARNING: Running in PRODUCTION mode. Real emails may be sent![/yellow]")
        confirm = input("Type 'yes' to continue: ")
        if confirm.lower() != "yes":
            console.print("[red]Aborted.[/red]")
            return
    
    pipeline = UnifiedPipeline(mode=mode)
    
    input_path = Path(args.input) if args.input else None
    
    await pipeline.run_full_pipeline(
        source=args.source,
        input_file=input_path,
        segment_filter=args.segment,
        limit=args.limit
    )


if __name__ == "__main__":
    asyncio.run(main())
