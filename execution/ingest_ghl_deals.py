"""
GoHighLevel Deals Ingestion
Imports won/lost deals for ICP validation and RL training.
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

GHL_API_KEY = os.getenv("GHL_API_KEY")
GHL_LOCATION_ID = os.getenv("GHL_LOCATION_ID")
GHL_BASE_URL = os.getenv("GHL_BASE_URL", "https://rest.gohighlevel.com")


class GHLDealsIngestion:
    """Ingest deal data from GoHighLevel for ICP validation."""
    
    def __init__(self):
        self.api_key = GHL_API_KEY
        self.location_id = GHL_LOCATION_ID
        self.base_url = GHL_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
        self.rate_limit_delay = 0.5
        self.log_file = LOG_DIR / f"ingest_ghl_deals_{datetime.now().strftime('%Y-%m-%d')}.log"
        
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
        
        try:
            time.sleep(self.rate_limit_delay)
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 429:
                self._log("Rate limited, waiting 60 seconds...")
                time.sleep(60)
                return self._make_request(endpoint, params)
            
            if response.status_code == 401:
                self._log("Authentication failed - check GHL_API_KEY")
                return None
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self._log(f"API Error: {e}")
            return None
    
    def get_pipelines(self) -> List[Dict]:
        """Get all pipelines for the location."""
        self._log("Fetching pipelines...")
        
        result = self._make_request(f"v1/pipelines", {
            "locationId": self.location_id
        })
        
        if not result:
            return []
        
        pipelines = result.get("pipelines", [])
        self._log(f"Found {len(pipelines)} pipelines")
        return pipelines
    
    def get_opportunities(self, pipeline_id: str, status: Optional[str] = None) -> List[Dict]:
        """Get opportunities (deals) from a pipeline."""
        params = {
            "locationId": self.location_id,
            "pipelineId": pipeline_id,
            "limit": 100
        }
        
        if status:
            params["status"] = status
        
        all_opportunities = []
        
        # Paginate through results
        while True:
            result = self._make_request("v1/opportunities/search", params)
            
            if not result:
                break
            
            opportunities = result.get("opportunities", [])
            all_opportunities.extend(opportunities)
            
            # Check for more pages
            if len(opportunities) < 100:
                break
            
            params["startAfterId"] = opportunities[-1].get("id", "")
        
        return all_opportunities
    
    def get_contact(self, contact_id: str) -> Optional[Dict]:
        """Get contact details."""
        result = self._make_request(f"v1/contacts/{contact_id}")
        return result.get("contact") if result else None
    
    def process_opportunity(self, opportunity: Dict) -> Dict:
        """Process an opportunity into our deal schema."""
        opp_id = opportunity.get("id", "")
        status = opportunity.get("status", "").lower()
        
        # Determine win/loss
        if status in ["won", "closed won", "customer"]:
            deal_status = "won"
        elif status in ["lost", "closed lost", "dead"]:
            deal_status = "lost"
        else:
            deal_status = "open"
        
        # Get contact details
        contact_id = opportunity.get("contactId", "")
        contact = None
        if contact_id:
            contact = self.get_contact(contact_id)
        
        # Extract company info
        company_name = ""
        company_size = 0
        title = ""
        industry = ""
        
        if contact:
            company_name = contact.get("companyName", "")
            title = contact.get("title", contact.get("jobTitle", ""))
            
            # Check custom fields for company size and industry
            custom_fields = contact.get("customFields", [])
            for field in custom_fields:
                field_key = field.get("key", "").lower()
                field_value = field.get("value", "")
                
                if "size" in field_key or "employees" in field_key:
                    try:
                        company_size = int(field_value.replace(",", "").split("-")[0])
                    except:
                        pass
                
                if "industry" in field_key:
                    industry = field_value
        
        # Calculate days to close
        created_at = opportunity.get("createdAt", "")
        closed_at = opportunity.get("updatedAt", "")  # Use updated as proxy for close date
        
        days_to_close = 0
        if created_at and closed_at and deal_status in ["won", "lost"]:
            try:
                created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                closed = datetime.fromisoformat(closed_at.replace("Z", "+00:00"))
                days_to_close = (closed - created).days
            except:
                pass
        
        # Estimate ICP score based on what we know
        icp_score = self._estimate_icp_score(company_size, title, industry)
        
        return {
            "deal_id": opp_id,
            "name": opportunity.get("name", ""),
            "status": deal_status,
            "value": opportunity.get("monetaryValue", 0),
            "pipeline_id": opportunity.get("pipelineId", ""),
            "stage_name": opportunity.get("pipelineStageName", ""),
            "source": opportunity.get("source", "unknown"),
            "days_to_close": days_to_close,
            "icp_score_estimate": icp_score,
            "contact": {
                "id": contact_id,
                "name": contact.get("name", "") if contact else "",
                "title": title,
                "company": company_name,
                "company_size": company_size,
                "industry": industry
            },
            "created_at": created_at,
            "tags": opportunity.get("tags", []),
            "loss_reason": opportunity.get("lostReasonId", ""),
            "ingested_at": datetime.now().isoformat()
        }
    
    def _estimate_icp_score(self, company_size: int, title: str, industry: str) -> int:
        """Estimate ICP score based on available data."""
        score = 50  # Base score
        
        # Company size scoring
        if 51 <= company_size <= 500:
            score += 20
        elif 20 <= company_size <= 50:
            score += 10
        elif company_size > 500:
            score += 5
        elif company_size > 0:
            score -= 10
        
        # Title scoring
        title_lower = title.lower()
        if any(x in title_lower for x in ["vp", "vice president", "cro", "chief revenue"]):
            score += 25
        elif any(x in title_lower for x in ["director", "head of"]):
            score += 15
        elif any(x in title_lower for x in ["manager", "lead"]):
            score += 5
        
        # Industry scoring
        industry_lower = industry.lower()
        if any(x in industry_lower for x in ["saas", "software", "technology"]):
            score += 15
        elif any(x in industry_lower for x in ["professional services", "consulting"]):
            score += 10
        
        return min(100, max(0, score))
    
    def ingest_all(self, days_back: int = 180) -> Dict[str, Any]:
        """Run full ingestion of deal data."""
        self._log(f"Starting GHL deals ingestion (last {days_back} days)")
        
        pipelines = self.get_pipelines()
        
        if not pipelines:
            self._log("No pipelines found")
            return {"success": False, "error": "No pipelines found"}
        
        all_deals = []
        won_deals = []
        lost_deals = []
        
        for pipeline in pipelines:
            pipeline_id = pipeline.get("id", "")
            pipeline_name = pipeline.get("name", "Unknown")
            
            self._log(f"Processing pipeline: {pipeline_name}")
            
            opportunities = self.get_opportunities(pipeline_id)
            self._log(f"Found {len(opportunities)} opportunities")
            
            for opp in opportunities:
                try:
                    deal = self.process_opportunity(opp)
                    all_deals.append(deal)
                    
                    if deal["status"] == "won":
                        won_deals.append(deal)
                    elif deal["status"] == "lost":
                        lost_deals.append(deal)
                    
                    # Save individual deal
                    output_file = KNOWLEDGE_DIR / "deals" / f"{deal['deal_id']}.json"
                    with open(output_file, "w", encoding="utf-8") as f:
                        json.dump(deal, f, indent=2)
                    
                except Exception as e:
                    self._log(f"Error processing opportunity: {e}")
        
        # Calculate ICP validation data
        icp_validation = self._calculate_icp_validation(won_deals, lost_deals)
        
        # Save ICP validation
        validation_file = KNOWLEDGE_DIR / "deals" / "_icp_validation.json"
        with open(validation_file, "w", encoding="utf-8") as f:
            json.dump(icp_validation, f, indent=2)
        
        # Save summary
        summary = {
            "ingested_at": datetime.now().isoformat(),
            "total_deals": len(all_deals),
            "won_deals": len(won_deals),
            "lost_deals": len(lost_deals),
            "open_deals": len(all_deals) - len(won_deals) - len(lost_deals),
            "icp_validation_file": str(validation_file)
        }
        
        summary_file = KNOWLEDGE_DIR / "deals" / "_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        
        self._log(f"Ingestion complete: {len(won_deals)} won, {len(lost_deals)} lost")
        
        return {
            "success": True,
            "total_deals": len(all_deals),
            "won_deals": len(won_deals),
            "lost_deals": len(lost_deals),
            "summary_file": str(summary_file),
            "icp_validation_file": str(validation_file)
        }
    
    def _calculate_icp_validation(self, won_deals: List[Dict], lost_deals: List[Dict]) -> Dict:
        """Calculate ICP validation metrics from won/lost deals."""
        validation = {
            "calculated_at": datetime.now().isoformat(),
            "sample_size": {
                "won": len(won_deals),
                "lost": len(lost_deals)
            },
            "icp_score_analysis": {
                "won": {},
                "lost": {}
            },
            "company_size_analysis": {
                "won": {},
                "lost": {}
            },
            "title_analysis": {
                "won": {},
                "lost": {}
            },
            "recommendations": []
        }
        
        # Analyze ICP scores
        for deal_type, deals in [("won", won_deals), ("lost", lost_deals)]:
            scores = [d.get("icp_score_estimate", 0) for d in deals]
            if scores:
                validation["icp_score_analysis"][deal_type] = {
                    "average": round(sum(scores) / len(scores), 1),
                    "min": min(scores),
                    "max": max(scores),
                    "distribution": {
                        "0-30": len([s for s in scores if s <= 30]),
                        "31-50": len([s for s in scores if 31 <= s <= 50]),
                        "51-70": len([s for s in scores if 51 <= s <= 70]),
                        "71-100": len([s for s in scores if s >= 71])
                    }
                }
        
        # Analyze company sizes
        for deal_type, deals in [("won", won_deals), ("lost", lost_deals)]:
            sizes = [d.get("contact", {}).get("company_size", 0) for d in deals if d.get("contact", {}).get("company_size", 0) > 0]
            if sizes:
                validation["company_size_analysis"][deal_type] = {
                    "average": round(sum(sizes) / len(sizes)),
                    "distribution": {
                        "1-20": len([s for s in sizes if s <= 20]),
                        "21-50": len([s for s in sizes if 21 <= s <= 50]),
                        "51-200": len([s for s in sizes if 51 <= s <= 200]),
                        "201-500": len([s for s in sizes if 201 <= s <= 500]),
                        "500+": len([s for s in sizes if s > 500])
                    }
                }
        
        # Analyze titles
        for deal_type, deals in [("won", won_deals), ("lost", lost_deals)]:
            titles = {}
            for d in deals:
                title = d.get("contact", {}).get("title", "").lower()
                if "vp" in title or "vice president" in title:
                    key = "VP Level"
                elif "director" in title:
                    key = "Director Level"
                elif "manager" in title:
                    key = "Manager Level"
                elif "c-" in title or "chief" in title:
                    key = "C-Level"
                else:
                    key = "Other"
                titles[key] = titles.get(key, 0) + 1
            validation["title_analysis"][deal_type] = titles
        
        # Generate recommendations
        won_avg_score = validation["icp_score_analysis"].get("won", {}).get("average", 0)
        lost_avg_score = validation["icp_score_analysis"].get("lost", {}).get("average", 0)
        
        if won_avg_score > lost_avg_score + 10:
            validation["recommendations"].append({
                "type": "icp_scoring",
                "insight": f"ICP scoring is predictive (won avg: {won_avg_score}, lost avg: {lost_avg_score})",
                "action": "Current scoring weights are effective"
            })
        else:
            validation["recommendations"].append({
                "type": "icp_scoring",
                "insight": f"ICP scoring needs calibration (won avg: {won_avg_score}, lost avg: {lost_avg_score})",
                "action": "Review and adjust scoring weights"
            })
        
        return validation


def main():
    parser = argparse.ArgumentParser(description="Ingest GHL deal data")
    parser.add_argument(
        "--days",
        type=int,
        default=180,
        help="Number of days to look back"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without saving"
    )
    
    args = parser.parse_args()
    
    if not GHL_API_KEY or not GHL_LOCATION_ID:
        print("❌ GHL_API_KEY and GHL_LOCATION_ID must be set in .env")
        sys.exit(1)
    
    ingestion = GHLDealsIngestion()
    
    if args.dry_run:
        pipelines = ingestion.get_pipelines()
        print(f"Would ingest from {len(pipelines)} pipelines:")
        for p in pipelines:
            print(f"  - {p.get('name', 'Unknown')}")
    else:
        result = ingestion.ingest_all(days_back=args.days)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
