"""
Verification Hooks - Cross-check agent outputs against rules and live data
Prevents hallucinations and ensures compliance
"""

import os
import re
import json
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any, Callable
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('verification_hooks')


class Severity(Enum):
    """Severity levels for verification failures"""
    ERROR = "error"      # Block output, requires fix
    WARNING = "warning"  # Flag for review, can proceed
    INFO = "info"        # Informational only


@dataclass
class VerificationResult:
    """Result of a single verification check"""
    passed: bool
    rule_id: str
    rule_name: str
    message: str
    severity: Severity
    suggested_fix: Optional[str] = None
    evidence: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            **asdict(self),
            'severity': self.severity.value
        }


@dataclass
class VerificationRule:
    """Definition of a verification rule"""
    id: str
    name: str
    description: str
    check_function: Callable
    severity: Severity
    category: str
    enabled: bool = True


@dataclass
class VerificationReport:
    """Complete verification report for an agent output"""
    output_id: str
    agent_name: str
    timestamp: str
    total_checks: int
    passed: int
    failed: int
    warnings: int
    results: List[VerificationResult]
    overall_status: str  # "passed", "warning", "failed"
    
    def to_dict(self) -> Dict:
        return {
            'output_id': self.output_id,
            'agent_name': self.agent_name,
            'timestamp': self.timestamp,
            'total_checks': self.total_checks,
            'passed': self.passed,
            'failed': self.failed,
            'warnings': self.warnings,
            'overall_status': self.overall_status,
            'results': [r.to_dict() for r in self.results]
        }


