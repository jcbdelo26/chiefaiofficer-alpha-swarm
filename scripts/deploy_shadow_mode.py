#!/usr/bin/env python3
"""
Shadow Mode Deployment Script - Day 30 Production Initialization
=================================================================

This script executes "Day 30" of the production transition:
1. Verifies config/production.json is in Shadow Mode
2. Validates API connections (noting missing keys)
3. Reads GHL contacts (live connection)
4. Shadow-processes contacts through the swarm (no actual sending)
5. Logs all actions to .hive-mind/shadow_mode_logs/

Usage:
    python scripts/deploy_shadow_mode.py --verify          # Check configuration
    python scripts/deploy_shadow_mode.py --fetch-contacts  # Fetch real GHL contacts
    python scripts/deploy_shadow_mode.py --shadow-process  # Process contacts in shadow mode
    python scripts/deploy_shadow_mode.py --full            # Run complete shadow deployment
"""

import os
import sys
import json
import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
import logging

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env', override=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('shadow_mode_deploy')

# Fix Windows console encoding for Unicode
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# =============================================================================
# CONFIGURATION
# =============================================================================

CONFIG_PATH = PROJECT_ROOT / "config" / "production.json"
SHADOW_LOG_PATH = PROJECT_ROOT / ".hive-mind" / "shadow_mode_logs"
SHADOW_EMAILS_PATH = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"


@dataclass
class ShadowModeConfig:
    """Shadow mode deployment configuration."""
    mode: str = "shadow"
    email_send_enabled: bool = False
    read_only_crm: bool = True
    log_all_actions: bool = True
    max_contacts_to_fetch: int = 20
    max_contacts_to_process: int = 20


@dataclass
class CredentialStatus:
    """Status of a required credential."""
    name: str
    env_var: str
    is_set: bool
    is_critical: bool
    value_length: int = 0
    masked_value: str = ""


@dataclass
class ShadowProcessResult:
    """Result of shadow-processing a contact."""
    contact_id: str
    contact_name: str
    contact_email: str
    processing_status: str = "pending"
    icp_score: Optional[float] = None
    tier: Optional[str] = None
    would_send_email: bool = False
    email_subject: Optional[str] = None
    email_body_full: Optional[str] = None
    email_body_preview: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    processed_at: str = ""
    
    def __post_init__(self):
        if not self.processed_at:
            self.processed_at = datetime.now(timezone.utc).isoformat()


@dataclass
class DeploymentReport:
    """Complete shadow mode deployment report."""
    deployment_id: str
    started_at: str
    completed_at: Optional[str] = None
    config_valid: bool = False
    credentials_status: List[Dict] = field(default_factory=list)
    missing_critical_credentials: List[str] = field(default_factory=list)
    contacts_fetched: int = 0
    contacts_processed: int = 0
    processing_results: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    status: str = "pending"
    
    def to_dict(self) -> Dict:
        return asdict(self)


# =============================================================================
# SHADOW MODE DEPLOYER
# =============================================================================

