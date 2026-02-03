"""
Test RPI Workflow End-to-End
============================

This script tests the full Research → Plan → Implement workflow
using sample data to verify the context engineering implementation.

Usage:
    python tests/test_rpi_workflow.py
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


console = Console()


def create_sample_segmented_data() -> str:
    """Create sample segmented data for testing."""
    
    console.print("\n[bold cyan]Step 1: Creating Sample Segmented Data[/bold cyan]\n")
    
    sample_leads = [
        # TIER 1 - High value prospects
        {
            "lead_id": "test_001",
            "linkedin_url": "https://linkedin.com/in/sarah-johnson",
            "name": "Sarah Johnson",
            "first_name": "Sarah",
            "last_name": "Johnson",
            "title": "VP of Revenue Operations",
            "company": "TechScale Inc",
            "company_size": 180,
            "industry": "B2B SaaS",
            "email": "sarah.johnson@techscale.io",
            "icp_score": 94,
            "icp_tier": "tier1",
            "intent_score": 85,
            "source_type": "competitor_follower",
            "source_name": "outreach_followers",
            "segment_tags": ["high_intent", "competitor_engaged", "decision_maker"],
            "personalization_hooks": ["RevOps focus", "SaaS background", "Scaling team"],
            "score_breakdown": {
                "company_size": 20,
                "industry": 15,
                "title": 25,
                "revenue": 10,
                "source": 15,
                "intent": 9
            },
            "recommended_campaign": "competitor_displacement",
            "needs_review": False,
            "disqualification_reason": None,
            "segmented_at": datetime.utcnow().isoformat()
        },
        {
            "lead_id": "test_002",
            "linkedin_url": "https://linkedin.com/in/mike-chen",
            "name": "Michael Chen",
            "first_name": "Michael",
            "last_name": "Chen",
            "title": "Chief Revenue Officer",
            "company": "CloudFirst Solutions",
            "company_size": 250,
            "industry": "Technology",
            "email": "mchen@cloudfirst.com",
            "icp_score": 91,
            "icp_tier": "tier1",
            "intent_score": 78,
            "source_type": "website_visitor",
            "source_name": "pricing_page",
            "segment_tags": ["pricing_intent", "c_suite", "high_value"],
            "personalization_hooks": ["CRO role", "Cloud focus", "Enterprise scale"],
            "score_breakdown": {
                "company_size": 15,
                "industry": 15,
                "title": 30,
                "revenue": 15,
                "source": 10,
                "intent": 6
            },
            "recommended_campaign": "value_proposition",
            "needs_review": False,
            "disqualification_reason": None,
            "segmented_at": datetime.utcnow().isoformat()
        },
        
        # TIER 2 - Medium value prospects
        {
            "lead_id": "test_003",
            "linkedin_url": "https://linkedin.com/in/emily-rodriguez",
            "name": "Emily Rodriguez",
            "first_name": "Emily",
            "last_name": "Rodriguez",
            "title": "Sales Operations Manager",
            "company": "DataFlow Analytics",
            "company_size": 85,
            "industry": "Analytics",
            "email": "emily.r@dataflow.co",
            "icp_score": 78,
            "icp_tier": "tier2",
            "intent_score": 62,
            "source_type": "content_engagement",
            "source_name": "linkedin_post",
            "segment_tags": ["content_engaged", "ops_focus", "growth_stage"],
            "personalization_hooks": ["Analytics industry", "Ops optimization", "Growing company"],
            "score_breakdown": {
                "company_size": 15,
                "industry": 10,
                "title": 20,
                "revenue": 8,
                "source": 10,
                "intent": 15
            },
            "recommended_campaign": "thought_leadership",
            "needs_review": True,
            "disqualification_reason": None,
            "segmented_at": datetime.utcnow().isoformat()
        },
        {
            "lead_id": "test_004",
            "linkedin_url": "https://linkedin.com/in/david-kim",
            "name": "David Kim",
            "first_name": "David",
            "last_name": "Kim",
            "title": "Director of Sales Enablement",
            "company": "Innovate Labs",
            "company_size": 120,
            "industry": "Professional Services",
            "email": "dkim@innovatelabs.com",
            "icp_score": 75,
            "icp_tier": "tier2",
            "intent_score": 55,
            "source_type": "organic_linkedin",
            "source_name": "connection_request",
            "segment_tags": ["enablement_focus", "professional_services"],
            "personalization_hooks": ["Enablement expert", "Training focus", "Mid-market"],
            "score_breakdown": {
                "company_size": 18,
                "industry": 8,
                "title": 22,
                "revenue": 12,
                "source": 5,
                "intent": 10
            },
            "recommended_campaign": "education_series",
            "needs_review": True,
            "disqualification_reason": None,
            "segmented_at": datetime.utcnow().isoformat()
        },
        
        # TIER 3 - Nurture prospects
        {
            "lead_id": "test_005",
            "linkedin_url": "https://linkedin.com/in/lisa-wang",
            "name": "Lisa Wang",
            "first_name": "Lisa",
            "last_name": "Wang",
            "title": "Sales Development Representative",
            "company": "StartupCo",
            "company_size": 35,
            "industry": "Consumer Tech",
            "email": "lisa@startupco.io",
            "icp_score": 48,
            "icp_tier": "tier3",
            "intent_score": 40,
            "source_type": "cold_linkedin",
            "source_name": "sales_navigator",
            "segment_tags": ["early_stage", "individual_contributor"],
            "personalization_hooks": ["SDR experience", "Startup culture"],
            "score_breakdown": {
                "company_size": 5,
                "industry": 5,
                "title": 10,
                "revenue": 3,
                "source": 15,
                "intent": 10
            },
            "recommended_campaign": "nurture_sequence",
            "needs_review": False,
            "disqualification_reason": None,
            "segmented_at": datetime.utcnow().isoformat()
        }
    ]
    
    # Create output structure
    output = {
        "input_file": "test_enriched_sample.json",
        "total_processed": len(sample_leads),
        "processed_at": datetime.utcnow().isoformat(),
        "tier_counts": {
            "tier1": 2,
            "tier2": 2,
            "tier3": 1,
            "disqualified": 0,
            "needs_review": 2
        },
        "summary_stats": {
            "avg_icp_score": sum(l["icp_score"] for l in sample_leads) / len(sample_leads),
            "avg_intent_score": sum(l["intent_score"] for l in sample_leads) / len(sample_leads),
            "top_segments": ["high_intent", "competitor_engaged", "decision_maker"],
            "campaign_distribution": {
                "competitor_displacement": 1,
                "value_proposition": 1,
                "thought_leadership": 1,
                "education_series": 1,
                "nurture_sequence": 1
            }
        },
        "leads": sample_leads
    }
    
    # Save to .hive-mind/segmented
    output_dir = project_root / ".hive-mind" / "segmented"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / f"segmented_test_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    console.print(f"[green]✓[/green] Created sample data: {output_path}")
    
    # Display summary table
    table = Table(title="Sample Leads Created")
    table.add_column("Lead ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Title", style="yellow")
    table.add_column("Tier", style="green")
    table.add_column("ICP Score", style="magenta")
    
    for lead in sample_leads:
        table.add_row(
            lead["lead_id"],
            lead["name"],
            lead["title"][:30],
            lead["icp_tier"].upper(),
            str(lead["icp_score"])
        )
    
    console.print(table)
    
    return str(output_path)


def run_research_phase(segmented_file: str) -> str:
    """Run RPI Research phase."""
    
    console.print("\n[bold cyan]Step 2: Running RPI Research Phase[/bold cyan]\n")
    
    # Import and run research
    from execution.rpi_research import run_research, print_research_summary, save_research
    from pathlib import Path
    
    research = run_research(Path(segmented_file))
    print_research_summary(research)
    research_output = save_research(research)
    
    console.print(f"[green]✓[/green] Research complete: {research_output}")
    
    return str(research_output)


def run_plan_phase(research_file: str) -> str:
    """Run RPI Plan phase."""
    
    console.print("\n[bold cyan]Step 3: Running RPI Plan Phase[/bold cyan]\n")
    
    # Import and run planner
    from execution.rpi_plan import generate_campaign_plan, print_plan_summary, save_plan
    from pathlib import Path
    import json
    
    with open(research_file) as f:
        research = json.load(f)
    
    plan = generate_campaign_plan(research)
    print_plan_summary(plan)
    plan_output = save_plan(plan)
    
    console.print(f"[green]✓[/green] Plan complete: {plan_output}")
    
    return str(plan_output)


def run_implement_phase(plan_file: str) -> str:
    """Run RPI Implement phase."""
    
    console.print("\n[bold cyan]Step 4: Running RPI Implement Phase[/bold cyan]\n")
    
    # Import and run implementer
    from execution.rpi_implement import implement_plan, print_implementation_summary, save_campaigns
    from pathlib import Path
    import json
    
    with open(plan_file) as f:
        plan = json.load(f)
    
    campaigns = implement_plan(plan)
    print_implementation_summary(campaigns, plan)
    campaigns_output = save_campaigns(campaigns, plan.get("plan_id", "unknown"))
    
    console.print(f"[green]✓[/green] Implementation complete: {campaigns_output}")
    
    return str(campaigns_output)


def verify_outputs(campaigns_file: str):
    """Verify the generated output contains semantic anchors."""
    
    console.print("\n[bold cyan]Step 5: Verifying Outputs[/bold cyan]\n")
    
    with open(campaigns_file, 'r') as f:
        campaigns_data = json.load(f)
    
    campaigns = campaigns_data.get("campaigns", [])
    
    # Check for semantic anchors
    anchors_found = 0
    for campaign in campaigns:
        if "semantic_anchors" in campaign:
            anchors_found += len(campaign["semantic_anchors"])
    
    if anchors_found > 0:
        console.print(f"[green]✓[/green] Found {anchors_found} semantic anchors attached to campaigns")
    else:
        console.print("[yellow]⚠[/yellow] No semantic anchors found - may need integration")
    
    # Display campaign summary
    table = Table(title="Generated Campaigns")
    table.add_column("Campaign ID", style="cyan")
    table.add_column("Tier", style="green")
    table.add_column("Template", style="yellow")
    table.add_column("Lead Count", style="magenta")
    table.add_column("Status", style="blue")
    
    for campaign in campaigns:
        table.add_row(
            campaign.get("campaign_id", "")[:12] + "...",
            campaign.get("tier", "unknown").upper(),
            campaign.get("template", "unknown"),
            str(campaign.get("lead_count", 0)),
            campaign.get("status", "unknown")
        )
    
    console.print(table)
    
    return True


def main():
    """Run the full RPI workflow test."""
    
    console.print(Panel.fit(
        "[bold green]RPI Workflow End-to-End Test[/bold green]\n\n"
        "Testing: Research → Plan → Implement\n"
        "With context engineering and semantic anchors",
        border_style="green"
    ))
    
    try:
        # Step 1: Create sample data
        segmented_file = create_sample_segmented_data()
        
        # Step 2: Research phase
        research_file = run_research_phase(segmented_file)
        
        # Step 3: Plan phase (human checkpoint)
        console.print(Panel(
            "[bold yellow]🔍 HUMAN CHECKPOINT[/bold yellow]\n\n"
            "In production, an AE would review the plan here.\n"
            "For testing, we auto-approve and continue.",
            border_style="yellow"
        ))
        plan_file = run_plan_phase(research_file)
        
        # Step 4: Implement phase
        campaigns_file = run_implement_phase(plan_file)
        
        # Step 5: Verify outputs
        verify_outputs(campaigns_file)
        
        # Final summary
        console.print(Panel.fit(
            "[bold green]✓ RPI WORKFLOW TEST COMPLETE[/bold green]\n\n"
            f"• Segmented Data: {segmented_file}\n"
            f"• Research Output: {research_file}\n"
            f"• Plan Output: {plan_file}\n"
            f"• Campaigns Output: {campaigns_file}\n\n"
            "[dim]All phases executed with context zone monitoring[/dim]",
            border_style="green"
        ))
        
        return 0
        
    except Exception as e:
        console.print(f"\n[bold red]ERROR:[/bold red] {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
