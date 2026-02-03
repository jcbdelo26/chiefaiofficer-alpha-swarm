#!/usr/bin/env python3
"""
Suppression List Sync
=====================
Syncs suppression lists between GoHighLevel and Instantly.
- Pulls unsubscribes from Instantly, adds DNC tag in GHL
- Pulls DNC contacts from GHL, adds to Instantly blocklist
- Runs as scheduled job or on-demand
- Logs all sync operations
- Supports --dry-run mode

Usage:
    python execution/sync_suppression.py
    python execution/sync_suppression.py --dry-run
    python execution/sync_suppression.py --direction ghl-to-instantly
    python execution/sync_suppression.py --direction instantly-to-ghl
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, asdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from core.safety import safe_operation
from core.event_log import log_event, EventType

console = Console()

DNC_TAG = "DNC"
SYNC_STATE_FILE = Path(".hive-mind/suppression_sync_state.json")


@dataclass
class SyncResult:
    """Result of a suppression sync operation."""
    direction: str
    emails_synced: List[str]
    emails_skipped: List[str]
    errors: List[Dict[str, str]]
    dry_run: bool
    started_at: str
    completed_at: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class GHLSuppressionClient:
    """GoHighLevel client for DNC operations."""
    
    def __init__(self):
        self.api_key = os.getenv("GHL_API_KEY")
        self.location_id = os.getenv("GHL_LOCATION_ID")
        self.base_url = "https://services.leadconnectorhq.com"
        
        if not self.api_key:
            raise ValueError("GHL_API_KEY not set")
        if not self.location_id:
            raise ValueError("GHL_LOCATION_ID not set")
    
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
    
    def get_dnc_contacts(self) -> List[Dict[str, Any]]:
        """Get all contacts with DNC tag."""
        import requests
        
        contacts = []
        params = {
            "locationId": self.location_id,
            "query": f"tags:{DNC_TAG}",
            "limit": 100
        }
        
        try:
            response = requests.get(
                f"{self.base_url}/contacts/",
                headers=self._headers(),
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                contacts = data.get("contacts", [])
            else:
                console.print(f"[red]Error fetching GHL contacts: {response.status_code}[/red]")
        except Exception as e:
            console.print(f"[red]Exception fetching GHL contacts: {e}[/red]")
        
        return contacts
    
    def get_contact_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get contact by email."""
        import requests
        
        try:
            response = requests.get(
                f"{self.base_url}/contacts/lookup",
                headers=self._headers(),
                params={"email": email, "locationId": self.location_id},
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json().get("contacts", [None])[0]
        except Exception:
            pass
        
        return None
    
    def add_dnc_tag(self, contact_id: str) -> bool:
        """Add DNC tag to contact."""
        import requests
        
        try:
            response = requests.post(
                f"{self.base_url}/contacts/{contact_id}/tags",
                headers=self._headers(),
                json={"tags": [DNC_TAG]},
                timeout=30
            )
            return response.status_code in [200, 201]
        except Exception:
            return False
    
    def create_contact_with_dnc(self, email: str) -> Optional[str]:
        """Create contact with DNC tag if doesn't exist."""
        import requests
        
        try:
            response = requests.post(
                f"{self.base_url}/contacts/",
                headers=self._headers(),
                json={
                    "locationId": self.location_id,
                    "email": email,
                    "tags": [DNC_TAG],
                    "source": "Suppression Sync"
                },
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                return response.json().get("contact", {}).get("id")
        except Exception:
            pass
        
        return None


class InstantlySuppressionClient:
    """Instantly client for blocklist operations."""
    
    def __init__(self):
        self.api_key = os.getenv("INSTANTLY_API_KEY")
        self.base_url = "https://api.instantly.ai/api/v1"
        
        if not self.api_key:
            raise ValueError("INSTANTLY_API_KEY not set")
    
    def _request(self, method: str, endpoint: str, data: Dict = None, params: Dict = None) -> Dict[str, Any]:
        """Make API request to Instantly."""
        import requests
        
        url = f"{self.base_url}/{endpoint}"
        
        if params is None:
            params = {}
        params["api_key"] = self.api_key
        
        try:
            if method == "GET":
                response = requests.get(url, params=params, timeout=30)
            elif method == "POST":
                response = requests.post(url, params=params, json=data, timeout=30)
            else:
                return {"success": False, "error": f"Unsupported method: {method}"}
            
            if response.status_code in [200, 201]:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": response.text, "status": response.status_code}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_unsubscribes(self, limit: int = 1000) -> List[str]:
        """Get all unsubscribed emails from Instantly."""
        result = self._request("GET", "lead/unsubscribes", params={"limit": limit})
        
        if result.get("success"):
            data = result.get("data", {})
            if isinstance(data, list):
                return [item.get("email") for item in data if item.get("email")]
            elif isinstance(data, dict):
                return [item.get("email") for item in data.get("leads", []) if item.get("email")]
        
        return []
    
    def get_blocklist(self, limit: int = 1000) -> List[str]:
        """Get all emails in blocklist."""
        result = self._request("GET", "blocklist/list", params={"limit": limit})
        
        if result.get("success"):
            data = result.get("data", {})
            if isinstance(data, list):
                return [item.get("email") for item in data if item.get("email")]
            elif isinstance(data, dict):
                return [item.get("email") for item in data.get("blocklist", []) if item.get("email")]
        
        return []
    
    def add_to_blocklist(self, emails: List[str]) -> Dict[str, Any]:
        """Add emails to blocklist."""
        if not emails:
            return {"success": True, "added": 0}
        
        result = self._request("POST", "blocklist/add", data={"emails": emails})
        return result
    
    def remove_from_campaigns(self, email: str) -> bool:
        """Remove email from all active campaigns."""
        result = self._request("POST", "lead/delete", data={"email": email})
        return result.get("success", False)


def load_sync_state() -> Dict[str, Any]:
    """Load previous sync state."""
    if SYNC_STATE_FILE.exists():
        try:
            with open(SYNC_STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    
    return {
        "last_sync_at": None,
        "synced_emails": [],
        "sync_history": []
    }


def save_sync_state(state: Dict[str, Any]) -> None:
    """Save sync state."""
    SYNC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SYNC_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


@safe_operation(operation_type="crm_write")
def sync_instantly_to_ghl(dry_run: bool = False) -> SyncResult:
    """
    Sync unsubscribes from Instantly to GHL DNC tag.
    """
    started_at = datetime.now(timezone.utc).isoformat()
    synced = []
    skipped = []
    errors = []
    
    console.print("\n[bold cyan]Syncing Instantly → GHL[/bold cyan]")
    console.print("Fetching unsubscribes from Instantly...")
    
    try:
        instantly = InstantlySuppressionClient()
        ghl = GHLSuppressionClient()
    except ValueError as e:
        return SyncResult(
            direction="instantly_to_ghl",
            emails_synced=[],
            emails_skipped=[],
            errors=[{"error": str(e)}],
            dry_run=dry_run,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat()
        )
    
    unsubscribes = instantly.get_unsubscribes()
    blocklist = instantly.get_blocklist()
    all_suppressed = set(unsubscribes + blocklist)
    
    console.print(f"Found {len(all_suppressed)} suppressed emails in Instantly")
    
    state = load_sync_state()
    already_synced = set(state.get("synced_emails", []))
    
    new_to_sync = all_suppressed - already_synced
    console.print(f"New emails to sync: {len(new_to_sync)}")
    
    for email in new_to_sync:
        try:
            if dry_run:
                console.print(f"  [yellow][DRY RUN][/yellow] Would add DNC tag for: {email}")
                synced.append(email)
                continue
            
            contact = ghl.get_contact_by_email(email)
            
            if contact:
                contact_id = contact.get("id")
                if ghl.add_dnc_tag(contact_id):
                    console.print(f"  [green]✓[/green] Added DNC tag: {email}")
                    synced.append(email)
                else:
                    errors.append({"email": email, "error": "Failed to add tag"})
            else:
                contact_id = ghl.create_contact_with_dnc(email)
                if contact_id:
                    console.print(f"  [green]✓[/green] Created contact with DNC: {email}")
                    synced.append(email)
                else:
                    errors.append({"email": email, "error": "Failed to create contact"})
                    
        except Exception as e:
            errors.append({"email": email, "error": str(e)})
    
    if not dry_run and synced:
        state["synced_emails"] = list(set(state.get("synced_emails", []) + synced))
        state["last_sync_at"] = datetime.now(timezone.utc).isoformat()
        save_sync_state(state)
    
    result = SyncResult(
        direction="instantly_to_ghl",
        emails_synced=synced,
        emails_skipped=list(already_synced),
        errors=errors,
        dry_run=dry_run,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc).isoformat()
    )
    
    log_event(
        EventType.SYSTEM_START,
        {
            "action": "suppression_sync",
            "direction": "instantly_to_ghl",
            "synced_count": len(synced),
            "error_count": len(errors),
            "dry_run": dry_run
        }
    )
    
    return result


@safe_operation(operation_type="email_send")
def sync_ghl_to_instantly(dry_run: bool = False) -> SyncResult:
    """
    Sync DNC contacts from GHL to Instantly blocklist.
    """
    started_at = datetime.now(timezone.utc).isoformat()
    synced = []
    skipped = []
    errors = []
    
    console.print("\n[bold cyan]Syncing GHL → Instantly[/bold cyan]")
    console.print("Fetching DNC contacts from GHL...")
    
    try:
        ghl = GHLSuppressionClient()
        instantly = InstantlySuppressionClient()
    except ValueError as e:
        return SyncResult(
            direction="ghl_to_instantly",
            emails_synced=[],
            emails_skipped=[],
            errors=[{"error": str(e)}],
            dry_run=dry_run,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat()
        )
    
    dnc_contacts = ghl.get_dnc_contacts()
    dnc_emails = [c.get("email") for c in dnc_contacts if c.get("email")]
    
    console.print(f"Found {len(dnc_emails)} DNC contacts in GHL")
    
    existing_blocklist = set(instantly.get_blocklist())
    console.print(f"Existing blocklist size: {len(existing_blocklist)}")
    
    new_to_block = [e for e in dnc_emails if e not in existing_blocklist]
    skipped = [e for e in dnc_emails if e in existing_blocklist]
    
    console.print(f"New emails to add to blocklist: {len(new_to_block)}")
    
    if new_to_block:
        if dry_run:
            console.print(f"  [yellow][DRY RUN][/yellow] Would add {len(new_to_block)} emails to blocklist")
            synced = new_to_block
        else:
            batch_size = 100
            for i in range(0, len(new_to_block), batch_size):
                batch = new_to_block[i:i + batch_size]
                result = instantly.add_to_blocklist(batch)
                
                if result.get("success"):
                    synced.extend(batch)
                    console.print(f"  [green]✓[/green] Added batch of {len(batch)} emails to blocklist")
                else:
                    for email in batch:
                        errors.append({"email": email, "error": result.get("error", "Unknown error")})
    
    result = SyncResult(
        direction="ghl_to_instantly",
        emails_synced=synced,
        emails_skipped=skipped,
        errors=errors,
        dry_run=dry_run,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc).isoformat()
    )
    
    log_event(
        EventType.SYSTEM_START,
        {
            "action": "suppression_sync",
            "direction": "ghl_to_instantly",
            "synced_count": len(synced),
            "error_count": len(errors),
            "dry_run": dry_run
        }
    )
    
    return result


def run_full_sync(dry_run: bool = False) -> Dict[str, SyncResult]:
    """Run bidirectional sync."""
    results = {}
    
    console.print(Panel.fit(
        f"[bold]Suppression List Sync[/bold]\n"
        f"{'[yellow]DRY RUN MODE[/yellow]' if dry_run else '[green]LIVE MODE[/green]'}",
        border_style="cyan"
    ))
    
    results["instantly_to_ghl"] = sync_instantly_to_ghl(dry_run=dry_run)
    results["ghl_to_instantly"] = sync_ghl_to_instantly(dry_run=dry_run)
    
    return results


def print_sync_summary(results: Dict[str, SyncResult]) -> None:
    """Print sync summary table."""
    table = Table(title="Suppression Sync Summary")
    table.add_column("Direction", style="cyan")
    table.add_column("Synced", style="green")
    table.add_column("Skipped", style="yellow")
    table.add_column("Errors", style="red")
    table.add_column("Dry Run", style="blue")
    
    for direction, result in results.items():
        table.add_row(
            direction.replace("_", " → ").upper(),
            str(len(result.emails_synced)),
            str(len(result.emails_skipped)),
            str(len(result.errors)),
            "Yes" if result.dry_run else "No"
        )
    
    console.print(table)
    
    for direction, result in results.items():
        if result.errors:
            console.print(f"\n[red]Errors in {direction}:[/red]")
            for error in result.errors[:5]:
                console.print(f"  - {error.get('email', 'N/A')}: {error.get('error', 'Unknown')}")
            if len(result.errors) > 5:
                console.print(f"  ... and {len(result.errors) - 5} more errors")


def save_sync_report(results: Dict[str, SyncResult]) -> Path:
    """Save sync report to file."""
    output_dir = Path(".hive-mind/sync_reports")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"suppression_sync_{timestamp}.json"
    
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "results": {k: v.to_dict() for k, v in results.items()}
    }
    
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Sync suppression lists between GHL and Instantly")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying")
    parser.add_argument(
        "--direction",
        choices=["both", "ghl-to-instantly", "instantly-to-ghl"],
        default="both",
        help="Sync direction"
    )
    
    args = parser.parse_args()
    
    try:
        if args.direction == "both":
            results = run_full_sync(dry_run=args.dry_run)
        elif args.direction == "ghl-to-instantly":
            result = sync_ghl_to_instantly(dry_run=args.dry_run)
            results = {"ghl_to_instantly": result}
        else:
            result = sync_instantly_to_ghl(dry_run=args.dry_run)
            results = {"instantly_to_ghl": result}
        
        print_sync_summary(results)
        
        report_path = save_sync_report(results)
        console.print(f"\n[dim]Report saved to: {report_path}[/dim]")
        
        total_errors = sum(len(r.errors) for r in results.values())
        return 1 if total_errors > 0 else 0
        
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
