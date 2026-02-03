#!/usr/bin/env python3
"""
Enrich Missing GHL Contacts
===========================

Scans GoHighLevel for contacts missing critical fields (Company Name, Job Title)
and enriches them via the Clay Direct Enrichment pipeline.

Workflow:
1. Fetch all GHL contacts (paginated)
2. Filter for contacts with missing critical fields
3. Submit to Clay for enrichment
4. Update GHL with results
5. Track unenrichable contacts
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import httpx

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env', override=True)

from core.clay_direct_enrichment import ClayDirectEnrichment, EnrichmentResult, EnrichmentStatus
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

# Configuration
CRITICAL_FIELDS = ["companyName", "title"]  # Fields to check in GHL
BATCH_SIZE = 10  # Max concurrent enrichments
EXCLUSION_FILE = PROJECT_ROOT / ".hive-mind" / "exclusions" / "unenrichable_contacts.json"

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(PROJECT_ROOT / ".hive-mind" / "logs" / "enrichment_pipeline.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("enrichment_pipeline")
console = Console()

class GHLConnector:
    """Helper for GHL API interactions."""
    
    def __init__(self):
        self.api_key = os.getenv("GHL_PROD_API_KEY")
        self.location_id = os.getenv("GHL_LOCATION_ID")
        self.base_url = "https://services.leadconnectorhq.com"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Version": "2021-07-28",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
    async def get_all_contacts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch contacts from GHL."""
        contacts = []
        url = f"{self.base_url}/contacts/"
        params = {
            "locationId": self.location_id,
            "limit": 100
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                response = await client.get(url, headers=self.headers, params=params)
                if response.status_code != 200:
                    logger.error(f"Failed to fetch GHL contacts: {response.text}")
                    break
                    
                data = response.json()
                batch = data.get("contacts", [])
                contacts.extend(batch)
                
                if len(contacts) >= limit or not batch:
                    break
                    
                # Pagination (simplistic for now, GHL uses search_after usually)
                # For this implementation, we'll implement robust search via POST /contacts/search
                # to handle pagination correctly if needed later.
                # For now, fetching first 'limit' contacts.
                break 
        
        return contacts[:limit]
    
    async def update_contact(self, contact_id: str, updates: Dict[str, Any]) -> bool:
        """Update a contact in GHL with enriched data."""
        url = f"{self.base_url}/contacts/{contact_id}"
        
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.put(url, headers=self.headers, json=updates)
                if response.status_code == 200:
                    logger.info(f"✅ Updated GHL contact {contact_id}")
                    return True
                else:
                    logger.error(f"❌ Failed to update GHL contact {contact_id}: {response.status_code} - {response.text}")
                    return False
            except Exception as e:
                logger.error(f"❌ Exception updating GHL contact {contact_id}: {e}")
                return False


class MissingFieldEnricher:
    """Orchestrates the enrichment of incomplete contacts."""
    
    def __init__(self):
        self.ghl = GHLConnector()
        self.enricher = ClayDirectEnrichment()
        self.unenrichable = self._load_exclusions()
        
    def _load_exclusions(self) -> Dict[str, Any]:
        if EXCLUSION_FILE.exists():
            return json.loads(EXCLUSION_FILE.read_text())
        return {"contacts": [], "last_updated": ""}
        
    def _save_exclusions(self):
        EXCLUSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        EXCLUSION_FILE.write_text(json.dumps(self.unenrichable, indent=2))
        
    def is_excluded(self, email: str) -> bool:
        for c in self.unenrichable["contacts"]:
            if c["email"] == email:
                return True
        return False
        
    def identify_missing_fields(self, contacts: List[Dict]) -> List[Dict]:
        """Filter contacts that need enrichment."""
        needed = []
        for c in contacts:
            if not c.get("email"):
                continue  # Can't enrich without email
                
            if self.is_excluded(c["email"]):
                continue
                
            missing = []
            if not c.get("companyName"):
                missing.append("companyName")
            
            # Check custom fields or tags for title if not standard
            # GHL doesn't always strictly enforce 'title' field location
            title = c.get("title") or c.get("jobTitle")
            if not title:
                 # Check custom fields list
                custom_fields = c.get("customFields", [])
                has_title = any(cf.get("id") == "job_title" or cf.get("key") == "job_title" for cf in custom_fields)
                if not has_title:
                    missing.append("title")
                    
            if missing:
                c["_missing_fields"] = missing
                needed.append(c)
        return needed

    async def process_batch(self, contacts: List[Dict]):
        """Process a batch of contacts."""
        tasks = []
        for contact in contacts:
            tasks.append(self.enrich_single(contact))
            
        results = await asyncio.gather(*tasks)
        return results

    async def enrich_single(self, contact: Dict) -> bool:
        """Enrich a single contact and update GHL."""
        email = contact.get("email")
        contact_id = contact.get("id")
        if not email or not contact_id:
            return False
            
        visitor_data = {
            "email": email,
            "first_name": contact.get("firstName"),
            "last_name": contact.get("lastName"),
            # Add existing data to help matching
            "company": {"name": contact.get("companyName", "")},
            "visitor_id": contact_id  # Use GHL ID as visitor ID ref
        }
        
        logger.info(f"Enriching {email} (Missing: {contact['_missing_fields']})")
        
        result = await self.enricher.enrich_visitor(visitor_data)
        
        if result.status == EnrichmentStatus.COMPLETED:
            if result.company_name or result.job_title:
                logger.info(f"✅ Enriched {email}: {result.company_name} | {result.job_title}")
                
                # ===================================================================
                # CRITICAL: Update GHL with enriched data
                # ===================================================================
                updates = {}
                if result.company_name:
                    updates["companyName"] = result.company_name
                if result.job_title:
                    updates["title"] = result.job_title
                
                if updates:
                    success = await self.ghl.update_contact(contact_id, updates)
                    if success:
                        logger.info(f"✅ GHL updated for {email}")
                        return True
                    else:
                        logger.error(f"❌ Failed to update GHL for {email}")
                        return False
                # ===================================================================
                
                return True
            else:
                logger.warning(f"❌ Completed but no data found for {email}")
                self._mark_unenrichable(contact, "No data returned from Clay")
                return False
        else:
            logger.error(f"❌ Enrichment failed for {email}: {result.error_message}")
            return False

    def _mark_unenrichable(self, contact: Dict, reason: str):
        self.unenrichable["contacts"].append({
            "ghl_contact_id": contact.get("id"),
            "email": contact.get("email"),
            "reason": reason,
            "added_at": datetime.now().isoformat()
        })
        self.unenrichable["last_updated"] = datetime.now().isoformat()
        self._save_exclusions()

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Enrich missing GHL contacts")
    parser.add_argument("--limit", type=int, default=50, help="Max contacts to check")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually update GHL")
    args = parser.parse_args()

    enricher = MissingFieldEnricher()
    
    console.print("[bold blue]Fetching GHL contacts...[/bold blue]")
    contacts = await enricher.ghl.get_all_contacts(limit=args.limit)
    console.print(f"Fetched {len(contacts)} contacts.")
    
    targets = enricher.identify_missing_fields(contacts)
    console.print(f"[bold yellow]Identified {len(targets)} contacts missing critical fields.[/bold yellow]")
    
    if not targets:
        console.print("[green]No contacts need enrichment![/green]")
        return

    if args.dry_run:
        console.print("[dim]Dry run - skipping enrichment[/dim]")
        for t in targets[:5]:
            console.print(f" - Would enrich: {t.get('email')} (Missing: {t['_missing_fields']})")
        return

    # Process in chunks
    total_processed = 0
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Enriching contacts...", total=len(targets))
        
        for i in range(0, len(targets), BATCH_SIZE):
            batch = targets[i:i+BATCH_SIZE]
            await enricher.process_batch(batch)
            progress.advance(task, len(batch))
            total_processed += len(batch)
            
    console.print(f"[bold green]Finished! Processed {total_processed} contacts.[/bold green]")

if __name__ == "__main__":
    asyncio.run(main())
