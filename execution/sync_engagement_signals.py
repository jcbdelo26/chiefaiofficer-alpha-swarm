#!/usr/bin/env python3
"""
Engagement Signal Sync Job
==========================

Aggregates engagement signals from all platforms:
- GoHighLevel (CRM activity, emails, meetings)
- Instantly (cold email stats)
- RB2B (website visitors)
- LinkedIn (connection status)

Runs on schedule to keep engagement_signals table updated.

Usage:
    python execution/sync_engagement_signals.py
    python execution/sync_engagement_signals.py --source ghl
    python execution/sync_engagement_signals.py --source instantly
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("sync-signals")


class GoHighLevelClient:
    """GoHighLevel API client for fetching contact engagement."""
    
    BASE_URL = "https://services.leadconnectorhq.com"
    
    def __init__(self, api_key: str, location_id: str):
        self.api_key = api_key
        self.location_id = location_id
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
    
    def get_contacts(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Fetch contacts from GHL."""
        import requests
        
        url = f"{self.BASE_URL}/contacts/"
        params = {
            "locationId": self.location_id,
            "limit": limit,
            "offset": offset
        }
        
        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        return data.get("contacts", [])
    
    def get_contact_by_email(self, email: str) -> Optional[Dict]:
        """Lookup contact by email."""
        import requests
        
        url = f"{self.BASE_URL}/contacts/lookup"
        params = {
            "locationId": self.location_id,
            "email": email
        }
        
        response = requests.get(url, headers=self.headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            contacts = data.get("contacts", [])
            return contacts[0] if contacts else None
        return None
    
    def get_contact_activities(self, contact_id: str) -> List[Dict]:
        """Get activity history for a contact."""
        import requests
        
        url = f"{self.BASE_URL}/contacts/{contact_id}/tasks"
        response = requests.get(url, headers=self.headers, timeout=30)
        
        if response.status_code == 200:
            return response.json().get("tasks", [])
        return []
    
    def get_appointments(self, contact_id: str) -> List[Dict]:
        """Get appointments for a contact."""
        import requests
        
        url = f"{self.BASE_URL}/contacts/{contact_id}/appointments"
        response = requests.get(url, headers=self.headers, timeout=30)
        
        if response.status_code == 200:
            return response.json().get("appointments", [])
        return []
    
    def extract_engagement_signals(self, contact: Dict) -> Dict[str, Any]:
        """Extract engagement signals from GHL contact."""
        signals = {
            "in_crm": True,
            "crm_contact_id": contact.get("id"),
            "crm_stage": contact.get("pipelineStage"),
            "last_crm_activity": contact.get("dateUpdated"),
        }
        
        # Check for form submissions
        if contact.get("source") in ["form", "landing_page", "website"]:
            signals["forms_submitted"] = 1
            signals["inbound_source"] = contact.get("source")
        
        # Check tags for intent signals
        tags = contact.get("tags", [])
        if "requested_demo" in tags or "contact_request" in tags:
            signals["requested_contact"] = True
        if "content_download" in tags:
            signals["downloaded_content"] = True
        
        return signals


class InstantlyClient:
    """Instantly.ai API client for fetching campaign stats."""
    
    BASE_URL = "https://api.instantly.ai/api/v1"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def get_campaigns(self) -> List[Dict]:
        """Fetch all campaigns."""
        import requests
        
        url = f"{self.BASE_URL}/campaign/list"
        params = {"api_key": self.api_key}
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        return response.json()
    
    def get_campaign_analytics(self, campaign_id: str) -> Dict:
        """Get analytics for a specific campaign."""
        import requests
        
        url = f"{self.BASE_URL}/analytics/campaign/summary"
        params = {
            "api_key": self.api_key,
            "campaign_id": campaign_id
        }
        
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        
        return response.json()
    
    def get_lead_status(self, email: str, campaign_id: str = None) -> Optional[Dict]:
        """Get lead engagement status from Instantly."""
        import requests
        
        url = f"{self.BASE_URL}/lead/get"
        params = {
            "api_key": self.api_key,
            "email": email,
        }
        if campaign_id:
            params["campaign_id"] = campaign_id
        
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            return response.json()
        return None
    
    def extract_engagement_signals(self, lead_data: Dict) -> Dict[str, Any]:
        """Extract engagement signals from Instantly lead data."""
        signals = {
            "emails_sent": lead_data.get("email_sent_count", 0),
            "emails_opened": lead_data.get("open_count", 0),
            "emails_clicked": lead_data.get("click_count", 0),
            "emails_replied": 1 if lead_data.get("replied") else 0,
            "emails_bounced": 1 if lead_data.get("bounced") else 0,
        }
        
        # Parse timestamps
        if lead_data.get("last_open"):
            signals["last_email_open"] = lead_data["last_open"]
        if lead_data.get("last_reply"):
            signals["last_email_reply"] = lead_data["last_reply"]
        
        return signals


class EngagementSyncService:
    """Main service for syncing engagement signals."""
    
    def __init__(self):
        from supabase import create_client
        
        self.supabase = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY")
        )
        
        # Initialize clients if credentials available
        self.ghl = None
        self.instantly = None
        
        if os.getenv("GHL_API_KEY") and os.getenv("GHL_LOCATION_ID"):
            self.ghl = GoHighLevelClient(
                os.getenv("GHL_API_KEY"),
                os.getenv("GHL_LOCATION_ID")
            )
            logger.info("GoHighLevel client initialized")
        
        if os.getenv("INSTANTLY_API_KEY"):
            self.instantly = InstantlyClient(os.getenv("INSTANTLY_API_KEY"))
            logger.info("Instantly client initialized")
        
        # Import router for scoring
        from core.lead_router import LeadRouter, EngagementSignals
        self.router = LeadRouter()
        self.EngagementSignals = EngagementSignals
    
    def sync_from_ghl(self) -> Dict[str, int]:
        """Sync engagement signals from GoHighLevel."""
        if not self.ghl:
            logger.warning("GHL client not configured")
            return {"synced": 0, "errors": 0}
        
        synced = 0
        errors = 0
        offset = 0
        
        logger.info("Starting GHL sync...")
        
        while True:
            try:
                contacts = self.ghl.get_contacts(limit=100, offset=offset)
                
                if not contacts:
                    break
                
                for contact in contacts:
                    try:
                        email = contact.get("email")
                        if not email:
                            continue
                        
                        signals = self.ghl.extract_engagement_signals(contact)
                        
                        # Get appointments
                        appointments = self.ghl.get_appointments(contact["id"])
                        signals["meetings_booked"] = len([a for a in appointments if a.get("status") == "booked"])
                        signals["meetings_completed"] = len([a for a in appointments if a.get("status") == "completed"])
                        
                        # Upsert to engagement_signals
                        self._upsert_signals(email, signals, "gohighlevel")
                        synced += 1
                        
                    except Exception as e:
                        logger.error(f"Error processing GHL contact: {e}")
                        errors += 1
                
                offset += len(contacts)
                logger.info(f"Processed {offset} GHL contacts...")
                
                if len(contacts) < 100:
                    break
                    
            except Exception as e:
                logger.error(f"GHL API error: {e}")
                break
        
        logger.info(f"GHL sync complete: {synced} synced, {errors} errors")
        return {"synced": synced, "errors": errors}
    
    def sync_from_instantly(self) -> Dict[str, int]:
        """Sync engagement signals from Instantly."""
        if not self.instantly:
            logger.warning("Instantly client not configured")
            return {"synced": 0, "errors": 0}
        
        synced = 0
        errors = 0
        
        logger.info("Starting Instantly sync...")
        
        try:
            # Get all leads from our database that are on Instantly
            result = self.supabase.table("engagement_signals").select(
                "email"
            ).eq("current_platform", "instantly").execute()
            
            for record in result.data:
                try:
                    email = record["email"]
                    lead_data = self.instantly.get_lead_status(email)
                    
                    if lead_data:
                        signals = self.instantly.extract_engagement_signals(lead_data)
                        self._upsert_signals(email, signals, "instantly")
                        synced += 1
                        
                except Exception as e:
                    logger.error(f"Error processing Instantly lead: {e}")
                    errors += 1
                    
        except Exception as e:
            logger.error(f"Instantly sync error: {e}")
        
        logger.info(f"Instantly sync complete: {synced} synced, {errors} errors")
        return {"synced": synced, "errors": errors}
    
    def sync_from_leads_table(self) -> Dict[str, int]:
        """Create signal records for leads without engagement_signals entry."""
        synced = 0
        errors = 0
        
        logger.info("Syncing from leads table...")
        
        try:
            # Get leads without signal records
            leads_result = self.supabase.table("leads").select("id, email, status, source").execute()
            signals_result = self.supabase.table("engagement_signals").select("email").execute()
            
            existing_emails = {r["email"] for r in signals_result.data if r["email"]}
            
            for lead in leads_result.data:
                if lead["email"] and lead["email"] not in existing_emails:
                    try:
                        # Create initial signal record
                        initial_signals = {
                            "lead_id": lead["id"],
                            "email": lead["email"],
                            "current_platform": "none",
                            "engagement_level": "cold",
                            "engagement_score": 0.0,
                        }
                        
                        # Check if from inbound source
                        if lead.get("source") in ["form", "referral", "inbound"]:
                            initial_signals["inbound_source"] = lead["source"]
                            initial_signals["engagement_level"] = "lukewarm"
                        
                        self.supabase.table("engagement_signals").insert(initial_signals).execute()
                        synced += 1
                        
                    except Exception as e:
                        logger.error(f"Error creating signal record: {e}")
                        errors += 1
                        
        except Exception as e:
            logger.error(f"Leads sync error: {e}")
        
        logger.info(f"Leads sync complete: {synced} new records, {errors} errors")
        return {"synced": synced, "errors": errors}
    
    def recalculate_scores(self) -> Dict[str, int]:
        """Recalculate engagement scores for all leads."""
        updated = 0
        errors = 0
        
        logger.info("Recalculating engagement scores...")
        
        try:
            result = self.supabase.table("engagement_signals").select("*").execute()
            
            for record in result.data:
                try:
                    # Build EngagementSignals from database record
                    signals = self.EngagementSignals(
                        emails_sent=record.get("emails_sent", 0),
                        emails_opened=record.get("emails_opened", 0),
                        emails_clicked=record.get("emails_clicked", 0),
                        emails_replied=record.get("emails_replied", 0),
                        linkedin_connected=record.get("linkedin_connected", False),
                        linkedin_messages_received=record.get("linkedin_messages_received", 0),
                        website_visits=record.get("website_visits", 0),
                        rb2b_identified=record.get("rb2b_identified", False),
                        in_crm=record.get("in_crm", False),
                        meetings_booked=record.get("meetings_booked", 0),
                        meetings_completed=record.get("meetings_completed", 0),
                        forms_submitted=record.get("forms_submitted", 0),
                        requested_contact=record.get("requested_contact", False),
                        downloaded_content=record.get("downloaded_content", False),
                    )
                    
                    # Calculate new score and routing
                    decision = self.router.route_lead(signals)
                    
                    # Update record
                    self.supabase.table("engagement_signals").update({
                        "engagement_score": decision.signals_summary["engagement_score"],
                        "engagement_level": decision.engagement_level.value,
                        "last_routing_decision": decision.to_dict(),
                        "last_routed_at": datetime.now(timezone.utc).isoformat(),
                    }).eq("id", record["id"]).execute()
                    
                    updated += 1
                    
                except Exception as e:
                    logger.error(f"Error updating score: {e}")
                    errors += 1
                    
        except Exception as e:
            logger.error(f"Score recalculation error: {e}")
        
        logger.info(f"Score recalculation complete: {updated} updated, {errors} errors")
        return {"updated": updated, "errors": errors}
    
    def check_transitions(self) -> List[Dict]:
        """Check for leads ready to transition from Instantly to GHL."""
        transitions = []
        
        logger.info("Checking for platform transitions...")
        
        try:
            result = self.supabase.rpc("get_leads_ready_for_ghl_transition").execute()
            
            for lead in result.data:
                logger.info(f"Transition candidate: {lead['email']} - {lead['trigger_reason']}")
                transitions.append(lead)
                
                # Record transition
                self.supabase.table("platform_transitions").insert({
                    "lead_id": lead["lead_id"],
                    "from_platform": "instantly",
                    "to_platform": "gohighlevel",
                    "trigger_event": lead["trigger_reason"],
                    "engagement_score_at_transition": lead["engagement_score"],
                    "engagement_level_at_transition": lead["engagement_level"],
                }).execute()
                
                # Update current platform
                self.supabase.table("engagement_signals").update({
                    "current_platform": "gohighlevel",
                    "transition_count": self.supabase.table("engagement_signals").select(
                        "transition_count"
                    ).eq("lead_id", lead["lead_id"]).execute().data[0].get("transition_count", 0) + 1
                }).eq("lead_id", lead["lead_id"]).execute()
                
        except Exception as e:
            logger.error(f"Transition check error: {e}")
        
        logger.info(f"Found {len(transitions)} leads ready for transition")
        return transitions
    
    def _upsert_signals(self, email: str, signals: Dict[str, Any], source: str):
        """Upsert engagement signals for an email."""
        # Get existing record
        existing = self.supabase.table("engagement_signals").select("*").eq("email", email).execute()
        
        if existing.data:
            # Update existing record
            record = existing.data[0]
            
            # Merge signals (don't overwrite with lower values)
            for key, value in signals.items():
                if isinstance(value, int) and key in record:
                    signals[key] = max(value, record.get(key, 0))
            
            self.supabase.table("engagement_signals").update(signals).eq("email", email).execute()
        else:
            # Insert new record
            signals["email"] = email
            signals["current_platform"] = source
            self.supabase.table("engagement_signals").insert(signals).execute()
        
        # Log event
        self._log_event(email, f"sync_from_{source}", source, signals)
    
    def _log_event(self, email: str, event_type: str, source: str, data: Dict):
        """Log engagement event."""
        try:
            # Get signal and lead IDs
            signal = self.supabase.table("engagement_signals").select("id, lead_id").eq("email", email).execute()
            
            if signal.data:
                self.supabase.table("engagement_events").insert({
                    "lead_id": signal.data[0].get("lead_id"),
                    "signal_id": signal.data[0]["id"],
                    "event_type": "platform_transition" if "sync" in event_type else event_type,
                    "event_source": source,
                    "event_data": data,
                }).execute()
        except Exception as e:
            logger.warning(f"Failed to log event: {e}")
    
    def run_full_sync(self) -> Dict[str, Any]:
        """Run full sync from all sources."""
        results = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "leads_sync": self.sync_from_leads_table(),
            "ghl_sync": self.sync_from_ghl(),
            "instantly_sync": self.sync_from_instantly(),
            "score_recalc": self.recalculate_scores(),
            "transitions": len(self.check_transitions()),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # Save results
        output_path = Path(__file__).parent.parent / ".hive-mind" / "last_sync.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Full sync complete. Results saved to {output_path}")
        return results


def main():
    parser = argparse.ArgumentParser(description="Sync engagement signals")
    parser.add_argument("--source", choices=["ghl", "instantly", "leads", "all"], default="all")
    parser.add_argument("--recalc", action="store_true", help="Only recalculate scores")
    parser.add_argument("--transitions", action="store_true", help="Only check transitions")
    args = parser.parse_args()
    
    service = EngagementSyncService()
    
    if args.recalc:
        service.recalculate_scores()
    elif args.transitions:
        service.check_transitions()
    elif args.source == "ghl":
        service.sync_from_ghl()
    elif args.source == "instantly":
        service.sync_from_instantly()
    elif args.source == "leads":
        service.sync_from_leads_table()
    else:
        service.run_full_sync()


if __name__ == "__main__":
    main()
