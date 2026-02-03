#!/usr/bin/env python3
"""
Priority #1: Simulation Harness
================================
Run 1000 leads through the full swarm pipeline to prove it works.

Features:
- Generate synthetic test leads with realistic data
- Run through: HUNTER → ENRICHER → SEGMENTOR → CRAFTER → GATEKEEPER
- Track metrics: success rate, confidence scores, tier distribution
- Generate detailed report

Usage:
    python execution/priority_1_simulation_harness.py --leads 1000
    python execution/priority_1_simulation_harness.py --leads 100 --quick
"""

import os
import sys
import json
import random
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
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel

console = Console(force_terminal=True)


# =============================================================================
# SYNTHETIC DATA GENERATION
# =============================================================================

FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda",
    "William", "Barbara", "David", "Elizabeth", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Christopher", "Karen", "Daniel", "Nancy", "Matthew", "Lisa",
    "Anthony", "Betty", "Mark", "Margaret", "Donald", "Sandra", "Steven", "Ashley"
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker"
]

COMPANIES = [
    ("Acme Corp", "acme.com", 250, "B2B SaaS"),
    ("TechFlow", "techflow.io", 120, "Technology"),
    ("DataDriven Inc", "datadriven.com", 500, "Enterprise Software"),
    ("CloudScale", "cloudscale.co", 75, "Cloud Infrastructure"),
    ("SalesForce Pro", "salesforcepro.com", 300, "Sales Technology"),
    ("MarketMind", "marketmind.io", 45, "Marketing Technology"),
    ("RevOps Hub", "revopshub.com", 180, "Revenue Operations"),
    ("GrowthEngine", "growthengine.co", 90, "Growth Platform"),
    ("PipelineAI", "pipelineai.com", 150, "AI Sales Tools"),
    ("LeadGenius", "leadgenius.io", 60, "Lead Generation"),
    ("CloserIQ", "closeriq.com", 200, "Sales Intelligence"),
    ("DealFlow", "dealflow.co", 110, "Deal Management"),
    ("ProspectPro", "prospectpro.io", 85, "Prospecting Tools"),
    ("OutreachMax", "outreachmax.com", 220, "Sales Engagement"),
    ("ConvertLabs", "convertlabs.io", 130, "Conversion Optimization"),
    ("RevenueCloud", "revenuecloud.com", 400, "Revenue Platform"),
    ("SalesStack", "salesstack.co", 95, "Sales Stack"),
    ("QuotaHit", "quotahit.io", 70, "Sales Performance"),
    ("WinRate", "winrate.com", 160, "Win Rate Analytics"),
    ("BookedMeetings", "bookedmeetings.co", 55, "Meeting Scheduling"),
]

TITLES = [
    ("CEO", 25, "c_level"),
    ("CRO", 25, "c_level"),
    ("CFO", 25, "c_level"),
    ("CTO", 22, "c_level"),
    ("VP of Sales", 22, "vp"),
    ("VP of Revenue", 22, "vp"),
    ("VP of Marketing", 20, "vp"),
    ("Head of Sales", 20, "vp"),
    ("Director of Sales", 15, "director"),
    ("Director of Revenue Operations", 15, "director"),
    ("Senior Director of Sales", 18, "director"),
    ("Sales Manager", 8, "manager"),
    ("Revenue Operations Manager", 10, "manager"),
    ("Account Executive", 5, "individual"),
    ("SDR Manager", 8, "manager"),
    ("Marketing Manager", 6, "manager"),
]

SOURCE_TYPES = [
    ("competitor_follower", 0.30),
    ("event_attendee", 0.20),
    ("website_visitor", 0.15),
    ("content_downloader", 0.12),
    ("post_commenter", 0.08),
    ("group_member", 0.08),
    ("demo_requester", 0.05),
    ("webinar_registrant", 0.02),
]

