#!/usr/bin/env python3
"""
GDPR Data Deletion (Right to Erasure)
======================================
Tombstones lead records and removes from active datasets while preserving audit trail.

Usage:
    python execution/gdpr_delete.py --lead-id <lead_id>
    python execution/gdpr_delete.py --email user@example.com
    python execution/gdpr_delete.py --purge-expired  # Remove audit trails > 90 days
"""

import os
import sys
import json
import argparse
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console

console = Console()

HIVE_MIND = Path(__file__).parent.parent / ".hive-mind"
TOMBSTONE_DIR = HIVE_MIND / "gdpr" / "tombstones"
AUDIT_RETENTION_DAYS = 90


def create_tombstone(lead_id: str, email: str = None, reason: str = "gdpr_erasure") -> Dict[str, Any]:
    """Create a tombstone record for a deleted lead."""
    
    TOMBSTONE_DIR.mkdir(parents=True, exist_ok=True)
    
    tombstone = {
        "lead_id": lead_id,
        "email_hash": hash(email) if email else None,
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "audit_expires_at": (datetime.now(timezone.utc) + timedelta(days=AUDIT_RETENTION_DAYS)).isoformat(),
        "deleted_from": [],
    }
    
    return tombstone


def save_tombstone(tombstone: Dict[str, Any]):
    """Save tombstone to file."""
    lead_id = tombstone["lead_id"]
    tombstone_file = TOMBSTONE_DIR / f"{lead_id}.json"
    tombstone_file.write_text(json.dumps(tombstone, indent=2))


def remove_from_json_file(file_path: Path, lead_id: str, email: str = None) -> int:
    """Remove matching leads from a JSON file. Returns count of removed records."""
    
    try:
        content = json.loads(file_path.read_text())
    except (json.JSONDecodeError, IOError):
        return 0
    
    removed = 0
    modified = False
    
    def matches(record: Dict[str, Any]) -> bool:
        if record.get("lead_id") == lead_id:
            return True
        if email and record.get("email", "").lower() == email.lower():
            return True
        return False
    
    # Handle leads array
    if "leads" in content and isinstance(content["leads"], list):
        original_count = len(content["leads"])
        content["leads"] = [l for l in content["leads"] if not matches(l)]
        removed += original_count - len(content["leads"])
        if removed > 0:
            modified = True
    
    # Handle campaigns with nested leads
    if "campaigns" in content and isinstance(content["campaigns"], list):
        for campaign in content["campaigns"]:
            if "leads" in campaign and isinstance(campaign["leads"], list):
                original_count = len(campaign["leads"])
                campaign["leads"] = [l for l in campaign["leads"] if not matches(l)]
                diff = original_count - len(campaign["leads"])
                if diff > 0:
                    removed += diff
                    modified = True
                    campaign["lead_count"] = len(campaign["leads"])
    
    # Handle single record files
    if "lead_id" in content and matches(content):
        # Replace with tombstone marker
        content = {
            "tombstone": True,
            "original_lead_id": lead_id,
            "deleted_at": datetime.now(timezone.utc).isoformat()
        }
        removed = 1
        modified = True
    
    if modified:
        file_path.write_text(json.dumps(content, indent=2))
    
    return removed


def remove_from_jsonl_file(file_path: Path, lead_id: str, email: str = None) -> int:
    """Remove matching entries from a JSONL file. Returns count of removed records."""
    
    if not file_path.exists():
        return 0
    
    def matches(record: Dict[str, Any]) -> bool:
        payload = record.get("payload", record)
        if payload.get("lead_id") == lead_id:
            return True
        if email and payload.get("email", "").lower() == email.lower():
            return True
        return False
    
    lines_to_keep = []
    removed = 0
    
    try:
        with open(file_path, "r") as f:
            for line in f:
                try:
                    record = json.loads(line.strip())
                    if matches(record):
                        removed += 1
                    else:
                        lines_to_keep.append(line)
                except json.JSONDecodeError:
                    lines_to_keep.append(line)
    except IOError:
        return 0
    
    if removed > 0:
        with open(file_path, "w") as f:
            f.writelines(lines_to_keep)
    
    return removed


def delete_lead_data(lead_id: str, email: str = None, reason: str = "gdpr_erasure") -> Dict[str, Any]:
    """Delete all data for a lead from active datasets."""
    
    tombstone = create_tombstone(lead_id, email, reason)
    
    directories_to_scan = [
        ("enriched", "json"),
        ("segmented", "json"),
        ("campaigns", "json"),
        ("scraped", "json"),
        ("outbox", "json"),
        ("replies", "json"),
    ]
    
    total_removed = 0
    
    for dir_name, file_type in directories_to_scan:
        dir_path = HIVE_MIND / dir_name
        if not dir_path.exists():
            continue
        
        dir_removed = 0
        for file in dir_path.glob(f"*.{file_type}"):
            count = remove_from_json_file(file, lead_id, email)
            if count > 0:
                dir_removed += count
                tombstone["deleted_from"].append({
                    "source": dir_name,
                    "file": file.name,
                    "records_removed": count
                })
        
        if dir_removed > 0:
            console.print(f"  [yellow]Removed {dir_removed} records from {dir_name}/[/yellow]")
            total_removed += dir_removed
    
    # Handle events.jsonl separately
    events_file = HIVE_MIND / "events.jsonl"
    if events_file.exists():
        events_removed = remove_from_jsonl_file(events_file, lead_id, email)
        if events_removed > 0:
            console.print(f"  [yellow]Removed {events_removed} events from events.jsonl[/yellow]")
            tombstone["deleted_from"].append({
                "source": "events",
                "file": "events.jsonl",
                "records_removed": events_removed
            })
            total_removed += events_removed
    
    tombstone["total_records_removed"] = total_removed
    save_tombstone(tombstone)
    
    return tombstone


