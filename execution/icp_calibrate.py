"""
ICP Calibration Tool
Calibrates ICP scoring based on AE validation feedback and historical deal outcomes.
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / ".hive-mind" / "knowledge"
HIVE_MIND = PROJECT_ROOT / ".hive-mind"

# Load environment variables
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")


class ICPCalibrator:
    """
    Calibrates ICP scoring weights based on:
    1. Historical deal outcomes (won vs lost)
    2. AE validation feedback
    3. Campaign performance by segment
    """
    
    def __init__(self):
        self.validation_file = KNOWLEDGE_DIR / "deals" / "_icp_validation.json"
        self.calibration_file = HIVE_MIND / "icp_calibration.json"
        self.current_weights = self._load_current_weights()
        
    def _load_current_weights(self) -> Dict:
        """Load current ICP scoring weights."""
        default_weights = {
            "version": "1.0",
            "updated_at": datetime.now().isoformat(),
            "company_size": {
                "weight": 20,
                "ranges": {
                    "1-20": -10,
                    "21-50": 10,
                    "51-200": 20,
                    "201-500": 20,
                    "501+": 5
                }
            },
            "title": {
                "weight": 25,
                "patterns": {
                    "c_level": 25,
                    "vp_level": 25,
                    "director": 15,
                    "manager": 5,
                    "other": 0
                }
            },
            "industry": {
                "weight": 20,
                "patterns": {
                    "saas": 20,
                    "technology": 15,
                    "professional_services": 10,
                    "other": 0
                }
            },
            "engagement": {
                "weight": 15,
                "factors": {
                    "competitor_follower": 15,
                    "event_attendee": 12,
                    "post_commenter": 10,
                    "group_member": 8,
                    "website_visitor": 10,
                    "passive_follower": 5
                }
            },
            "intent_signals": {
                "weight": 20,
                "factors": {
                    "hiring_revops": 20,
                    "recent_funding": 15,
                    "new_leadership": 10,
                    "competitor_usage": 15,
                    "tech_adoption": 10
                }
            }
        }
        
        if self.calibration_file.exists():
            try:
                with open(self.calibration_file) as f:
                    return json.load(f)
            except:
                pass
        
        return default_weights
    
    def load_validation_data(self) -> Optional[Dict]:
        """Load ICP validation data from deal ingestion."""
        if not self.validation_file.exists():
            print("❌ No validation data found. Run ingest_ghl_deals.py first.")
            return None
        
        with open(self.validation_file) as f:
            return json.load(f)
    
    def analyze_feedback(self, feedback_file: Path) -> Dict:
        """
        Analyze AE feedback for calibration.
        
        Expected feedback format:
        {
            "leads": [
                {
                    "lead_id": "...",
                    "system_tier": "tier1",
                    "ae_tier": "tier2",
                    "reason": "Company too small",
                    "override_direction": "downgrade"
                }
            ]
        }
        """
        if not feedback_file.exists():
            return {"overrides": [], "patterns": {}}
        
        with open(feedback_file) as f:
            feedback = json.load(f)
        
        overrides = feedback.get("leads", [])
        
        # Analyze override patterns
        patterns = {
            "total_overrides": len(overrides),
            "upgrades": 0,
            "downgrades": 0,
            "reasons": {}
        }
        
        for override in overrides:
            direction = override.get("override_direction", "")
            reason = override.get("reason", "Other")
            
            if direction == "upgrade":
                patterns["upgrades"] += 1
            elif direction == "downgrade":
                patterns["downgrades"] += 1
            
            patterns["reasons"][reason] = patterns["reasons"].get(reason, 0) + 1
        
        return patterns
    
    def calibrate_from_deals(self, validation_data: Dict) -> Dict[str, Any]:
        """Calibrate scoring based on deal outcomes."""
        adjustments = {
            "timestamp": datetime.now().isoformat(),
            "changes": [],
            "new_weights": self.current_weights.copy()
        }
        
        # Analyze ICP score distribution
        won_analysis = validation_data.get("icp_score_analysis", {}).get("won", {})
        lost_analysis = validation_data.get("icp_score_analysis", {}).get("lost", {})
        
        won_avg = won_analysis.get("average", 50)
        lost_avg = lost_analysis.get("average", 50)
        
        score_gap = won_avg - lost_avg
        
        if score_gap < 5:
            adjustments["changes"].append({
                "type": "scoring_gap",
                "issue": f"Won/Lost score gap too small ({score_gap:.1f} points)",
                "recommendation": "Increase weight on differentiating factors"
            })
        
        # Analyze company size patterns
        won_sizes = validation_data.get("company_size_analysis", {}).get("won", {}).get("distribution", {})
        lost_sizes = validation_data.get("company_size_analysis", {}).get("lost", {}).get("distribution", {})
        
        # Find sweet spot
        best_size_range = None
        best_ratio = 0
        
        for size_range in ["1-20", "21-50", "51-200", "201-500", "500+"]:
            won = won_sizes.get(size_range, 0)
            lost = lost_sizes.get(size_range, 0)
            
            if won + lost > 0:
                ratio = won / (won + lost)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_size_range = size_range
        
        if best_size_range:
            adjustments["changes"].append({
                "type": "company_size",
                "insight": f"Best converting size range: {best_size_range} ({best_ratio*100:.1f}% win rate)",
                "recommendation": f"Increase weight for {best_size_range} range"
            })
            
            # Apply adjustment
            if best_size_range in adjustments["new_weights"]["company_size"]["ranges"]:
                current = adjustments["new_weights"]["company_size"]["ranges"][best_size_range]
                adjustments["new_weights"]["company_size"]["ranges"][best_size_range] = min(25, current + 5)
        
        # Analyze title patterns
        won_titles = validation_data.get("title_analysis", {}).get("won", {})
        lost_titles = validation_data.get("title_analysis", {}).get("lost", {})
        
        for title_level in ["VP Level", "Director Level", "Manager Level", "C-Level"]:
            won = won_titles.get(title_level, 0)
            lost = lost_titles.get(title_level, 0)
            
            if won > lost * 1.5:  # Significant win bias
                adjustments["changes"].append({
                    "type": "title",
                    "insight": f"{title_level} converts well ({won} won vs {lost} lost)",
                    "recommendation": f"Maintain or increase weight for {title_level}"
                })
        
        return adjustments
    
    def generate_ae_validation_template(self, output_file: Path, num_leads: int = 50):
        """
        Generate a template for AE validation of random leads.
        AE fills this out and we use it for calibration.
        """
        template = {
            "generated_at": datetime.now().isoformat(),
            "instructions": """
