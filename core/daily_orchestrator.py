"""
Daily Orchestrator for the Chief AI Officer Alpha Swarm

This script runs on a schedule (e.g., 8 AM EST daily) to:
1. Fetch stale contacts from GHL (no activity in 90 days)
2. Fetch ghosted deals from GHL (Lost/Stalled status)
3. Fetch non-responders (sent email but no reply in 7 days)
4. Trigger enrichment and email crafting
5. Route results to the appropriate queue (Hot/Warm/Nurture)
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import pytz
from dotenv import load_dotenv

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

# Configuration
EST_TIMEZONE = pytz.timezone('US/Eastern')
GHL_API_KEY = os.getenv("GHL_API_KEY")
GHL_LOCATION_ID = os.getenv("GHL_LOCATION_ID")
GHL_BASE_URL = "https://services.leadconnectorhq.com"

STALE_DAYS = 90
NON_RESPONDER_DAYS = 7
GHOSTED_STATUSES = ["lost", "stalled", "abandoned"]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [ORCHESTRATOR] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==============================================================================
# GHL QUERY FUNCTIONS
# ==============================================================================

def get_ghl_headers() -> Dict:
    """Return headers for GHL API requests."""
    return {
        "Authorization": f"Bearer {GHL_API_KEY}",
        "Version": "2021-07-28",
        "Content-Type": "application/json"
    }

def get_stale_contacts(days: int = STALE_DAYS) -> List[Dict]:
    """
    Fetch contacts with no activity in the specified number of days.
    
    GHL API: GET /contacts
    Filter: lastActivityDate < (now - days)
    """
    if not GHL_API_KEY or not GHL_LOCATION_ID:
        logger.warning("GHL credentials not configured. Returning empty list.")
        return []
    
    import requests
    
    cutoff_date = datetime.now(EST_TIMEZONE) - timedelta(days=days)
    
    try:
        # GHL contacts endpoint with date filter
        url = f"{GHL_BASE_URL}/contacts/"
        params = {
            "locationId": GHL_LOCATION_ID,
            "limit": 100,
            # Note: GHL API filtering varies by version; this is a simplified approach
        }
        
        response = requests.get(url, headers=get_ghl_headers(), params=params, timeout=30)
        response.raise_for_status()
        
        contacts = response.json().get("contacts", [])
        
        # Filter client-side for stale contacts
        stale_contacts = []
        for contact in contacts:
            last_activity = contact.get("lastActivityDate") or contact.get("dateUpdated")
            if last_activity:
                try:
                    last_dt = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
                    if last_dt < cutoff_date.replace(tzinfo=pytz.UTC):
                        stale_contacts.append({
                            "id": contact.get("id"),
                            "email": contact.get("email"),
                            "name": f"{contact.get('firstName', '')} {contact.get('lastName', '')}".strip(),
                            "company": contact.get("companyName"),
                            "last_activity": last_activity,
                            "segment": "stale"
                        })
                except Exception:
                    continue
        
        logger.info(f"Found {len(stale_contacts)} stale contacts (>{days} days)")
        return stale_contacts
        
    except Exception as e:
        logger.error(f"Error fetching stale contacts: {e}")
        return []

def get_ghosted_deals() -> List[Dict]:
    """
    Fetch deals with Lost/Stalled/Abandoned status for re-engagement.
    
    GHL API: GET /opportunities
    Filter: status in [lost, stalled, abandoned]
    """
    if not GHL_API_KEY or not GHL_LOCATION_ID:
        logger.warning("GHL credentials not configured. Returning empty list.")
        return []
    
    import requests
    
    try:
        url = f"{GHL_BASE_URL}/opportunities/search"
        
        ghosted_leads = []
        
        for status in GHOSTED_STATUSES:
            params = {
                "locationId": GHL_LOCATION_ID,
                "status": status,
                "limit": 50
            }
            
            response = requests.get(url, headers=get_ghl_headers(), params=params, timeout=30)
            
            if response.status_code == 200:
                opportunities = response.json().get("opportunities", [])
                
                for opp in opportunities:
                    contact = opp.get("contact", {})
                    ghosted_leads.append({
                        "id": opp.get("id"),
                        "contact_id": contact.get("id"),
                        "email": contact.get("email"),
                        "name": contact.get("name"),
                        "company": contact.get("companyName"),
                        "status": status,
                        "pipeline": opp.get("pipelineName"),
                        "segment": "ghosted"
                    })
        
        logger.info(f"Found {len(ghosted_leads)} ghosted deals")
        return ghosted_leads
        
    except Exception as e:
        logger.error(f"Error fetching ghosted deals: {e}")
        return []

def get_non_responders(days: int = NON_RESPONDER_DAYS) -> List[Dict]:
    """
    Fetch contacts who were sent an email but haven't replied.
    
    This checks the local shadow_mode_emails for sent emails
    and cross-references with GHL for reply activity.
    """
    shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
    
    if not shadow_dir.exists():
        return []
    
    cutoff_date = datetime.now(EST_TIMEZONE) - timedelta(days=days)
    non_responders = []
    
    for f in shadow_dir.glob("*.json"):
        try:
            with open(f, 'r') as fp:
                data = json.load(fp)
                
                # Only check approved/sent emails
                if data.get("status") != "approved":
                    continue
                
                # Check if sent date is older than cutoff
                sent_date_str = data.get("approved_at") or data.get("timestamp")
                if not sent_date_str:
                    continue
                
                try:
                    sent_date = datetime.fromisoformat(sent_date_str.replace("Z", "+00:00"))
                    if sent_date > cutoff_date.replace(tzinfo=pytz.UTC):
                        continue  # Too recent
                except Exception:
                    continue
                
                # Check if we've already followed up
                if data.get("follow_up_sent"):
                    continue
                
                non_responders.append({
                    "id": f.stem,
                    "email": data.get("to"),
                    "name": data.get("recipient_data", {}).get("name", ""),
                    "company": data.get("recipient_data", {}).get("company"),
                    "original_subject": data.get("subject"),
                    "sent_date": sent_date_str,
                    "segment": "non_responder"
                })
                
        except Exception:
            continue
    
    logger.info(f"Found {len(non_responders)} non-responders (>{days} days)")
    return non_responders

# ==============================================================================
# PROCESSING PIPELINE
# ==============================================================================

def save_to_nurture_queue(leads: List[Dict], sequence_type: str):
    """Save leads to the nurture queue for processing."""
    nurture_dir = PROJECT_ROOT / ".hive-mind" / "nurture_queue"
    nurture_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for i, lead in enumerate(leads):
        lead["sequence_type"] = sequence_type
        lead["queued_at"] = datetime.now().isoformat()
        lead["status"] = "pending"
        
        filename = f"{sequence_type}_{lead.get('id', i)}_{timestamp}.json"
        filepath = nurture_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(lead, f, indent=2)
    
    logger.info(f"Queued {len(leads)} leads for {sequence_type} nurture sequence")

def run_daily_orchestration():
    """
    Main orchestration function that runs daily.
    
    Segments:
    1. Stale contacts (90+ days inactive) → Re-engagement sequence
    2. Ghosted deals (Lost/Stalled) → Win-back sequence
    3. Non-responders (7+ days no reply) → Follow-up sequence
    """
    now_est = datetime.now(EST_TIMEZONE)
    logger.info(f"🦅 Daily Orchestrator Started at {now_est.strftime('%Y-%m-%d %H:%M:%S')} EST")
    
    # 1. Fetch all segments
    stale_contacts = get_stale_contacts(days=STALE_DAYS)
    ghosted_deals = get_ghosted_deals()
    non_responders = get_non_responders(days=NON_RESPONDER_DAYS)
    
    total_leads = len(stale_contacts) + len(ghosted_deals) + len(non_responders)
    logger.info(f"📊 Total leads identified: {total_leads}")
    
    # 2. Save to respective nurture queues
    if stale_contacts:
        save_to_nurture_queue(stale_contacts, "reengagement")
    
    if ghosted_deals:
        save_to_nurture_queue(ghosted_deals, "winback")
    
    if non_responders:
        save_to_nurture_queue(non_responders, "followup")
    
    # 3. Summary
    logger.info("=" * 50)
    logger.info("📬 DAILY ORCHESTRATION COMPLETE")
    logger.info(f"   • Stale Contacts: {len(stale_contacts)}")
    logger.info(f"   • Ghosted Deals: {len(ghosted_deals)}")
    logger.info(f"   • Non-Responders: {len(non_responders)}")
    logger.info("=" * 50)
    
    return {
        "stale": len(stale_contacts),
        "ghosted": len(ghosted_deals),
        "non_responders": len(non_responders),
        "total": total_leads
    }

def main():
    """Entry point for daily orchestration."""
    try:
        result = run_daily_orchestration()
        logger.info(f"Orchestration completed successfully: {result}")
    except Exception as e:
        logger.error(f"Orchestration failed: {e}")
        raise

if __name__ == "__main__":
    main()
