#!/usr/bin/env python3
"""
GHL Local Sync - Background Sync Service
=========================================

Syncs GHL contacts/opportunities to local Supabase for:
- Instant reads without API calls
- No rate limit issues on read operations
- Offline resilience

Sync Strategy:
- Full sync: Every 4 hours (or on demand)
- Incremental sync: Every 15 minutes (recently modified only)
- Real-time: Webhook updates from GHL

Usage:
    from core.ghl_local_sync import get_ghl_sync, GHLLocalSync
    
    sync = get_ghl_sync()
    
    # Read from local (instant, no API call)
    contact = await sync.get_contact("contact_123")
    
    # Force sync from GHL
    await sync.sync_contacts(full=True)
"""

import os
import sys
import json
import asyncio
import logging
import aiohttp
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ghl_local_sync")


@dataclass
class SyncStats:
    """Statistics for sync operations."""
    last_full_sync: Optional[str] = None
    last_incremental_sync: Optional[str] = None
    contacts_synced: int = 0
    opportunities_synced: int = 0
    local_reads: int = 0
    api_reads_avoided: int = 0
    sync_errors: int = 0


class GHLLocalSync:
    """
    Syncs GHL data to local storage for instant reads.
    
    Architecture:
        Agent needs contact → Check local cache → Return instantly
                                    ↓ (if miss)
                           Fetch from GHL → Cache locally → Return
    
    Background sync keeps local data fresh without blocking agents.
    """
    
    GHL_BASE_URL = "https://services.leadconnectorhq.com"
    
    def __init__(self):
        self.api_key = os.getenv("GHL_API_KEY") or os.getenv("GHL_PROD_API_KEY")
        self.location_id = os.getenv("GHL_LOCATION_ID")
        
        # Local storage
        self.data_dir = PROJECT_ROOT / ".hive-mind" / "ghl_cache"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.contacts_file = self.data_dir / "contacts.json"
        self.opportunities_file = self.data_dir / "opportunities.json"
        self.stats_file = self.data_dir / "sync_stats.json"
        
        # In-memory cache for hot data
        self._contacts: Dict[str, Dict] = {}
        self._opportunities: Dict[str, Dict] = {}
        self._contact_by_email: Dict[str, str] = {}  # email -> contact_id
        
        # Stats
        self.stats = self._load_stats()
        
        # Session
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Load existing data
        self._load_local_data()
        
        logger.info(f"GHL Local Sync initialized with {len(self._contacts)} cached contacts")
    
    def _load_stats(self) -> SyncStats:
        """Load sync statistics."""
        if self.stats_file.exists():
            try:
                data = json.loads(self.stats_file.read_text())
                return SyncStats(**data)
            except Exception:
                pass
        return SyncStats()
    
    def _save_stats(self):
        """Save sync statistics."""
        self.stats_file.write_text(json.dumps(asdict(self.stats), indent=2))
    
    def _load_local_data(self):
        """Load cached data from disk."""
        if self.contacts_file.exists():
            try:
                contacts = json.loads(self.contacts_file.read_text())
                self._contacts = {c["id"]: c for c in contacts if "id" in c}
                self._contact_by_email = {
                    c.get("email", "").lower(): c["id"] 
                    for c in contacts if c.get("email")
                }
                logger.info(f"Loaded {len(self._contacts)} contacts from cache")
            except Exception as e:
                logger.warning(f"Failed to load contacts cache: {e}")
        
        if self.opportunities_file.exists():
            try:
                opps = json.loads(self.opportunities_file.read_text())
                self._opportunities = {o["id"]: o for o in opps if "id" in o}
                logger.info(f"Loaded {len(self._opportunities)} opportunities from cache")
            except Exception as e:
                logger.warning(f"Failed to load opportunities cache: {e}")
    
    def _save_local_data(self):
        """Save cached data to disk."""
        try:
            self.contacts_file.write_text(
                json.dumps(list(self._contacts.values()), indent=2)
            )
            self.opportunities_file.write_text(
                json.dumps(list(self._opportunities.values()), indent=2)
            )
        except Exception as e:
            logger.error(f"Failed to save local data: {e}")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Version": "2021-07-28"
                },
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session
    
    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._save_stats()
    
    # =========================================================================
    # LOCAL READ OPERATIONS (Instant, no API calls)
    # =========================================================================
    
    async def get_contact(self, contact_id: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        Get contact from local cache.
        
        Args:
            contact_id: GHL contact ID
            force_refresh: If True, fetch from GHL even if cached
            
        Returns:
            Contact data or None if not found
        """
        if not force_refresh and contact_id in self._contacts:
            self.stats.local_reads += 1
            self.stats.api_reads_avoided += 1
            return self._contacts[contact_id]
        
        # Cache miss - fetch from GHL
        contact = await self._fetch_contact_from_ghl(contact_id)
        if contact:
            self._contacts[contact_id] = contact
            if contact.get("email"):
                self._contact_by_email[contact["email"].lower()] = contact_id
            self._save_local_data()
        
        return contact
    
    async def get_contact_by_email(self, email: str, force_refresh: bool = False) -> Optional[Dict]:
        """
        Get contact by email from local cache.
        
        Args:
            email: Contact email address
            force_refresh: If True, search GHL even if cached
            
        Returns:
            Contact data or None if not found
        """
        email_lower = email.lower()
        
        if not force_refresh and email_lower in self._contact_by_email:
            contact_id = self._contact_by_email[email_lower]
            self.stats.local_reads += 1
            self.stats.api_reads_avoided += 1
            return self._contacts.get(contact_id)
        
        # Cache miss - search GHL
        contact = await self._search_contact_in_ghl(email)
        if contact:
            self._contacts[contact["id"]] = contact
            self._contact_by_email[email_lower] = contact["id"]
            self._save_local_data()
        
        return contact
    
    def get_all_contacts(self) -> List[Dict]:
        """Get all cached contacts (instant, no API call)."""
        self.stats.local_reads += 1
        return list(self._contacts.values())
    
    def search_contacts_local(self, query: str) -> List[Dict]:
        """
        Search contacts locally (instant).
        
        Args:
            query: Search term (matches name, email, company)
            
        Returns:
            List of matching contacts
        """
        query_lower = query.lower()
        self.stats.local_reads += 1
        
        matches = []
        for contact in self._contacts.values():
            searchable = " ".join([
                contact.get("firstName", ""),
                contact.get("lastName", ""),
                contact.get("email", ""),
                contact.get("companyName", ""),
            ]).lower()
            
            if query_lower in searchable:
                matches.append(contact)
        
        return matches
    
    # =========================================================================
    # SEARCH / FILTER (Local cache, instant)
    # =========================================================================

    def search_by_tags(self, tags: List[str], match_all: bool = False) -> List[Dict]:
        """
        Search cached contacts by GHL tags.

        Args:
            tags: List of tag names to match
            match_all: If True, contact must have ALL tags. If False, ANY tag matches.

        Returns:
            List of matching contacts
        """
        self.stats.local_reads += 1
        tags_lower = [t.lower() for t in tags]
        matches = []

        for contact in self._contacts.values():
            contact_tags = [t.lower() for t in (contact.get("tags") or [])]
            if match_all:
                if all(t in contact_tags for t in tags_lower):
                    matches.append(contact)
            else:
                if any(t in contact_tags for t in tags_lower):
                    matches.append(contact)

        return matches

    def search_by_pipeline_stage(self, stages: List[str]) -> List[Dict]:
        """
        Search cached contacts by pipeline stage name.

        GHL contacts may have pipeline/stage info in opportunities or custom fields.
        Checks: pipelineStage, customField.pipeline_stage, and tags containing stage names.
        """
        self.stats.local_reads += 1
        stages_lower = [s.lower() for s in stages]
        matches = []

        for contact in self._contacts.values():
            # Check direct pipeline stage field
            stage = (contact.get("pipelineStage") or "").lower()
            if stage and stage in stages_lower:
                matches.append(contact)
                continue

            # Check custom fields
            custom_fields = contact.get("customField") or contact.get("customFields") or {}
            if isinstance(custom_fields, dict):
                ps = (custom_fields.get("pipeline_stage") or "").lower()
                if ps and ps in stages_lower:
                    matches.append(contact)
                    continue
            elif isinstance(custom_fields, list):
                for cf in custom_fields:
                    if (cf.get("key") or cf.get("name", "")).lower() == "pipeline_stage":
                        if (cf.get("value") or "").lower() in stages_lower:
                            matches.append(contact)
                            break

            # Check tags containing stage names
            contact_tags = [t.lower() for t in (contact.get("tags") or [])]
            if any(s in contact_tags for s in stages_lower):
                matches.append(contact)

        return matches

    def get_stale_contacts(self, inactive_days: int = 30) -> List[Dict]:
        """
        Get contacts with no activity in N days.

        Uses dateLastActivity (GHL field) or _synced_at as fallback.
        Returns contacts sorted by staleness (most stale first).
        """
        self.stats.local_reads += 1
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=inactive_days)
        stale = []

        for contact in self._contacts.values():
            # Skip contacts without email
            if not contact.get("email"):
                continue

            # Determine last activity date
            last_activity_str = (
                contact.get("dateLastActivity")
                or contact.get("lastActivity")
                or contact.get("dateUpdated")
                or contact.get("_synced_at")
            )

            if not last_activity_str:
                # No activity date at all — consider stale
                stale.append((contact, inactive_days + 999))
                continue

            try:
                last_activity = datetime.fromisoformat(
                    last_activity_str.replace("Z", "+00:00")
                )
                if last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=timezone.utc)

                if last_activity < cutoff:
                    days_inactive = (now - last_activity).days
                    stale.append((contact, days_inactive))
            except (ValueError, TypeError):
                continue

        # Sort by staleness (most inactive first)
        stale.sort(key=lambda x: x[1], reverse=True)
        return [contact for contact, _ in stale]

    # =========================================================================
    # GHL API OPERATIONS (When cache miss)
    # =========================================================================
    
    async def _fetch_contact_from_ghl(self, contact_id: str) -> Optional[Dict]:
        """Fetch single contact from GHL API."""
        if not self.api_key:
            logger.warning("GHL API key not configured")
            return None
        
        try:
            session = await self._get_session()
            url = f"{self.GHL_BASE_URL}/contacts/{contact_id}"
            
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    contact = data.get("contact", data)
                    contact["_synced_at"] = datetime.now(timezone.utc).isoformat()
                    return contact
                else:
                    logger.warning(f"Failed to fetch contact {contact_id}: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching contact: {e}")
            self.stats.sync_errors += 1
            return None
    
    async def _search_contact_in_ghl(self, email: str) -> Optional[Dict]:
        """Search for contact by email in GHL."""
        if not self.api_key or not self.location_id:
            return None
        
        try:
            session = await self._get_session()
            url = f"{self.GHL_BASE_URL}/contacts/search"
            params = {
                "locationId": self.location_id,
                "query": email
            }
            
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    contacts = data.get("contacts", [])
                    for contact in contacts:
                        if contact.get("email", "").lower() == email.lower():
                            contact["_synced_at"] = datetime.now(timezone.utc).isoformat()
                            return contact
                return None
        except Exception as e:
            logger.error(f"Error searching contact: {e}")
            self.stats.sync_errors += 1
            return None
    
    # =========================================================================
    # SYNC OPERATIONS (Background)
    # =========================================================================
    
    async def sync_contacts(self, full: bool = False, limit: int = 100) -> int:
        """
        Sync contacts from GHL to local cache.
        
        Args:
            full: If True, sync all contacts. If False, sync recently modified only.
            limit: Maximum contacts to sync per call
            
        Returns:
            Number of contacts synced
        """
        if not self.api_key or not self.location_id:
            logger.warning("GHL credentials not configured")
            return 0
        
        synced = 0
        
        try:
            session = await self._get_session()
            
            # Build query params
            params = {
                "locationId": self.location_id,
                "limit": min(limit, 100)
            }
            
            if not full and self.stats.last_incremental_sync:
                # Only get contacts modified since last sync
                last_sync = datetime.fromisoformat(self.stats.last_incremental_sync.replace("Z", "+00:00"))
                params["startAfter"] = last_sync.isoformat()
            
            url = f"{self.GHL_BASE_URL}/contacts/"
            
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    contacts = data.get("contacts", [])
                    
                    for contact in contacts:
                        contact["_synced_at"] = datetime.now(timezone.utc).isoformat()
                        self._contacts[contact["id"]] = contact
                        if contact.get("email"):
                            self._contact_by_email[contact["email"].lower()] = contact["id"]
                        synced += 1
                    
                    self._save_local_data()
                    self.stats.contacts_synced += synced
                    
                    if full:
                        self.stats.last_full_sync = datetime.now(timezone.utc).isoformat()
                    else:
                        self.stats.last_incremental_sync = datetime.now(timezone.utc).isoformat()
                    
                    self._save_stats()
                    logger.info(f"Synced {synced} contacts from GHL")
                else:
                    logger.error(f"Sync failed: {resp.status}")
                    self.stats.sync_errors += 1
                    
        except Exception as e:
            logger.error(f"Sync error: {e}")
            self.stats.sync_errors += 1
        
        return synced
    
    async def handle_webhook_update(self, event_type: str, contact_data: Dict):
        """
        Handle real-time webhook update from GHL.
        
        Args:
            event_type: GHL event type (e.g., "contact.created", "contact.updated")
            contact_data: Contact data from webhook
        """
        contact_id = contact_data.get("id")
        if not contact_id:
            return
        
        contact_data["_synced_at"] = datetime.now(timezone.utc).isoformat()
        contact_data["_source"] = "webhook"
        
        self._contacts[contact_id] = contact_data
        if contact_data.get("email"):
            self._contact_by_email[contact_data["email"].lower()] = contact_id
        
        self._save_local_data()
        logger.info(f"Webhook update: {event_type} for contact {contact_id}")
    
    # =========================================================================
    # STATS & STATUS
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get sync statistics."""
        return {
            "cached_contacts": len(self._contacts),
            "cached_opportunities": len(self._opportunities),
            "local_reads": self.stats.local_reads,
            "api_reads_avoided": self.stats.api_reads_avoided,
            "total_synced": self.stats.contacts_synced,
            "sync_errors": self.stats.sync_errors,
            "last_full_sync": self.stats.last_full_sync,
            "last_incremental_sync": self.stats.last_incremental_sync,
            "estimated_api_calls_saved": self.stats.api_reads_avoided,
            "cache_freshness": self._get_cache_freshness()
        }
    
    def _get_cache_freshness(self) -> str:
        """Get cache freshness status."""
        if not self.stats.last_incremental_sync:
            return "never_synced"
        
        last_sync = datetime.fromisoformat(
            self.stats.last_incremental_sync.replace("Z", "+00:00")
        )
        age = datetime.now(timezone.utc) - last_sync
        
        if age < timedelta(minutes=15):
            return "fresh"
        elif age < timedelta(hours=1):
            return "recent"
        elif age < timedelta(hours=4):
            return "stale"
        else:
            return "very_stale"


# Singleton
_ghl_sync: Optional[GHLLocalSync] = None

def get_ghl_sync() -> GHLLocalSync:
    """Get singleton instance of GHLLocalSync."""
    global _ghl_sync
    if _ghl_sync is None:
        _ghl_sync = GHLLocalSync()
    return _ghl_sync


# Background sync task
async def run_background_sync(interval_minutes: int = 15):
    """
    Run background sync loop.
    
    Args:
        interval_minutes: How often to sync (default 15 minutes)
    """
    sync = get_ghl_sync()
    
    while True:
        try:
            await sync.sync_contacts(full=False, limit=100)
        except Exception as e:
            logger.error(f"Background sync error: {e}")
        
        await asyncio.sleep(interval_minutes * 60)


if __name__ == "__main__":
    async def main():
        sync = get_ghl_sync()
        
        print("=" * 60)
        print("GHL Local Sync - Test")
        print("=" * 60)
        
        # Show current stats
        stats = sync.get_stats()
        print(f"\nCached contacts: {stats['cached_contacts']}")
        print(f"API calls saved: {stats['api_reads_avoided']}")
        print(f"Cache freshness: {stats['cache_freshness']}")
        
        # Test local search
        print("\nSearching locally for 'test'...")
        results = sync.search_contacts_local("test")
        print(f"Found {len(results)} matches")
        
        # Sync some contacts
        print("\nSyncing contacts from GHL...")
        synced = await sync.sync_contacts(full=False, limit=10)
        print(f"Synced {synced} contacts")
        
        await sync.close()
    
    asyncio.run(main())