AE Validation Instructions:
1. Review each lead below
2. For each lead, confirm or override the system tier
3. If overriding, specify the correct tier and reason
4. Save this file and run: python execution/icp_calibrate.py --feedback <this_file>
            """,
            "tier_definitions": {
                "tier1_vip": "Score 85-100: Personalized 1:1, AE direct",
                "tier2_high": "Score 70-84: Personalized sequence",
                "tier3_standard": "Score 50-69: Semi-personalized batch",
                "tier4_nurture": "Score 30-49: Nurture sequence",
                "dq": "Score 0-29: Do not contact"
            },
            "leads": []
        }
        
        # Try to load recent segmented leads
        segmented_dir = HIVE_MIND / "segmented"
        leads_to_validate = []
        
        if segmented_dir.exists():
            for f in sorted(segmented_dir.glob("*.json"), reverse=True)[:5]:
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                        if isinstance(data, list):
                            leads_to_validate.extend(data[:10])
                except:
                    pass
        
        # Create validation entries
        for i, lead in enumerate(leads_to_validate[:num_leads]):
            template["leads"].append({
                "lead_id": lead.get("id", f"lead_{i}"),
                "name": lead.get("name", "Unknown"),
                "company": lead.get("company", "Unknown"),
                "title": lead.get("title", "Unknown"),
                "system_score": lead.get("icp_score", 0),
                "system_tier": lead.get("icp_tier", "unknown"),
                "ae_agrees": True,  # AE changes to False if disagreeing
                "ae_tier": "",  # AE fills if disagreeing
                "reason": "",  # AE explains override
                "override_direction": ""  # "upgrade" or "downgrade"
            })
        
        # If no leads, create empty template
        if not template["leads"]:
            template["leads"] = [
                {
                    "lead_id": "example_1",
                    "name": "John Doe",
                    "company": "Example Corp",
                    "title": "VP of Sales",
                    "system_score": 82,
                    "system_tier": "tier2_high",
                    "ae_agrees": True,
                    "ae_tier": "",
                    "reason": "",
                    "override_direction": ""
                }
            ]
        
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2)
        
        print(f"✓ AE validation template created: {output_file}")
        print(f"  Contains {len(template['leads'])} leads for review")
        return template
    
    def apply_calibration(self, adjustments: Dict):
        """Apply calibration adjustments to scoring weights."""
        new_weights = adjustments.get("new_weights", self.current_weights)
        new_weights["version"] = str(float(new_weights.get("version", "1.0")) + 0.1)
        new_weights["updated_at"] = datetime.now().isoformat()
        new_weights["last_calibration"] = adjustments
        
        with open(self.calibration_file, "w", encoding="utf-8") as f:
            json.dump(new_weights, f, indent=2)
        
        print(f"✓ Calibration applied. New weights saved to: {self.calibration_file}")
        print(f"  Version: {new_weights['version']}")
        print(f"  Changes made: {len(adjustments.get('changes', []))}")
        
        return new_weights
    
    def run_full_calibration(self, feedback_file: Optional[Path] = None) -> Dict:
        """Run full calibration process."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "steps_completed": [],
            "adjustments": None,
            "new_weights": None
        }
        
        # Step 1: Load deal validation data
        validation_data = self.load_validation_data()
        if validation_data:
            results["steps_completed"].append("deal_validation_loaded")
            
            # Step 2: Calibrate from deals
            adjustments = self.calibrate_from_deals(validation_data)
            results["adjustments"] = adjustments
            results["steps_completed"].append("deal_calibration_complete")
        
        # Step 3: Process AE feedback if provided
        if feedback_file and feedback_file.exists():
            feedback_patterns = self.analyze_feedback(feedback_file)
            results["feedback_patterns"] = feedback_patterns
            results["steps_completed"].append("ae_feedback_processed")
            
            # Incorporate feedback into adjustments
            if results.get("adjustments"):
                results["adjustments"]["feedback_summary"] = feedback_patterns
        
        # Step 4: Apply calibration
        if results.get("adjustments"):
            new_weights = self.apply_calibration(results["adjustments"])
            results["new_weights"] = new_weights
            results["steps_completed"].append("calibration_applied")
        
        return results


def main():
    parser = argparse.ArgumentParser(description="ICP Calibration Tool")
    parser.add_argument(
        "--generate-template",
        action="store_true",
        help="Generate AE validation template"
    )
    parser.add_argument(
        "--template-output",
        type=str,
        default=".tmp/ae_validation_template.json",
        help="Output path for validation template"
    )
    parser.add_argument(
        "--num-leads",
        type=int,
        default=50,
        help="Number of leads for AE validation"
    )
    parser.add_argument(
        "--feedback",
        type=str,
        help="Path to completed AE feedback file"
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Run full calibration"
    )
    parser.add_argument(
        "--show-weights",
        action="store_true",
        help="Show current ICP weights"
    )
    
    args = parser.parse_args()
    
    calibrator = ICPCalibrator()
    
    if args.show_weights:
        print(json.dumps(calibrator.current_weights, indent=2))
        return
    
    if args.generate_template:
        output = PROJECT_ROOT / args.template_output
        calibrator.generate_ae_validation_template(output, args.num_leads)
        return
    
    if args.calibrate:
        feedback_file = Path(args.feedback) if args.feedback else None
        results = calibrator.run_full_calibration(feedback_file)
        print(json.dumps(results, indent=2, default=str))
        return
    
    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()
