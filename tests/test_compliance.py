"""
Test Compliance Validators
==========================
Unit tests for core/compliance.py validators including CAN-SPAM,
brand safety, GDPR, and LinkedIn ToS checks.

Usage:
    pytest tests/test_compliance.py -v
"""

import pytest
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.compliance import (
    CANSPAMValidator,
    BrandSafetyValidator,
    GDPRValidator,
    LinkedInToSValidator,
    ValidationIssue,
    ValidationResult,
    ComplianceCategory,
    validate_campaign,
)


@pytest.fixture
def sample_email_step():
    """Basic email step with all required elements."""
    return {
        "channel": "email",
        "subject_a": "Quick question about your sales process",
        "subject_b": "Thoughts on improving pipeline velocity?",
        "body_a": """
            Hi {{ lead.first_name }},

            I noticed your company is growing rapidly.
            
            Would you be open to a quick chat?
            
            Best,
            {{ sender.name }}
            
            {{ sender.physical_address }}
            
            {{ sender.unsubscribe_link }}
        """,
        "body_b": """
            Hi {{ lead.first_name }},

            Quick question about your outbound process.
            
            Best,
            {{ sender.name }}
            
            {{ sender.physical_address }}
            
            Unsubscribe: {{ sender.unsubscribe_link }}
        """
    }


@pytest.fixture
def sample_linkedin_step():
    """Basic LinkedIn step."""
    return {
        "channel": "linkedin",
        "message": "Hi {{ lead.first_name }}, noticed your work at {{ lead.company }}."
    }


@pytest.fixture
def sample_campaign(sample_email_step):
    """Complete sample campaign."""
    return {
        "campaign_id": "test_campaign_001",
        "name": "Test Campaign",
        "sequence": [sample_email_step],
        "leads": [],
        "metadata": {
            "sender_name": "John Smith"
        }
    }


@pytest.fixture
def sample_lead_gdpr_compliant():
    """GDPR-compliant lead."""
    return {
        "lead_id": "lead_001",
        "email": "test@example.com",
        "first_name": "Test",
        "last_name": "User",
        "legal_basis": "legitimate_interests",
        "data_collected_at": datetime.now(timezone.utc).isoformat()
    }


@pytest.fixture
def sample_lead_consent_based():
    """Lead with consent-based processing."""
    return {
        "lead_id": "lead_002",
        "email": "consent@example.com",
        "first_name": "Consent",
        "last_name": "User",
        "legal_basis": "consent",
        "data_collected_at": datetime.now(timezone.utc).isoformat(),
        "consent_documentation": {
            "consent_given_at": datetime.now(timezone.utc).isoformat(),
            "consent_source": "website_form",
            "consent_scope": "marketing_emails"
        }
    }


class TestCANSPAMPhysicalAddress:
    """Tests for CAN-SPAM physical address requirement."""
    
    def test_canspam_physical_address_required_passes(self, sample_campaign):
        """Email with physical address should pass."""
        validator = CANSPAMValidator()
        issues = validator.validate(sample_campaign)
        
        address_issues = [i for i in issues if i.code == "CANSPAM_NO_ADDRESS"]
        assert len(address_issues) == 0
    
    def test_canspam_physical_address_required_fails(self):
        """Email without physical address should fail."""
        campaign = {
            "sequence": [{
                "channel": "email",
                "subject_a": "Hello",
                "body_a": "Just a message with no address. {{ sender.unsubscribe_link }}",
                "body_b": "Another version without address. Unsubscribe here."
            }]
        }
        
        validator = CANSPAMValidator()
        issues = validator.validate(campaign)
        
        address_issues = [i for i in issues if i.code == "CANSPAM_NO_ADDRESS"]
        assert len(address_issues) == 1
        assert address_issues[0].severity == "failure"
        assert address_issues[0].category == ComplianceCategory.CAN_SPAM.value