TECHNOLOGIES = [
    "Salesforce", "HubSpot", "Gong", "Clari", "Outreach", "SalesLoft",
    "ZoomInfo", "Apollo", "LinkedIn Sales Navigator", "Pipedrive",
    "Monday.com", "Slack", "Zoom", "Microsoft Teams", "Intercom"
]


def generate_synthetic_lead(lead_id: int) -> Dict[str, Any]:
    """Generate a single synthetic lead with realistic data."""
    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)
    company_data = random.choice(COMPANIES)
    title_data = random.choice(TITLES)
    
    # Weight source types
    source_type = random.choices(
        [s[0] for s in SOURCE_TYPES],
        weights=[s[1] for s in SOURCE_TYPES]
    )[0]
    
    # Generate email (80% have email)
    has_email = random.random() < 0.80
    email = f"{first_name.lower()}.{last_name.lower()}@{company_data[1]}" if has_email else None
    
    # Generate intent signals (varies by source)
    intent = {}
    if source_type in ["website_visitor", "content_downloader", "demo_requester"]:
        intent["website_visits"] = random.randint(1, 10)
        if random.random() < 0.3:
            intent["pricing_page_visits"] = random.randint(1, 3)
        if source_type == "content_downloader":
            intent["content_downloads"] = random.randint(1, 5)
        if source_type == "demo_requester":
            intent["demo_requested"] = True
    
    # Generate tech stack (60% have tech data)
    technologies = []
    if random.random() < 0.60:
        num_techs = random.randint(2, 6)
        technologies = random.sample(TECHNOLOGIES, min(num_techs, len(TECHNOLOGIES)))
    
    # Add some variability to company size
    base_size = company_data[2]
    employee_count = max(10, base_size + random.randint(-50, 50))
    
    return {
        "lead_id": f"sim_lead_{lead_id:05d}",
        "linkedin_url": f"https://linkedin.com/in/{first_name.lower()}{last_name.lower()}{random.randint(100,999)}",
        "name": f"{first_name} {last_name}",
        "first_name": first_name,
        "last_name": last_name,
        "title": title_data[0],
        "title_score": title_data[1],
        "title_level": title_data[2],
        "email": email,
        "company": {
            "name": company_data[0],
            "domain": company_data[1],
            "employee_count": employee_count,
            "industry": company_data[3],
            "technologies": technologies
        },
        "source_type": source_type,
        "source_name": f"Simulation Source {lead_id % 10}",
        "intent": intent,
        "created_at": datetime.now(timezone.utc).isoformat()
    }


def generate_lead_batch(count: int) -> List[Dict[str, Any]]:
    """Generate a batch of synthetic leads."""
    return [generate_synthetic_lead(i) for i in range(count)]


# =============================================================================
# SIMULATION ENGINE
# =============================================================================

@dataclass
class SimulationMetrics:
    """Metrics collected during simulation."""
    total_leads: int = 0
    processed_leads: int = 0
    failed_leads: int = 0
    
    # Tier distribution
    tier_1_count: int = 0
    tier_2_count: int = 0
    tier_3_count: int = 0
    tier_4_count: int = 0
    
    # Confidence metrics
    confidence_scores: List[float] = field(default_factory=list)
    replan_triggered: int = 0
    
    # Stage success rates
    enrichment_success: int = 0
    enrichment_failed: int = 0
    qualification_success: int = 0
    crafting_success: int = 0
    approval_requested: int = 0
    
    # Timing
    total_time_seconds: float = 0
    avg_lead_time_ms: float = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "avg_confidence": sum(self.confidence_scores) / len(self.confidence_scores) if self.confidence_scores else 0,
            "success_rate": (self.processed_leads / self.total_leads * 100) if self.total_leads else 0,
            "tier_distribution": {
                "tier_1": self.tier_1_count,
                "tier_2": self.tier_2_count,
                "tier_3": self.tier_3_count,
                "tier_4": self.tier_4_count
            }
        }


