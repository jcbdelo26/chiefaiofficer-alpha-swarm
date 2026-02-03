"""
Instantly Email Templates Ingestion
Imports successful email templates for voice training and CRAFTER improvement.
"""

import os
import sys
import json
import time
import argparse
import requests
from datetime import datetime
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


class TemplateIngestion:
    """Ingest email templates from Instantly for voice training."""
    
    def __init__(self):
        self.api_key = INSTANTLY_API_KEY
        self.base_url = INSTANTLY_BASE_URL
        self.session = requests.Session()
        self.rate_limit_delay = 1.0
        self.log_file = LOG_DIR / f"ingest_templates_{datetime.now().strftime('%Y-%m-%d')}.log"
        
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
                self._log("Rate limited, waiting 60 seconds...")
                time.sleep(60)
                return self._make_request(endpoint, params)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self._log(f"API Error: {e}")
            return None
    
    def get_campaigns_with_sequences(self) -> List[Dict]:
        """Get campaigns with their email sequences."""
        self._log("Fetching campaigns with sequences...")
        
        campaigns_result = self._make_request("campaign/list")
        
        if not campaigns_result:
            return []
        
        campaigns = campaigns_result if isinstance(campaigns_result, list) else campaigns_result.get("campaigns", [])
        
        campaigns_with_sequences = []
        
        for campaign in campaigns:
            campaign_id = campaign.get("id", "")
            
            # Get campaign details including sequences
            details = self._make_request("campaign/get", {"campaign_id": campaign_id})
            
            if details:
                campaigns_with_sequences.append({
                    "campaign_id": campaign_id,
                    "name": campaign.get("name", "Unknown"),
                    "status": campaign.get("status", "unknown"),
                    "sequences": details.get("sequences", []),
                    "subject_lines": self._extract_subjects(details.get("sequences", []))
                })
        
        self._log(f"Retrieved {len(campaigns_with_sequences)} campaigns with sequences")
        return campaigns_with_sequences
    
    def _extract_subjects(self, sequences: List[Dict]) -> List[str]:
        """Extract subject lines from sequences."""
        subjects = []
        for seq in sequences:
            if isinstance(seq, dict):
                subject = seq.get("subject", "")
                if subject:
                    subjects.append(subject)
            elif isinstance(seq, list):
                for step in seq:
                    if isinstance(step, dict):
                        subject = step.get("subject", "")
                        if subject:
                            subjects.append(subject)
        return subjects
    
    def analyze_template_performance(self, campaign: Dict, analytics: Dict) -> Dict:
        """Analyze template performance based on campaign metrics."""
        emails_sent = analytics.get("emails_sent", 0)
        open_rate = analytics.get("opens", 0) / emails_sent if emails_sent > 0 else 0
        reply_rate = analytics.get("replies", 0) / emails_sent if emails_sent > 0 else 0
        
        # Score the template (simple heuristic)
        # Weight: 40% open rate, 60% reply rate
        performance_score = (open_rate * 0.4) + (reply_rate * 0.6) * 10  # Scale reply rate
        
        # Categorize
        if performance_score > 0.5:
            category = "high_performer"
        elif performance_score > 0.3:
            category = "good"
        elif performance_score > 0.15:
            category = "average"
        else:
            category = "low_performer"
        
        return {
            "performance_score": round(performance_score, 4),
            "category": category,
            "open_rate": round(open_rate, 4),
            "reply_rate": round(reply_rate, 4),
            "sample_size": emails_sent
        }
    
    def extract_voice_patterns(self, templates: List[Dict]) -> Dict:
        """Extract voice patterns from high-performing templates."""
        patterns = {
            "extracted_at": datetime.now().isoformat(),
            "templates_analyzed": 0,
            "subject_line_patterns": [],
            "opening_patterns": [],
            "cta_patterns": [],
            "tone_indicators": [],
            "high_performers": []
        }
        
        for template in templates:
            if template.get("performance", {}).get("category") in ["high_performer", "good"]:
                patterns["templates_analyzed"] += 1
                patterns["high_performers"].append({
                    "campaign_name": template.get("campaign_name", ""),
                    "subjects": template.get("subject_lines", []),
                    "performance": template.get("performance", {}),
                    "sequences": template.get("sequences", [])
                })
                
                # Extract patterns from subjects
                for subject in template.get("subject_lines", []):
                    patterns["subject_line_patterns"].append({
                        "subject": subject,
                        "length": len(subject),
                        "has_personalization": any(x in subject.lower() for x in ["{{", "{first", "{company"]),
                        "has_question": "?" in subject,
                        "has_number": any(c.isdigit() for c in subject)
                    })
        
        return patterns
    
    def ingest_all(self, min_open_rate: float = 0.4) -> Dict[str, Any]:
        """Run full ingestion of email templates."""
        self._log(f"Starting template ingestion (min open rate: {min_open_rate})")
        
        campaigns = self.get_campaigns_with_sequences()
        
        if not campaigns:
            return {"success": False, "error": "No campaigns found"}
        
        processed_templates = []
        
        for campaign in campaigns:
            campaign_id = campaign.get("campaign_id", "")
            
            # Get analytics for performance scoring
            analytics = self._make_request("analytics/campaign/summary", {
                "campaign_id": campaign_id
            })
            
            if not analytics:
                analytics = {}
            
            performance = self.analyze_template_performance(campaign, analytics)
            
            # Only include templates meeting minimum criteria
            if performance.get("open_rate", 0) >= min_open_rate:
                template_data = {
                    "campaign_id": campaign_id,
                    "campaign_name": campaign.get("name", ""),
                    "sequences": campaign.get("sequences", []),
                    "subject_lines": campaign.get("subject_lines", []),
                    "performance": performance,
                    "ingested_at": datetime.now().isoformat()
                }
                processed_templates.append(template_data)
                
                # Save individual template
                output_file = KNOWLEDGE_DIR / "templates" / f"{campaign_id}.json"
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(template_data, f, indent=2)
        
        self._log(f"Found {len(processed_templates)} high-performing templates")
        
        # Extract voice patterns
        voice_patterns = self.extract_voice_patterns(processed_templates)
        
        # Save voice patterns
        patterns_file = KNOWLEDGE_DIR / "voice_samples" / "voice_patterns.json"
        patterns_file.parent.mkdir(parents=True, exist_ok=True)
        with open(patterns_file, "w", encoding="utf-8") as f:
            json.dump(voice_patterns, f, indent=2)
        
        # Save summary
        summary = {
            "ingested_at": datetime.now().isoformat(),
            "total_campaigns": len(campaigns),
            "qualifying_templates": len(processed_templates),
            "min_open_rate_filter": min_open_rate,
            "voice_patterns_file": str(patterns_file)
        }
        
        summary_file = KNOWLEDGE_DIR / "templates" / "_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        
        self._log(f"Ingestion complete. Voice patterns saved to {patterns_file}")
        
        return {
            "success": True,
            "templates_imported": len(processed_templates),
            "voice_patterns_extracted": voice_patterns["templates_analyzed"],
            "summary_file": str(summary_file)
        }


def main():
    parser = argparse.ArgumentParser(description="Ingest Instantly email templates")
    parser.add_argument(
        "--min-open-rate",
        type=float,
        default=0.4,
        help="Minimum open rate to qualify as high-performing (0.0-1.0)"
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
    
    ingestion = TemplateIngestion()
    
    if args.dry_run:
        campaigns = ingestion.get_campaigns_with_sequences()
        print(f"Would analyze {len(campaigns)} campaigns for templates")
    else:
        result = ingestion.ingest_all(min_open_rate=args.min_open_rate)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
