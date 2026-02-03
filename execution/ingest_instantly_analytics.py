"""
Instantly Campaign Analytics Ingestion
Imports historical campaign data for RL training and baseline metrics.
"""

import os
import sys
import json
import time
import argparse
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / ".hive-mind" / "knowledge"
LOG_DIR = PROJECT_ROOT / ".tmp" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Load environment variables
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

INSTANTLY_API_KEY = os.getenv("INSTANTLY_API_KEY")
INSTANTLY_BASE_URL = os.getenv("INSTANTLY_BASE_URL", "https://api.instantly.ai/api/v1")


class InstantlyIngestion:
    """Ingest campaign data from Instantly.ai API."""
    
    def __init__(self):
        self.api_key = INSTANTLY_API_KEY
        self.base_url = INSTANTLY_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })
        self.rate_limit_delay = 1.0  # seconds between requests
        self.log_file = LOG_DIR / f"ingest_instantly_{datetime.now().strftime('%Y-%m-%d')}.log"
        
    def _log(self, message: str):
        """Log message to file and console."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"{timestamp} | {message}"
        print(log_line)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(log_line + "\n")
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make rate-limited API request."""
        url = f"{self.base_url}/{endpoint}"
        
        if params is None:
            params = {}
        params["api_key"] = self.api_key
        
        try:
            time.sleep(self.rate_limit_delay)
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 429:
                # Rate limited - wait and retry
                self._log("Rate limited, waiting 60 seconds...")
                time.sleep(60)
                return self._make_request(endpoint, params)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self._log(f"API Error: {e}")
            return None
    
    def get_campaigns(self) -> List[Dict]:
        """Get all campaigns from Instantly."""
        self._log("Fetching campaigns...")
        
        result = self._make_request("campaign/list")
        
        if not result:
            self._log("Failed to fetch campaigns")
            return []
        
        campaigns = result if isinstance(result, list) else result.get("campaigns", [])
        self._log(f"Found {len(campaigns)} campaigns")
        return campaigns
    
    def get_campaign_analytics(self, campaign_id: str) -> Optional[Dict]:
        """Get analytics for a specific campaign."""
        result = self._make_request("analytics/campaign/summary", {
            "campaign_id": campaign_id
        })
        return result
    
    def get_campaign_leads(self, campaign_id: str, limit: int = 1000) -> List[Dict]:
        """Get leads from a campaign with their status."""
        result = self._make_request("lead/list", {
            "campaign_id": campaign_id,
            "limit": limit
        })
        
        if not result:
            return []
        
        return result if isinstance(result, list) else result.get("leads", [])
    
    def process_campaign(self, campaign: Dict) -> Dict:
        """Process a single campaign into our schema."""
        campaign_id = campaign.get("id", "")
        campaign_name = campaign.get("name", "Unknown")
        
        self._log(f"Processing campaign: {campaign_name}")
        
        # Get analytics
        analytics = self.get_campaign_analytics(campaign_id)
        
        if not analytics:
            analytics = {}
        
        # Extract metrics
        emails_sent = analytics.get("emails_sent", 0)
        opens = analytics.get("opens", 0)
        replies = analytics.get("replies", 0)
        bounces = analytics.get("bounces", 0)
        
        # Calculate rates
        open_rate = (opens / emails_sent) if emails_sent > 0 else 0
        reply_rate = (replies / emails_sent) if emails_sent > 0 else 0
        bounce_rate = (bounces / emails_sent) if emails_sent > 0 else 0
        
        # Infer segment from campaign name
        segment = self._infer_segment(campaign_name)
        
        return {
            "campaign_id": campaign_id,
            "name": campaign_name,
            "status": campaign.get("status", "unknown"),
            "created_at": campaign.get("timestamp_created", ""),
            "metrics": {
                "emails_sent": emails_sent,
                "opens": opens,
                "open_rate": round(open_rate, 4),
                "replies": replies,
                "reply_rate": round(reply_rate, 4),
                "bounces": bounces,
                "bounce_rate": round(bounce_rate, 4),
                "positive_replies": analytics.get("positive_replies", 0),
                "meetings_booked": analytics.get("meetings_booked", 0)
            },
            "segment": segment,
            "ingested_at": datetime.now().isoformat()
        }
    
    def _infer_segment(self, campaign_name: str) -> str:
        """Infer segment from campaign name."""
        name_lower = campaign_name.lower()
        
        if any(x in name_lower for x in ["gong", "clari", "chorus", "competitor"]):
            return "competitor_displacement"
        elif any(x in name_lower for x in ["event", "conference", "summit"]):
            return "event_followup"
        elif any(x in name_lower for x in ["group", "community"]):
            return "community_outreach"
        elif any(x in name_lower for x in ["visitor", "rb2b", "website"]):
            return "website_visitor"
        elif any(x in name_lower for x in ["tier1", "vip", "enterprise"]):
            return "tier1_vip"
        else:
            return "general"
    
    def ingest_all(self, days_back: int = 90) -> Dict[str, Any]:
        """Run full ingestion of campaign data."""
        self._log(f"Starting Instantly ingestion (last {days_back} days)")
        
        campaigns = self.get_campaigns()
        
        if not campaigns:
            return {"success": False, "error": "No campaigns found"}
        
        # Filter by date if possible
        cutoff = datetime.now() - timedelta(days=days_back)
        
        processed = []
        skipped = 0
        
        for campaign in campaigns:
            try:
                # Check if already ingested
                campaign_id = campaign.get("id", "")
                output_file = KNOWLEDGE_DIR / "campaigns" / f"{campaign_id}.json"
                
                if output_file.exists():
                    skipped += 1
                    continue
                
                # Process campaign
                processed_campaign = self.process_campaign(campaign)
                processed.append(processed_campaign)
                
                # Save individual campaign
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(processed_campaign, f, indent=2)
                
            except Exception as e:
                self._log(f"Error processing campaign {campaign.get('name', 'unknown')}: {e}")
        
        # Save summary
        summary = {
            "ingested_at": datetime.now().isoformat(),
            "total_campaigns": len(campaigns),
            "newly_processed": len(processed),
            "skipped_existing": skipped,
            "campaigns": processed
        }
        
        summary_file = KNOWLEDGE_DIR / "campaigns" / "_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        
        self._log(f"Ingestion complete: {len(processed)} new, {skipped} skipped")
        
        # Calculate and save baseline metrics
        self._calculate_baselines(processed)
        
        return {
            "success": True,
            "newly_processed": len(processed),
            "skipped": skipped,
            "summary_file": str(summary_file)
        }
    
    def _calculate_baselines(self, campaigns: List[Dict]):
        """Calculate baseline metrics from ingested campaigns."""
        if not campaigns:
            return
        
        # Aggregate metrics
        total_sent = sum(c["metrics"]["emails_sent"] for c in campaigns)
        total_opens = sum(c["metrics"]["opens"] for c in campaigns)
        total_replies = sum(c["metrics"]["replies"] for c in campaigns)
        total_meetings = sum(c["metrics"]["meetings_booked"] for c in campaigns)
        
        # Calculate averages
        baselines = {
            "calculated_at": datetime.now().isoformat(),
            "campaigns_analyzed": len(campaigns),
            "overall": {
                "total_emails_sent": total_sent,
                "average_open_rate": round(total_opens / total_sent, 4) if total_sent > 0 else 0,
                "average_reply_rate": round(total_replies / total_sent, 4) if total_sent > 0 else 0,
                "meeting_rate": round(total_meetings / total_sent, 4) if total_sent > 0 else 0
            },
            "by_segment": {}
        }
        
        # Calculate by segment
        segments = {}
        for c in campaigns:
            seg = c["segment"]
            if seg not in segments:
                segments[seg] = {"sent": 0, "opens": 0, "replies": 0, "meetings": 0, "count": 0}
            segments[seg]["sent"] += c["metrics"]["emails_sent"]
            segments[seg]["opens"] += c["metrics"]["opens"]
            segments[seg]["replies"] += c["metrics"]["replies"]
            segments[seg]["meetings"] += c["metrics"]["meetings_booked"]
            segments[seg]["count"] += 1
        
        for seg, data in segments.items():
            baselines["by_segment"][seg] = {
                "campaigns": data["count"],
                "emails_sent": data["sent"],
                "open_rate": round(data["opens"] / data["sent"], 4) if data["sent"] > 0 else 0,
                "reply_rate": round(data["replies"] / data["sent"], 4) if data["sent"] > 0 else 0,
                "meeting_rate": round(data["meetings"] / data["sent"], 4) if data["sent"] > 0 else 0
            }
        
        # Save baselines
        baselines_file = KNOWLEDGE_DIR / "campaigns" / "_baselines.json"
        with open(baselines_file, "w", encoding="utf-8") as f:
            json.dump(baselines, f, indent=2)
        
        self._log(f"Baseline metrics saved to {baselines_file}")


def main():
    parser = argparse.ArgumentParser(description="Ingest Instantly campaign data")
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Number of days to look back"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without saving"
    )
    
    args = parser.parse_args()
    
    if not INSTANTLY_API_KEY:
        print("❌ INSTANTLY_API_KEY not set in .env")
        sys.exit(1)
    
    ingestion = InstantlyIngestion()
    
    if args.dry_run:
        campaigns = ingestion.get_campaigns()
        print(f"Would ingest {len(campaigns)} campaigns")
        for c in campaigns[:5]:
            print(f"  - {c.get('name', 'Unknown')}")
        if len(campaigns) > 5:
            print(f"  ... and {len(campaigns) - 5} more")
    else:
        result = ingestion.ingest_all(days_back=args.days)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