class SimulationEngine:
    """
    Runs synthetic leads through the full swarm pipeline.
    
    Simulates:
    1. HUNTER: Lead capture (already generated)
    2. ENRICHER: Data validation/augmentation
    3. SEGMENTOR: ICP scoring and tier assignment
    4. CRAFTER: Email generation
    5. GATEKEEPER: Approval routing
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(".hive-mind/simulations")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metrics = SimulationMetrics()
        self.results: List[Dict[str, Any]] = []
        
        # Import core modules
        try:
            from core.confidence_replanning import ConfidenceAwareSegmentor, QualificationResult
            self.segmentor = ConfidenceAwareSegmentor(confidence_threshold=0.85)
            self.confidence_available = True
        except ImportError:
            self.segmentor = None
            self.confidence_available = False
    
    async def simulate_enrichment(self, lead: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """Simulate ENRICHER stage."""
        # Simulate enrichment success/failure (90% success rate)
        success = random.random() < 0.90
        
        if success:
            # Add enriched data
            enriched = lead.copy()
            
            # Add email if missing (70% success)
            if not enriched.get("email") and random.random() < 0.70:
                first = enriched.get("first_name", "user").lower()
                last = enriched.get("last_name", "name").lower()
                domain = enriched.get("company", {}).get("domain", "example.com")
                enriched["email"] = f"{first}.{last}@{domain}"
                enriched["email_verified"] = True
            
            # Add phone (30% of time)
            if random.random() < 0.30:
                enriched["phone"] = f"+1-555-{random.randint(100,999)}-{random.randint(1000,9999)}"
            
            return True, enriched
        else:
            return False, {"error": "Enrichment failed", "lead_id": lead.get("lead_id")}
    
    def calculate_icp_score(self, lead: Dict[str, Any]) -> Tuple[int, Dict[str, int]]:
        """Calculate ICP score for a lead."""
        score = 0
        breakdown = {}
        
        # Company size scoring (20 points max)
        employee_count = lead.get("company", {}).get("employee_count", 0)
        if 51 <= employee_count <= 500:
            breakdown["company_size"] = 20
        elif 501 <= employee_count <= 1000:
            breakdown["company_size"] = 15
        elif 20 <= employee_count <= 50:
            breakdown["company_size"] = 12
        elif employee_count > 1000:
            breakdown["company_size"] = 10
        else:
            breakdown["company_size"] = 5
        
        # Title scoring (25 points max)
        title_level = lead.get("title_level", "individual")
        if title_level == "c_level":
            breakdown["title_seniority"] = 25
        elif title_level == "vp":
            breakdown["title_seniority"] = 22
        elif title_level == "director":
            breakdown["title_seniority"] = 15
        elif title_level == "manager":
            breakdown["title_seniority"] = 8
        else:
            breakdown["title_seniority"] = 3
        
        # Industry scoring (20 points max)
        industry = lead.get("company", {}).get("industry", "").lower()
        if "saas" in industry or "software" in industry:
            breakdown["industry_fit"] = 20
        elif "technology" in industry or "tech" in industry:
            breakdown["industry_fit"] = 15
        else:
            breakdown["industry_fit"] = 5
        
        # Tech stack scoring (15 points max)
        technologies = lead.get("company", {}).get("technologies", [])
        crm_techs = ["salesforce", "hubspot", "pipedrive"]
        sales_techs = ["gong", "clari", "outreach", "salesloft"]
        
        tech_score = 0
        for tech in technologies:
            if any(crm in tech.lower() for crm in crm_techs):
                tech_score += 8
            if any(st in tech.lower() for st in sales_techs):
                tech_score += 5
        breakdown["tech_stack"] = min(tech_score, 15)
        
        # Intent scoring (20 points max)
        intent = lead.get("intent", {})
        intent_score = 0
        if intent.get("demo_requested"):
            intent_score += 10
        if intent.get("pricing_page_visits", 0) > 0:
            intent_score += 6
        if intent.get("content_downloads", 0) > 0:
            intent_score += 4
        if intent.get("website_visits", 0) > 2:
            intent_score += 4
        breakdown["intent_signals"] = min(intent_score, 20)
        
        # Calculate total
        score = sum(breakdown.values())
        
        return min(score, 100), breakdown
    
    def get_tier(self, score: int) -> str:
        """Get tier from score."""
        if score >= 80:
            return "tier_1"
        elif score >= 60:
            return "tier_2"
        elif score >= 40:
            return "tier_3"
        else:
            return "tier_4"
    
    async def simulate_segmentation(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate SEGMENTOR stage with confidence scoring."""
        icp_score, breakdown = self.calculate_icp_score(lead)
        tier = self.get_tier(icp_score)
        
        if self.confidence_available and self.segmentor:
            # Use confidence-aware segmentor
            result = self.segmentor.qualify_lead(
                lead=lead,
                icp_score=icp_score,
                tier=tier,
                score_breakdown=breakdown
            )
            
            return {
                "icp_score": icp_score,
                "tier": tier,
                "category": result.category,
                "confidence": result.confidence,
                "reason": result.reason,
                "next_action": result.next_action,
                "needs_replan": result.needs_replan,
                "enrichment_gaps": result.enrichment_gaps,
                "breakdown": breakdown
            }
        else:
            # Fallback without confidence
            return {
                "icp_score": icp_score,
                "tier": tier,
                "category": "HOT_LEAD" if tier == "tier_1" else "WARM_LEAD" if tier == "tier_2" else "NURTURE",
                "confidence": 0.75,
                "reason": "Simulated qualification",
                "breakdown": breakdown
            }
    
    async def simulate_crafting(self, lead: Dict[str, Any], qualification: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate CRAFTER stage."""
        # Only craft for tier 1 and tier 2
        if qualification["tier"] not in ["tier_1", "tier_2"]:
            return {"crafted": False, "reason": "Lead not qualified for outreach"}
        
        # Generate mock email
        subject_templates = [
            f"Quick question about {lead.get('company', {}).get('name', 'your company')}'s AI strategy",
            f"Saw you at [Event] - thoughts on AI for RevOps?",
            f"{{first_name}}, 3 ways AI is changing {lead.get('company', {}).get('industry', 'B2B')}",
        ]
        
        return {
            "crafted": True,
            "subject": random.choice(subject_templates).replace("{first_name}", lead.get("first_name", "there")),
            "template_id": f"template_{qualification['tier']}_{lead.get('source_type', 'default')}",
            "personalization_hooks": qualification.get("personalization_hooks", []),
            "estimated_send_time": (datetime.now(timezone.utc) + timedelta(hours=random.randint(1, 48))).isoformat()
        }
    
    async def simulate_approval(self, lead: Dict[str, Any], craft_result: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate GATEKEEPER approval routing."""
        if not craft_result.get("crafted"):
            return {"approval_needed": False, "reason": "No email to approve"}
        
        return {
            "approval_needed": True,
            "approval_id": f"approval_{uuid.uuid4().hex[:8]}",
            "status": "pending",
            "routed_to": "AE_QUEUE",
            "priority": 1 if lead.get("tier") == "tier_1" else 2,
            "deadline": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        }
    
    async def process_lead(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single lead through the full pipeline."""
        result = {
            "lead_id": lead.get("lead_id"),
            "name": lead.get("name"),
            "company": lead.get("company", {}).get("name"),
            "stages": {}
        }
        
        try:
            # Stage 1: Enrichment
            enrich_success, enriched_lead = await self.simulate_enrichment(lead)
            result["stages"]["enrichment"] = {
                "success": enrich_success,
                "email_found": enriched_lead.get("email") is not None if enrich_success else False
            }
            
            if not enrich_success:
                result["final_status"] = "enrichment_failed"
                self.metrics.enrichment_failed += 1
                return result
            
            self.metrics.enrichment_success += 1
            
            # Stage 2: Segmentation
            qualification = await self.simulate_segmentation(enriched_lead)
            result["stages"]["segmentation"] = qualification
            
            # Track metrics
            tier = qualification["tier"]
            if tier == "tier_1":
                self.metrics.tier_1_count += 1
            elif tier == "tier_2":
                self.metrics.tier_2_count += 1
            elif tier == "tier_3":
                self.metrics.tier_3_count += 1
            else:
                self.metrics.tier_4_count += 1
            
            if qualification.get("confidence"):
                self.metrics.confidence_scores.append(qualification["confidence"])
            
            if qualification.get("needs_replan"):
                self.metrics.replan_triggered += 1
            
            self.metrics.qualification_success += 1
            
            # Stage 3: Crafting (only for qualified leads)
            craft_result = await self.simulate_crafting(enriched_lead, qualification)
            result["stages"]["crafting"] = craft_result
            
            if craft_result.get("crafted"):
                self.metrics.crafting_success += 1
            
            # Stage 4: Approval routing
            approval_result = await self.simulate_approval(enriched_lead, craft_result)
            result["stages"]["approval"] = approval_result
            
            if approval_result.get("approval_needed"):
                self.metrics.approval_requested += 1
            
            result["final_status"] = "completed"
            self.metrics.processed_leads += 1
            
        except Exception as e:
            result["final_status"] = "error"
            result["error"] = str(e)
            self.metrics.failed_leads += 1
        
        return result
    
    async def run_simulation(self, leads: List[Dict[str, Any]], concurrency: int = 10) -> Dict[str, Any]:
        """Run simulation on a batch of leads."""
        self.metrics = SimulationMetrics()
        self.metrics.total_leads = len(leads)
        self.results = []
        
        start_time = datetime.now(timezone.utc)
        
        console.print(Panel(
            f"[bold blue]Starting Simulation[/bold blue]\n"
            f"Leads: {len(leads)}\n"
            f"Concurrency: {concurrency}\n"
            f"Confidence Scoring: {'[green]Enabled[/green]' if self.confidence_available else '[red]Disabled[/red]'}"
        ))
        
        # Process in batches for concurrency control
        processed = 0
        for i in range(0, len(leads), concurrency):
            batch = leads[i:i + concurrency]
            results = await asyncio.gather(*[self.process_lead(lead) for lead in batch])
            self.results.extend(results)
            processed += len(batch)
            console.print(f"  Processing: {processed}/{len(leads)} leads...")
        
        end_time = datetime.now(timezone.utc)
        self.metrics.total_time_seconds = (end_time - start_time).total_seconds()
        self.metrics.avg_lead_time_ms = (self.metrics.total_time_seconds * 1000) / len(leads)
        
        # Save results
        simulation_id = f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._save_results(simulation_id)
        
        return {
            "simulation_id": simulation_id,
            "metrics": self.metrics.to_dict(),
            "results_file": str(self.output_dir / f"{simulation_id}_results.json")
        }
    
    def _save_results(self, simulation_id: str):
        """Save simulation results to disk."""
        # Save detailed results
        results_file = self.output_dir / f"{simulation_id}_results.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2)
        
        # Save metrics summary
        metrics_file = self.output_dir / f"{simulation_id}_metrics.json"
        with open(metrics_file, 'w', encoding='utf-8') as f:
            json.dump(self.metrics.to_dict(), f, indent=2)
        
        console.print(f"\n[green]Results saved to:[/green] {results_file}")
    
    def print_report(self):
        """Print a summary report of the simulation."""
        metrics = self.metrics.to_dict()
        
        console.print("\n")
        console.print(Panel("[bold green]SIMULATION COMPLETE[/bold green]", expand=False))
        
        # Summary table
        summary_table = Table(title="Simulation Summary", show_header=True)
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")
        
        summary_table.add_row("Total Leads", str(metrics["total_leads"]))
        summary_table.add_row("Processed Successfully", str(metrics["processed_leads"]))
        summary_table.add_row("Failed", str(metrics["failed_leads"]))
        summary_table.add_row("Success Rate", f"{metrics['success_rate']:.1f}%")
        summary_table.add_row("Total Time", f"{metrics['total_time_seconds']:.2f}s")
        summary_table.add_row("Avg Time per Lead", f"{metrics['avg_lead_time_ms']:.2f}ms")
        
        console.print(summary_table)
        
        # Tier distribution
        tier_table = Table(title="Tier Distribution", show_header=True)
        tier_table.add_column("Tier", style="cyan")
        tier_table.add_column("Count", style="green")
        tier_table.add_column("Percentage", style="yellow")
        
        total = metrics["total_leads"]
        tier_table.add_row("Tier 1 (Hot)", str(metrics["tier_1_count"]), f"{metrics['tier_1_count']/total*100:.1f}%")
        tier_table.add_row("Tier 2 (Warm)", str(metrics["tier_2_count"]), f"{metrics['tier_2_count']/total*100:.1f}%")
        tier_table.add_row("Tier 3 (Nurture)", str(metrics["tier_3_count"]), f"{metrics['tier_3_count']/total*100:.1f}%")
        tier_table.add_row("Tier 4 (Monitor)", str(metrics["tier_4_count"]), f"{metrics['tier_4_count']/total*100:.1f}%")
        
        console.print(tier_table)
        
        # Confidence metrics
        if metrics.get("avg_confidence"):
            conf_table = Table(title="Confidence Metrics", show_header=True)
            conf_table.add_column("Metric", style="cyan")
            conf_table.add_column("Value", style="green")
            
            conf_table.add_row("Average Confidence", f"{metrics['avg_confidence']:.2f}")
            conf_table.add_row("Replan Triggered", str(metrics["replan_triggered"]))
            conf_table.add_row("Replan Rate", f"{metrics['replan_triggered']/total*100:.1f}%")
            
            console.print(conf_table)
        
        # Pipeline metrics
        pipeline_table = Table(title="Pipeline Metrics", show_header=True)
        pipeline_table.add_column("Stage", style="cyan")
        pipeline_table.add_column("Success", style="green")
        pipeline_table.add_column("Failed/Skipped", style="red")
        
        pipeline_table.add_row(
            "Enrichment",
            str(metrics["enrichment_success"]),
            str(metrics["enrichment_failed"])
        )
        pipeline_table.add_row(
            "Qualification",
            str(metrics["qualification_success"]),
            str(metrics["failed_leads"])
        )
        pipeline_table.add_row(
            "Crafting",
            str(metrics["crafting_success"]),
            str(metrics["processed_leads"] - metrics["crafting_success"])
        )
        pipeline_table.add_row(
            "Approval Queued",
            str(metrics["approval_requested"]),
            "-"
        )
        
        console.print(pipeline_table)


# =============================================================================
# CLI
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="Run lead simulation through swarm pipeline")
    parser.add_argument("--leads", type=int, default=100, help="Number of leads to simulate")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent processing limit")
    parser.add_argument("--quick", action="store_true", help="Quick mode with reduced leads")
    parser.add_argument("--output", type=str, help="Output directory for results")
    
    args = parser.parse_args()
    
    num_leads = 50 if args.quick else args.leads
    output_dir = Path(args.output) if args.output else None
    
    console.print(f"\n[bold]Generating {num_leads} synthetic leads...[/bold]")
    leads = generate_lead_batch(num_leads)
    
    engine = SimulationEngine(output_dir=output_dir)
    await engine.run_simulation(leads, concurrency=args.concurrency)
    engine.print_report()
    
    console.print("\n[bold green]Simulation complete![/bold green]")
    console.print("\n[yellow]Next step:[/yellow] Review results and run Priority #2 (API key setup)")


if __name__ == "__main__":
    asyncio.run(main())