class VerificationHooks:
    """
    Verification system for agent outputs
    
    Ensures:
    1. ICP compliance
    2. Email compliance (CAN-SPAM)
    3. Personalization accuracy
    4. Data integrity
    """
    
    # Spam trigger words to avoid
    SPAM_WORDS = [
        'free', 'guarantee', 'no obligation', 'winner', 'cash',
        'urgent', 'act now', 'limited time', 'click here', 'buy now',
        'make money', 'earn extra', 'double your', 'million dollars',
        'no credit check', 'no fees', 'risk free', 'special promotion'
    ]
    
    # Required unsubscribe patterns
    UNSUBSCRIBE_PATTERNS = [
        r'unsubscribe',
        r'opt.?out',
        r'remove.*from.*list',
        r'stop.*receiving',
        r'manage.*preferences'
    ]
    
    def __init__(self):
        """Initialize verification hooks"""
        self.timestamp = datetime.now()
        self.hive_mind_path = Path(__file__).parent.parent / ".hive-mind"
        self.hive_mind_path.mkdir(exist_ok=True)
        self.config_path = Path(__file__).parent.parent / "config"
        
        # Load ICP criteria
        self.icp_criteria = self._load_icp_criteria()
        
        # Initialize rules
        self.rules = self._build_rules()
        
        # Verification log
        self.verification_log: List[VerificationReport] = []
        
        logger.info(f"Verification hooks initialized with {len(self.rules)} rules")
    
    def _load_icp_criteria(self) -> Dict:
        """Load ICP criteria from config"""
        icp_file = self.config_path / "icp_criteria.json"
        
        if icp_file.exists():
            with open(icp_file) as f:
                return json.load(f)
        
        # Default ICP criteria
        return {
            "employee_range": {"min": 51, "max": 500},
            "industries": [
                "B2B SaaS", "Technology", "Software", "Enterprise Software",
                "FinTech", "HealthTech", "MarTech", "Sales Tech"
            ],
            "titles": {
                "include": ["VP", "Director", "Head of", "Chief", "CRO", "CMO", "CEO"],
                "exclude": ["Intern", "Assistant", "Junior", "Entry"]
            },
            "disqualifiers": [
                "Agency", "Consulting", "Freelance", "Student"
            ],
            "min_company_age_years": 2
        }
    
    def _build_rules(self) -> List[VerificationRule]:
        """Build all verification rules"""
        return [
            VerificationRule(
                id="ICP-001",
                name="Employee Count Range",
                description="Company employee count within ICP range",
                check_function=self._check_employee_count,
                severity=Severity.ERROR,
                category="icp"
            ),
            VerificationRule(
                id="ICP-002",
                name="Industry Match",
                description="Company industry matches ICP criteria",
                check_function=self._check_industry,
                severity=Severity.WARNING,
                category="icp"
            ),
            VerificationRule(
                id="ICP-003",
                name="Title Seniority",
                description="Contact title matches target seniority",
                check_function=self._check_title_seniority,
                severity=Severity.WARNING,
                category="icp"
            ),
            VerificationRule(
                id="ICP-004",
                name="Disqualifier Check",
                description="Company not in disqualified categories",
                check_function=self._check_disqualifiers,
                severity=Severity.ERROR,
                category="icp"
            ),
            VerificationRule(
                id="EMAIL-001",
                name="Unsubscribe Link",
                description="Email contains unsubscribe mechanism",
                check_function=self._check_unsubscribe,
                severity=Severity.ERROR,
                category="compliance"
            ),
            VerificationRule(
                id="EMAIL-002",
                name="Email Length",
                description="Email within optimal length (50-300 words)",
                check_function=self._check_email_length,
                severity=Severity.WARNING,
                category="compliance"
            ),
            VerificationRule(
                id="EMAIL-003",
                name="Spam Words",
                description="Email avoids spam trigger words",
                check_function=self._check_spam_words,
                severity=Severity.WARNING,
                category="compliance"
            ),
            VerificationRule(
                id="PERS-001",
                name="Personalization Resolved",
                description="All personalization tokens are resolved",
                check_function=self._check_personalization_resolved,
                severity=Severity.ERROR,
                category="personalization"
            ),
            VerificationRule(
                id="PERS-002",
                name="Company Name Match",
                description="Company name in email matches lead record",
                check_function=self._check_company_name_match,
                severity=Severity.ERROR,
                category="personalization"
            ),
            VerificationRule(
                id="PERS-003",
                name="First Name Match",
                description="First name in email matches lead record",
                check_function=self._check_first_name_match,
                severity=Severity.ERROR,
                category="personalization"
            ),
            VerificationRule(
                id="DATA-001",
                name="Email Format Valid",
                description="Lead email is properly formatted",
                check_function=self._check_email_format,
                severity=Severity.ERROR,
                category="data"
            ),
            VerificationRule(
                id="DATA-002",
                name="Required Fields Present",
                description="All required lead fields are populated",
                check_function=self._check_required_fields,
                severity=Severity.ERROR,
                category="data"
            )
        ]
    
    # === ICP Verification Checks ===
    
    def _check_employee_count(self, lead: Dict, **kwargs) -> VerificationResult:
        """Verify employee count within ICP range"""
        employee_count = lead.get('employee_count', 0)
        min_emp = self.icp_criteria['employee_range']['min']
        max_emp = self.icp_criteria['employee_range']['max']
        
        if min_emp <= employee_count <= max_emp:
            return VerificationResult(
                passed=True,
                rule_id="ICP-001",
                rule_name="Employee Count Range",
                message=f"Employee count {employee_count} within range [{min_emp}-{max_emp}]",
                severity=Severity.INFO
            )
        else:
            return VerificationResult(
                passed=False,
                rule_id="ICP-001",
                rule_name="Employee Count Range",
                message=f"Employee count {employee_count} outside range [{min_emp}-{max_emp}]",
                severity=Severity.ERROR,
                suggested_fix="Consider excluding this lead or override with manual approval"
            )
    
    def _check_industry(self, lead: Dict, **kwargs) -> VerificationResult:
        """Verify industry matches ICP"""
        industry = lead.get('industry', '').lower()
        icp_industries = [i.lower() for i in self.icp_criteria.get('industries', [])]
        
        if any(icp_ind in industry or industry in icp_ind for icp_ind in icp_industries):
            return VerificationResult(
                passed=True,
                rule_id="ICP-002",
                rule_name="Industry Match",
                message=f"Industry '{lead.get('industry')}' matches ICP",
                severity=Severity.INFO
            )
        else:
            return VerificationResult(
                passed=False,
                rule_id="ICP-002",
                rule_name="Industry Match",
                message=f"Industry '{lead.get('industry')}' not in ICP list",
                severity=Severity.WARNING,
                suggested_fix="Verify industry manually or expand ICP criteria"
            )
    
    def _check_title_seniority(self, lead: Dict, **kwargs) -> VerificationResult:
        """Verify title matches target seniority"""
        title = lead.get('title', '').lower()
        include_titles = [t.lower() for t in self.icp_criteria.get('titles', {}).get('include', [])]
        exclude_titles = [t.lower() for t in self.icp_criteria.get('titles', {}).get('exclude', [])]
        
        # Check for exclusions first
        for exclude in exclude_titles:
            if exclude in title:
                return VerificationResult(
                    passed=False,
                    rule_id="ICP-003",
                    rule_name="Title Seniority",
                    message=f"Title '{lead.get('title')}' contains excluded term '{exclude}'",
                    severity=Severity.WARNING,
                    suggested_fix="Target more senior contacts at this company"
                )
        
        # Check for inclusions
        for include in include_titles:
            if include in title:
                return VerificationResult(
                    passed=True,
                    rule_id="ICP-003",
                    rule_name="Title Seniority",
                    message=f"Title '{lead.get('title')}' matches seniority criteria",
                    severity=Severity.INFO
                )
        
        return VerificationResult(
            passed=False,
            rule_id="ICP-003",
            rule_name="Title Seniority",
            message=f"Title '{lead.get('title')}' doesn't match target seniority",
            severity=Severity.WARNING,
            suggested_fix="Consider targeting VP, Director, or C-level contacts"
        )
    
    def _check_disqualifiers(self, lead: Dict, **kwargs) -> VerificationResult:
        """Check for disqualifying characteristics"""
        company = lead.get('company_name', '').lower()
        industry = lead.get('industry', '').lower()
        
        disqualifiers = [d.lower() for d in self.icp_criteria.get('disqualifiers', [])]
        
        for disq in disqualifiers:
            if disq in company or disq in industry:
                return VerificationResult(
                    passed=False,
                    rule_id="ICP-004",
                    rule_name="Disqualifier Check",
                    message=f"Company matches disqualifier: '{disq}'",
                    severity=Severity.ERROR,
                    suggested_fix="Exclude this lead from campaign"
                )
        
        return VerificationResult(
            passed=True,
            rule_id="ICP-004",
            rule_name="Disqualifier Check",
            message="No disqualifiers found",
            severity=Severity.INFO
        )
    
    # === Email Compliance Checks ===
    
    def _check_unsubscribe(self, lead: Dict, email_content: str = "", **kwargs) -> VerificationResult:
        """Verify email contains unsubscribe mechanism"""
        if not email_content:
            return VerificationResult(
                passed=True,
                rule_id="EMAIL-001",
                rule_name="Unsubscribe Link",
                message="No email content to check (skipped)",
                severity=Severity.INFO
            )
        
        email_lower = email_content.lower()
        
        for pattern in self.UNSUBSCRIBE_PATTERNS:
            if re.search(pattern, email_lower):
                return VerificationResult(
                    passed=True,
                    rule_id="EMAIL-001",
                    rule_name="Unsubscribe Link",
                    message="Unsubscribe mechanism found",
                    severity=Severity.INFO
                )
        
        return VerificationResult(
            passed=False,
            rule_id="EMAIL-001",
            rule_name="Unsubscribe Link",
            message="No unsubscribe link/text found (CAN-SPAM violation)",
            severity=Severity.ERROR,
            suggested_fix="Add unsubscribe link or 'Reply STOP to unsubscribe' text"
        )
    
    def _check_email_length(self, lead: Dict, email_content: str = "", **kwargs) -> VerificationResult:
        """Verify email is within optimal length"""
        if not email_content:
            return VerificationResult(
                passed=True,
                rule_id="EMAIL-002",
                rule_name="Email Length",
                message="No email content to check (skipped)",
                severity=Severity.INFO
            )
        
        word_count = len(email_content.split())
        
        if 50 <= word_count <= 300:
            return VerificationResult(
                passed=True,
                rule_id="EMAIL-002",
                rule_name="Email Length",
                message=f"Email length ({word_count} words) is optimal",
                severity=Severity.INFO
            )
        elif word_count < 50:
            return VerificationResult(
                passed=False,
                rule_id="EMAIL-002",
                rule_name="Email Length",
                message=f"Email too short ({word_count} words, minimum 50)",
                severity=Severity.WARNING,
                suggested_fix="Add more context or value proposition"
            )
        else:
            return VerificationResult(
                passed=False,
                rule_id="EMAIL-002",
                rule_name="Email Length",
                message=f"Email too long ({word_count} words, maximum 300)",
                severity=Severity.WARNING,
                suggested_fix="Shorten email for better engagement"
            )
    
    def _check_spam_words(self, lead: Dict, email_content: str = "", **kwargs) -> VerificationResult:
        """Check for spam trigger words"""
        if not email_content:
            return VerificationResult(
                passed=True,
                rule_id="EMAIL-003",
                rule_name="Spam Words",
                message="No email content to check (skipped)",
                severity=Severity.INFO
            )
        
        email_lower = email_content.lower()
        found_spam = []
        
        for word in self.SPAM_WORDS:
            if word in email_lower:
                found_spam.append(word)
        
        if not found_spam:
            return VerificationResult(
                passed=True,
                rule_id="EMAIL-003",
                rule_name="Spam Words",
                message="No spam trigger words found",
                severity=Severity.INFO
            )
        else:
            return VerificationResult(
                passed=False,
                rule_id="EMAIL-003",
                rule_name="Spam Words",
                message=f"Found spam trigger words: {', '.join(found_spam)}",
                severity=Severity.WARNING,
                suggested_fix="Replace spam words with professional alternatives"
            )
    
    # === Personalization Checks ===
    
    def _check_personalization_resolved(self, lead: Dict, email_content: str = "", **kwargs) -> VerificationResult:
        """Verify all personalization tokens are resolved"""
        if not email_content:
            return VerificationResult(
                passed=True,
                rule_id="PERS-001",
                rule_name="Personalization Resolved",
                message="No email content to check (skipped)",
                severity=Severity.INFO
            )
        
        # Look for unresolved tokens like {first_name}, {{company}}, etc.
        unresolved = re.findall(r'\{+\s*\w+\s*\}+', email_content)
        
        if not unresolved:
            return VerificationResult(
                passed=True,
                rule_id="PERS-001",
                rule_name="Personalization Resolved",
                message="All personalization tokens resolved",
                severity=Severity.INFO
            )
        else:
            return VerificationResult(
                passed=False,
                rule_id="PERS-001",
                rule_name="Personalization Resolved",
                message=f"Unresolved tokens: {', '.join(unresolved)}",
                severity=Severity.ERROR,
                suggested_fix="Ensure all tokens are mapped to lead data"
            )
    
    def _check_company_name_match(self, lead: Dict, email_content: str = "", **kwargs) -> VerificationResult:
        """Verify company name in email matches lead record"""
        if not email_content:
            return VerificationResult(
                passed=True,
                rule_id="PERS-002",
                rule_name="Company Name Match",
                message="No email content to check (skipped)",
                severity=Severity.INFO
            )
        
        company = lead.get('company_name', '')
        if not company:
            return VerificationResult(
                passed=False,
                rule_id="PERS-002",
                rule_name="Company Name Match",
                message="Lead has no company name",
                severity=Severity.WARNING
            )
        
        if company.lower() in email_content.lower():
            return VerificationResult(
                passed=True,
                rule_id="PERS-002",
                rule_name="Company Name Match",
                message=f"Company '{company}' found in email",
                severity=Severity.INFO
            )
        else:
            return VerificationResult(
                passed=False,
                rule_id="PERS-002",
                rule_name="Company Name Match",
                message=f"Company '{company}' not found in email (possible wrong personalization)",
                severity=Severity.ERROR,
                suggested_fix="Verify company name mapping is correct"
            )
    
    def _check_first_name_match(self, lead: Dict, email_content: str = "", **kwargs) -> VerificationResult:
        """Verify first name in email matches lead record"""
        if not email_content:
            return VerificationResult(
                passed=True,
                rule_id="PERS-003",
                rule_name="First Name Match",
                message="No email content to check (skipped)",
                severity=Severity.INFO
            )
        
        first_name = lead.get('first_name', '')
        if not first_name:
            # Try to extract from full name
            full_name = lead.get('name', lead.get('contact_name', ''))
            if full_name:
                first_name = full_name.split()[0] if full_name else ''
        
        if not first_name:
            return VerificationResult(
                passed=False,
                rule_id="PERS-003",
                rule_name="First Name Match",
                message="Lead has no first name",
                severity=Severity.WARNING
            )
        
        if first_name.lower() in email_content.lower():
            return VerificationResult(
                passed=True,
                rule_id="PERS-003",
                rule_name="First Name Match",
                message=f"First name '{first_name}' found in email",
                severity=Severity.INFO
            )
        else:
            return VerificationResult(
                passed=False,
                rule_id="PERS-003",
                rule_name="First Name Match",
                message=f"First name '{first_name}' not found in email",
                severity=Severity.ERROR,
                suggested_fix="Verify first name mapping is correct"
            )
    
    # === Data Integrity Checks ===
    
    def _check_email_format(self, lead: Dict, **kwargs) -> VerificationResult:
        """Verify lead email is properly formatted"""
        email = lead.get('email', '')
        
        if not email:
            return VerificationResult(
                passed=False,
                rule_id="DATA-001",
                rule_name="Email Format Valid",
                message="Lead has no email address",
                severity=Severity.ERROR
            )
        
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        if re.match(email_pattern, email):
            return VerificationResult(
                passed=True,
                rule_id="DATA-001",
                rule_name="Email Format Valid",
                message=f"Email '{email}' is valid format",
                severity=Severity.INFO
            )
        else:
            return VerificationResult(
                passed=False,
                rule_id="DATA-001",
                rule_name="Email Format Valid",
                message=f"Email '{email}' has invalid format",
                severity=Severity.ERROR,
                suggested_fix="Verify email or exclude from campaign"
            )
    
    def _check_required_fields(self, lead: Dict, **kwargs) -> VerificationResult:
        """Verify all required fields are populated"""
        required_fields = ['email', 'first_name', 'company_name']
        optional_but_recommended = ['title', 'industry', 'employee_count']
        
        missing_required = []
        missing_recommended = []
        
        for field in required_fields:
            value = lead.get(field)
            # Also check for 'name' as alternative to 'first_name'
            if field == 'first_name' and not value:
                value = lead.get('name', lead.get('contact_name'))
            if not value:
                missing_required.append(field)
        
        for field in optional_but_recommended:
            if not lead.get(field):
                missing_recommended.append(field)
        
        if missing_required:
            return VerificationResult(
                passed=False,
                rule_id="DATA-002",
                rule_name="Required Fields Present",
                message=f"Missing required fields: {', '.join(missing_required)}",
                severity=Severity.ERROR,
                suggested_fix="Enrich lead data before adding to campaign"
            )
        elif missing_recommended:
            return VerificationResult(
                passed=True,
                rule_id="DATA-002",
                rule_name="Required Fields Present",
                message=f"All required fields present (missing optional: {', '.join(missing_recommended)})",
                severity=Severity.INFO
            )
        else:
            return VerificationResult(
                passed=True,
                rule_id="DATA-002",
                rule_name="Required Fields Present",
                message="All required and recommended fields present",
                severity=Severity.INFO
            )
    
    # === Main Verification Methods ===
    
    def verify_icp_match(self, lead: Dict) -> List[VerificationResult]:
        """Run all ICP-related verifications"""
        icp_rules = [r for r in self.rules if r.category == "icp" and r.enabled]
        results = []
        
        for rule in icp_rules:
            result = rule.check_function(lead)
            results.append(result)
        
        return results
    
    def verify_email_compliance(self, email_content: str, lead: Dict = None) -> List[VerificationResult]:
        """Run all email compliance verifications"""
        compliance_rules = [r for r in self.rules if r.category == "compliance" and r.enabled]
        results = []
        
        for rule in compliance_rules:
            result = rule.check_function(lead or {}, email_content=email_content)
            results.append(result)
        
        return results
    
    def verify_personalization(self, email_content: str, lead: Dict) -> List[VerificationResult]:
        """Run all personalization verifications"""
        pers_rules = [r for r in self.rules if r.category == "personalization" and r.enabled]
        results = []
        
        for rule in pers_rules:
            result = rule.check_function(lead, email_content=email_content)
            results.append(result)
        
        return results
    
    def run_all_verifications(
        self,
        lead: Dict,
        email_content: str = "",
        agent_name: str = "unknown",
        output_id: str = None
    ) -> VerificationReport:
        """
        Run all applicable verification checks
        
        Args:
            lead: Lead data dictionary
            email_content: Optional email content to verify
            agent_name: Name of the agent that produced this output
            output_id: Unique identifier for this output
            
        Returns:
            VerificationReport with all results
        """
        logger.info(f"\n🔍 Running verification for {lead.get('email', 'unknown lead')}...")
        
        if not output_id:
            output_id = f"OUT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        all_results = []
        
        # Run all enabled rules
        for rule in self.rules:
            if not rule.enabled:
                continue
            
            try:
                result = rule.check_function(lead, email_content=email_content)
                all_results.append(result)
            except Exception as e:
                logger.error(f"Error in rule {rule.id}: {e}")
                all_results.append(VerificationResult(
                    passed=False,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    message=f"Rule execution error: {str(e)}",
                    severity=Severity.ERROR
                ))
        
        # Calculate summary
        passed = sum(1 for r in all_results if r.passed)
        failed = sum(1 for r in all_results if not r.passed and r.severity == Severity.ERROR)
        warnings = sum(1 for r in all_results if not r.passed and r.severity == Severity.WARNING)
        
        # Determine overall status
        if failed > 0:
            overall_status = "failed"
        elif warnings > 0:
            overall_status = "warning"
        else:
            overall_status = "passed"
        
        report = VerificationReport(
            output_id=output_id,
            agent_name=agent_name,
            timestamp=self.timestamp.isoformat(),
            total_checks=len(all_results),
            passed=passed,
            failed=failed,
            warnings=warnings,
            results=all_results,
            overall_status=overall_status
        )
        
        # Log results
        logger.info(f"  Total: {len(all_results)}, Passed: {passed}, Failed: {failed}, Warnings: {warnings}")
        logger.info(f"  Status: {overall_status.upper()}")
        
        # Save to log
        self._save_verification_log(report)
        
        return report
    
    def get_violations(self, results: List[VerificationResult]) -> List[VerificationResult]:
        """Filter to only failed verifications"""
        return [r for r in results if not r.passed]
    
    def _save_verification_log(self, report: VerificationReport) -> None:
        """Save verification report to log file"""
        log_file = self.hive_mind_path / "verification_log.json"
        
        # Load existing log
        if log_file.exists():
            with open(log_file) as f:
                log_data = json.load(f)
        else:
            log_data = {"reports": []}
        
        # Append new report
        log_data["reports"].append(report.to_dict())
        
        # Keep last 1000 reports
        log_data["reports"] = log_data["reports"][-1000:]
        log_data["updated_at"] = datetime.now().isoformat()
        
        with open(log_file, 'w') as f:
            json.dump(log_data, f, indent=2)