class TestCANSPAMUnsubscribe:
    """Tests for CAN-SPAM unsubscribe requirement."""
    
    def test_canspam_unsubscribe_required_passes(self, sample_campaign):
        """Email with unsubscribe should pass."""
        validator = CANSPAMValidator()
        issues = validator.validate(sample_campaign)
        
        unsub_issues = [i for i in issues if i.code == "CANSPAM_NO_UNSUBSCRIBE"]
        assert len(unsub_issues) == 0
    
    def test_canspam_unsubscribe_required_fails(self):
        """Email without unsubscribe should fail."""
        campaign = {
            "sequence": [{
                "channel": "email",
                "subject_a": "Hello",
                "body_a": "Just a message {{ sender.physical_address }}",
                "body_b": "Another version {{ sender.physical_address }}"
            }]
        }
        
        validator = CANSPAMValidator()
        issues = validator.validate(campaign)
        
        unsub_issues = [i for i in issues if i.code == "CANSPAM_NO_UNSUBSCRIBE"]
        assert len(unsub_issues) == 1
        assert unsub_issues[0].severity == "failure"
    
    def test_canspam_unsubscribe_variations(self):
        """Various unsubscribe patterns should pass."""
        patterns = [
            "{{ sender.unsubscribe_link }}",
            "Click here to unsubscribe",
            "Opt-out of future emails",
            "opt out here",
            "Remove me from list"
        ]
        
        validator = CANSPAMValidator()
        
        for pattern in patterns:
            campaign = {
                "sequence": [{
                    "channel": "email",
                    "subject_a": "Test",
                    "body_a": f"Message {{ sender.physical_address }} {pattern}"
                }]
            }
            issues = validator.validate(campaign)
            unsub_issues = [i for i in issues if i.code == "CANSPAM_NO_UNSUBSCRIBE"]
            assert len(unsub_issues) == 0, f"Pattern '{pattern}' should be recognized as unsubscribe"


class TestBrandSafetyProhibitedTerms:
    """Tests for brand safety prohibited terms."""
    
    def test_brand_safety_prohibited_terms_detected(self):
        """Prohibited terms should be flagged."""
        campaign = {
            "sequence": [{
                "channel": "email",
                "subject_a": "Test",
                "body_a": "We guarantee results. Only we can solve this problem."
            }]
        }
        
        validator = BrandSafetyValidator()
        issues = validator.validate(campaign)
        
        prohibited_issues = [i for i in issues if i.code == "BRAND_PROHIBITED_TERM"]
        assert len(prohibited_issues) >= 1
    
    def test_brand_safety_best_claim(self):
        """'Best in class' without qualification should be flagged."""
        campaign = {
            "sequence": [{
                "channel": "email",
                "subject_a": "Test",
                "body_a": "Our best in class solution helps companies grow."
            }]
        }
        
        validator = BrandSafetyValidator()
        issues = validator.validate(campaign)
        
        prohibited_issues = [i for i in issues if i.code == "BRAND_PROHIBITED_TERM"]
        assert len(prohibited_issues) >= 1
    
    def test_brand_safety_qualified_claims_pass(self):
        """Qualified claims with asterisk should pass."""
        campaign = {
            "sequence": [{
                "channel": "email",
                "subject_a": "Test",
                "body_a": "We guarantee results* (*based on customer surveys). Best in class* solution."
            }]
        }
        
        validator = BrandSafetyValidator()
        issues = validator.validate(campaign)
        
        prohibited_issues = [i for i in issues if i.code == "BRAND_PROHIBITED_TERM"]
        assert len(prohibited_issues) == 0


class TestBrandSafetyCompetitorSubject:
    """Tests for competitor mentions in subject lines."""
    
    def test_brand_safety_competitor_in_subject(self):
        """Competitor name in subject should be flagged."""
        campaign = {
            "sequence": [{
                "channel": "email",
                "subject_a": "Better than Gong for sales calls",
                "subject_b": "Outreach alternative you'll love",
                "body_a": "Regular body content",
                "body_b": "Regular body content"
            }]
        }
        
        validator = BrandSafetyValidator()
        issues = validator.validate(campaign)
        
        competitor_issues = [i for i in issues if i.code == "BRAND_COMPETITOR_SUBJECT"]
        assert len(competitor_issues) >= 1
        assert competitor_issues[0].severity == "warning"
    
    def test_brand_safety_no_competitor_subject_passes(self, sample_campaign):
        """Subject without competitor should pass."""
        validator = BrandSafetyValidator()
        issues = validator.validate(sample_campaign)
        
        competitor_issues = [i for i in issues if i.code == "BRAND_COMPETITOR_SUBJECT"]
        assert len(competitor_issues) == 0


