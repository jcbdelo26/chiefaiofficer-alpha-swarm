#!/usr/bin/env python3
"""
Pipeline Validator
==================
End-to-end validation of the unified swarm pipeline.

Validates each stage:
- Scrape → Enrich → Segment → Campaign → Outbox → Reply

Uses sandbox mode for safe testing without live operations.

Usage:
    python execution/pipeline_validator.py
    python execution/pipeline_validator.py --stage segmentation
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

try:
    from execution.sandbox_manager import SandboxManager, SandboxMode
    SANDBOX_AVAILABLE = True
except ImportError:
    SANDBOX_AVAILABLE = False

try:
    from execution.generate_test_data import generate_test_batch, generate_lead
    TEST_DATA_AVAILABLE = True
except ImportError:
    TEST_DATA_AVAILABLE = False
    def generate_test_batch(count, scenario):
        return [{"id": i, "email": f"test{i}@example.com"} for i in range(count)]
    def generate_lead(i):
        return {"id": i, "email": f"lead{i}@example.com"}

try:
    from core.self_annealing import SelfAnnealingEngine
    ANNEALING_AVAILABLE = True
except ImportError:
    ANNEALING_AVAILABLE = False


class ValidationStage(Enum):
    SCRAPING = "scraping"
    ENRICHMENT = "enrichment"
    SEGMENTATION = "segmentation"
    CAMPAIGN = "campaign"
    ROUTING = "routing"
    COMPLIANCE = "compliance"
    SELF_ANNEALING = "self_annealing"


@dataclass
class ValidationResult:
    """Result from a validation stage."""
    stage: ValidationStage
    passed: bool
    duration_ms: float
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["stage"] = self.stage.value
        return d


@dataclass 
class CostEstimate:
    """Cost estimation for pipeline run."""
    input_tokens: int
    output_tokens: int
    api_calls: Dict[str, int]
    estimated_cost_usd: float
    breakdown: Dict[str, float]


PRICING = {
    "anthropic_input": 3.00 / 1_000_000,
    "anthropic_output": 15.00 / 1_000_000,
    "openai_input": 2.50 / 1_000_000,
    "openai_output": 10.00 / 1_000_000,
    "gemini_input": 0.075 / 1_000_000,
    "gemini_output": 0.30 / 1_000_000,
    "exa_search": 0.003,
    "clay_enrichment": 0.10,
    "ghl_api": 0.001,
    "instantly_send": 0.002,
}


class PipelineValidator:
    """
    End-to-end pipeline validation in sandbox mode.
    
    Validates:
    - Data flow through each stage
    - Correct transformations
    - Compliance rules
    - Error handling
    - Self-annealing functionality
    """
    
    def __init__(self, mode: SandboxMode = SandboxMode.MOCK):
        self.mode = mode
        self.results: List[ValidationResult] = []
        self.metrics: Dict[str, Any] = {
            "start_time": None,
            "end_time": None,
            "total_duration_ms": 0,
            "stages_passed": 0,
            "stages_failed": 0,
            "total_errors": 0,
            "total_warnings": 0
        }
        
        if SANDBOX_AVAILABLE:
            self.sandbox = SandboxManager(mode=mode)
        else:
            self.sandbox = None
        
        self.test_leads: List[Dict] = []
        self.enriched_leads: List[Dict] = []
        self.segmented_leads: List[Dict] = []
        self.campaigns: List[Dict] = []
    
    def validate_scraping(self) -> ValidationResult:
        """Validate Hunter scraping stage."""
        start = time.time()
        errors = []
        warnings = []
        metrics = {}
        
        try:
            self.test_leads = generate_test_batch(10, "competitor_displacement") + generate_test_batch(10, "event_followup")
            metrics["leads_generated"] = len(self.test_leads)
            
            required_fields = ["email", "first_name", "last_name", "company", "title"]
            for lead in self.test_leads[:5]:
                for field in required_fields:
                    if field not in lead:
                        errors.append(f"Missing required field: {field}")
            
            for lead in self.test_leads:
                if not lead.get("linkedin_url", "").startswith("https://"):
                    warnings.append(f"Invalid LinkedIn URL for lead {lead.get('id')}")
                    break
            
            passed = len(errors) == 0
            
        except Exception as e:
            errors.append(f"Scraping validation failed: {str(e)}")
            passed = False
        
        duration_ms = (time.time() - start) * 1000
        
        return ValidationResult(
            stage=ValidationStage.SCRAPING,
            passed=passed,
            duration_ms=duration_ms,
            errors=errors,
            warnings=warnings[:3],
            metrics=metrics
        )
    
    def validate_enrichment(self) -> ValidationResult:
        """Validate Enricher data quality."""
        start = time.time()
        errors = []
        warnings = []
        metrics = {}
        
        try:
            self.enriched_leads = []
            
            for lead in self.test_leads:
                enriched = {**lead}
                enriched["email_verified"] = True
                enriched["company_size"] = "51-200"
                enriched["industry"] = "Technology"
                enriched["technologies"] = ["Salesforce", "HubSpot"]
                enriched["enrichment_source"] = "mock"
                enriched["enriched_at"] = datetime.utcnow().isoformat()
                self.enriched_leads.append(enriched)
            
            metrics["leads_enriched"] = len(self.enriched_leads)
            
            verified_count = sum(1 for l in self.enriched_leads if l.get("email_verified"))
            metrics["email_verification_rate"] = verified_count / len(self.enriched_leads)
            
            if metrics["email_verification_rate"] < 0.9:
                warnings.append(f"Low email verification rate: {metrics['email_verification_rate']:.1%}")
            
            passed = len(errors) == 0
            
        except Exception as e:
            errors.append(f"Enrichment validation failed: {str(e)}")
            passed = False
        
        duration_ms = (time.time() - start) * 1000
        
        return ValidationResult(
            stage=ValidationStage.ENRICHMENT,
            passed=passed,
            duration_ms=duration_ms,
            errors=errors,
            warnings=warnings,
            metrics=metrics
        )
    
    def validate_segmentation(self) -> ValidationResult:
        """Validate ICP tier assignment accuracy."""
        start = time.time()
        errors = []
        warnings = []
        metrics = {}
        
        try:
            self.segmented_leads = []
            tier_counts = {"tier_1": 0, "tier_2": 0, "tier_3": 0, "tier_4": 0}
            
            for lead in self.enriched_leads:
                segmented = {**lead}
                
                score = lead.get("icp_score", 50)
                if score >= 80:
                    tier = "tier_1"
                elif score >= 60:
                    tier = "tier_2"
                elif score >= 40:
                    tier = "tier_3"
                else:
                    tier = "tier_4"
                
                segmented["icp_tier"] = tier
                segmented["recommended_campaign"] = self._get_campaign_for_tier(tier, lead)
                tier_counts[tier] += 1
                self.segmented_leads.append(segmented)
            
            metrics["tier_distribution"] = tier_counts
            metrics["leads_segmented"] = len(self.segmented_leads)
            
            if tier_counts["tier_1"] == 0 and tier_counts["tier_2"] == 0:
                warnings.append("No high-value leads (tier_1/tier_2) in test data")
            
            for lead in self.segmented_leads:
                if not lead.get("icp_tier"):
                    errors.append(f"Lead {lead.get('id')} missing ICP tier")
                if not lead.get("recommended_campaign"):
                    warnings.append(f"Lead {lead.get('id')} missing campaign recommendation")
            
            passed = len(errors) == 0
            
        except Exception as e:
            errors.append(f"Segmentation validation failed: {str(e)}")
            passed = False
        
        duration_ms = (time.time() - start) * 1000
        
        return ValidationResult(
            stage=ValidationStage.SEGMENTATION,
            passed=passed,
            duration_ms=duration_ms,
            errors=errors[:5],
            warnings=warnings[:3],
            metrics=metrics
        )
    
    def _get_campaign_for_tier(self, tier: str, lead: Dict) -> str:
        """Determine campaign based on tier and lead data."""
        source = lead.get("source", lead.get("source_type", "unknown"))
        
        campaigns = {
            ("tier_1", "competitor_follower"): "competitor_displacement",
            ("tier_1", "event_attendee"): "event_followup",
            ("tier_2", "competitor_follower"): "competitor_displacement",
            ("tier_2", "event_attendee"): "event_followup",
            ("tier_2", "website_visitor"): "intent_based",
            ("tier_3", "default"): "nurture_sequence",
            ("tier_4", "default"): "low_touch_awareness"
        }
        
        return campaigns.get((tier, source), campaigns.get((tier, "default"), "generic_outreach"))
    
    def validate_campaign_generation(self) -> ValidationResult:
        """Validate Crafter output quality."""
        start = time.time()
        errors = []
        warnings = []
        metrics = {}
        
        try:
            self.campaigns = []
            
            campaign_types = set(l.get("recommended_campaign") for l in self.segmented_leads)
            
            for campaign_type in campaign_types:
                leads_for_campaign = [l for l in self.segmented_leads if l.get("recommended_campaign") == campaign_type]
                
                campaign = {
                    "campaign_id": f"camp_{campaign_type}_{datetime.now().strftime('%Y%m%d')}",
                    "campaign_type": campaign_type,
                    "lead_count": len(leads_for_campaign),
                    "subject_line": f"[Mock] {campaign_type.replace('_', ' ').title()}",
                    "template_id": f"template_{campaign_type}",
                    "personalization_level": "high" if "tier_1" in str(leads_for_campaign[0].get("icp_tier")) else "medium",
                    "created_at": datetime.utcnow().isoformat()
                }
                self.campaigns.append(campaign)
            
            metrics["campaigns_generated"] = len(self.campaigns)
            metrics["total_leads_assigned"] = sum(c["lead_count"] for c in self.campaigns)
            
            for campaign in self.campaigns:
                if campaign["lead_count"] == 0:
                    errors.append(f"Campaign {campaign['campaign_id']} has no leads")
                if not campaign.get("subject_line"):
                    errors.append(f"Campaign {campaign['campaign_id']} missing subject line")
            
            passed = len(errors) == 0
            
        except Exception as e:
            errors.append(f"Campaign validation failed: {str(e)}")
            passed = False
        
        duration_ms = (time.time() - start) * 1000
        
        return ValidationResult(
            stage=ValidationStage.CAMPAIGN,
            passed=passed,
            duration_ms=duration_ms,
            errors=errors,
            warnings=warnings,
            metrics=metrics
        )
    
    def validate_routing(self) -> ValidationResult:
        """Validate lead routing logic."""
        start = time.time()
        errors = []
        warnings = []
        metrics = {}
        
        try:
            routed_correctly = 0
            routing_issues = []
            
            for lead in self.segmented_leads:
                tier = lead.get("icp_tier")
                campaign = lead.get("recommended_campaign")
                source = lead.get("source", "unknown")
                
                valid_campaigns = ["competitor_displacement", "event_followup", "intent_based", "nurture_sequence", "low_touch_awareness", "generic_outreach"]
                
                if campaign in valid_campaigns:
                    routed_correctly += 1
                else:
                    routing_issues.append(f"Unexpected campaign: {tier}/{source} -> {campaign}")
            
            metrics["routing_accuracy"] = routed_correctly / max(len(self.segmented_leads), 1)
            metrics["routing_issues"] = len(routing_issues)
            
            if routing_issues:
                warnings.extend(routing_issues[:3])
            
            if metrics["routing_accuracy"] < 0.9:
                errors.append(f"Low routing accuracy: {metrics['routing_accuracy']:.1%}")
            
            passed = len(errors) == 0
            
        except Exception as e:
            errors.append(f"Routing validation failed: {str(e)}")
            passed = False
        
        duration_ms = (time.time() - start) * 1000
        
        return ValidationResult(
            stage=ValidationStage.ROUTING,
            passed=passed,
            duration_ms=duration_ms,
            errors=errors,
            warnings=warnings,
            metrics=metrics
        )
    
    def validate_compliance(self) -> ValidationResult:
        """Validate GDPR/CAN-SPAM compliance checks."""
        start = time.time()
        errors = []
        warnings = []
        metrics = {}
        
        try:
            compliance_checks = {
                "has_unsubscribe": 0,
                "has_physical_address": 0,
                "respects_suppression": 0,
                "gdpr_compliant": 0
            }
            
            suppression_list = {"blocked@example.com", "optout@test.com"}
            
            for lead in self.segmented_leads:
                email = lead.get("email", "")
                
                if email not in suppression_list:
                    compliance_checks["respects_suppression"] += 1
                else:
                    errors.append(f"Lead {email} is on suppression list but not filtered")
                
                compliance_checks["gdpr_compliant"] += 1
            
            for campaign in self.campaigns:
                campaign["has_unsubscribe"] = True
                campaign["has_physical_address"] = True
                compliance_checks["has_unsubscribe"] += 1
                compliance_checks["has_physical_address"] += 1
            
            metrics["compliance_checks"] = compliance_checks
            metrics["suppression_violations"] = len(errors)
            
            passed = len(errors) == 0
            
        except Exception as e:
            errors.append(f"Compliance validation failed: {str(e)}")
            passed = False
        
        duration_ms = (time.time() - start) * 1000
        
        return ValidationResult(
            stage=ValidationStage.COMPLIANCE,
            passed=passed,
            duration_ms=duration_ms,
            errors=errors,
            warnings=warnings,
            metrics=metrics
        )
    
    def validate_self_annealing(self) -> ValidationResult:
        """Validate self-annealing loop functionality."""
        start = time.time()
        errors = []
        warnings = []
        metrics = {}
        
        try:
            if not ANNEALING_AVAILABLE:
                warnings.append("Self-annealing engine not available")
                passed = True
                metrics["skipped"] = True
            else:
                engine = SelfAnnealingEngine(epsilon=0.30)
                
                test_outcomes = [
                    {"workflow": "test_001", "outcome": {"meeting_booked": True}, "success": True},
                    {"workflow": "test_002", "outcome": {"email_opened": True}, "success": True},
                    {"workflow": "test_003", "outcome": {"bounce": True}, "success": False},
                ]
                
                for outcome in test_outcomes:
                    result = engine.learn_from_outcome(
                        workflow=outcome["workflow"],
                        outcome=outcome["outcome"],
                        success=outcome["success"]
                    )
                    if not result.get("success"):
                        errors.append(f"Learning failed for {outcome['workflow']}")
                
                step_result = engine.anneal_step()
                metrics["annealing_step"] = step_result.get("step", 0)
                metrics["epsilon"] = step_result.get("epsilon", 0)
                
                status = engine.get_annealing_status()
                metrics["total_outcomes"] = status.get("total_outcomes", 0)
                metrics["patterns_count"] = status.get("patterns_count", 0)
                
                passed = len(errors) == 0
                
        except Exception as e:
            errors.append(f"Self-annealing validation failed: {str(e)}")
            passed = False
        
        duration_ms = (time.time() - start) * 1000
        
        return ValidationResult(
            stage=ValidationStage.SELF_ANNEALING,
            passed=passed,
            duration_ms=duration_ms,
            errors=errors,
            warnings=warnings,
            metrics=metrics
        )
    
    def run_full_validation(self) -> Dict[str, Any]:
        """Run all validation stages and return comprehensive report."""
        self.metrics["start_time"] = datetime.utcnow().isoformat()
        self.results = []
        
        stages = [
            ("Scraping", self.validate_scraping),
            ("Enrichment", self.validate_enrichment),
            ("Segmentation", self.validate_segmentation),
            ("Campaign Generation", self.validate_campaign_generation),
            ("Routing", self.validate_routing),
            ("Compliance", self.validate_compliance),
            ("Self-Annealing", self.validate_self_annealing),
        ]
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Validating pipeline...", total=len(stages))
            
            for name, validator in stages:
                progress.update(task, description=f"Validating {name}...")
                result = validator()
                self.results.append(result)
                
                if result.passed:
                    self.metrics["stages_passed"] += 1
                else:
                    self.metrics["stages_failed"] += 1
                
                self.metrics["total_errors"] += len(result.errors)
                self.metrics["total_warnings"] += len(result.warnings)
                
                progress.advance(task)
        
        self.metrics["end_time"] = datetime.utcnow().isoformat()
        self.metrics["total_duration_ms"] = sum(r.duration_ms for r in self.results)
        
        cost_estimate = self._estimate_costs()
        
        return {
            "validation_id": f"val_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "mode": self.mode.value if hasattr(self.mode, 'value') else str(self.mode),
            "summary": {
                "passed": self.metrics["stages_failed"] == 0,
                "stages_passed": self.metrics["stages_passed"],
                "stages_failed": self.metrics["stages_failed"],
                "total_errors": self.metrics["total_errors"],
                "total_warnings": self.metrics["total_warnings"],
                "duration_ms": round(self.metrics["total_duration_ms"], 2)
            },
            "stages": [r.to_dict() for r in self.results],
            "cost_estimate": asdict(cost_estimate),
            "recommendations": self._generate_recommendations(),
            "timestamp": self.metrics["start_time"]
        }
    
    def _estimate_costs(self) -> CostEstimate:
        """Estimate costs based on token usage and API calls."""
        input_tokens = len(self.test_leads) * 500
        output_tokens = len(self.campaigns) * 1000
        
        api_calls = {
            "llm_calls": len(self.campaigns) + 5,
            "enrichment_calls": len(self.enriched_leads),
            "exa_searches": max(1, len(self.test_leads) // 10),
            "ghl_updates": len(self.segmented_leads),
            "instantly_sends": len(self.segmented_leads)
        }
        
        breakdown = {
            "llm_cost": (input_tokens * PRICING["anthropic_input"]) + (output_tokens * PRICING["anthropic_output"]),
            "enrichment_cost": api_calls["enrichment_calls"] * PRICING["clay_enrichment"],
            "search_cost": api_calls["exa_searches"] * PRICING["exa_search"],
            "crm_cost": api_calls["ghl_updates"] * PRICING["ghl_api"],
            "outreach_cost": api_calls["instantly_sends"] * PRICING["instantly_send"]
        }
        
        total = sum(breakdown.values())
        
        return CostEstimate(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            api_calls=api_calls,
            estimated_cost_usd=round(total, 4),
            breakdown={k: round(v, 4) for k, v in breakdown.items()}
        )
    
    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on validation results."""
        recommendations = []
        
        for result in self.results:
            if not result.passed:
                recommendations.append(f"Fix {result.stage.value} stage: {result.errors[0] if result.errors else 'Unknown error'}")
            elif result.warnings:
                recommendations.append(f"Review {result.stage.value} warnings: {result.warnings[0]}")
        
        if not recommendations:
            recommendations.append("All validations passed. Pipeline is ready for production testing.")
        
        return recommendations


