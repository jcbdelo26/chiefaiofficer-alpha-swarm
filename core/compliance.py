"""
Compliance Validation System
============================
Validates campaigns against CAN-SPAM, brand safety, LinkedIn ToS, and GDPR requirements.
"""

import re
import json
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Literal
from pathlib import Path
from enum import Enum


class ComplianceCategory(Enum):
    CAN_SPAM = "can_spam"
    BRAND_SAFETY = "brand_safety"
    LINKEDIN_TOS = "linkedin_tos"
    GDPR = "gdpr"


@dataclass
class ValidationIssue:
    """Single validation issue."""
    category: str
    severity: Literal["warning", "failure"]
    code: str
    message: str
    location: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of campaign validation."""
    passed: bool
    warnings: List[ValidationIssue] = field(default_factory=list)
    failures: List[ValidationIssue] = field(default_factory=list)
    validated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "warnings": [asdict(w) for w in self.warnings],
            "failures": [asdict(f) for f in self.failures],
            "validated_at": self.validated_at
        }


class CANSPAMValidator:
    """Validates email content for CAN-SPAM compliance."""
    
    REQUIRED_TOKENS = [
        ("{{ sender.physical_address }}", "sender.physical_address"),
        ("{{sender.physical_address}}", "sender.physical_address"),
    ]
    
    UNSUBSCRIBE_PATTERNS = [
        r"\{\{\s*sender\.unsubscribe_link\s*\}\}",
        r"unsubscribe",
        r"opt[- ]?out",
        r"remove me",
    ]
    
    DECEPTIVE_SUBJECT_PATTERNS = [
        (r"^re:\s", "Fake reply thread"),
        (r"^fwd?:\s", "Fake forward"),
        (r"urgent!+\s*$", "Fake urgency"),
        (r"you'?ve?\s+won", "Prize claim"),
        (r"act\s+now", "Pressure tactic"),
        (r"limited\s+time\s+only", "Artificial scarcity"),
    ]
    
    def validate(self, campaign: Dict[str, Any]) -> List[ValidationIssue]:
        issues = []
        
        for step_idx, step in enumerate(campaign.get("sequence", [])):
            if step.get("channel") != "email":
                continue
            
            location = f"sequence[{step_idx}]"
            
            # Check for physical address
            body_a = step.get("body_a", "")
            body_b = step.get("body_b", "")
            combined_body = f"{body_a} {body_b}"
            
            has_address = any(
                token in combined_body 
                for token, _ in self.REQUIRED_TOKENS
            )
            if not has_address:
                issues.append(ValidationIssue(
                    category=ComplianceCategory.CAN_SPAM.value,
                    severity="failure",
                    code="CANSPAM_NO_ADDRESS",
                    message="Email must include sender physical address",
                    location=location
                ))
            
            # Check for unsubscribe mechanism
            has_unsubscribe = any(
                re.search(pattern, combined_body, re.IGNORECASE)
                for pattern in self.UNSUBSCRIBE_PATTERNS
            )
            if not has_unsubscribe:
                issues.append(ValidationIssue(
                    category=ComplianceCategory.CAN_SPAM.value,
                    severity="failure",
                    code="CANSPAM_NO_UNSUBSCRIBE",
                    message="Email must include unsubscribe mechanism",
                    location=location
                ))
            
            # Check subject lines for deceptive patterns
            for subject_field in ["subject_a", "subject_b"]:
                subject = step.get(subject_field, "")
                for pattern, description in self.DECEPTIVE_SUBJECT_PATTERNS:
                    if re.search(pattern, subject, re.IGNORECASE):
                        issues.append(ValidationIssue(
                            category=ComplianceCategory.CAN_SPAM.value,
                            severity="failure",
                            code="CANSPAM_DECEPTIVE_SUBJECT",
                            message=f"Subject line may be deceptive: {description}",
                            location=f"{location}.{subject_field}"
                        ))
            
            # Check From header accuracy (if present)
            from_header = step.get("from_header", "")
            sender_name = campaign.get("metadata", {}).get("sender_name", "")
            if from_header and sender_name:
                if sender_name.lower() not in from_header.lower():
                    issues.append(ValidationIssue(
                        category=ComplianceCategory.CAN_SPAM.value,
                        severity="warning",
                        code="CANSPAM_FROM_MISMATCH",
                        message="From header may not accurately identify sender",
                        location=location
                    ))
        
        return issues


class BrandSafetyValidator:
    """Validates content for brand safety guidelines."""
    
    PROHIBITED_TERMS = [
        (r"\bguarantee[ds]?\b(?!\*)", "Unqualified guarantee claim"),
        (r"\bonly\s+(we|company|solution)\b", "'Only' claim without evidence"),
        (r"\bbest\s+(in\s+class|solution|platform)\b(?!\*)", "'Best' claim without qualification"),
        (r"\b#1\b", "Ranking claim without source"),
        (r"\b100%\s+(success|satisfaction)\b", "Absolute percentage claim"),
    ]
    
    COMPETITOR_NAMES = [
        "gong", "chorus", "salesloft", "outreach", "apollo",
        "zoominfo", "6sense", "bombora", "clearbit", "lusha"
    ]
    
    PLACEHOLDER_PATTERN = r"\{\{[^}]+\}\}"
    
    def validate(self, campaign: Dict[str, Any], rendered_content: Optional[Dict[str, str]] = None) -> List[ValidationIssue]:
        issues = []
        
        for step_idx, step in enumerate(campaign.get("sequence", [])):
            location = f"sequence[{step_idx}]"
            
            # Check subject lines
            for subject_field in ["subject_a", "subject_b"]:
                subject = step.get(subject_field, "")
                
                # No ALL CAPS subjects
                words = subject.split()
                caps_words = [w for w in words if w.isupper() and len(w) > 2]
                if len(caps_words) > 2 or (len(caps_words) > 0 and len(caps_words) / max(len(words), 1) > 0.5):
                    issues.append(ValidationIssue(
                        category=ComplianceCategory.BRAND_SAFETY.value,
                        severity="failure",
                        code="BRAND_ALLCAPS_SUBJECT",
                        message="Subject line contains excessive ALL CAPS",
                        location=f"{location}.{subject_field}"
                    ))
                
                # No competitor names in subject
                subject_lower = subject.lower()
                for competitor in self.COMPETITOR_NAMES:
                    if competitor in subject_lower:
                        issues.append(ValidationIssue(
                            category=ComplianceCategory.BRAND_SAFETY.value,
                            severity="warning",
                            code="BRAND_COMPETITOR_SUBJECT",
                            message=f"Subject line mentions competitor: {competitor}",
                            location=f"{location}.{subject_field}"
                        ))
            
            # Check body content
            for body_field in ["body_a", "body_b"]:
                body = step.get(body_field, "")
                
                # Prohibited terms - but skip if body contains asterisk (qualified claims)
                has_asterisk_qualifier = "*" in body
                for pattern, description in self.PROHIBITED_TERMS:
                    if re.search(pattern, body, re.IGNORECASE) and not has_asterisk_qualifier:
                        issues.append(ValidationIssue(
                            category=ComplianceCategory.BRAND_SAFETY.value,
                            severity="warning",
                            code="BRAND_PROHIBITED_TERM",
                            message=f"Contains prohibited term: {description}",
                            location=f"{location}.{body_field}"
                        ))
                
                # Fake urgency patterns
                urgency_patterns = [
                    r"act\s+now\s+or",
                    r"expires?\s+(today|tonight|soon)",
                    r"last\s+chance",
                    r"don'?t\s+miss\s+out",
                    r"hurry\s+while",
                ]
                for pattern in urgency_patterns:
                    if re.search(pattern, body, re.IGNORECASE):
                        issues.append(ValidationIssue(
                            category=ComplianceCategory.BRAND_SAFETY.value,
                            severity="warning",
                            code="BRAND_FAKE_URGENCY",
                            message="Content contains fake urgency language",
                            location=f"{location}.{body_field}"
                        ))
                
                # Misleading statistics
                stats_pattern = r"\b\d{2,3}%\s+(of\s+)?(companies|customers|users|clients)"
                if re.search(stats_pattern, body, re.IGNORECASE):
                    # Check if there's a citation or source
                    if not re.search(r"\*|source:|according to|study|report", body, re.IGNORECASE):
                        issues.append(ValidationIssue(
                            category=ComplianceCategory.BRAND_SAFETY.value,
                            severity="warning",
                            code="BRAND_UNCITED_STAT",
                            message="Statistics should include source citation",
                            location=f"{location}.{body_field}"
                        ))
        
        # Check rendered content for remaining placeholders
        if rendered_content:
            for field_name, content in rendered_content.items():
                placeholders = re.findall(self.PLACEHOLDER_PATTERN, content)
                if placeholders:
                    issues.append(ValidationIssue(
                        category=ComplianceCategory.BRAND_SAFETY.value,
                        severity="failure",
                        code="BRAND_UNRENDERED_PLACEHOLDER",
                        message=f"Unrendered placeholder tokens: {', '.join(placeholders[:3])}",
                        location=field_name
                    ))
        
        return issues


class LinkedInToSValidator:
    """Validates LinkedIn activity against Terms of Service limits."""
    
    LIMITS = {
        "profiles_per_hour": 50,
        "profiles_per_day": 500,
        "connections_per_week": 100,
        "messages_per_day": 50,
    }
    
    def __init__(self, tracking_file: Optional[Path] = None, storage_path: Optional[Path] = None):
        if storage_path:
            self.tracking_file = storage_path / "linkedin_activity.json"
        elif tracking_file:
            self.tracking_file = tracking_file
        else:
            self.tracking_file = Path(".hive-mind/linkedin_activity.json")
        self._ensure_tracking_file()
    
    def _ensure_tracking_file(self):
        if not self.tracking_file.exists():
            self.tracking_file.parent.mkdir(parents=True, exist_ok=True)
            self.tracking_file.write_text(json.dumps({"actions": []}))
    
    def _load_actions(self) -> List[Dict[str, Any]]:
        try:
            data = json.loads(self.tracking_file.read_text())
            return data.get("actions", [])
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def _save_actions(self, actions: List[Dict[str, Any]]):
        self.tracking_file.write_text(json.dumps({"actions": actions}, indent=2))
    
    def record_linkedin_action(self, kind: str, ts: Optional[datetime] = None):
        """Record a LinkedIn action for rate limiting."""
        if ts is None:
            ts = datetime.now(timezone.utc)
        
        actions = self._load_actions()
        actions.append({
            "kind": kind,
            "timestamp": ts.isoformat()
        })
        
        # Prune old actions (older than 7 days)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        actions = [
            a for a in actions
            if datetime.fromisoformat(a["timestamp"].replace("Z", "+00:00")) > cutoff
        ]
        
        self._save_actions(actions)
    
    def _count_actions(self, kind: str, since: datetime) -> int:
        actions = self._load_actions()
        count = 0
        for action in actions:
            if action["kind"] == kind:
                action_ts = datetime.fromisoformat(action["timestamp"].replace("Z", "+00:00"))
                if action_ts > since:
                    count += 1
        return count
    
    def check_limits(self) -> List[ValidationIssue]:
        """Check current LinkedIn activity against limits."""
        issues = []
        now = datetime.now(timezone.utc)
        
        # Profiles per hour
        hourly_profiles = self._count_actions("profile_view", now - timedelta(hours=1))
        if hourly_profiles >= self.LIMITS["profiles_per_hour"]:
            issues.append(ValidationIssue(
                category=ComplianceCategory.LINKEDIN_TOS.value,
                severity="failure",
                code="LINKEDIN_HOURLY_LIMIT",
                message=f"Hourly profile view limit reached ({hourly_profiles}/{self.LIMITS['profiles_per_hour']})",
            ))
        elif hourly_profiles >= self.LIMITS["profiles_per_hour"] * 0.8:
            issues.append(ValidationIssue(
                category=ComplianceCategory.LINKEDIN_TOS.value,
                severity="warning",
                code="LINKEDIN_HOURLY_WARNING",
                message=f"Approaching hourly profile limit ({hourly_profiles}/{self.LIMITS['profiles_per_hour']})",
            ))
        
        # Profiles per day
        daily_profiles = self._count_actions("profile_view", now - timedelta(days=1))
        if daily_profiles >= self.LIMITS["profiles_per_day"]:
            issues.append(ValidationIssue(
                category=ComplianceCategory.LINKEDIN_TOS.value,
                severity="failure",
                code="LINKEDIN_DAILY_LIMIT",
                message=f"Daily profile view limit reached ({daily_profiles}/{self.LIMITS['profiles_per_day']})",
            ))
        
        # Connections per week
        weekly_connections = self._count_actions("connection_request", now - timedelta(weeks=1))
        if weekly_connections >= self.LIMITS["connections_per_week"]:
            issues.append(ValidationIssue(
                category=ComplianceCategory.LINKEDIN_TOS.value,
                severity="failure",
                code="LINKEDIN_CONNECTION_LIMIT",
                message=f"Weekly connection limit reached ({weekly_connections}/{self.LIMITS['connections_per_week']})",
            ))
        
        # Messages per day
        daily_messages = self._count_actions("message", now - timedelta(days=1))
        if daily_messages >= self.LIMITS["messages_per_day"]:
            issues.append(ValidationIssue(
                category=ComplianceCategory.LINKEDIN_TOS.value,
                severity="failure",
                code="LINKEDIN_MESSAGE_LIMIT",
                message=f"Daily message limit reached ({daily_messages}/{self.LIMITS['messages_per_day']})",
            ))
        
        return issues
    
    def validate(self, campaign: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate campaign won't exceed LinkedIn limits."""
        issues = self.check_limits()
        
        # Count LinkedIn actions in campaign
        linkedin_messages = 0
        for step in campaign.get("sequence", []):
            if step.get("channel") == "linkedin":
                linkedin_messages += len(campaign.get("leads", []))
        
        if linkedin_messages > 0:
            now = datetime.now(timezone.utc)
            current_daily = self._count_actions("message", now - timedelta(days=1))
            projected = current_daily + linkedin_messages
            
            if projected > self.LIMITS["messages_per_day"]:
                issues.append(ValidationIssue(
                    category=ComplianceCategory.LINKEDIN_TOS.value,
                    severity="failure",
                    code="LINKEDIN_CAMPAIGN_EXCEEDS",
                    message=f"Campaign would exceed daily message limit ({projected}/{self.LIMITS['messages_per_day']})",
                ))
        
        return issues


