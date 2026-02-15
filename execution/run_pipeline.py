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

import platform
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.panel import Panel

# On Windows, disable legacy renderer to avoid cp1252 braille/emoji crashes
_is_windows = platform.system() == "Windows"
console = Console(force_terminal=not _is_windows)

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
    from core.alerts import send_warning, send_critical, send_info
    ALERTS_AVAILABLE = True
except ImportError:
    ALERTS_AVAILABLE = False

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
    6. OUTBOX: Queue to shadow mode for HoS dashboard approval → GHL send
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
        """Check if pipeline should use test data instead of real APIs.

        Safe mode is triggered when:
        - Mode is explicitly SANDBOX or DRY_RUN
        - No scraping credentials at all (no cookie AND no API keys)
        """
        if self.mode in [PipelineMode.DRY_RUN, PipelineMode.SANDBOX]:
            return True
        # Allow scraping if ANY credential is available (cookie or Apollo)
        import os
        has_cookie = bool(os.getenv("LINKEDIN_COOKIE"))
        has_apollo = bool(os.getenv("APOLLO_API_KEY"))
        if not has_cookie and not has_apollo:
            console.print("[yellow]No scraping credentials set — using test data fallback[/yellow]")
            return True
        return False
    
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
        
        # Use ASCII spinner on Windows to avoid cp1252 braille character crash
        spinner = SpinnerColumn("line") if _is_windows else SpinnerColumn()
        with Progress(
            spinner,
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
                        if ALERTS_AVAILABLE:
                            send_warning(
                                f"Pipeline stage failed: {name}",
                                f"Stage '{name}' failed in run {self.run_id} "
                                f"({self.mode.value}). Errors: {'; '.join(result.errors[:3])}",
                                metadata={"run_id": self.run_id,
                                          "stage": name,
                                          "mode": self.mode.value,
                                          "error_count": len(result.errors)},
                                source="pipeline",
                            )
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
                    if ALERTS_AVAILABLE:
                        send_critical(
                            f"Pipeline stage exception: {name}",
                            f"Stage '{name}' threw an exception in run "
                            f"{self.run_id}: {e}",
                            metadata={"run_id": self.run_id,
                                      "stage": name,
                                      "mode": self.mode.value,
                                      "exception": str(e)},
                            source="pipeline",
                        )
                
                progress.advance(task)
        
        self.current_run.completed_at = datetime.utcnow().isoformat()
        self.current_run.total_leads_processed = len(self.segmented)
        self.current_run.total_campaigns_created = len(self.campaigns)
        self.current_run.total_errors = sum(len(s.errors) for s in self.current_run.stages)
        
        self._save_run_report()
        self._print_summary()

        # Send pipeline completion alert
        if ALERTS_AVAILABLE and self.current_run.total_errors > 0:
            send_warning(
                f"Pipeline completed with {self.current_run.total_errors} errors",
                f"Run {self.run_id} ({self.mode.value}): "
                f"{self.current_run.total_leads_processed} leads, "
                f"{self.current_run.total_campaigns_created} campaigns, "
                f"{self.current_run.total_errors} errors.",
                metadata={"run_id": self.run_id,
                          "mode": self.mode.value,
                          "leads": self.current_run.total_leads_processed,
                          "campaigns": self.current_run.total_campaigns_created},
                source="pipeline",
            )

        return self.current_run
    
    # Hard timeout for scrape stage — prevents pipeline from ever hanging
    SCRAPE_STAGE_TIMEOUT_SECONDS = 45
    
    async def _stage_scrape(
        self, 
        source: Optional[str], 
        input_file: Optional[Path],
        limit: int
    ) -> StageResult:
        """Stage 1: Scrape or load leads.
        
        Architecture:
        1. If input_file provided → load from file (instant)
        2. If safe mode → generate test data (instant)
        3. Otherwise → attempt LinkedIn scraping with hard timeout
           - Pre-flight: validate LinkedIn session (10s timeout)
           - Scrape: fetch_followers with 30s timeout
           - Backstop: asyncio.wait_for(45s) wraps entire attempt
           - On ANY failure → graceful fallback to test data
        """
        import time
        start = time.time()
        errors = []
        scraper_source = "test_data"  # Track actual data source
        
        if input_file and input_file.exists():
            with open(input_file) as f:
                self.leads = json.load(f)[:limit]
            scraper_source = f"file:{input_file.name}"
        elif self._is_safe_mode():
            from execution.generate_test_data import generate_test_batch
            scenario = "competitor_displacement" if source and "competitor" in source else "event_followup"
            self.leads = generate_test_batch(min(limit, 20), scenario)
            scraper_source = "test_data_safe_mode"
        else:
            try:
                # Wrap entire scraper path in a hard timeout
                self.leads = await asyncio.wait_for(
                    self._attempt_live_scrape(source, limit),
                    timeout=self.SCRAPE_STAGE_TIMEOUT_SECONDS
                )
                scraper_source = f"linkedin_live:{source or 'gong'}"
            except asyncio.TimeoutError:
                errors.append(
                    f"Scraper timed out after {self.SCRAPE_STAGE_TIMEOUT_SECONDS}s — "
                    "falling back to test data"
                )
                from execution.generate_test_data import generate_test_batch
                self.leads = generate_test_batch(20, "competitor_displacement")
                scraper_source = "test_data_timeout_fallback"
            except Exception as e:
                errors.append(f"Scraper error: {e}")
                from execution.generate_test_data import generate_test_batch
                self.leads = generate_test_batch(20, "competitor_displacement")
                scraper_source = "test_data_error_fallback"
        
        duration = (time.time() - start) * 1000
        
        # Stage succeeds if we have leads (even via fallback). Errors become warnings.
        return StageResult(
            stage=PipelineStage.SCRAPE,
            success=len(self.leads) > 0,
            duration_ms=duration,
            input_count=0,
            output_count=len(self.leads),
            errors=errors,
            metrics={"source": scraper_source}
        )
    
    async def _attempt_live_scrape(
        self, source: Optional[str], limit: int
    ) -> List[Dict]:
        """Attempt live LinkedIn scraping with pre-flight validation.
        
        Runs in a thread executor to prevent blocking the async event loop.
        Raises ScraperUnavailableError if session is invalid.
        """
        from execution.hunter_scrape_followers import (
            LinkedInFollowerScraper, ScraperUnavailableError
        )
        
        def _sync_scrape():
            scraper = LinkedInFollowerScraper()
            
            # Pre-flight: validate session before attempting scrape
            scraper.validate_session()
            
            if source and source.startswith("competitor_"):
                company = source.replace("competitor_", "")
                results = scraper.fetch_followers(
                    f"https://www.linkedin.com/company/{company}",
                    company, limit=limit
                )
            else:
                results = scraper.fetch_followers(
                    "https://www.linkedin.com/company/gong",
                    "gong", limit=limit
                )
            
            # Convert dataclass to dict if needed
            return [vars(l) if hasattr(l, '__dict__') else l for l in results]
        
        # Run synchronous scraper in thread pool to avoid blocking event loop
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_scrape)
    
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
                from execution.enricher_waterfall import ClayEnricher
                from dataclasses import asdict
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
                        if result is not None:
                            # Merge original lead dict with enrichment data
                            enriched_dict = {**lead, **asdict(result), "enriched": True}
                            self.enriched.append(enriched_dict)
                        else:
                            # Normalize company to dict for downstream segmentor compatibility
                            fallback = {**lead, "enriched": False}
                            if isinstance(fallback.get("company"), str):
                                fallback["company"] = {"name": fallback["company"]}
                            self.enriched.append(fallback)
                    except Exception as e:
                        errors.append(f"Enrich failed for {lead.get('email', 'unknown')}: {e}")
                        fallback = {**lead, "enriched": False, "enrich_error": str(e)}
                        if isinstance(fallback.get("company"), str):
                            fallback["company"] = {"name": fallback["company"]}
                        self.enriched.append(fallback)

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
        
        # Normalize lead fields for downstream crafter compatibility
        for lead in self.segmented:
            if not lead.get("first_name") and lead.get("name"):
                parts = lead["name"].strip().split(None, 1)
                lead["first_name"] = parts[0] if parts else ""
                lead["last_name"] = parts[1] if len(parts) > 1 else ""

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
        """Stage 6: Queue emails to shadow mode for HoS dashboard approval.

        All campaign emails are written to .hive-mind/shadow_mode_emails/
        with status 'pending'. The HoS dashboard shows these for human
        review, and approved emails are sent via GHL.
        """
        import time
        start = time.time()
        errors = []
        queued = 0

        shadow_dir = self.hive_mind / "shadow_mode_emails"
        shadow_dir.mkdir(parents=True, exist_ok=True)

        approved_campaigns = [c for c in self.campaigns
                              if c.get("status") in ["approved", "approved_sandbox",
                                                      "pending_review"]]

        for campaign in approved_campaigns:
            leads = campaign.get("leads", [])
            sequence = campaign.get("sequence", [])

            # Extract first email step content (production has full sequence)
            if sequence:
                step = sequence[0] if isinstance(sequence[0], dict) else {}
                subject = step.get("subject_a", campaign.get("subject_line", "Outreach"))
                body = step.get("body_a", "")
            else:
                subject = campaign.get("subject_line", "Personalized outreach")
                body = ""

            for lead in leads:
                # Resolve email from multiple possible locations
                email_addr = (
                    lead.get("email")
                    or lead.get("work_email")
                    or lead.get("contact", {}).get("verified_email")
                    or lead.get("contact", {}).get("work_email")
                    or lead.get("original_lead", {}).get("email")
                )
                if not email_addr:
                    errors.append(f"No email for lead {lead.get('name', 'unknown')}")
                    continue

                lead_slug = (lead.get("name", "unknown")
                             .replace(" ", "_").lower()[:30])
                email_id = (f"pipeline_{campaign['campaign_id']}"
                            f"_{lead_slug}_{uuid.uuid4().hex[:6]}")

                tier = lead.get("icp_tier", "tier_3")
                company_raw = lead.get("company", "")
                company_name = (company_raw if isinstance(company_raw, str)
                                else company_raw.get("name", "")
                                if isinstance(company_raw, dict) else "")

                shadow_email = {
                    "email_id": email_id,
                    "status": "pending",
                    "to": email_addr,
                    "subject": subject,
                    "body": body,
                    "source": "pipeline",
                    "timestamp": datetime.utcnow().isoformat() + "+00:00",
                    "created_at": datetime.utcnow().isoformat() + "+00:00",
                    "recipient_data": {
                        "name": lead.get("name", ""),
                        "company": company_name,
                        "title": lead.get("title", ""),
                        "linkedin_url": lead.get("linkedin_url"),
                    },
                    "context": {
                        "intent_score": lead.get("intent_score", 0),
                        "icp_tier": tier,
                        "icp_score": lead.get("icp_score", 0),
                        "campaign_type": campaign.get("campaign_type", ""),
                        "campaign_id": campaign.get("campaign_id", ""),
                        "pipeline_run_id": self.run_id,
                    },
                    "priority": ("high" if tier == "tier_1"
                                 else "medium" if tier == "tier_2"
                                 else "normal"),
                    "tier": tier,
                    "synthetic": self._is_safe_mode(),
                    "contact_id": lead.get("contact_id"),
                    "template_id": None,
                }

                filepath = shadow_dir / f"{email_id}.json"
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        json.dump(shadow_email, f, indent=2, ensure_ascii=False)
                    queued += 1
                except Exception as e:
                    errors.append(f"Failed to write shadow email: {e}")

            campaign["shadow_queued"] = True
            campaign["shadow_email_count"] = len(leads)

        duration = (time.time() - start) * 1000

        return StageResult(
            stage=PipelineStage.SEND,
            success=queued > 0 or len(approved_campaigns) == 0,
            duration_ms=duration,
            input_count=len(approved_campaigns),
            output_count=queued,
            errors=errors,
            metrics={"emails_queued": queued,
                     "campaigns_processed": len(approved_campaigns)}
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
