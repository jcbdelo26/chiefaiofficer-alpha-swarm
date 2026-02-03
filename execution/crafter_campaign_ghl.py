#!/usr/bin/env python3
"""
CRAFTER Agent - GoHighLevel Email Campaign Creator
===================================================
Alternative to Instantly.ai - uses GoHighLevel for email campaigns.

This allows the Alpha Swarm to be production-ready without Instantly dependency.

Test Mode:
    --test-mode: Generate campaigns without making real API calls
    --input: Path to segmented leads JSON file
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import requests

from core.signal_detector import SignalDetector, DetectedSignal
from core.messaging_strategy import MessagingStrategy

load_dotenv()


class PersonalizationMetrics:
    """Track personalization quality metrics."""
    
    def __init__(self):
        self.total_fields = 0
        self.resolved_fields = 0
        self.unresolved_variables: List[Dict[str, Any]] = []
    
    def check_template(self, template: str, data: Dict[str, Any], context: str = "") -> Tuple[str, List[str]]:
        """
        Resolve template variables and track metrics.
        
        Returns:
            Tuple of (resolved_text, list_of_unresolved_variables)
        """
        pattern = r'\{(\w+)\}'
        variables = re.findall(pattern, template)
        unresolved = []
        
        self.total_fields += len(variables)
        
        result = template
        for var in variables:
            # Handle potential None values safely
            val = data.get(var)
            if val is not None:
                result = result.replace(f'{{{var}}}', str(val))
                self.resolved_fields += 1
            else:
                unresolved.append(var)
                self.unresolved_variables.append({
                    "variable": var,
                    "context": context,
                    "lead_email": data.get("email", "unknown")
                })
        
        return result, unresolved
    
    def get_personalization_rate(self) -> float:
        """Calculate personalization rate as percentage."""
        if self.total_fields == 0:
            return 100.0
        return (self.resolved_fields / self.total_fields) * 100
    
    def get_report(self) -> Dict[str, Any]:
        """Generate metrics report."""
        return {
            "total_fields": self.total_fields,
            "resolved_fields": self.resolved_fields,
            "personalization_rate": round(self.get_personalization_rate(), 2),
            "unresolved_variables": self.unresolved_variables,
            "hallucination_check": {
                "has_unresolved": len(self.unresolved_variables) > 0,
                "count": len(self.unresolved_variables)
            },
            "meets_day3_criteria": self.get_personalization_rate() >= 90.0
        }


class GHLCampaignCrafter:
    """Creates and sends email campaigns via GoHighLevel."""
    
    def __init__(self):
        """Initialize GHL campaign crafter."""
        self.api_key = os.getenv("GHL_API_KEY")
        self.location_id = os.getenv("GHL_LOCATION_ID")
        self.base_url = os.getenv("GHL_BASE_URL", "https://services.leadconnectorhq.com")
        
        self.signal_detector = SignalDetector()
        self.messaging_strategy = MessagingStrategy()
        
        if not self.api_key or not self.location_id:
            # Warn but allow init for testing imports
            print("Warning: Missing GHL_API_KEY or GHL_LOCATION_ID")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
    
    def create_contact(self, lead_data: Dict[str, Any]) -> Optional[str]:
        """
        Create or update contact in GHL.
        """
        url = f"{self.base_url}/contacts/"
        
        payload = {
            "locationId": self.location_id,
            "email": lead_data.get("email"),
            "firstName": lead_data.get("first_name", ""),
            "lastName": lead_data.get("last_name", ""),
            "name": lead_data.get("full_name", f"{lead_data.get('first_name', '')} {lead_data.get('last_name', '')}"),
            "companyName": lead_data.get("company", ""),
            "source": "Alpha Swarm - Lead Harvesting",
            "tags": ["alpha-swarm", "automated-outreach"],
            "customFields": [
                {"key": "linkedin_url", "value": lead_data.get("linkedin_url", "")},
                {"key": "title", "value": lead_data.get("title", "")},
                {"key": "industry", "value": lead_data.get("industry", "")},
            ]
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=10)
            
            if response.status_code in [200, 201]:
                data = response.json()
                contact_id = data.get("contact", {}).get("id")
                print(f"✅ Contact created/updated: {contact_id}")
                return contact_id
            else:
                print(f"❌ Failed to create contact: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Error creating contact: {e}")
            return None
    
    def send_email(
        self, 
        contact_id: str, 
        subject: str, 
        body: str,
        campaign_id: Optional[str] = None
    ) -> bool:
        """
        Send email to contact via GHL.
        """
        url = f"{self.base_url}/conversations/messages"
        
        payload = {
            "type": "Email",
            "contactId": contact_id,
            "locationId": self.location_id,
            "subject": subject,
            "html": body,
            "emailFrom": os.getenv("GHL_EMAIL_FROM", "outreach@chiefaiofficer.com"),
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=10)
            
            if response.status_code in [200, 201]:
                print(f"✅ Email sent to contact {contact_id}")
                
                # Log campaign event
                self._log_campaign_event(contact_id, campaign_id, "sent", {
                    "subject": subject,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                return True
            else:
                print(f"❌ Failed to send email: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error sending email: {e}")
            return False
    
    def create_campaign(
        self,
        leads: List[Dict[str, Any]],
        campaign_name: str
    ) -> Dict[str, Any]:
        """
        Create and execute email campaign for multiple leads.
        Uses SignalDetector and MessagingStrategy for dynamic content.
        """
        campaign_id = f"ghl-{campaign_name}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        skipped_dir = Path(__file__).parent.parent / ".hive-mind" / "skipped_leads"
        skipped_dir.mkdir(parents=True, exist_ok=True)
        
        results = {
            "campaign_id": campaign_id,
            "total_leads": len(leads),
            "contacts_created": 0,
            "emails_sent": 0,
            "failures": 0,
            "skipped": 0,
            "skipped_reasons": [],
            "started_at": datetime.utcnow().isoformat()
        }
        
        print(f"\n🚀 Starting campaign: {campaign_id}")
        print(f"📊 Total leads: {len(leads)}")
        
        skipped_leads = []
        
        for i, lead in enumerate(leads, 1):
            email = lead.get('email', 'unknown')
            print(f"\n[{i}/{len(leads)}] Processing: {email}")
            
            # Validation: Check critical fields
            critical_missing = []
            if not lead.get("email"): critical_missing.append("email")
            
            if critical_missing:
                reason = f"Missing critical fields: {', '.join(critical_missing)}"
                print(f"⚠️ SKIPPING: {reason}")
                results["skipped"] += 1
                skipped_leads.append({"email": email, "reason": reason})
                continue
            
            # 1. Detect Signals
            signals = self.signal_detector.detect_signals(lead)
            primary_signal = self.signal_detector.get_primary_signal(signals)
            
            print(f"   Signals Detected: {[s.type.value for s in signals]}")
            print(f"   Primary Strategy: {primary_signal.type.value} -> {primary_signal.value}")
            
            # 2. Select Template
            tmpl_id, subject_template, body_template = self.messaging_strategy.select_template(lead, primary_signal)
            print(f"   Selected Template: {tmpl_id}")
            
            # 3. Create/update contact
            contact_id = self.create_contact(lead)
            if not contact_id:
                results["failures"] += 1
                continue
            
            results["contacts_created"] += 1
            
            # 4. Personalize email
            try:
                # Basic fill plus any extra logic can go here
                subject = subject_template.format(**lead)
                body = body_template.format(**lead)
            except KeyError as e:
                # Catch variable resolution errors
                reason = f"Template variable missing: {e}"
                print(f"⚠️ SKIPPING: {reason}")
                results["skipped"] += 1
                skipped_leads.append({"email": email, "reason": reason})
                continue
            
            # 5. Send email
            if self.send_email(contact_id, subject, body, campaign_id):
                results["emails_sent"] += 1
            else:
                results["failures"] += 1
        
        # Save skipped leads
        if skipped_leads:
            skipped_file = skipped_dir / f"skipped_{campaign_id}.json"
            with open(skipped_file, 'w') as f:
                json.dump(skipped_leads, f, indent=2)
            print(f"⚠️ Skipped {len(skipped_leads)} leads (saved to {skipped_file})")

        results["completed_at"] = datetime.utcnow().isoformat()
        
        # Save campaign results
        self._save_campaign_results(results)
        
        print(f"\n✅ Campaign complete!")
        print(f"📧 Emails sent: {results['emails_sent']}/{results['total_leads']}")
        print(f"⚠️ Skipped: {results['skipped']}")
        
        return results
    
    def _log_campaign_event(
        self, 
        contact_id: str, 
        campaign_id: Optional[str], 
        event_type: str, 
        event_data: Dict[str, Any]
    ):
        """Log campaign event for tracking."""
        log_dir = Path(__file__).parent.parent / ".hive-mind"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "campaign_events.jsonl"
        
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "campaign_id": campaign_id,
            "contact_id": contact_id,
            "event_type": event_type,
            "event_data": event_data,
            "platform": "gohighlevel"
        }
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(event) + '\n')
    
    def _save_campaign_results(self, results: Dict[str, Any]):
        """Save campaign results."""
        results_dir = Path(__file__).parent.parent / ".hive-mind" / "campaigns"
        results_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{results['campaign_id']}.json"
        filepath = results_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"💾 Results saved: {filepath}")


class TestModeCrafter:
    """Test mode crafter - generates campaigns without real API calls."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.output_dir = self.project_root / ".hive-mind" / "testing" 
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metrics = PersonalizationMetrics()
        
        # New Components
        self.signal_detector = SignalDetector()
        self.messaging_strategy = MessagingStrategy()
    
    def _enrich_lead_data(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich lead data with derived fields for template resolution."""
        enriched = lead.copy()
        
        # Extract data from original_lead if present (from enricher output)
        original = lead.get("original_lead", {})
        if original:
            for key in ["first_name", "last_name", "title", "email", "industry", 
                        "tier", "hiring", "technologies"]:
                if key not in enriched or not enriched.get(key):
                    if key in original:
                        enriched[key] = original[key]
        
        # Derive full_name if missing
        if "full_name" not in enriched or not enriched.get("full_name"):
            enriched["full_name"] = f"{enriched.get('first_name', '')} {enriched.get('last_name', '')}".strip()
            
        return enriched
    
    def generate_campaigns(
        self,
        leads: List[Dict[str, Any]],
        campaign_name: str = "test-campaign"
    ) -> Dict[str, Any]:
        """
        Generate sample campaigns using SignalDetector + MessagingStrategy.
        """
        campaign_id = f"test-{campaign_name}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        
        results = {
            "campaign_id": campaign_id,
            "mode": "test",
            "total_leads": len(leads),
            "campaigns_generated": 0,
            "started_at": datetime.utcnow().isoformat(),
            "sample_campaigns": []
        }
        
        print(f"\n🧪 TEST MODE - Starting campaign generation: {campaign_id}")
        print(f"📊 Total leads: {len(leads)}")
        print("=" * 60)
        
        for i, lead in enumerate(leads, 1):
            tier = lead.get("tier", 3)
            enriched_lead = self._enrich_lead_data(lead)
            
            print(f"\n[{i}/{len(leads)}] Processing: {lead.get('email')} (Tier {tier})")
            
            # 1. Detect Signals
            signals = self.signal_detector.detect_signals(enriched_lead)
            primary_signal = self.signal_detector.get_primary_signal(signals)
            
            print(f"    Signals: {[s.type.value for s in signals]}")
            print(f"    Primary: {primary_signal.type.value} -> {primary_signal.value}")

            # 2. Select Template
            tmpl_id, subject_template, body_template = self.messaging_strategy.select_template(enriched_lead, primary_signal)
            print(f"    Template: {tmpl_id}")
            
            # 3. Check Personalization
            subject, subj_unresolved = self.metrics.check_template(
                subject_template, enriched_lead, f"subject-{lead.get('email')}"
            )
            body, body_unresolved = self.metrics.check_template(
                body_template, enriched_lead, f"body-{lead.get('email')}"
            )
            
            all_unresolved = subj_unresolved + body_unresolved
            if all_unresolved:
                print(f"    ⚠️ Unresolved variables: {all_unresolved}")
            else:
                print(f"    ✅ All variables resolved")
            
            campaign_entry = {
                "lead_id": lead.get("id", f"lead-{i}"),
                "email": lead.get("email"),
                "tier": tier,
                "signals": [s.type.value for s in signals],
                "template_used": tmpl_id,
                "subject": subject,
                "body": body,
                "unresolved_variables": all_unresolved,
                "personalization_complete": len(all_unresolved) == 0,
                "generated_at": datetime.utcnow().isoformat()
            }
            
            results["sample_campaigns"].append(campaign_entry)
            results["campaigns_generated"] += 1
        
        results["completed_at"] = datetime.utcnow().isoformat()
        results["metrics"] = self.metrics.get_report()
        
        self._save_sample_campaigns(results)
        self._print_summary(results)
        
        return results
    
    def _save_sample_campaigns(self, results: Dict[str, Any]):
        """Save sample campaigns to testing directory."""
        filepath = self.output_dir / "sample_campaigns.json"
        
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n💾 Sample campaigns saved: {filepath}")
    
    def _print_summary(self, results: Dict[str, Any]):
        """Print campaign generation summary."""
        metrics = results.get("metrics", {})
        rate = metrics.get("personalization_rate", 0)
        meets_criteria = metrics.get("meets_day3_criteria", False)
        
        print("\n" + "=" * 60)
        print("📊 PERSONALIZATION METRICS")
        print("=" * 60)
        print(f"Total template fields:    {metrics.get('total_fields', 0)}")
        print(f"Resolved fields:          {metrics.get('resolved_fields', 0)}")
        print(f"Personalization rate:     {rate}%")
        print(f"Unresolved variables:     {metrics.get('hallucination_check', {}).get('count', 0)}")
        print(f"Day 3 Criteria (≥90%):    {'✅ PASS' if meets_criteria else '❌ FAIL'}")
        print("=" * 60)


def load_leads_from_file(filepath: str) -> List[Dict[str, Any]]:
    """Load leads from a JSON file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {filepath}")
    
    with open(path, 'r') as f:
        data = json.load(f)
    
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        if "test_leads" in data:
            return data["test_leads"]
        elif "leads" in data:
            return data["leads"]
        elif "segmented_leads" in data:
            all_leads = []
            for tier_data in data["segmented_leads"].values():
                if isinstance(tier_data, list):
                    all_leads.extend(tier_data)
            return all_leads
    
    raise ValueError("Could not parse leads from input file")


def main():
    """Run GHL Campaign Crafter."""
    parser = argparse.ArgumentParser(
        description="CRAFTER Agent - GoHighLevel Email Campaign Creator"
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Generate campaigns without making real API calls"
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Path to segmented leads JSON file"
    )
    parser.add_argument(
        "--campaign-name",
        type=str,
        default="test-campaign",
        help="Campaign name identifier"
    )
    
    args = parser.parse_args()
    
    if args.test_mode:
        print("🧪 Running in TEST MODE - No real API calls will be made")
        
        crafter = TestModeCrafter()
        
        if args.input:
            leads = load_leads_from_file(args.input)
        else:
            default_input = Path(__file__).parent.parent / ".hive-mind" / "testing" / "test-leads.json"
            if default_input.exists():
                leads = load_leads_from_file(str(default_input))
                print(f"📂 Using default test leads: {default_input}")
            else:
                print("❌ No input file specified and no default test leads found")
                print("   Use --input to specify a leads file")
                sys.exit(1)
        
        results = crafter.generate_campaigns(
            leads=leads,
            campaign_name=args.campaign_name
        )
        
        if results["metrics"]["meets_day3_criteria"]:
            print("\n✅ Campaign generation successful - Ready for production!")
            sys.exit(0)
        else:
            print("\n⚠️ Personalization rate below 90% threshold")
            sys.exit(1)
    
    else:
        crafter = GHLCampaignCrafter()
        
         # In Real Mode, we'd load leads too, but let's just show test lead for now
        test_lead = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "full_name": "John Doe",
            "company": "Acme Corp",
            "title": "VP of Sales",
            "linkedin_url": "https://linkedin.com/in/johndoe",
            "industry": "Technology",
            "tier": 1,
            "hiring": "We are looking for an AI Engineer"
        }
        
        results = crafter.create_campaign(
            leads=[test_lead],
            campaign_name="test-campaign"
        )
        
        print(f"\n📊 Campaign Results:")
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
    """Track personalization quality metrics."""
    
    def __init__(self):
        self.total_fields = 0
        self.resolved_fields = 0
        self.unresolved_variables: List[Dict[str, Any]] = []
    
    def check_template(self, template: str, data: Dict[str, Any], context: str = "") -> Tuple[str, List[str]]:
        """
        Resolve template variables and track metrics.
        
        Returns:
            Tuple of (resolved_text, list_of_unresolved_variables)
        """
        pattern = r'\{(\w+)\}'
        variables = re.findall(pattern, template)
        unresolved = []
        
        self.total_fields += len(variables)
        
        result = template
        for var in variables:
            if var in data and data[var]:
                result = result.replace(f'{{{var}}}', str(data[var]))
                self.resolved_fields += 1
            else:
                unresolved.append(var)
                self.unresolved_variables.append({
                    "variable": var,
                    "context": context,
                    "lead_email": data.get("email", "unknown")
                })
        
        return result, unresolved
    
    def get_personalization_rate(self) -> float:
        """Calculate personalization rate as percentage."""
        if self.total_fields == 0:
            return 100.0
        return (self.resolved_fields / self.total_fields) * 100
    
    def get_report(self) -> Dict[str, Any]:
        """Generate metrics report."""
        return {
            "total_fields": self.total_fields,
            "resolved_fields": self.resolved_fields,
            "personalization_rate": round(self.get_personalization_rate(), 2),
            "unresolved_variables": self.unresolved_variables,
            "hallucination_check": {
                "has_unresolved": len(self.unresolved_variables) > 0,
                "count": len(self.unresolved_variables)
            },
            "meets_day3_criteria": self.get_personalization_rate() >= 90.0
        }