class GDPRValidator:
    """Validates leads have proper GDPR compliance documentation."""
    
    VALID_LEGAL_BASES = [
        "consent",
        "contract",
        "legal_obligation",
        "vital_interests",
        "public_task",
        "legitimate_interests",
    ]
    
    def validate_lead(self, lead: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate a single lead for GDPR compliance."""
        issues = []
        lead_id = lead.get("lead_id", "unknown")
        
        # Check legal basis
        legal_basis = lead.get("legal_basis")
        if not legal_basis:
            issues.append(ValidationIssue(
                category=ComplianceCategory.GDPR.value,
                severity="failure",
                code="GDPR_NO_LEGAL_BASIS",
                message="Lead has no documented legal basis for processing",
                location=f"lead:{lead_id}"
            ))
        elif legal_basis not in self.VALID_LEGAL_BASES:
            issues.append(ValidationIssue(
                category=ComplianceCategory.GDPR.value,
                severity="warning",
                code="GDPR_INVALID_LEGAL_BASIS",
                message=f"Legal basis '{legal_basis}' is not standard",
                location=f"lead:{lead_id}"
            ))
        
        # Check data collection timestamp
        data_collected_at = lead.get("data_collected_at")
        if not data_collected_at:
            issues.append(ValidationIssue(
                category=ComplianceCategory.GDPR.value,
                severity="failure",
                code="GDPR_NO_COLLECTION_TIMESTAMP",
                message="Lead has no data collection timestamp",
                location=f"lead:{lead_id}"
            ))
        
        # Check consent documentation for consent-based processing
        if legal_basis == "consent":
            consent_doc = lead.get("consent_documentation")
            if not consent_doc:
                issues.append(ValidationIssue(
                    category=ComplianceCategory.GDPR.value,
                    severity="failure",
                    code="GDPR_NO_CONSENT_DOC",
                    message="Consent-based processing requires consent documentation",
                    location=f"lead:{lead_id}"
                ))
            else:
                # Validate consent documentation fields
                required_fields = ["consent_given_at", "consent_source", "consent_scope"]
                for field in required_fields:
                    if field not in consent_doc:
                        issues.append(ValidationIssue(
                            category=ComplianceCategory.GDPR.value,
                            severity="warning",
                            code="GDPR_INCOMPLETE_CONSENT",
                            message=f"Consent documentation missing '{field}'",
                            location=f"lead:{lead_id}"
                        ))
        
        return issues
    
    def validate(self, campaign: Dict[str, Any]) -> List[ValidationIssue]:
        """Validate all leads in a campaign for GDPR compliance."""
        issues = []
        
        for lead in campaign.get("leads", []):
            issues.extend(self.validate_lead(lead))
        
        return issues


def validate_campaign(
    campaign: Dict[str, Any],
    rendered_content: Optional[Dict[str, str]] = None,
    skip_linkedin: bool = False
) -> ValidationResult:
    """
    Run all compliance validators on a campaign.
    
    Args:
        campaign: Campaign data dictionary
        rendered_content: Optional dict of field_name -> rendered content for placeholder check
        skip_linkedin: Skip LinkedIn ToS validation (for email-only campaigns)
    
    Returns:
        ValidationResult with passed status, warnings, and failures
    """
    all_warnings = []
    all_failures = []
    
    # CAN-SPAM validation
    canspam = CANSPAMValidator()
    canspam_issues = canspam.validate(campaign)
    
    # Brand safety validation
    brand = BrandSafetyValidator()
    brand_issues = brand.validate(campaign, rendered_content)
    
    # LinkedIn ToS validation
    linkedin_issues = []
    if not skip_linkedin:
        has_linkedin = any(
            step.get("channel") == "linkedin"
            for step in campaign.get("sequence", [])
        )
        if has_linkedin:
            linkedin = LinkedInToSValidator()
            linkedin_issues = linkedin.validate(campaign)
    
    # GDPR validation
    gdpr = GDPRValidator()
    gdpr_issues = gdpr.validate(campaign)
    
    # Aggregate all issues
    all_issues = canspam_issues + brand_issues + linkedin_issues + gdpr_issues
    
    for issue in all_issues:
        if issue.severity == "warning":
            all_warnings.append(issue)
        else:
            all_failures.append(issue)
    
    passed = len(all_failures) == 0
    
    return ValidationResult(
        passed=passed,
        warnings=all_warnings,
        failures=all_failures
    )
