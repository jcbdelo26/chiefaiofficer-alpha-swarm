#!/usr/bin/env python3
"""
GDPR Data Export
================
Exports all stored data for a lead as structured JSON (Subject Access Request).

Usage:
    python execution/gdpr_export.py --lead-id <lead_id>
    python execution/gdpr_export.py --email user@example.com
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console

console = Console()

HIVE_MIND = Path(__file__).parent.parent / ".hive-mind"
SAR_TRACKING_FILE = HIVE_MIND / "gdpr" / "sar_requests.json"


def find_lead_data(lead_id: str = None, email: str = None) -> Dict[str, Any]:
    """Find all data associated with a lead across all data stores."""
    
    if not lead_id and not email:
        raise ValueError("Must provide lead_id or email")
    
    data = {
        "lead_id": lead_id,
        "email": email,
        "export_timestamp": datetime.now(timezone.utc).isoformat(),
        "data_sources": {},
    }
    
    def matches_lead(record: Dict[str, Any]) -> bool:
        if lead_id and record.get("lead_id") == lead_id:
            return True
        if email and record.get("email", "").lower() == email.lower():
            return True
        return False
    
    # Search enriched data
    enriched_dir = HIVE_MIND / "enriched"
    if enriched_dir.exists():
        enriched_records = []
        for file in enriched_dir.glob("*.json"):
            try:
                content = json.loads(file.read_text())
                leads = content.get("leads", [content] if "lead_id" in content else [])
                for lead in leads:
                    if matches_lead(lead):
                        enriched_records.append({
                            "source_file": file.name,
                            "data": lead
                        })
                        if not lead_id:
                            lead_id = lead.get("lead_id")
                            data["lead_id"] = lead_id
            except (json.JSONDecodeError, IOError):
                continue
        if enriched_records:
            data["data_sources"]["enriched"] = enriched_records
    
    # Search segmented data
    segmented_dir = HIVE_MIND / "segmented"
    if segmented_dir.exists():
        segmented_records = []
        for file in segmented_dir.glob("*.json"):
            try:
                content = json.loads(file.read_text())
                leads = content.get("leads", [])
                for lead in leads:
                    if matches_lead(lead):
                        segmented_records.append({
                            "source_file": file.name,
                            "data": lead
                        })
            except (json.JSONDecodeError, IOError):
                continue
        if segmented_records:
            data["data_sources"]["segmented"] = segmented_records
    
    # Search campaigns
    campaigns_dir = HIVE_MIND / "campaigns"
    if campaigns_dir.exists():
        campaign_records = []
        for file in campaigns_dir.glob("*.json"):
            try:
                content = json.loads(file.read_text())
                campaigns = content.get("campaigns", [])
                for campaign in campaigns:
                    for lead in campaign.get("leads", []):
                        if matches_lead(lead):
                            campaign_records.append({
                                "campaign_id": campaign.get("campaign_id"),
                                "campaign_name": campaign.get("name"),
                                "source_file": file.name,
                                "lead_data": lead,
                                "sequence_included": True
                            })
            except (json.JSONDecodeError, IOError):
                continue
        if campaign_records:
            data["data_sources"]["campaigns"] = campaign_records
    
    # Search scraped data
    scraped_dir = HIVE_MIND / "scraped"
    if scraped_dir.exists():
        scraped_records = []
        for file in scraped_dir.glob("*.json"):
            try:
                content = json.loads(file.read_text())
                leads = content.get("leads", content.get("followers", content.get("members", [])))
                if isinstance(leads, list):
                    for lead in leads:
                        if matches_lead(lead):
                            scraped_records.append({
                                "source_file": file.name,
                                "data": lead
                            })
            except (json.JSONDecodeError, IOError):
                continue
        if scraped_records:
            data["data_sources"]["scraped"] = scraped_records
    
    # Search event log
    events_file = HIVE_MIND / "events.jsonl"
    if events_file.exists():
        related_events = []
        try:
            with open(events_file, "r") as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        payload = event.get("payload", {})
                        if matches_lead(payload) or payload.get("lead_id") == lead_id:
                            related_events.append(event)
                    except json.JSONDecodeError:
                        continue
        except IOError:
            pass
        if related_events:
            data["data_sources"]["events"] = related_events
    
    # Search outbox (pending communications)
    outbox_dir = HIVE_MIND / "outbox"
    if outbox_dir.exists():
        outbox_records = []
        for file in outbox_dir.glob("*.json"):
            try:
                content = json.loads(file.read_text())
                if matches_lead(content):
                    outbox_records.append({
                        "source_file": file.name,
                        "data": content
                    })
            except (json.JSONDecodeError, IOError):
                continue
        if outbox_records:
            data["data_sources"]["outbox"] = outbox_records
    
    # Search replies
    replies_dir = HIVE_MIND / "replies"
    if replies_dir.exists():
        reply_records = []
        for file in replies_dir.glob("*.json"):
            try:
                content = json.loads(file.read_text())
                if matches_lead(content):
                    reply_records.append({
                        "source_file": file.name,
                        "data": content
                    })
            except (json.JSONDecodeError, IOError):
                continue
        if reply_records:
            data["data_sources"]["replies"] = reply_records
    
    return data


def track_sar_request(lead_id: str, email: str = None) -> Dict[str, Any]:
    """Track a Subject Access Request for 30-day compliance."""
    
    SAR_TRACKING_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    requests = []
    if SAR_TRACKING_FILE.exists():
        try:
            requests = json.loads(SAR_TRACKING_FILE.read_text()).get("requests", [])
        except (json.JSONDecodeError, IOError):
            requests = []
    
    request_id = f"SAR-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{lead_id[:8] if lead_id else 'unknown'}"
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=30)
    
    sar_record = {
        "request_id": request_id,
        "lead_id": lead_id,
        "email": email,
        "requested_at": now.isoformat(),
        "deadline": deadline.isoformat(),
        "status": "pending",
        "completed_at": None,
    }
    
    requests.append(sar_record)
    SAR_TRACKING_FILE.write_text(json.dumps({"requests": requests}, indent=2))
    
    return sar_record


def complete_sar_request(request_id: str) -> bool:
    """Mark a SAR request as completed."""
    
    if not SAR_TRACKING_FILE.exists():
        return False
    
    try:
        data = json.loads(SAR_TRACKING_FILE.read_text())
        requests = data.get("requests", [])
        
        for req in requests:
            if req["request_id"] == request_id:
                req["status"] = "completed"
                req["completed_at"] = datetime.now(timezone.utc).isoformat()
                SAR_TRACKING_FILE.write_text(json.dumps({"requests": requests}, indent=2))
                return True
        
        return False
    except (json.JSONDecodeError, IOError):
        return False


def get_pending_sar_requests() -> List[Dict[str, Any]]:
    """Get all pending SAR requests, highlighting overdue ones."""
    
    if not SAR_TRACKING_FILE.exists():
        return []
    
    try:
        data = json.loads(SAR_TRACKING_FILE.read_text())
        requests = data.get("requests", [])
        
        now = datetime.now(timezone.utc)
        pending = []
        
        for req in requests:
            if req["status"] == "pending":
                deadline = datetime.fromisoformat(req["deadline"].replace("Z", "+00:00"))
                req["days_remaining"] = (deadline - now).days
                req["overdue"] = now > deadline
                pending.append(req)
        
        return pending
    except (json.JSONDecodeError, IOError):
        return []


def export_lead_data(lead_id: str = None, email: str = None, output_file: Path = None) -> Path:
    """Export all lead data and save to file."""
    
    # Track the SAR request
    sar = track_sar_request(lead_id, email)
    console.print(f"[blue]Tracked SAR request: {sar['request_id']}[/blue]")
    console.print(f"[yellow]Deadline: {sar['deadline']}[/yellow]")
    
    # Gather all data
    data = find_lead_data(lead_id, email)
    data["sar_request_id"] = sar["request_id"]
    
    # Determine output file
    if output_file is None:
        export_dir = HIVE_MIND / "gdpr" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        lead_ref = lead_id[:8] if lead_id else email.split("@")[0] if email else "unknown"
        output_file = export_dir / f"export_{lead_ref}_{timestamp}.json"
    
    # Write export
    output_file.write_text(json.dumps(data, indent=2, default=str))
    
    # Mark SAR as completed
    complete_sar_request(sar["request_id"])
    
    return output_file


def main():
    parser = argparse.ArgumentParser(description="Export all GDPR data for a lead")
    parser.add_argument("--lead-id", help="Lead ID to export")
    parser.add_argument("--email", help="Email address to search for")
    parser.add_argument("--output", type=Path, help="Output file path")
    parser.add_argument("--list-pending", action="store_true", help="List pending SAR requests")
    
    args = parser.parse_args()
    
    if args.list_pending:
        pending = get_pending_sar_requests()
        if not pending:
            console.print("[green]No pending SAR requests[/green]")
        else:
            console.print(f"\n[bold]Pending SAR Requests ({len(pending)})[/bold]\n")
            for req in pending:
                status = "[red]OVERDUE[/red]" if req["overdue"] else f"[yellow]{req['days_remaining']} days remaining[/yellow]"
                console.print(f"  {req['request_id']}: {req['lead_id'] or req['email']} - {status}")
        return
    
    if not args.lead_id and not args.email:
        console.print("[red]Must provide --lead-id or --email[/red]")
        sys.exit(1)
    
    try:
        output_path = export_lead_data(args.lead_id, args.email, args.output)
        console.print(f"\n[green]✅ Data exported to: {output_path}[/green]")
        
        # Show summary
        data = json.loads(output_path.read_text())
        sources = data.get("data_sources", {})
        console.print(f"\n[bold]Export Summary:[/bold]")
        for source, records in sources.items():
            console.print(f"  - {source}: {len(records)} records")
        
    except Exception as e:
        console.print(f"[red]❌ Export failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