class GHLCampaignCrafter:
    """Creates and sends email campaigns via GoHighLevel."""
    
    def __init__(self):
        """Initialize GHL campaign crafter."""
        self.api_key = os.getenv("GHL_API_KEY")
        self.location_id = os.getenv("GHL_LOCATION_ID")
        self.base_url = os.getenv("GHL_BASE_URL", "https://services.leadconnectorhq.com")
        
        if not self.api_key or not self.location_id:
            raise ValueError("Missing GHL_API_KEY or GHL_LOCATION_ID")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
    
    def create_contact(self, lead_data: Dict[str, Any]) -> Optional[str]:
        """
        Create or update contact in GHL.
        
        Args:
            lead_data: Lead information (email, name, company, etc.)
        
        Returns:
            Contact ID if successful, None otherwise
        """
        url = f"{self.base_url}/contacts/"
        
        payload = {
            "locationId": self.location_id,
            "email": lead_data.get("email"),
            "firstName": lead_data.get("first_name", ""),
            "lastName": lead_data.get("last_name", ""),
            "name": lead_data.get("full_name", f"{lead_data.get('first_name', '')} {lead_data.get('last_name', '')}"),
            "companyName": lead_data.get("company", ""),
            "source": "Alpha Swarm - Lead Harvesting",
            "tags": ["alpha-swarm", "automated-outreach"],
            "customFields": [
                {"key": "linkedin_url", "value": lead_data.get("linkedin_url", "")},
                {"key": "title", "value": lead_data.get("title", "")},
                {"key": "industry", "value": lead_data.get("industry", "")},
            ]
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=10)
            
            if response.status_code in [200, 201]:
                data = response.json()
                contact_id = data.get("contact", {}).get("id")
                print(f"✅ Contact created/updated: {contact_id}")
                return contact_id
            else:
                print(f"❌ Failed to create contact: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"❌ Error creating contact: {e}")
            return None
    
    def send_email(
        self, 
        contact_id: str, 
        subject: str, 
        body: str,
        campaign_id: Optional[str] = None
    ) -> bool:
        """
        Send email to contact via GHL.
        
        Args:
            contact_id: GHL contact ID
            subject: Email subject line
            body: Email body (HTML supported)
            campaign_id: Optional campaign identifier for tracking
        
        Returns:
            True if sent successfully, False otherwise
        """
        url = f"{self.base_url}/conversations/messages"
        
        payload = {
            "type": "Email",
            "contactId": contact_id,
            "locationId": self.location_id,
            "subject": subject,
            "html": body,
            "emailFrom": os.getenv("GHL_EMAIL_FROM", "outreach@chiefaiofficer.com"),
        }
        
        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=10)
            
            if response.status_code in [200, 201]:
                print(f"✅ Email sent to contact {contact_id}")
                
                # Log campaign event
                self._log_campaign_event(contact_id, campaign_id, "sent", {
                    "subject": subject,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                return True
            else:
                print(f"❌ Failed to send email: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error sending email: {e}")
            return False
    
    def create_campaign(
        self,
        leads: List[Dict[str, Any]],
        subject_template: str,
        body_template: str,
        campaign_name: str
    ) -> Dict[str, Any]:
        """
        Create and execute email campaign for multiple leads.
        
        Args:
            leads: List of lead data dictionaries
            subject_template: Email subject (supports {variables})
            body_template: Email body (supports {variables})
            campaign_name: Campaign identifier
        
        Returns:
            Campaign results summary
        """
        campaign_id = f"ghl-{campaign_name}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        skipped_dir = Path(__file__).parent.parent / ".hive-mind" / "skipped_leads"
        skipped_dir.mkdir(parents=True, exist_ok=True)
        
        results = {
            "campaign_id": campaign_id,
            "total_leads": len(leads),
            "contacts_created": 0,
            "emails_sent": 0,
            "failures": 0,
            "skipped": 0,
            "skipped_reasons": [],
            "started_at": datetime.utcnow().isoformat()
        }
        
        print(f"\n🚀 Starting campaign: {campaign_id}")
        print(f"📊 Total leads: {len(leads)}")
        
        skipped_leads = []
        
        for i, lead in enumerate(leads, 1):
            email = lead.get('email', 'unknown')
            print(f"\n[{i}/{len(leads)}] Processing: {email}")
            
            # Validation: Check critical fields
            critical_missing = []
            if not lead.get("email"): critical_missing.append("email")
            if not lead.get("first_name"): critical_missing.append("first_name")
            if not lead.get("company") and not lead.get("companyName"): critical_missing.append("company")
            
            if critical_missing:
                reason = f"Missing critical fields: {', '.join(critical_missing)}"
                print(f"⚠️ SKIPPING: {reason}")
                results["skipped"] += 1
                results["skipped_reasons"].append({"email": email, "reason": reason})
                skipped_leads.append({
                    "email": email,
                    "lead_data": lead,
                    "reason": reason,
                    "timestamp": datetime.utcnow().isoformat()
                })
                continue
            
            # Create/update contact
            contact_id = self.create_contact(lead)
            if not contact_id:
                results["failures"] += 1
                continue
            
            results["contacts_created"] += 1
            
            # Personalize email
            try:
                subject = subject_template.format(**lead)
                body = body_template.format(**lead)
            except KeyError as e:
                # Catch variable resolution errors
                reason = f"Template variable missing: {e}"
                print(f"⚠️ SKIPPING: {reason}")
                results["skipped"] += 1
                results["skipped_reasons"].append({"email": email, "reason": reason})
                skipped_leads.append({
                    "email": email,
                    "lead_data": lead,
                    "reason": reason,
                    "timestamp": datetime.utcnow().isoformat()
                })
                continue
            
            # Send email
            if self.send_email(contact_id, subject, body, campaign_id):
                results["emails_sent"] += 1
            else:
                results["failures"] += 1
        
        # Save skipped leads
        if skipped_leads:
            skipped_file = skipped_dir / f"skipped_{campaign_id}.json"
            with open(skipped_file, 'w') as f:
                json.dump(skipped_leads, f, indent=2)
            print(f"⚠️ Skipped {len(skipped_leads)} leads (saved to {skipped_file})")

        results["completed_at"] = datetime.utcnow().isoformat()
        
        # Save campaign results
        self._save_campaign_results(results)
        
        print(f"\n✅ Campaign complete!")
        print(f"📧 Emails sent: {results['emails_sent']}/{results['total_leads']}")
        print(f"⚠️ Skipped: {results['skipped']}")
        
        return results
    
    def _log_campaign_event(
        self, 
        contact_id: str, 
        campaign_id: Optional[str], 
        event_type: str, 
        event_data: Dict[str, Any]
    ):
        """Log campaign event for tracking."""
        log_dir = Path(__file__).parent.parent / ".hive-mind"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "campaign_events.jsonl"
        
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "campaign_id": campaign_id,
            "contact_id": contact_id,
            "event_type": event_type,
            "event_data": event_data,
            "platform": "gohighlevel"
        }
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(event) + '\n')
    
    def _save_campaign_results(self, results: Dict[str, Any]):
        """Save campaign results."""
        results_dir = Path(__file__).parent.parent / ".hive-mind" / "campaigns"
        results_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{results['campaign_id']}.json"
        filepath = results_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"💾 Results saved: {filepath}")