def purge_expired_tombstones() -> int:
    """Remove tombstones older than retention period."""
    
    if not TOMBSTONE_DIR.exists():
        return 0
    
    now = datetime.now(timezone.utc)
    purged = 0
    
    for tombstone_file in TOMBSTONE_DIR.glob("*.json"):
        try:
            tombstone = json.loads(tombstone_file.read_text())
            expires_at = datetime.fromisoformat(tombstone["audit_expires_at"].replace("Z", "+00:00"))
            
            if now > expires_at:
                tombstone_file.unlink()
                purged += 1
                console.print(f"  [dim]Purged expired tombstone: {tombstone_file.name}[/dim]")
        except (json.JSONDecodeError, IOError, KeyError):
            continue
    
    return purged


def is_deleted(lead_id: str) -> bool:
    """Check if a lead has been deleted (tombstone exists)."""
    tombstone_file = TOMBSTONE_DIR / f"{lead_id}.json"
    return tombstone_file.exists()


def get_tombstone(lead_id: str) -> Optional[Dict[str, Any]]:
    """Get tombstone record for a lead if it exists."""
    tombstone_file = TOMBSTONE_DIR / f"{lead_id}.json"
    if not tombstone_file.exists():
        return None
    
    try:
        return json.loads(tombstone_file.read_text())
    except (json.JSONDecodeError, IOError):
        return None


def list_tombstones() -> List[Dict[str, Any]]:
    """List all active tombstones."""
    
    if not TOMBSTONE_DIR.exists():
        return []
    
    tombstones = []
    for tombstone_file in TOMBSTONE_DIR.glob("*.json"):
        try:
            tombstone = json.loads(tombstone_file.read_text())
            tombstones.append(tombstone)
        except (json.JSONDecodeError, IOError):
            continue
    
    return sorted(tombstones, key=lambda t: t.get("deleted_at", ""), reverse=True)


def main():
    parser = argparse.ArgumentParser(description="GDPR-compliant data deletion")
    parser.add_argument("--lead-id", help="Lead ID to delete")
    parser.add_argument("--email", help="Email address to search and delete")
    parser.add_argument("--reason", default="gdpr_erasure", help="Reason for deletion")
    parser.add_argument("--purge-expired", action="store_true", help="Purge expired tombstones")
    parser.add_argument("--list", action="store_true", help="List all tombstones")
    parser.add_argument("--force", action="store_true", help="Skip confirmation")
    
    args = parser.parse_args()
    
    if args.list:
        tombstones = list_tombstones()
        if not tombstones:
            console.print("[green]No tombstones found[/green]")
        else:
            console.print(f"\n[bold]Tombstone Records ({len(tombstones)})[/bold]\n")
            for t in tombstones:
                expires = datetime.fromisoformat(t["audit_expires_at"].replace("Z", "+00:00"))
                days_left = (expires - datetime.now(timezone.utc)).days
                console.print(f"  {t['lead_id']}: deleted {t['deleted_at'][:10]} - {t['total_records_removed']} records - audit expires in {days_left} days")
        return
    
    if args.purge_expired:
        console.print("[bold]Purging expired tombstones...[/bold]")
        purged = purge_expired_tombstones()
        console.print(f"[green]Purged {purged} expired tombstones[/green]")
        return
    
    if not args.lead_id and not args.email:
        console.print("[red]Must provide --lead-id or --email[/red]")
        sys.exit(1)
    
    # Confirmation
    if not args.force:
        identifier = args.lead_id or args.email
        console.print(f"\n[bold red]⚠️  WARNING: This will permanently delete all data for: {identifier}[/bold red]")
        console.print(f"[yellow]Reason: {args.reason}[/yellow]")
        console.print(f"[yellow]Audit trail will be retained for {AUDIT_RETENTION_DAYS} days[/yellow]\n")
        
        confirm = input("Type 'DELETE' to confirm: ")
        if confirm != "DELETE":
            console.print("[yellow]Deletion cancelled[/yellow]")
            sys.exit(0)
    
    try:
        console.print(f"\n[bold]Deleting data...[/bold]")
        tombstone = delete_lead_data(args.lead_id, args.email, args.reason)
        
        console.print(f"\n[green]✅ Deletion complete[/green]")
        console.print(f"[bold]Summary:[/bold]")
        console.print(f"  Lead ID: {tombstone['lead_id']}")
        console.print(f"  Records removed: {tombstone['total_records_removed']}")
        console.print(f"  Audit trail expires: {tombstone['audit_expires_at'][:10]}")
        tombstone_path = TOMBSTONE_DIR / f"{tombstone['lead_id']}.json"
        console.print(f"  Tombstone: {tombstone_path}")
        
    except Exception as e:
        console.print(f"[red]❌ Deletion failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