class TestBrandSafetyAllCapsSubject:
    """Tests for all-caps subject lines."""
    
    def test_brand_safety_all_caps_subject(self):
        """ALL CAPS subject should be flagged."""
        campaign = {
            "sequence": [{
                "channel": "email",
                "subject_a": "URGENT ACTION REQUIRED NOW",
                "body_a": "Normal body content"
            }]
        }
        
        validator = BrandSafetyValidator()
        issues = validator.validate(campaign)
        
        caps_issues = [i for i in issues if i.code == "BRAND_ALLCAPS_SUBJECT"]
        assert len(caps_issues) == 1
        assert caps_issues[0].severity == "failure"
    
    def test_brand_safety_normal_caps_passes(self, sample_campaign):
        """Normal capitalization should pass."""
        validator = BrandSafetyValidator()
        issues = validator.validate(sample_campaign)
        
        caps_issues = [i for i in issues if i.code == "BRAND_ALLCAPS_SUBJECT"]
        assert len(caps_issues) == 0
    
    def test_brand_safety_single_caps_word_passes(self):
        """Single caps word (like acronym) should pass."""
        campaign = {
            "sequence": [{
                "channel": "email",
                "subject_a": "How our API helps your team",
                "body_a": "Normal body content"
            }]
        }
        
        validator = BrandSafetyValidator()
        issues = validator.validate(campaign)
        
        caps_issues = [i for i in issues if i.code == "BRAND_ALLCAPS_SUBJECT"]
        assert len(caps_issues) == 0


class TestGDPRLegalBasis:
    """Tests for GDPR legal basis requirement."""
    
    def test_gdpr_legal_basis_required_passes(self, sample_lead_gdpr_compliant):
        """Lead with legal basis should pass."""
        campaign = {
            "sequence": [],
            "leads": [sample_lead_gdpr_compliant]
        }
        
        validator = GDPRValidator()
        issues = validator.validate(campaign)
        
        legal_basis_issues = [i for i in issues if i.code == "GDPR_NO_LEGAL_BASIS"]
        assert len(legal_basis_issues) == 0
    
    def test_gdpr_legal_basis_required_fails(self):
        """Lead without legal basis should fail."""
        lead = {
            "lead_id": "lead_no_basis",
            "email": "test@example.com",
            "data_collected_at": datetime.now(timezone.utc).isoformat()
        }
        
        campaign = {
            "sequence": [],
            "leads": [lead]
        }
        
        validator = GDPRValidator()
        issues = validator.validate(campaign)
        
        legal_basis_issues = [i for i in issues if i.code == "GDPR_NO_LEGAL_BASIS"]
        assert len(legal_basis_issues) == 1
        assert legal_basis_issues[0].severity == "failure"
    
    def test_gdpr_invalid_legal_basis_warning(self):
        """Invalid legal basis should trigger warning."""
        lead = {
            "lead_id": "lead_invalid_basis",
            "email": "test@example.com",
            "legal_basis": "because_i_said_so",
            "data_collected_at": datetime.now(timezone.utc).isoformat()
        }
        
        campaign = {
            "sequence": [],
            "leads": [lead]
        }
        
        validator = GDPRValidator()
        issues = validator.validate(campaign)
        
        invalid_basis_issues = [i for i in issues if i.code == "GDPR_INVALID_LEGAL_BASIS"]
        assert len(invalid_basis_issues) == 1
        assert invalid_basis_issues[0].severity == "warning"


class TestGDPRDataCollectedAt:
    """Tests for GDPR data collection timestamp requirement."""
    
    def test_gdpr_data_collected_at_required_passes(self, sample_lead_gdpr_compliant):
        """Lead with data_collected_at should pass."""
        campaign = {
            "sequence": [],
            "leads": [sample_lead_gdpr_compliant]
        }
        
        validator = GDPRValidator()
        issues = validator.validate(campaign)
        
        timestamp_issues = [i for i in issues if i.code == "GDPR_NO_COLLECTION_TIMESTAMP"]
        assert len(timestamp_issues) == 0
    
    def test_gdpr_data_collected_at_required_fails(self):
        """Lead without data_collected_at should fail."""
        lead = {
            "lead_id": "lead_no_timestamp",
            "email": "test@example.com",
            "legal_basis": "legitimate_interests"
        }
        
        campaign = {
            "sequence": [],
            "leads": [lead]
        }
        
        validator = GDPRValidator()
        issues = validator.validate(campaign)
        
        timestamp_issues = [i for i in issues if i.code == "GDPR_NO_COLLECTION_TIMESTAMP"]
        assert len(timestamp_issues) == 1
        assert timestamp_issues[0].severity == "failure"