class ShadowModeDeployer:
    """
    Deploys the swarm in Shadow Mode for Day 30 production initialization.
    
    Shadow Mode means:
    - Live connections to GHL (read contacts)
    - All processing happens (scoring, email generation)
    - NO emails are actually sent
    - All would-be actions are logged for review
    """
    
    def __init__(self):
        self.config = ShadowModeConfig()
        self.report = DeploymentReport(
            deployment_id=f"shadow_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            started_at=datetime.now(timezone.utc).isoformat()
        )
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Ensure required directories exist."""
        SHADOW_LOG_PATH.mkdir(parents=True, exist_ok=True)
        SHADOW_EMAILS_PATH.mkdir(parents=True, exist_ok=True)
    
    def load_production_config(self) -> Tuple[bool, Dict[str, Any]]:
        """Load and validate production.json configuration."""
        print("\n" + "=" * 70)
        print("  STEP 1: Loading Production Configuration")
        print("=" * 70)
        
        if not CONFIG_PATH.exists():
            error = f"Configuration file not found: {CONFIG_PATH}"
            self.report.errors.append(error)
            print(f"  ❌ {error}")
            return False, {}
        
        try:
            with open(CONFIG_PATH) as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            error = f"Invalid JSON in config: {e}"
            self.report.errors.append(error)
            print(f"  ❌ {error}")
            return False, {}
        
        # Validate shadow mode settings
        checks = []
        
        # Check rollout phase
        rollout_phase = config.get("rollout_phase", {}).get("current", "")
        checks.append(("Rollout Phase", rollout_phase == "shadow", rollout_phase))
        
        # Check email behavior
        email_behavior = config.get("email_behavior", {})
        checks.append(("Shadow Mode Enabled", email_behavior.get("shadow_mode", False), 
                      str(email_behavior.get("shadow_mode", False))))
        checks.append(("Actually Send Disabled", not email_behavior.get("actually_send", True),
                      f"actually_send={email_behavior.get('actually_send', True)}"))
        checks.append(("Max Daily Sends = 0", email_behavior.get("max_daily_sends", 1) == 0,
                      f"max_daily_sends={email_behavior.get('max_daily_sends', 'not set')}"))
        
        # Check guardrails
        guardrails = config.get("guardrails", {})
        checks.append(("Audit All Actions", guardrails.get("audit_all_actions", False),
                      str(guardrails.get("audit_all_actions", False))))
        
        print("\n  Configuration Checks:")
        all_passed = True
        for check_name, passed, value in checks:
            icon = "✅" if passed else "❌"
            print(f"    {icon} {check_name}: {value}")
            if not passed:
                all_passed = False
                self.report.warnings.append(f"{check_name} check failed: {value}")
        
        # Count active agents
        failure_tracker = config.get("failure_tracker", {})
        active_agents = failure_tracker.get("active_agent_count", 0)
        print(f"\n  Active Agents: {active_agents}")
        
        # List enabled agents
        agents = failure_tracker.get("agents", {})
        enabled = [name for name, cfg in agents.items() if cfg.get("enabled", False)]
        print(f"  Enabled: {', '.join(enabled)}")
        
        self.report.config_valid = all_passed
        return all_passed, config
    
    def validate_credentials(self) -> Tuple[bool, List[CredentialStatus]]:
        """Validate all required API credentials."""
        print("\n" + "=" * 70)
        print("  STEP 2: Validating API Credentials")
        print("=" * 70)
        
        # Define required credentials
        credentials = [
            ("GHL Production API Key", "GHL_PROD_API_KEY", True),
            ("GHL Location ID", "GHL_LOCATION_ID", True),
            ("Supabase URL", "SUPABASE_URL", True),
            ("Supabase Key", "SUPABASE_KEY", True),
            ("RB2B API Key", "RB2B_API_KEY", False),  # Not critical for shadow mode
            ("Clay API Key", "CLAY_API_KEY", False),
            ("Slack Webhook URL", "SLACK_WEBHOOK_URL", False),
            ("Instantly API Key", "INSTANTLY_API_KEY", False),  # Not used (GHL is email platform)
        ]
        
        statuses = []
        critical_missing = []
        
        print("\n  Credential Status:")
        for name, env_var, is_critical in credentials:
            value = os.getenv(env_var, "")
            is_set = bool(value) and value not in ["", "your_key_here", "placeholder"]
            
            # Mask value for display
            if is_set:
                if len(value) > 10:
                    masked = f"{value[:4]}...{value[-4:]}"
                else:
                    masked = "***SET***"
            else:
                masked = "NOT SET"
            
            status = CredentialStatus(
                name=name,
                env_var=env_var,
                is_set=is_set,
                is_critical=is_critical,
                value_length=len(value),
                masked_value=masked
            )
            statuses.append(status)
            
            critical_tag = " [CRITICAL]" if is_critical else ""
            icon = "✅" if is_set else ("❌" if is_critical else "⚠️")
            print(f"    {icon} {name}{critical_tag}: {masked}")
            
            if is_critical and not is_set:
                critical_missing.append(env_var)
        
        self.report.credentials_status = [asdict(s) for s in statuses]
        self.report.missing_critical_credentials = critical_missing
        
        if critical_missing:
            print(f"\n  ⚠️  Missing Critical Credentials: {', '.join(critical_missing)}")
            print("      Shadow mode can still run with mock data.")
        
        return len(critical_missing) == 0, statuses
    
    async def fetch_ghl_contacts(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch contacts from GHL (live connection)."""
        print("\n" + "=" * 70)
        print("  STEP 3: Fetching GHL Contacts (Live Connection)")
        print("=" * 70)
        
        api_key = os.getenv("GHL_PROD_API_KEY", "")
        location_id = os.getenv("GHL_LOCATION_ID", "")
        
        if not api_key or not location_id:
            print("  ⚠️  GHL credentials not set. Using synthetic test data.")
            return self._generate_synthetic_contacts(limit)
        
        try:
            import requests
            
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
                'Version': '2021-07-28'
            }
            
            url = f"https://services.leadconnectorhq.com/contacts/?locationId={location_id}&limit={limit}"
            print(f"  Fetching from: {url[:50]}...")
            
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                contacts = data.get("contacts", [])
                print(f"  ✅ Fetched {len(contacts)} contacts from GHL")
                self.report.contacts_fetched = len(contacts)
                
                # Log raw response (sanitized)
                log_file = SHADOW_LOG_PATH / f"ghl_fetch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                sanitized = self._sanitize_for_log(contacts)
                with open(log_file, 'w') as f:
                    json.dump(sanitized, f, indent=2)
                print(f"  Logged to: {log_file.name}")
                
                return contacts
            else:
                error = f"GHL API returned {response.status_code}: {response.text[:200]}"
                print(f"  ❌ {error}")
                self.report.errors.append(error)
                print("  Falling back to synthetic test data...")
                return self._generate_synthetic_contacts(limit)
                
        except Exception as e:
            error = f"Failed to fetch GHL contacts: {e}"
            print(f"  ❌ {error}")
            self.report.errors.append(error)
            print("  Falling back to synthetic test data...")
            return self._generate_synthetic_contacts(limit)
    
    def _generate_synthetic_contacts(self, count: int) -> List[Dict[str, Any]]:
        """Generate synthetic contacts for testing when GHL is unavailable."""
        print(f"  Generating {count} synthetic contacts for shadow testing...")
        
        synthetic = []
        titles = ["VP of Sales", "Director of Revenue Operations", "CRO", "Head of Growth", "Sales Manager"]
        companies = ["TechCorp", "DataFlow Inc", "CloudScale", "RevenuePro", "SalesForce Clone"]
        
        for i in range(count):
            contact = {
                "id": f"synthetic_{i+1:04d}",
                "firstName": f"Test{i+1}",
                "lastName": "User",
                "email": f"test{i+1}@example.com",
                "phone": f"+1555000{i+1:04d}",
                "companyName": companies[i % len(companies)],
                "customFields": [
                    {"key": "title", "value": titles[i % len(titles)]},
                    {"key": "employee_count", "value": str((i + 1) * 50)},
                    {"key": "industry", "value": "B2B SaaS"}
                ],
                "tags": ["synthetic", "shadow_test"],
                "dateAdded": datetime.now(timezone.utc).isoformat(),
                "_synthetic": True
            }
            synthetic.append(contact)
        
        self.report.contacts_fetched = len(synthetic)
        self.report.warnings.append("Using synthetic test data (GHL unavailable)")
        
        return synthetic
    
    def _sanitize_for_log(self, data: Any) -> Any:
        """Sanitize data for logging (redact PII)."""
        if isinstance(data, dict):
            sanitized = {}
            for k, v in data.items():
                if k.lower() in ["email", "phone", "ssn", "password", "token"]:
                    sanitized[k] = f"[REDACTED:{k.upper()}]"
                else:
                    sanitized[k] = self._sanitize_for_log(v)
            return sanitized
        elif isinstance(data, list):
            return [self._sanitize_for_log(item) for item in data]
        else:
            return data
    
    async def shadow_process_contacts(self, contacts: List[Dict[str, Any]]) -> List[ShadowProcessResult]:
        """
        Shadow-process contacts through the swarm.
        
        This simulates the full pipeline:
        1. SEGMENTOR: Score and classify
        2. CRAFTER: Generate email (but don't send)
        3. GATEKEEPER: Would require approval
        
        All actions are logged, nothing is actually sent.
        """
        print("\n" + "=" * 70)
        print("  STEP 4: Shadow Processing Contacts")
        print("=" * 70)
        
        results = []
        
        # Import core modules for processing
        try:
            from core.unified_guardrails import UnifiedGuardrails, ActionType
            from core.ghl_execution_gateway import get_gateway
            guardrails = UnifiedGuardrails()
            gateway = get_gateway()
            has_core = True
        except ImportError as e:
            print(f"  ⚠️  Could not import core modules: {e}")
            print("  Running simplified shadow processing...")
            has_core = False
        
        for i, contact in enumerate(contacts[:self.config.max_contacts_to_process]):
            contact_id = contact.get("id", f"unknown_{i}")
            name = f"{contact.get('firstName', 'Unknown')} {contact.get('lastName', '')}"
            email = contact.get("email", "no-email@example.com")
            
            print(f"\n  [{i+1}/{min(len(contacts), self.config.max_contacts_to_process)}] Processing: {name}")
            
            result = ShadowProcessResult(
                contact_id=contact_id,
                contact_name=name.strip(),
                contact_email=email
            )
            
            try:
                # Step 1: Score the contact (SEGMENTOR)
                icp_score = self._calculate_icp_score(contact)
                result.icp_score = icp_score
                result.tier = "tier_1" if icp_score >= 0.8 else "tier_2" if icp_score >= 0.6 else "tier_3"
                print(f"      ICP Score: {icp_score:.2f} → {result.tier}")
                
                # Step 2: Generate email (CRAFTER) - shadow only
                if icp_score >= 0.5:
                    email_content = self._generate_shadow_email(contact, result.tier)
                    result.would_send_email = True
                    result.email_subject = email_content["subject"]
                    result.email_body_full = email_content["body"]
                    result.email_body_preview = email_content["body"][:200] + "..."
                    print(f"      Would Send Email: {result.email_subject}")
                else:
                    result.would_send_email = False
                    result.warnings.append("ICP score too low for outreach")
                    print(f"      No email (ICP too low)")
                
                # Step 3: Validate with guardrails (if available)
                if has_core and result.would_send_email:
                    valid, reason = guardrails.validate_action(
                        agent_name="CRAFTER",
                        action_type=ActionType.SEND_EMAIL,
                        grounding_evidence={
                            "source": "shadow_mode",
                            "data_id": contact_id,
                            "verified_at": datetime.now(timezone.utc).isoformat()
                        }
                    )
                    if not valid:
                        result.warnings.append(f"Guardrails: {reason}")
                        print(f"      Guardrails: {reason}")
                
                result.processing_status = "shadow_complete"
                
            except Exception as e:
                result.processing_status = "error"
                result.errors.append(str(e))
                print(f"      ❌ Error: {e}")
            
            results.append(result)
            
            # Log individual result
            self._log_shadow_email(result, contact)
        
        self.report.contacts_processed = len(results)
        self.report.processing_results = [asdict(r) for r in results]
        
        return results
    
    def _calculate_icp_score(self, contact: Dict[str, Any]) -> float:
        """Calculate ICP score for a contact."""
        score = 0.3  # Base score (lower to differentiate)
        
        # Extract custom fields
        custom_fields = {cf.get("key"): cf.get("value") for cf in contact.get("customFields", [])}
        
        # Extract tags (GHL uses tags array)
        tags = [t.lower() for t in contact.get("tags", [])]
        
        # Tag-based scoring (GHL enrichment tags)
        if "high" in tags:
            score += 0.35  # High priority leads
        elif "medium" in tags:
            score += 0.20
        elif "low" in tags:
            score += 0.05
        
        # RB2B enriched contacts get bonus
        if "rb2b-enriched" in tags:
            score += 0.15
        
        # Email type scoring
        if "email_corporate" in tags:
            score += 0.15  # Corporate emails more valuable
        elif "email_consumer" in tags:
            score += 0.05
        
        # Source scoring
        source = (contact.get("source") or "").lower()
        if "rb2b" in source:
            score += 0.10  # Website visitors show intent
        
        # Title scoring (from custom fields or contact name patterns)
        title = custom_fields.get("title", contact.get("title", "")).lower()
        title_scores = {
            "vp": 0.2, "director": 0.15, "cro": 0.25, "head": 0.15,
            "chief": 0.25, "ceo": 0.25, "coo": 0.20, "manager": 0.1, 
            "sales": 0.1, "revenue": 0.15, "founder": 0.20
        }
        for keyword, bonus in title_scores.items():
            if keyword in title:
                score += bonus
                break  # Only count once
        
        # Has complete contact info
        has_name = bool(contact.get("firstName"))
        has_email = bool(contact.get("email"))
        has_company = bool(contact.get("companyName") or contact.get("website"))
        
        if has_name:
            score += 0.05
        if has_email:
            score += 0.05
        if has_company:
            score += 0.10
        
        # Website indicates business context
        website = contact.get("website", "")
        if website and "." in website:
            score += 0.05
        
        # Company size scoring (if available)
        try:
            employee_count = int(custom_fields.get("employee_count", 0))
            if 51 <= employee_count <= 500:
                score += 0.15  # Sweet spot
            elif 20 <= employee_count <= 50:
                score += 0.05
        except (ValueError, TypeError):
            pass
        
        return min(1.0, max(0.0, score))
    
    def _generate_shadow_email(self, contact: Dict[str, Any], tier: str) -> Dict[str, str]:
        """Generate a shadow email (not actually sent)."""
        first_name = contact.get("firstName", "there")
        company = contact.get("companyName", "your company")
        
        custom_fields = {cf.get("key"): cf.get("value") for cf in contact.get("customFields", [])}
        title = custom_fields.get("title", "")
        
        if tier == "tier_1":
            subject = f"{first_name}, AI is transforming RevOps at companies like {company}"
            body = f"""Hi {first_name},

I noticed you're leading {title} at {company}. Companies your size are seeing 
20-30% operational cost reductions with AI-powered revenue operations.

Would you be open to a 15-minute call to explore if similar results are 
possible for {company}?

Best,
Chris Daigle
Chief AI Officer
https://caio.cx/ai-exec-briefing-call

Reply STOP to unsubscribe."""

        elif tier == "tier_2":
            subject = f"Quick question about {company}'s revenue operations"
            body = f"""Hi {first_name},

I've been researching {company} and wanted to reach out. Many {title} leaders 
are exploring AI to streamline their operations.

Interested in learning how other companies are achieving 40%+ efficiency gains?

Best,
Chris Daigle

Reply STOP to unsubscribe."""

        else:
            subject = f"Resource for {company}"
            body = f"""Hi {first_name},

Thought you might find value in our AI Readiness Assessment tool.

https://ai-readiness-assessment-549851735707.us-west1.run.app/

Best,
Chris

Reply STOP to unsubscribe."""

        return {"subject": subject, "body": body}
    
    def _log_shadow_email(self, result: ShadowProcessResult, contact: Dict[str, Any] = None):
        """Log shadow email to file with complete data for dashboard display."""
        if not result.would_send_email:
            return
        
        log_file = SHADOW_EMAILS_PATH / f"{result.contact_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Extract custom fields for recipient data
        custom_fields = {}
        if contact:
            custom_fields = {cf.get("key"): cf.get("value") for cf in contact.get("customFields", [])}
        
        log_data = {
            "email_id": f"{result.contact_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "status": "pending",
            "shadow_mode": True,
            "would_have_sent": True,
            "actual_sent": False,
            "contact_id": result.contact_id,
            "contact_name": result.contact_name,
            "to": result.contact_email,  # Include actual email for dashboard display
            "subject": result.email_subject,
            "body": result.email_body_full,  # Full email body for dashboard
            "body_preview": result.email_body_preview,
            "icp_score": result.icp_score,
            "tier": result.tier,
            "timestamp": result.processed_at,
            "warnings": result.warnings,
            "recipient_data": {
                "name": result.contact_name,
                "company": contact.get("companyName", "Unknown Corp") if contact else "Unknown Corp",
                "title": custom_fields.get("title", "Unknown Title"),
                "location": custom_fields.get("location") or custom_fields.get("city", "Unknown Location"),
                "employees": custom_fields.get("employee_count", "N/A"),
                "industry": custom_fields.get("industry", "N/A"),
                "linkedin_url": contact.get("linkedin_url") if contact else None
            },
            "source": "shadow_mode_processor",
            "synthetic": contact.get("_synthetic", False) if contact else False
        }
        
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)
    
    def print_summary(self):
        """Print deployment summary."""
        print("\n" + "=" * 70)
        print("  SHADOW MODE DEPLOYMENT SUMMARY")
        print("=" * 70)
        
        self.report.completed_at = datetime.now(timezone.utc).isoformat()
        
        # Determine overall status
        if self.report.errors:
            self.report.status = "completed_with_errors"
            status_icon = "⚠️"
        elif self.report.warnings:
            self.report.status = "completed_with_warnings"
            status_icon = "✅"
        else:
            self.report.status = "success"
            status_icon = "✅"
        
        print(f"\n  {status_icon} Status: {self.report.status.upper()}")
        print(f"  Deployment ID: {self.report.deployment_id}")
        print(f"  Duration: {self.report.started_at} → {self.report.completed_at}")
        
        print("\n  Metrics:")
        print(f"    Config Valid: {'Yes' if self.report.config_valid else 'No'}")
        print(f"    Contacts Fetched: {self.report.contacts_fetched}")
        print(f"    Contacts Processed: {self.report.contacts_processed}")
        
        if self.report.processing_results:
            would_send = sum(1 for r in self.report.processing_results if r.get("would_send_email"))
            print(f"    Would Send Emails: {would_send}")
            
            tier_counts = {}
            for r in self.report.processing_results:
                tier = r.get("tier", "unknown")
                tier_counts[tier] = tier_counts.get(tier, 0) + 1
            print(f"    Tier Distribution: {tier_counts}")
        
        if self.report.missing_critical_credentials:
            print(f"\n  ⚠️  Missing Critical Keys: {', '.join(self.report.missing_critical_credentials)}")
        
        if self.report.warnings:
            print(f"\n  Warnings ({len(self.report.warnings)}):")
            for w in self.report.warnings[:5]:
                print(f"    - {w}")
        
        if self.report.errors:
            print(f"\n  Errors ({len(self.report.errors)}):")
            for e in self.report.errors[:5]:
                print(f"    - {e}")
        
        # Save full report
        report_file = SHADOW_LOG_PATH / f"deployment_report_{self.report.deployment_id}.json"
        with open(report_file, 'w') as f:
            json.dump(self.report.to_dict(), f, indent=2, default=str)
        print(f"\n  Full report: {report_file}")
        
        print("\n  Shadow Mode Logs: .hive-mind/shadow_mode_logs/")
        print("  Shadow Emails: .hive-mind/shadow_mode_emails/")
        
        print("\n" + "=" * 70)
        print("  SHADOW MODE ACTIVE - No emails will be sent")
        print("  Review shadow logs before transitioning to Parallel Mode")
        print("=" * 70 + "\n")
    
    async def run_full_deployment(self):
        """Run complete shadow mode deployment."""
        print("\n" + "=" * 70)
        print("  🚀 SHADOW MODE DEPLOYMENT - DAY 30 PRODUCTION INITIALIZATION")
        print("=" * 70)
        print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Step 1: Load config
        config_valid, config = self.load_production_config()
        
        # Step 2: Validate credentials
        creds_valid, cred_statuses = self.validate_credentials()
        
        # Step 3: Fetch GHL contacts
        contacts = await self.fetch_ghl_contacts(limit=self.config.max_contacts_to_fetch)
        
        # Step 4: Shadow process
        if contacts:
            results = await self.shadow_process_contacts(contacts)
        else:
            self.report.warnings.append("No contacts to process")
        
        # Step 5: Print summary
        self.print_summary()
        
        return self.report