def main():
    """Test verification hooks"""
    print("=" * 60)
    print("🔍 VERIFICATION HOOKS TEST")
    print("=" * 60)
    
    hooks = VerificationHooks()
    
    # Test lead (good)
    good_lead = {
        "email": "john.smith@acmecorp.com",
        "first_name": "John",
        "last_name": "Smith",
        "company_name": "ACME Corporation",
        "title": "VP of Sales",
        "industry": "B2B SaaS",
        "employee_count": 150
    }
    
    # Test lead (bad)
    bad_lead = {
        "email": "invalid-email",
        "first_name": "",
        "company_name": "Freelance Consulting",
        "title": "Intern",
        "industry": "Consulting",
        "employee_count": 5
    }
    
    # Test email content
    good_email = """
Hi John,

I noticed ACME Corporation has been growing rapidly. 
We help companies like yours automate revenue operations.

Would you be open to a quick call next week?

Best,
Chris

P.S. Reply STOP to unsubscribe
"""

    bad_email = """
Hi {first_name},

FREE MONEY! Act now for a LIMITED TIME offer!
Click here to GUARANTEE your success!

{company_name} needs this!
"""

    print("\n1. Testing good lead with good email:")
    print("-" * 40)
    report = hooks.run_all_verifications(good_lead, good_email, "CRAFTER")
    print(f"\n   Result: {report.overall_status.upper()}")
    
    print("\n2. Testing bad lead with bad email:")
    print("-" * 40)
    report = hooks.run_all_verifications(bad_lead, bad_email, "CRAFTER")
    print(f"\n   Result: {report.overall_status.upper()}")
    
    violations = hooks.get_violations(report.results)
    if violations:
        print("\n   Violations:")
        for v in violations:
            print(f"   - [{v.severity.value}] {v.rule_name}: {v.message}")
    
    print("\n" + "=" * 60)
    print("✓ VERIFICATION HOOKS TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
