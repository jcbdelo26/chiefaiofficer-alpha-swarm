#!/usr/bin/env python3
"""
Crafter Agent - Campaign Generator
==================================
Generates hyper-personalized email campaigns from segmented leads.

Usage:
    python execution/crafter_campaign.py --input .hive-mind/segmented/leads.json
    python execution/crafter_campaign.py --segment tier1_gong --template competitor_displacement
"""

import os
import sys
import json
import uuid
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from jinja2 import Template, Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from core.compliance import validate_campaign, ValidationResult
from core.event_log import log_event, EventType
from core.retry import retry, schedule_retry
from core.alerts import send_warning, send_critical
from core.context import (
    compact_lead_batch, 
    get_context_zone, 
    ContextZone,
    estimate_tokens
)

console = Console()

# Dumb Zone protection settings
SMART_ZONE_BATCH_SIZE = 25  # Process leads in batches to stay in Smart Zone
CONTEXT_WARNING_THRESHOLD = 0.4  # Warn when approaching Dumb Zone


@dataclass
class EmailStep:
    """Single email in a sequence."""
    step: int
    delay_days: int
    channel: str  # email, linkedin
    subject_a: str
    subject_b: str
    body_a: str
    body_b: str
    personalization_level: int  # 1-3


@dataclass
class Campaign:
    """Complete campaign with leads and sequence."""
    campaign_id: str
    name: str
    segment: str
    campaign_type: str
    leads: List[Dict[str, Any]]
    lead_count: int
    sequence: List[EmailStep]
    status: str  # draft, pending_review, approved, active, paused
    created_at: str
    avg_icp_score: float
    avg_intent_score: float
    personalization_hooks: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class CampaignCrafter:
    """Generates hyper-personalized email campaigns."""
    
    # Email templates
    TEMPLATES = {
        "competitor_displacement": {
            "subject_a": "{{lead.first_name}}, what {{context.competitor}} isn't showing you",
            "subject_b": "Beyond {{context.competitor}} for {{lead.company}}",
            "body": """Hi {{lead.first_name}},

I noticed you follow {{source.name}}'s updates on LinkedIn - smart move staying current on {{context.topics[0] if context.topics else 'revenue intelligence'}}.

Here's what I've been hearing from {{lead.title}}s like yourself at companies your size:

"{{source.name}} shows us what happened... but we still can't predict what's going to happen next quarter."

At Chiefaiofficer.com, we're building the layer ABOVE traditional tools - connecting insights to predictions to coaching in one AI-native system.

Worth a 15-min look? {{sender.calendar_link}}

Best,
{{sender.name}}
{{sender.title}}, {{sender.company}}

P.S. - No generic demo. I'll show you exactly how this would work for {{lead.company}}."""
        },
        "event_followup": {
            "subject_a": "Quick follow-up from {{source.name}}",
            "subject_b": "{{lead.first_name}}, loved the {{source.name}} discussion",
            "body": """Hi {{lead.first_name}},

I saw you attended {{source.name}} - great session on {{context.topics[0] if context.topics else 'revenue operations'}}.

The discussion around {{context.topics[0] if context.topics else 'AI in RevOps'}} is exactly where we focus at Chiefaiofficer.com.

Would love to share how {{lead.company}} could apply some of these concepts.

15 minutes this week? {{sender.calendar_link}}

{{sender.name}}"""
        },
        "thought_leadership": {
            "subject_a": "Your take on {{context.topics[0] if context.topics else 'RevOps'}}",
            "subject_b": "{{lead.first_name}}, re: your LinkedIn comment",
            "body": """{{lead.first_name}},

I came across your comment on LinkedIn about {{context.topics[0] if context.topics else 'revenue operations'}}:

"{{engagement.content[:100] if engagement.content else 'Your thoughtful perspective on the industry'}}..."

Couldn't agree more. The challenges you're describing are exactly what we're solving at Chiefaiofficer.com.

We're working with companies like {{lead.company}} addressing exactly this. Curious if you'd find our approach interesting?

Quick 15-min chat? {{sender.calendar_link}}

{{sender.name}}
P.S. - Would love to compare notes on your experience."""
        },
        "community_outreach": {
            "subject_a": "Fellow {{source.name}} member",
            "subject_b": "{{lead.first_name}}, connecting from {{source.name}}",
            "body": """Hi {{lead.first_name}},

I noticed we're both members of {{source.name}} - great community for {{context.topics[0] if context.topics else 'revenue operations'}} professionals.

Given your role as {{lead.title}} at {{lead.company}}, thought you might be interested in what we're building at Chiefaiofficer.com.

We're helping {{lead.company}}-sized companies transform their revenue operations with AI.

Open to a quick 15-min call to explore? {{sender.calendar_link}}

{{sender.name}}"""
        },
        "website_visitor": {
            "subject_a": "You were on our site earlier",
            "subject_b": "Following up on your visit, {{lead.first_name}}",
            "body": """{{lead.first_name}},

I noticed you were exploring Chiefaiofficer.com earlier.

Based on your role as {{lead.title}} at {{lead.company}}, I'd love to give you a personalized walkthrough of how we can help.

Worth 15 minutes? {{sender.calendar_link}}

{{sender.name}}"""
        }
    }
    
    # Follow-up sequence templates
    FOLLOWUP_TEMPLATES = [
        {
            "delay_days": 3,
            "subject": "Quick follow-up, {{lead.first_name}}",
            "body": """{{lead.first_name}},

Just bumping this up. Thought this might be relevant given your focus on {{context.topics[0] if context.topics else 'revenue operations'}}.

Here's a quick case study of how we helped a similar company: [Case Study Link]

Still open to that 15-min conversation? {{sender.calendar_link}}

{{sender.name}}"""
        },
        {
            "delay_days": 7,
            "subject": "{{lead.company}} + Chiefaiofficer.com",
            "body": """{{lead.first_name}},

Companies like {{lead.company}} are seeing 40% improvement in forecast accuracy.

I know you're busy, but I think you'd find real value in a quick conversation.

Last ask: {{sender.calendar_link}}

{{sender.name}}"""
        },
        {
            "delay_days": 14,
            "subject": "Should I close the loop?",
            "body": """{{lead.first_name}},

I haven't heard back, so I'm guessing timing isn't right.

Totally understand - I'll close out this thread but happy to reconnect whenever makes sense for {{lead.company}}.

Feel free to reach out anytime.

{{sender.name}}"""
        }
    ]
    
    def __init__(self):
        self.sender_info = {
            "name": "Chris Daigle",
            "title": "CEO",
            "company": "Chiefaiofficer.com",
            "calendar_link": "https://calendly.com/chiefaiofficer/intro"
        }
    
    def _select_template(self, lead: Dict[str, Any]) -> str:
        """Select appropriate template based on lead source."""
        source_type = lead.get("source_type", "")
        recommended = lead.get("recommended_campaign", "")
        
        # Use recommended campaign if available
        if recommended and recommended in self.TEMPLATES:
            return recommended
        
        # Map source type to template
        source_to_template = {
            "competitor_follower": "competitor_displacement",
            "event_attendee": "event_followup",
            "post_commenter": "thought_leadership",
            "group_member": "community_outreach",
            "post_liker": "competitor_displacement",
            "website_visitor": "website_visitor"
        }
        
        return source_to_template.get(source_type, "competitor_displacement")
    
    def _render_template(self, template_str: str, variables: Dict[str, Any]) -> str:
        """Render a Jinja2 template with variables."""
        try:
            template = Template(template_str)
            return template.render(**variables)
        except Exception as e:
            console.print(f"[yellow]Template rendering warning: {e}[/yellow]")
            return template_str
    
    def _build_template_variables(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Build template variables from lead data."""
        return {
            "lead": {
                "first_name": lead.get("first_name", lead.get("name", "").split()[0] if lead.get("name") else "there"),
                "last_name": lead.get("last_name", ""),
                "name": lead.get("name", ""),
                "title": lead.get("title", ""),
                "company": lead.get("company", "your company"),
                "location": lead.get("location", "")
            },
            "source": {
                "type": lead.get("source_type", ""),
                "name": lead.get("source_name", ""),
                "url": lead.get("source_url", "")
            },
            "engagement": {
                "action": lead.get("engagement_action", ""),
                "content": lead.get("engagement_content", ""),
                "timestamp": lead.get("engagement_timestamp", "")
            },
            "context": {
                "competitor": lead.get("source_name", "competitors"),
                "topics": lead.get("personalization_hooks", []),
                "pain_points": [],
                "angle": lead.get("recommended_campaign", "")
            },
            "company": {
                "size": lead.get("company_size", 0),
                "industry": lead.get("industry", ""),
                "tech_stack": []
            },
            "sender": self.sender_info
        }
    
    def generate_email(self, lead: Dict[str, Any], template_name: str = None) -> Dict[str, Any]:
        """Generate a personalized email for a single lead."""
        
        if not template_name:
            template_name = self._select_template(lead)
        
        template = self.TEMPLATES.get(template_name, self.TEMPLATES["competitor_displacement"])
        variables = self._build_template_variables(lead)
        
        # Render both A/B variants
        subject_a = self._render_template(template["subject_a"], variables)
        subject_b = self._render_template(template["subject_b"], variables)
        body = self._render_template(template["body"], variables)
        
        return {
            "lead_id": lead.get("lead_id", ""),
            "email": lead.get("email", ""),
            "template": template_name,
            "subject_a": subject_a,
            "subject_b": subject_b,
            "body": body,
            "personalization_level": 3 if lead.get("icp_tier") == "tier_1" else 2
        }
    
    def generate_sequence(self, lead: Dict[str, Any], template_name: str = None) -> List[EmailStep]:
        """Generate a full email sequence for a lead."""
        
        if not template_name:
            template_name = self._select_template(lead)
        
        template = self.TEMPLATES.get(template_name, self.TEMPLATES["competitor_displacement"])
        variables = self._build_template_variables(lead)
        
        sequence = []
        
        # Step 1: Initial email
        sequence.append(EmailStep(
            step=1,
            delay_days=0,
            channel="email",
            subject_a=self._render_template(template["subject_a"], variables),
            subject_b=self._render_template(template["subject_b"], variables),
            body_a=self._render_template(template["body"], variables),
            body_b=self._render_template(template["body"], variables),
            personalization_level=3
        ))
        
        # Follow-up steps
        for i, followup in enumerate(self.FOLLOWUP_TEMPLATES, start=2):
            sequence.append(EmailStep(
                step=i,
                delay_days=followup["delay_days"],
                channel="email",
                subject_a=self._render_template(followup["subject"], variables),
                subject_b=self._render_template(followup["subject"], variables),
                body_a=self._render_template(followup["body"], variables),
                body_b=self._render_template(followup["body"], variables),
                personalization_level=2
            ))
        
        return sequence
    
    def create_campaign(
        self, 
        leads: List[Dict[str, Any]], 
        segment: str,
        campaign_type: str = None
    ) -> Campaign:
        """Create a full campaign from a list of leads."""
        if not leads:
            return None
        
        # Calculate campaign metadata
        avg_icp_score = sum(l.get("icp_score", 0) for l in leads) / len(leads)
        avg_intent_score = sum(l.get("intent", {}).get("score", 0) for l in leads) / len(leads)
        
        # Determine campaign type if not provided
        if not campaign_type:
            campaign_type = "competitor_displacement" if any(l.get("competitor") for l in leads) else "standard_outreach"
            
        print(f"Creating {campaign_type} campaign for {len(leads)} leads (Segment: {segment})")
        
        processed_leads = []
        skipped_leads = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Generating emails...", total=len(leads))
            
            for lead in leads:
                # Validation: Check critical fields
                critical_missing = []
                if not lead.get("email"): critical_missing.append("email")
                if not lead.get("first_name"): critical_missing.append("first_name")
                if not lead.get("company_name") and not lead.get("company"): critical_missing.append("company")
                
                if critical_missing:
                    reason = f"Missing critical fields: {', '.join(critical_missing)}"
                    skipped_leads.append({"email": lead.get("email", "unknown"), "reason": reason})
                    progress.advance(task)
                    continue

                # Generate sequence
                sequence = self.generate_sequence(lead, campaign_type)
                if sequence:
                    lead["sequence"] = sequence
                    processed_leads.append(lead)
                
                progress.advance(task)
        
        if skipped_leads:
            print(f"⚠️ Skipped {len(skipped_leads)} leads due to missing data.")
            
        return Campaign(
            campaign_id=f"camp_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name=f"{segment.title()} Campaign - {datetime.now().strftime('%B %d')}",
            segment=segment,
            campaign_type=campaign_type,
            leads=processed_leads,
            lead_count=len(processed_leads),
            sequence=[], # Sequence is now per-lead
            status="draft",
            created_at=datetime.now().isoformat(),
            avg_icp_score=avg_icp_score,
            avg_intent_score=avg_intent_score,
            metadata={
                "skipped_count": len(skipped_leads),
                "skipped_reasons": skipped_leads
            }
        )
    
    def process_segmented_file(self, input_file: Path, segment_filter: str = None) -> List[Campaign]:
        """
        Process a segmented leads file and create campaigns.
        
        Implements Dumb Zone protection via Frequent Intentional Compaction (FIC).
        Large batches are automatically processed in chunks to keep context <40%.
        """
        
        console.print(f"\n[bold blue]✍️ CRAFTER: Generating campaigns[/bold blue]")
        
        with open(input_file) as f:
            data = json.load(f)
        
        leads = data.get("leads", [])
        
        if segment_filter:
            leads = [l for l in leads if segment_filter in l.get("segment_tags", [])]
        
        # === DUMB ZONE PROTECTION ===
        # Check context zone before processing
        token_estimate = estimate_tokens(leads)
        context_zone = get_context_zone(token_estimate)
        
        if context_zone == ContextZone.SMART:
            console.print(f"[dim]Context zone: SMART ({token_estimate:,} tokens) - optimal processing[/dim]")
        elif context_zone == ContextZone.CAUTION:
            console.print(f"[yellow]⚠️ Context zone: CAUTION ({token_estimate:,} tokens) - enabling batch mode[/yellow]")
        elif context_zone in [ContextZone.DUMB, ContextZone.CRITICAL]:
            console.print(f"[red]🚨 Context zone: {context_zone.value.upper()} ({token_estimate:,} tokens)[/red]")
            console.print(f"[yellow]   Large batch detected. Compacting and batching to stay in Smart Zone.[/yellow]")
            
            # Compact the lead batch for overview
            compacted = compact_lead_batch(leads, max_leads=20)
            if compacted['compacted']:
                console.print(f"[dim]   Compacted {compacted['total_count']} leads to {compacted['sample_count']} for analysis[/dim]")
                console.print(f"[dim]   Tier distribution: {compacted['tier_distribution']}[/dim]")
        
        # Group leads by tier and campaign type
        groups = {}
        for lead in leads:
            tier = lead.get("icp_tier", "tier_4")
            campaign_type = lead.get("recommended_campaign", "competitor_displacement")
            key = f"{tier}_{campaign_type}"
            
            if key not in groups:
                groups[key] = []
            groups[key].append(lead)
        
        campaigns = []
        failed_segments = []
        
        with Progress() as progress:
            task = progress.add_task("Creating campaigns...", total=len(groups))
            
            for segment, segment_leads in groups.items():
                if "disqualified" in segment:
                    progress.update(task, advance=1)
                    continue
                
                try:
                    campaign_type = segment.split("_", 1)[1] if "_" in segment else "competitor_displacement"
                    
                    # === BATCH PROCESSING FOR DUMB ZONE PROTECTION ===
                    # If segment is large, process in batches to stay in Smart Zone
                    if len(segment_leads) > SMART_ZONE_BATCH_SIZE:
                        console.print(f"[dim]   Batching {len(segment_leads)} leads in {segment} (batch size: {SMART_ZONE_BATCH_SIZE})[/dim]")
                        
                        for batch_idx in range(0, len(segment_leads), SMART_ZONE_BATCH_SIZE):
                            batch = segment_leads[batch_idx:batch_idx + SMART_ZONE_BATCH_SIZE]
                            batch_num = batch_idx // SMART_ZONE_BATCH_SIZE + 1
                            batch_segment = f"{segment}_batch{batch_num}"
                            
                            campaign = self.create_campaign(batch, batch_segment, campaign_type)
                            campaigns.append(campaign)
                            
                            log_event(EventType.CAMPAIGN_CREATED, {
                                "campaign_id": campaign.campaign_id,
                                "campaign_name": campaign.name,
                                "lead_count": campaign.lead_count,
                                "segment": batch_segment,
                                "campaign_type": campaign_type,
                                "batch_processing": True,
                                "batch_number": batch_num
                            })
                    else:
                        # Normal processing for smaller segments
                        campaign = self.create_campaign(segment_leads, segment, campaign_type)
                        campaigns.append(campaign)
                        
                        log_event(EventType.CAMPAIGN_CREATED, {
                            "campaign_id": campaign.campaign_id,
                            "campaign_name": campaign.name,
                            "lead_count": campaign.lead_count,
                            "segment": segment,
                            "campaign_type": campaign_type
                        })
                        
                except Exception as e:
                    failed_segments.append(segment)
                    schedule_retry(
                        operation_name="campaign_creation",
                        payload={
                            "segment": segment,
                            "lead_count": len(segment_leads),
                            "input_file": str(input_file)
                        },
                        error=e,
                        policy_name="campaign_delivery_failure",
                        metadata={"segment": segment}
                    )
                    console.print(f"[yellow]Failed to create campaign for {segment}: {e}[/yellow]")
                
                progress.update(task, advance=1)
        
        if failed_segments:
            send_warning(
                "Campaign Creation Partially Failed",
                f"{len(failed_segments)} campaign segments failed and have been queued for retry.",
                {"failed_segments": failed_segments, "success_count": len(campaigns)}
            )
        
        console.print(f"[green]✅ Created {len(campaigns)} campaigns[/green]")
        
        return campaigns
    
    def save_campaigns(self, campaigns: List[Campaign], output_dir: Optional[Path] = None) -> Path:
        """Save campaigns to JSON file."""
        
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / ".hive-mind" / "campaigns"
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"campaigns_{timestamp}.json"
        output_path = output_dir / filename
        
        campaigns_data = [asdict(c) for c in campaigns]
        
        # Calculate totals
        total_leads = sum(c.lead_count for c in campaigns)
        
        with open(output_path, "w") as f:
            json.dump({
                "created_at": datetime.now(timezone.utc).isoformat(),
                "campaign_count": len(campaigns),
                "total_leads": total_leads,
                "status": "pending_review",
                "campaigns": campaigns_data
            }, f, indent=2)
        
        console.print(f"[green]✅ Saved campaigns to {output_path}[/green]")
        
        return output_path
    
    def print_summary(self, campaigns: List[Campaign]):
        """Print campaign summary."""
        
        table = Table(title="Campaign Summary")
        table.add_column("Campaign", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Leads", style="yellow")
        table.add_column("Avg ICP", style="magenta")
        table.add_column("Status", style="blue")
        
        for campaign in campaigns:
            table.add_row(
                campaign.name[:40],
                campaign.campaign_type[:20],
                str(campaign.lead_count),
                f"{campaign.avg_icp_score:.0f}",
                campaign.status
            )
        
        console.print(table)
        
        total_leads = sum(c.lead_count for c in campaigns)
        console.print(f"\n[bold]Total: {len(campaigns)} campaigns, {total_leads} leads[/bold]")


def main():
    parser = argparse.ArgumentParser(description="Generate email campaigns from segmented leads")
    parser.add_argument("--input", type=Path, help="Input segmented leads JSON file")
    parser.add_argument("--segment", help="Filter by segment tag")
    parser.add_argument("--template", choices=list(CampaignCrafter.TEMPLATES.keys()),
                        help="Force specific template")
    
    args = parser.parse_args()
    
    if not args.input:
        # Find latest segmented file
        segmented_dir = Path(__file__).parent.parent / ".hive-mind" / "segmented"
        if segmented_dir.exists():
            files = sorted(segmented_dir.glob("*.json"), reverse=True)
            if files:
                args.input = files[0]
    
    if not args.input or not args.input.exists():
        console.print("[red]No input file specified and no segmented files found.[/red]")
        console.print("Run: python execution/segmentor_classify.py first")
        sys.exit(1)
    
    try:
        crafter = CampaignCrafter()
        campaigns = crafter.process_segmented_file(args.input, args.segment)
        
        if campaigns:
            crafter.print_summary(campaigns)
            output_path = crafter.save_campaigns(campaigns)
            
            console.print(f"\n[bold green]✅ Campaign generation complete![/bold green]")
            console.print(f"Campaigns are [yellow]pending_review[/yellow]")
            console.print(f"\nNext step: Submit for AE review via GATEKEEPER")
            console.print(f"  python execution/gatekeeper_queue.py --input {output_path}")
            
    except Exception as e:
        console.print(f"[red]❌ Campaign generation failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
