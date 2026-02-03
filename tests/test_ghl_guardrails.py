"""
Tests for GHL Guardrails - Email Deliverability Protection
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch

from core.ghl_guardrails import (
    EmailDeliverabilityGuard,
    EmailLimits,
    DomainHealth,
    ValidationResult,
    get_email_guard
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for test data"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def email_guard(temp_data_dir):
    """Create an EmailDeliverabilityGuard with temp storage"""
    return EmailDeliverabilityGuard(data_path=temp_data_dir / "email_limits.json")


# =============================================================================
# EMAIL LIMITS TESTS
# =============================================================================

class TestEmailLimits:
    """Test EmailLimits dataclass"""
    
    def test_default_limits(self):
        """Test default limit values"""
        limits = EmailLimits()
        assert limits.monthly_limit == 3000
        assert limits.daily_limit == 150
        assert limits.hourly_limit == 20
        assert limits.per_domain_hourly_limit == 5
        assert limits.working_hours_start == 8
        assert limits.working_hours_end == 18
    
    def test_warmup_mode_defaults(self):
        """Test warmup mode defaults"""
        limits = EmailLimits()
        assert limits.warmup_mode is False
        assert limits.warmup_daily_limit == 20


# =============================================================================
# DOMAIN HEALTH TESTS
# =============================================================================

class TestDomainHealth:
    """Test DomainHealth dataclass"""
    
    def test_initial_health_score(self):
        """Test initial health score is 100"""
        health = DomainHealth(domain="test.com")
        health.calculate_health()
        assert health.health_score == 100.0
        assert health.is_healthy is True
    
    def test_bounce_penalty(self):
        """Test bounce rate penalty"""
        health = DomainHealth(domain="test.com", total_sent=100, bounces=6)
        health.calculate_health()
        assert health.health_score < 100.0  # Should have penalty
    
    def test_complaint_penalty(self):
        """Test complaint penalty"""
        health = DomainHealth(domain="test.com", total_sent=1000, complaints=2)
        health.calculate_health()
        assert health.health_score < 100.0  # Should have penalty
    
    def test_engagement_bonus(self):
        """Test reply rate bonus"""
        health = DomainHealth(domain="test.com", total_sent=100, replies=10, opens=50)
        health.calculate_health()
        # Should have bonus for replies but no penalty for engagement
        assert health.is_healthy is True
    
    def test_unhealthy_domain(self):
        """Test domain becomes unhealthy"""
        health = DomainHealth(
            domain="test.com", 
            total_sent=100, 
            bounces=10,  # 10% bounce rate
            complaints=5  # 5% complaint rate
        )
        health.calculate_health()
        assert health.is_healthy is False
        assert health.health_score < 50


# =============================================================================
# EMAIL DELIVERABILITY GUARD TESTS
# =============================================================================

class TestEmailDeliverabilityGuard:
    """Test EmailDeliverabilityGuard"""
    
    def test_can_send_within_limits(self, email_guard):
        """Test email can be sent when within limits"""
        with patch.object(email_guard, '_reset_counters_if_needed'):
            # Mock working hours
            with patch('core.ghl_guardrails.datetime') as mock_dt:
                mock_now = datetime(2025, 1, 23, 10, 0, 0)  # Thursday 10 AM
                mock_dt.now.return_value = mock_now
                mock_dt.fromisoformat = datetime.fromisoformat
                
                can_send, reason = email_guard.can_send_email(
                    recipient="test@example.com",
                    sender_domain="mycompany.com"
                )
                assert can_send is True
                assert reason == "OK"
    
    def test_monthly_limit_blocks(self, email_guard):
        """Test monthly limit blocks sending"""
        email_guard.limits.monthly_sent = 3000
        email_guard.limits.monthly_limit = 3000
        
        can_send, reason = email_guard.can_send_email("test@example.com")
        assert can_send is False
        assert "Monthly limit" in reason
    
    def test_daily_limit_blocks(self, email_guard):
        """Test daily limit blocks sending"""
        email_guard.limits.daily_sent = 150
        email_guard.limits.daily_limit = 150
        
        can_send, reason = email_guard.can_send_email("test@example.com")
        assert can_send is False
        assert "Daily limit" in reason
    
    def test_hourly_limit_blocks(self, email_guard):
        """Test hourly limit blocks sending"""
        email_guard.limits.hourly_sent = 20
        email_guard.limits.hourly_limit = 20
        
        can_send, reason = email_guard.can_send_email("test@example.com")
        assert can_send is False
        assert "Hourly limit" in reason
    
    def test_warmup_mode_reduced_limit(self, email_guard):
        """Test warmup mode uses reduced daily limit"""
        email_guard.limits.warmup_mode = True
        email_guard.limits.warmup_daily_limit = 20
        email_guard.limits.daily_sent = 20
        
        can_send, reason = email_guard.can_send_email("test@example.com")
        assert can_send is False
        assert "Daily limit reached (20)" in reason
    
    def test_unhealthy_domain_blocks(self, email_guard):
        """Test unhealthy domain blocks sending"""
        email_guard.domain_health["bad.com"] = DomainHealth(
            domain="bad.com",
            health_score=30.0,
            is_healthy=False
        )
        
        with patch('core.ghl_guardrails.datetime') as mock_dt:
            mock_now = datetime(2025, 1, 23, 10, 0, 0)
            mock_dt.now.return_value = mock_now
            
            can_send, reason = email_guard.can_send_email(
                "test@example.com", 
                sender_domain="bad.com"
            )
            assert can_send is False
            assert "unhealthy" in reason


class TestEmailContentValidation:
    """Test email content validation"""
    
    def test_valid_email_content(self, email_guard):
        """Test valid email passes validation"""
        valid, issues = email_guard.validate_email_content(
            subject="Quick question",
            body="Hi there, would you like to chat? Reply STOP to unsubscribe."
        )
        assert valid is True
        assert len(issues) == 0
    
    def test_spam_words_detected(self, email_guard):
        """Test spam words are detected"""
        valid, issues = email_guard.validate_email_content(
            subject="FREE offer",
            body="Act now for a guaranteed win! Unsubscribe here."
        )
        assert valid is False
        assert any("Spam trigger" in issue for issue in issues)
    
    def test_missing_unsubscribe(self, email_guard):
        """Test missing unsubscribe is flagged"""
        valid, issues = email_guard.validate_email_content(
            subject="Hello",
            body="This is a message with no way for the recipient to leave."
        )
        assert valid is False
        assert any("unsubscribe" in issue.lower() for issue in issues)
    
    def test_subject_too_long(self, email_guard):
        """Test long subject is flagged"""
        valid, issues = email_guard.validate_email_content(
            subject="x" * 70,
            body="Body with unsubscribe option."
        )
        assert valid is False
        assert any("too long" in issue for issue in issues)
    
    def test_all_caps_subject(self, email_guard):
        """Test ALL CAPS subject is flagged"""
        valid, issues = email_guard.validate_email_content(
            subject="HELLO THERE",
            body="Body with unsubscribe option."
        )
        assert valid is False
        assert any("ALL CAPS" in issue for issue in issues)
    
    def test_excessive_punctuation(self, email_guard):
        """Test excessive punctuation is flagged"""
        valid, issues = email_guard.validate_email_content(
            subject="Hello!!!",
            body="Body with unsubscribe option."
        )
        assert valid is False
        assert any("punctuation" in issue for issue in issues)


class TestRecordSend:
    """Test send recording"""
    
    def test_record_send_increments_counters(self, email_guard):
        """Test record_send increments all counters"""
        initial_monthly = email_guard.limits.monthly_sent
        initial_daily = email_guard.limits.daily_sent
        initial_hourly = email_guard.limits.hourly_sent
        
        email_guard.record_send("test@example.com", "sender.com")
        
        assert email_guard.limits.monthly_sent == initial_monthly + 1
        assert email_guard.limits.daily_sent == initial_daily + 1
        assert email_guard.limits.hourly_sent == initial_hourly + 1
    
    def test_record_send_updates_domain_health(self, email_guard):
        """Test record_send updates domain health"""
        email_guard.record_send("test@example.com", "sender.com")
        
        assert "sender.com" in email_guard.domain_health
        assert email_guard.domain_health["sender.com"].total_sent == 1


class TestRecordEngagement:
    """Test engagement recording"""
    
    def test_record_open(self, email_guard):
        """Test recording opens"""
        email_guard.domain_health["sender.com"] = DomainHealth(domain="sender.com")
        email_guard.record_engagement("sender.com", "open")
        assert email_guard.domain_health["sender.com"].opens == 1
    
    def test_record_reply(self, email_guard):
        """Test recording replies"""
        email_guard.domain_health["sender.com"] = DomainHealth(domain="sender.com")
        email_guard.record_engagement("sender.com", "reply")
        assert email_guard.domain_health["sender.com"].replies == 1
    
    def test_bounce_triggers_cooling_off(self, email_guard):
        """Test high bounce rate triggers cooling off"""
        email_guard.domain_health["sender.com"] = DomainHealth(
            domain="sender.com",
            total_sent=100,
            bounces=5  # Will hit 6% after this bounce
        )
        email_guard.record_engagement("sender.com", "bounce")
        assert email_guard.domain_health["sender.com"].cooling_off_until is not None
    
    def test_complaint_triggers_immediate_cooling_off(self, email_guard):
        """Test complaint triggers immediate 48h cooling off"""
        email_guard.domain_health["sender.com"] = DomainHealth(domain="sender.com")
        email_guard.record_engagement("sender.com", "complaint")
        assert email_guard.domain_health["sender.com"].cooling_off_until is not None


class TestGetStatus:
    """Test status reporting"""
    
    def test_get_status_returns_limits(self, email_guard):
        """Test get_status returns current limits"""
        email_guard.limits.monthly_sent = 100
        email_guard.limits.daily_sent = 10
        email_guard.limits.hourly_sent = 5
        
        status = email_guard.get_status()
        
        assert status['monthly']['sent'] == 100
        assert status['daily']['sent'] == 10
        assert status['hourly']['sent'] == 5
        assert 'remaining' in status['monthly']


class TestWarmupMode:
    """Test warmup mode"""
    
    def test_enable_warmup_mode(self, email_guard):
        """Test enabling warmup mode"""
        email_guard.enable_warmup_mode(days=14)
        
        assert email_guard.limits.warmup_mode is True
        assert email_guard.limits.warmup_days_remaining == 14


class TestGetEmailGuard:
    """Test singleton factory"""
    
    def test_get_email_guard_returns_instance(self):
        """Test get_email_guard returns an instance"""
        guard = get_email_guard()
        assert isinstance(guard, EmailDeliverabilityGuard)
    
    def test_get_email_guard_returns_same_instance(self):
        """Test get_email_guard returns singleton"""
        guard1 = get_email_guard()
        guard2 = get_email_guard()
        assert guard1 is guard2