# =============================================================================
# CLI
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(
        description="Shadow Mode Deployment - Day 30 Production Initialization"
    )
    parser.add_argument("--verify", action="store_true", 
                       help="Verify configuration only")
    parser.add_argument("--fetch-contacts", action="store_true",
                       help="Fetch contacts from GHL")
    parser.add_argument("--shadow-process", action="store_true",
                       help="Shadow-process contacts")
    parser.add_argument("--full", action="store_true",
                       help="Run complete shadow deployment")
    parser.add_argument("--contacts", type=int, default=10,
                       help="Number of contacts to fetch (default: 10)")
    
    args = parser.parse_args()
    
    deployer = ShadowModeDeployer()
    deployer.config.max_contacts_to_fetch = args.contacts
    
    if args.verify:
        deployer.load_production_config()
        deployer.validate_credentials()
    elif args.fetch_contacts:
        deployer.load_production_config()
        deployer.validate_credentials()
        await deployer.fetch_ghl_contacts(limit=args.contacts)
    elif args.shadow_process:
        deployer.load_production_config()
        deployer.validate_credentials()
        contacts = await deployer.fetch_ghl_contacts(limit=args.contacts)
        await deployer.shadow_process_contacts(contacts)
        deployer.print_summary()
    else:
        # Default: full deployment
        await deployer.run_full_deployment()


if __name__ == "__main__":
    asyncio.run(main())