class TestGDPRConsentDocumentation:
    """Tests for consent-based processing documentation."""
    
    def test_gdpr_consent_requires_documentation(self):
        """Consent-based lead without documentation should fail."""
        lead = {
            "lead_id": "lead_consent_no_doc",
            "email": "test@example.com",
            "legal_basis": "consent",
            "data_collected_at": datetime.now(timezone.utc).isoformat()
        }
        
        campaign = {
            "sequence": [],
            "leads": [lead]
        }
        
        validator = GDPRValidator()
        issues = validator.validate(campaign)
        
        consent_issues = [i for i in issues if i.code == "GDPR_NO_CONSENT_DOC"]
        assert len(consent_issues) == 1
    
    def test_gdpr_consent_with_documentation_passes(self, sample_lead_consent_based):
        """Consent-based lead with full documentation should pass."""
        campaign = {
            "sequence": [],
            "leads": [sample_lead_consent_based]
        }
        
        validator = GDPRValidator()
        issues = validator.validate(campaign)
        
        consent_issues = [i for i in issues if "CONSENT" in i.code]
        assert len(consent_issues) == 0


class TestLinkedInRateLimits:
    """Tests for LinkedIn ToS rate limit validation."""
    
    def test_linkedin_rate_limits_initial_check(self, tmp_path):
        """Fresh validator should have no limit issues."""
        validator = LinkedInToSValidator(storage_path=tmp_path)
        issues = validator.check_limits()
        
        limit_failures = [i for i in issues if i.severity == "failure"]
        assert len(limit_failures) == 0
    
    def test_linkedin_rate_limits_hourly_exceeded(self, tmp_path):
        """Exceeding hourly limit should trigger failure."""
        validator = LinkedInToSValidator(storage_path=tmp_path)
        
        for _ in range(51):
            validator.record_linkedin_action("profile_view")
        
        issues = validator.check_limits()
        
        hourly_issues = [i for i in issues if i.code == "LINKEDIN_HOURLY_LIMIT"]
        assert len(hourly_issues) == 1
        assert hourly_issues[0].severity == "failure"
    
    def test_linkedin_rate_limits_approaching_warning(self, tmp_path):
        """Approaching limit should trigger warning."""
        validator = LinkedInToSValidator(storage_path=tmp_path)
        
        for _ in range(42):
            validator.record_linkedin_action("profile_view")
        
        issues = validator.check_limits()
        
        warning_issues = [i for i in issues if i.code == "LINKEDIN_HOURLY_WARNING"]
        assert len(warning_issues) == 1
        assert warning_issues[0].severity == "warning"
    
    def test_linkedin_campaign_would_exceed_limit(self, tmp_path, sample_linkedin_step):
        """Campaign that would exceed limit should fail."""
        validator = LinkedInToSValidator(storage_path=tmp_path)
        
        for _ in range(40):
            validator.record_linkedin_action("message")
        
        campaign = {
            "sequence": [sample_linkedin_step],
            "leads": [{"lead_id": f"lead_{i}"} for i in range(20)]
        }
        
        issues = validator.validate(campaign)
        
        exceed_issues = [i for i in issues if i.code == "LINKEDIN_CAMPAIGN_EXCEEDS"]
        assert len(exceed_issues) == 1


class TestValidateCampaignIntegration:
    """Integration tests for full campaign validation."""
    
    def test_validate_campaign_passes_compliant(self, sample_campaign, sample_lead_gdpr_compliant):
        """Compliant campaign should pass."""
        sample_campaign["leads"] = [sample_lead_gdpr_compliant]
        
        result = validate_campaign(sample_campaign, skip_linkedin=True)
        
        assert result.passed is True
        assert len(result.failures) == 0
    
    def test_validate_campaign_fails_non_compliant(self):
        """Non-compliant campaign should fail."""
        campaign = {
            "sequence": [{
                "channel": "email",
                "subject_a": "URGENT BUY NOW!!!",
                "body_a": "We guarantee 100% satisfaction. Only we can help."
            }],
            "leads": [{
                "lead_id": "bad_lead",
                "email": "test@example.com"
            }]
        }
        
        result = validate_campaign(campaign, skip_linkedin=True)
        
        assert result.passed is False
        assert len(result.failures) >= 1
    
    def test_validate_campaign_returns_all_categories(self, sample_campaign, sample_lead_gdpr_compliant):
        """Validation should check all categories."""
        campaign = {
            "sequence": [{
                "channel": "email",
                "subject_a": "URGENT Gong alternative",
                "body_a": "We guarantee results!"
            }],
            "leads": [{
                "lead_id": "test",
                "email": "test@example.com"
            }]
        }
        
        result = validate_campaign(campaign, skip_linkedin=True)
        
        categories_found = set()
        for issue in result.warnings + result.failures:
            categories_found.add(issue.category)
        
        assert ComplianceCategory.CAN_SPAM.value in categories_found
        assert ComplianceCategory.BRAND_SAFETY.value in categories_found
        assert ComplianceCategory.GDPR.value in categories_found


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