class TestModeCrafter:
    """Test mode crafter - generates campaigns without real API calls."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.templates_path = self.project_root / ".hive-mind" / "knowledge" / "messaging" / "templates.json"
        self.output_dir = self.project_root / ".hive-mind" / "testing"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metrics = PersonalizationMetrics()
        self.templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, Any]:
        """Load messaging templates."""
        if not self.templates_path.exists():
            print(f"⚠️ Templates not found at {self.templates_path}")
            return {"templates": {}}
        
        with open(self.templates_path, 'r') as f:
            return json.load(f)
    
    def _get_template_for_tier(self, tier: int) -> Tuple[str, str, str]:
        """Get appropriate template based on lead tier."""
        sequences = self.templates.get("sequence_recommendations", {})
        templates = self.templates.get("templates", {})
        
        tier_key = f"tier_{tier}_sequence"
        sequence = sequences.get(tier_key, ["pain_point_discovery"])
        template_name = sequence[0] if sequence else "pain_point_discovery"
        
        template = templates.get(template_name, {})
        subject_lines = template.get("subject_lines", ["Quick question about {company}"])
        subject = subject_lines[0] if subject_lines else "Quick question about {company}"
        body = template.get("body", "Hi {first_name},\n\nI'd like to connect.\n\nBest,\nChris")
        
        return template_name, subject, body
    
    def _enrich_lead_data(self, lead: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich lead data with derived fields for template resolution."""
        enriched = lead.copy()
        
        # Extract data from original_lead if present (from enricher output)
        original = lead.get("original_lead", {})
        if original:
            # Copy key fields from original lead data
            for key in ["first_name", "last_name", "title", "email", "industry", 
                        "pain_points", "buying_signals", "tier"]:
                if key not in enriched or not enriched.get(key):
                    if key in original:
                        enriched[key] = original[key]
            
            # Get company name from original if not present
            if not enriched.get("company") and original.get("company"):
                enriched["company"] = original["company"]
        
        # Fallback: try to get email from contact if not present
        if not enriched.get("email"):
            contact = lead.get("contact", {})
            enriched["email"] = contact.get("work_email") or contact.get("personal_email", "")
        
        # Fallback: try to get company from company object
        if not enriched.get("company"):
            company = lead.get("company", {})
            if isinstance(company, dict):
                enriched["company"] = company.get("name", "")
        
        # Derive full_name
        if "full_name" not in enriched or not enriched.get("full_name"):
            enriched["full_name"] = f"{enriched.get('first_name', '')} {enriched.get('last_name', '')}".strip()
        
        # Derive pain_point from pain_points list
        pain_points = enriched.get("pain_points", [])
        if pain_points and "pain_point" not in enriched:
            enriched["pain_point"] = pain_points[0]
        
        # Derive trigger_event from buying_signals list
        buying_signals = enriched.get("buying_signals", [])
        if buying_signals and "trigger_event" not in enriched:
            enriched["trigger_event"] = buying_signals[0]
        
        # Get industry from company object if not present
        if not enriched.get("industry"):
            company = lead.get("company", {})
            if isinstance(company, dict):
                enriched["industry"] = company.get("industry", "")
        
        return enriched
    
    def generate_campaigns(
        self,
        leads: List[Dict[str, Any]],
        campaign_name: str = "test-campaign"
    ) -> Dict[str, Any]:
        """
        Generate sample campaigns without sending.
        
        Args:
            leads: List of segmented leads
            campaign_name: Campaign identifier
        
        Returns:
            Campaign generation results with metrics
        """
        campaign_id = f"test-{campaign_name}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        
        results = {
            "campaign_id": campaign_id,
            "mode": "test",
            "total_leads": len(leads),
            "campaigns_generated": 0,
            "started_at": datetime.utcnow().isoformat(),
            "sample_campaigns": []
        }
        
        print(f"\n🧪 TEST MODE - Starting campaign generation: {campaign_id}")
        print(f"📊 Total leads: {len(leads)}")
        print("=" * 60)
        
        for i, lead in enumerate(leads, 1):
            tier = lead.get("tier", 2)
            enriched_lead = self._enrich_lead_data(lead)
            template_name, subject_template, body_template = self._get_template_for_tier(tier)
            
            print(f"\n[{i}/{len(leads)}] Processing: {lead.get('email')} (Tier {tier})")
            print(f"    Template: {template_name}")
            
            subject, subj_unresolved = self.metrics.check_template(
                subject_template, enriched_lead, f"subject-{lead.get('email')}"
            )
            body, body_unresolved = self.metrics.check_template(
                body_template, enriched_lead, f"body-{lead.get('email')}"
            )
            
            all_unresolved = subj_unresolved + body_unresolved
            if all_unresolved:
                print(f"    ⚠️ Unresolved variables: {all_unresolved}")
            else:
                print(f"    ✅ All variables resolved")
            
            campaign_entry = {
                "lead_id": lead.get("id", f"lead-{i}"),
                "email": lead.get("email"),
                "tier": tier,
                "template_used": template_name,
                "subject": subject,
                "body": body,
                "unresolved_variables": all_unresolved,
                "personalization_complete": len(all_unresolved) == 0,
                "generated_at": datetime.utcnow().isoformat()
            }
            
            results["sample_campaigns"].append(campaign_entry)
            results["campaigns_generated"] += 1
        
        results["completed_at"] = datetime.utcnow().isoformat()
        results["metrics"] = self.metrics.get_report()
        
        self._save_sample_campaigns(results)
        self._print_summary(results)
        
        return results
    
    def _save_sample_campaigns(self, results: Dict[str, Any]):
        """Save sample campaigns to testing directory."""
        filepath = self.output_dir / "sample_campaigns.json"
        
        with open(filepath, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n💾 Sample campaigns saved: {filepath}")
    
    def _print_summary(self, results: Dict[str, Any]):
        """Print campaign generation summary."""
        metrics = results.get("metrics", {})
        rate = metrics.get("personalization_rate", 0)
        meets_criteria = metrics.get("meets_day3_criteria", False)
        
        print("\n" + "=" * 60)
        print("📊 PERSONALIZATION METRICS")
        print("=" * 60)
        print(f"Total template fields:    {metrics.get('total_fields', 0)}")
        print(f"Resolved fields:          {metrics.get('resolved_fields', 0)}")
        print(f"Personalization rate:     {rate}%")
        print(f"Unresolved variables:     {metrics.get('hallucination_check', {}).get('count', 0)}")
        print(f"Day 3 Criteria (≥90%):    {'✅ PASS' if meets_criteria else '❌ FAIL'}")
        print("=" * 60)
        
        if not meets_criteria:
            print("\n⚠️ HALLUCINATION CHECK - Unresolved Variables:")
            for item in metrics.get("unresolved_variables", []):
                print(f"    - {item['variable']} in {item['context']}")


def load_leads_from_file(filepath: str) -> List[Dict[str, Any]]:
    """Load leads from a JSON file."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {filepath}")
    
    with open(path, 'r') as f:
        data = json.load(f)
    
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        if "test_leads" in data:
            return data["test_leads"]
        elif "leads" in data:
            return data["leads"]
        elif "segmented_leads" in data:
            all_leads = []
            for tier_data in data["segmented_leads"].values():
                if isinstance(tier_data, list):
                    all_leads.extend(tier_data)
            return all_leads
    
    raise ValueError("Could not parse leads from input file")


def main():
    """Run GHL Campaign Crafter."""
    parser = argparse.ArgumentParser(
        description="CRAFTER Agent - GoHighLevel Email Campaign Creator"
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help="Generate campaigns without making real API calls"
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Path to segmented leads JSON file"
    )
    parser.add_argument(
        "--campaign-name",
        type=str,
        default="test-campaign",
        help="Campaign name identifier"
    )
    
    args = parser.parse_args()
    
    if args.test_mode:
        print("🧪 Running in TEST MODE - No real API calls will be made")
        
        crafter = TestModeCrafter()
        
        if args.input:
            leads = load_leads_from_file(args.input)
        else:
            default_input = Path(__file__).parent.parent / ".hive-mind" / "testing" / "test-leads.json"
            if default_input.exists():
                leads = load_leads_from_file(str(default_input))
                print(f"📂 Using default test leads: {default_input}")
            else:
                print("❌ No input file specified and no default test leads found")
                print("   Use --input to specify a leads file")
                sys.exit(1)
        
        results = crafter.generate_campaigns(
            leads=leads,
            campaign_name=args.campaign_name
        )
        
        if results["metrics"]["meets_day3_criteria"]:
            print("\n✅ Campaign generation successful - Ready for production!")
            sys.exit(0)
        else:
            print("\n⚠️ Personalization rate below 90% threshold")
            sys.exit(1)
    
    else:
        crafter = GHLCampaignCrafter()
        
        test_lead = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "full_name": "John Doe",
            "company": "Acme Corp",
            "title": "VP of Sales",
            "linkedin_url": "https://linkedin.com/in/johndoe",
            "industry": "Technology"
        }
        
        subject = "Quick question about {company}'s revenue operations"
        body = """
        <p>Hi {first_name},</p>
        
        <p>I noticed you're the {title} at {company}. I'm reaching out because we've helped similar companies in {industry} automate their revenue operations with AI.</p>
        
        <p>Would you be open to a quick 15-minute call to discuss how we could help {company}?</p>
        
        <p>Best regards,<br>
        Chris Daigle<br>
        Chief AI Officer</p>
        """
        
        results = crafter.create_campaign(
            leads=[test_lead],
            subject_template=subject,
            body_template=body,
            campaign_name="test-campaign"
        )
        
        print(f"\n📊 Campaign Results:")
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