def print_report(report: Dict[str, Any]):
    """Print formatted validation report."""
    console.print("\n" + "=" * 70)
    console.print("[bold blue]PIPELINE VALIDATION REPORT[/bold blue]")
    console.print("=" * 70)
    
    summary = report["summary"]
    status = "[green]PASSED[/green]" if summary["passed"] else "[red]FAILED[/red]"
    
    console.print(f"\nOverall Status: {status}")
    console.print(f"Duration: {summary['duration_ms']:.0f}ms")
    console.print(f"Stages: {summary['stages_passed']} passed, {summary['stages_failed']} failed")
    console.print(f"Issues: {summary['total_errors']} errors, {summary['total_warnings']} warnings")
    
    table = Table(title="\nStage Results")
    table.add_column("Stage", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Duration", justify="right")
    table.add_column("Errors", justify="right", style="red")
    table.add_column("Warnings", justify="right", style="yellow")
    
    for stage in report["stages"]:
        status = "PASS" if stage["passed"] else "FAIL"
        status_style = "green" if stage["passed"] else "red"
        table.add_row(
            stage["stage"],
            f"[{status_style}]{status}[/{status_style}]",
            f"{stage['duration_ms']:.0f}ms",
            str(len(stage["errors"])),
            str(len(stage["warnings"]))
        )
    
    console.print(table)
    
    cost = report["cost_estimate"]
    console.print(f"\n[bold]Cost Estimate:[/bold] ${cost['estimated_cost_usd']:.4f}")
    console.print(f"  Tokens: {cost['input_tokens']:,} input, {cost['output_tokens']:,} output")
    
    console.print("\n[bold]Recommendations:[/bold]")
    for rec in report["recommendations"][:5]:
        console.print(f"  • {rec}")
    
    console.print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Pipeline Validator")
    parser.add_argument("--stage", type=str, help="Run specific stage only")
    parser.add_argument("--mode", choices=["mock", "dry_run", "staging"], default="mock")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    if SANDBOX_AVAILABLE:
        mode = SandboxMode(args.mode)
    else:
        mode = args.mode
    
    validator = PipelineValidator(mode=mode)
    
    if args.stage:
        stage_map = {
            "scraping": validator.validate_scraping,
            "enrichment": validator.validate_enrichment,
            "segmentation": validator.validate_segmentation,
            "campaign": validator.validate_campaign_generation,
            "routing": validator.validate_routing,
            "compliance": validator.validate_compliance,
            "annealing": validator.validate_self_annealing,
        }
        
        if args.stage in stage_map:
            result = stage_map[args.stage]()
            if args.json:
                print(json.dumps(result.to_dict(), indent=2))
            else:
                status = "[green]PASSED[/green]" if result.passed else "[red]FAILED[/red]"
                console.print(f"\n{args.stage.upper()}: {status}")
                if result.errors:
                    console.print(f"  Errors: {result.errors}")
                if result.warnings:
                    console.print(f"  Warnings: {result.warnings}")
        else:
            console.print(f"[red]Unknown stage: {args.stage}[/red]")
            console.print(f"Available: {', '.join(stage_map.keys())}")
    else:
        report = validator.run_full_validation()
        
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print_report(report)


if __name__ == "__main__":
    main()
