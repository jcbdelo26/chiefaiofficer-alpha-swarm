"""
GHL Guardrails - Email Deliverability Protection
=================================================

Thin library focused on email deliverability best practices:
1. Rate limiting (monthly/daily/hourly)
2. Per-domain sending limits
3. Working hours enforcement
4. Domain health monitoring
5. Warmup mode for new domains

For action validation, approval flows, and audit logging,
use unified_guardrails.py instead.

Usage:
    from core.ghl_guardrails import get_email_guard, EmailDeliverabilityGuard
    
    guard = get_email_guard()
    can_send, reason = guard.can_send_email("john@example.com", "chiefaiofficer.com")
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ghl_guardrails')


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class EmailLimits:
    """Email sending limits to protect deliverability"""
    # Monthly limits
    monthly_limit: int = 3000
    monthly_sent: int = 0
    
    # Daily limits (spread sends throughout day)
    daily_limit: int = 150
    daily_sent: int = 0
    
    # Hourly limits (prevent bursts)
    hourly_limit: int = 20
    hourly_sent: int = 0
    
    # Per-domain limits (protect subdomain reputation)
    per_domain_hourly_limit: int = 5
    domain_sends: Dict[str, int] = field(default_factory=dict)
    
    # Timing constraints
    min_delay_between_sends_seconds: int = 30
    last_send_time: Optional[str] = None
    
    # Working hours (recipient timezone aware)
    working_hours_start: int = 8   # 8 AM
    working_hours_end: int = 18    # 6 PM
    
    # Warmup mode for new domains
    warmup_mode: bool = False
    warmup_daily_limit: int = 20
    warmup_days_remaining: int = 0


@dataclass
class DomainHealth:
    """Track health of sending domains"""
    domain: str
    total_sent: int = 0
    bounces: int = 0
    complaints: int = 0
    unsubscribes: int = 0
    opens: int = 0
    replies: int = 0
    last_send: Optional[str] = None
    health_score: float = 100.0  # 0-100
    is_healthy: bool = True
    cooling_off_until: Optional[str] = None
    
    def calculate_health(self):
        """Calculate domain health score"""
        if self.total_sent == 0:
            self.health_score = 100.0
            self.is_healthy = True
            return
        
        bounce_rate = (self.bounces / self.total_sent) * 100
        complaint_rate = (self.complaints / self.total_sent) * 100
        open_rate = (self.opens / self.total_sent) * 100
        
        # Scoring (higher is better)
        score = 100.0
        
        # Bounce penalty (critical)
        if bounce_rate > 5:
            score -= 30
        elif bounce_rate > 2:
            score -= 15
        elif bounce_rate > 1:
            score -= 5
        
        # Complaint penalty (critical)
        if complaint_rate > 0.1:
            score -= 40
        elif complaint_rate > 0.05:
            score -= 20
        
        # Low engagement penalty
        if open_rate < 20:
            score -= 20
        elif open_rate < 30:
            score -= 10
        
        # Reply bonus
        reply_rate = (self.replies / self.total_sent) * 100
        if reply_rate > 5:
            score += 10
        
        self.health_score = max(0, min(100, score))
        self.is_healthy = self.health_score >= 50


@dataclass
class ValidationResult:
    """Result of email validation check"""
    valid: bool
    checks_passed: List[str]
    checks_failed: List[str]
    warnings: List[str]
    wait_seconds: int = 0


# =============================================================================
# EMAIL DELIVERABILITY GUARDRAILS
# =============================================================================

class EmailDeliverabilityGuard:
    """
    Protects email domain reputation and deliverability.
    
    Best Practices Enforced:
    1. Rate limiting (monthly/daily/hourly)
    2. Per-domain sending limits
    3. Working hours only
    4. Minimum delays between sends
    5. Domain health monitoring
    6. Automatic cooling off for unhealthy domains
    7. Warmup mode for new domains
    """
    
    # Spam trigger words
    SPAM_WORDS = [
        'free', 'guarantee', 'no obligation', 'winner', 'urgent',
        'act now', 'limited time', 'exclusive deal', 'click here',
        'buy now', 'order now', 'special promotion', 'risk free',
        'no cost', 'bonus', 'prize', 'congratulations', 'selected',
        'million dollars', 'wire transfer', 'nigerian', 'inheritance'
    ]
    
    # Required elements for good deliverability
    REQUIRED_ELEMENTS = ['unsubscribe', 'opt out', 'opt-out', 'stop']
    
    def __init__(self, data_path: Path = None):
        self.data_path = data_path or Path(__file__).parent.parent / ".hive-mind" / "email_limits.json"
        self.health_path = self.data_path.parent / "domain_health.json"
        
        # Ensure directories exist
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.limits = self._load_limits()
        self.domain_health: Dict[str, DomainHealth] = self._load_domain_health()
        
        logger.info("Email Deliverability Guard initialized")
    
    def _load_limits(self) -> EmailLimits:
        """Load email limits from persistent storage"""
        if self.data_path.exists():
            with open(self.data_path) as f:
                data = json.load(f)
                return EmailLimits(**data)
        return EmailLimits()
    
    def _save_limits(self):
        """Save email limits to persistent storage"""
        with open(self.data_path, 'w') as f:
            json.dump({
                'monthly_limit': self.limits.monthly_limit,
                'monthly_sent': self.limits.monthly_sent,
                'daily_limit': self.limits.daily_limit,
                'daily_sent': self.limits.daily_sent,
                'hourly_limit': self.limits.hourly_limit,
                'hourly_sent': self.limits.hourly_sent,
                'per_domain_hourly_limit': self.limits.per_domain_hourly_limit,
                'domain_sends': self.limits.domain_sends,
                'min_delay_between_sends_seconds': self.limits.min_delay_between_sends_seconds,
                'last_send_time': self.limits.last_send_time,
                'working_hours_start': self.limits.working_hours_start,
                'working_hours_end': self.limits.working_hours_end,
                'warmup_mode': self.limits.warmup_mode,
                'warmup_daily_limit': self.limits.warmup_daily_limit,
                'warmup_days_remaining': self.limits.warmup_days_remaining
            }, f, indent=2)
    
    def _load_domain_health(self) -> Dict[str, DomainHealth]:
        """Load domain health from persistent storage"""
        if self.health_path.exists():
            with open(self.health_path) as f:
                data = json.load(f)
                return {
                    domain: DomainHealth(**health)
                    for domain, health in data.items()
                }
        return {}
    
    def _save_domain_health(self):
        """Save domain health to persistent storage"""
        with open(self.health_path, 'w') as f:
            json.dump({
                domain: {
                    'domain': h.domain,
                    'total_sent': h.total_sent,
                    'bounces': h.bounces,
                    'complaints': h.complaints,
                    'unsubscribes': h.unsubscribes,
                    'opens': h.opens,
                    'replies': h.replies,
                    'last_send': h.last_send,
                    'health_score': h.health_score,
                    'is_healthy': h.is_healthy,
                    'cooling_off_until': h.cooling_off_until
                }
                for domain, h in self.domain_health.items()
            }, f, indent=2)
    
    def _reset_counters_if_needed(self):
        """Reset hourly/daily/monthly counters based on time"""
        now = datetime.now()
        
        if self.limits.last_send_time:
            last_send = datetime.fromisoformat(self.limits.last_send_time)
            
            # Reset hourly counter
            if now.hour != last_send.hour or (now - last_send).total_seconds() > 3600:
                self.limits.hourly_sent = 0
                self.limits.domain_sends = {}
            
            # Reset daily counter
            if now.date() != last_send.date():
                self.limits.daily_sent = 0
                
                # Decrement warmup days
                if self.limits.warmup_mode and self.limits.warmup_days_remaining > 0:
                    self.limits.warmup_days_remaining -= 1
                    if self.limits.warmup_days_remaining == 0:
                        self.limits.warmup_mode = False
                        logger.info("Warmup period complete!")
            
            # Reset monthly counter
            if now.month != last_send.month:
                self.limits.monthly_sent = 0
    
    def can_send_email(self, recipient: str, sender_domain: str = None) -> Tuple[bool, str]:
        """
        Check if an email can be sent.
        
        Args:
            recipient: Email address of recipient
            sender_domain: Domain being used to send (for health tracking)
            
        Returns:
            (can_send: bool, reason: str)
        """
        self._reset_counters_if_needed()
        now = datetime.now()
        
        # Check 1: Monthly limit
        if self.limits.monthly_sent >= self.limits.monthly_limit:
            return False, f"Monthly limit reached ({self.limits.monthly_limit})"
        
        # Check 2: Daily limit
        daily_limit = self.limits.warmup_daily_limit if self.limits.warmup_mode else self.limits.daily_limit
        if self.limits.daily_sent >= daily_limit:
            return False, f"Daily limit reached ({daily_limit})"
        
        # Check 3: Hourly limit
        if self.limits.hourly_sent >= self.limits.hourly_limit:
            return False, f"Hourly limit reached ({self.limits.hourly_limit})"
        
        # Check 4: Per-domain hourly limit
        if sender_domain:
            recipient_domain = recipient.split('@')[-1] if '@' in recipient else 'unknown'
            domain_key = f"{sender_domain}:{recipient_domain}"
            domain_sends = self.limits.domain_sends.get(domain_key, 0)
            
            if domain_sends >= self.limits.per_domain_hourly_limit:
                return False, f"Per-domain hourly limit reached for {recipient_domain}"
        
        # Check 5: Minimum delay
        if self.limits.last_send_time:
            last_send = datetime.fromisoformat(self.limits.last_send_time)
            seconds_since = (now - last_send).total_seconds()
            
            if seconds_since < self.limits.min_delay_between_sends_seconds:
                wait = self.limits.min_delay_between_sends_seconds - seconds_since
                return False, f"Minimum delay not met (wait {wait:.0f}s)"
        
        # Check 6: Working hours
        if not (self.limits.working_hours_start <= now.hour < self.limits.working_hours_end):
            return False, f"Outside working hours ({self.limits.working_hours_start}:00-{self.limits.working_hours_end}:00)"
        
        # Check 7: Weekend
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False, "Emails not sent on weekends"
        
        # Check 8: Domain health
        if sender_domain and sender_domain in self.domain_health:
            health = self.domain_health[sender_domain]
            
            # Cooling off period
            if health.cooling_off_until:
                cooling_until = datetime.fromisoformat(health.cooling_off_until)
                if now < cooling_until:
                    return False, f"Domain {sender_domain} in cooling off until {cooling_until}"
            
            # Unhealthy domain
            if not health.is_healthy:
                return False, f"Domain {sender_domain} is unhealthy (score: {health.health_score:.0f})"
        
        return True, "OK"
    
    def validate_email_content(self, subject: str, body: str) -> Tuple[bool, List[str]]:
        """
        Validate email content for deliverability.
        
        Args:
            subject: Email subject line
            body: Email body content
            
        Returns:
            (valid: bool, issues: List[str])
        """
        issues = []
        combined = (subject + " " + body).lower()
        
        # Check for spam words
        spam_found = [word for word in self.SPAM_WORDS if word in combined]
        if spam_found:
            issues.append(f"Spam trigger words found: {', '.join(spam_found[:5])}")
        
        # Check for unsubscribe
        has_unsubscribe = any(elem in combined for elem in self.REQUIRED_ELEMENTS)
        if not has_unsubscribe:
            issues.append("Missing unsubscribe/opt-out option")
        
        # Check subject length
        if len(subject) > 60:
            issues.append(f"Subject too long ({len(subject)} chars, max 60)")
        
        # Check for all caps
        if subject.isupper():
            issues.append("Subject is ALL CAPS (spam trigger)")
        
        # Check for excessive punctuation
        if subject.count('!') > 1 or subject.count('?') > 2:
            issues.append("Excessive punctuation in subject")
        
        # Check for suspicious patterns
        if 'http://' in body and 'https://' not in body:
            issues.append("Using HTTP instead of HTTPS for links")
        
        return len(issues) == 0, issues
    
    def record_send(self, recipient: str, sender_domain: str):
        """Record that an email was sent (update counters)"""
        now = datetime.now()
        
        self._reset_counters_if_needed()
        
        # Update counters
        self.limits.monthly_sent += 1
        self.limits.daily_sent += 1
        self.limits.hourly_sent += 1
        self.limits.last_send_time = now.isoformat()
        
        # Update per-domain counter
        if sender_domain:
            recipient_domain = recipient.split('@')[-1] if '@' in recipient else 'unknown'
            domain_key = f"{sender_domain}:{recipient_domain}"
            self.limits.domain_sends[domain_key] = self.limits.domain_sends.get(domain_key, 0) + 1
        
        # Update domain health
        if sender_domain not in self.domain_health:
            self.domain_health[sender_domain] = DomainHealth(domain=sender_domain)
        
        self.domain_health[sender_domain].total_sent += 1
        self.domain_health[sender_domain].last_send = now.isoformat()
        
        # Persist
        self._save_limits()
        self._save_domain_health()
    
    def record_engagement(self, sender_domain: str, event_type: str):
        """Record engagement event (open, reply, bounce, etc.)"""
        if sender_domain not in self.domain_health:
            return
        
        health = self.domain_health[sender_domain]
        
        if event_type == 'open':
            health.opens += 1
        elif event_type == 'reply':
            health.replies += 1
        elif event_type == 'bounce':
            health.bounces += 1
            # Trigger cooling off if bounce rate spikes
            if health.total_sent > 10:
                bounce_rate = health.bounces / health.total_sent
                if bounce_rate > 0.05:
                    health.cooling_off_until = (datetime.now() + timedelta(hours=24)).isoformat()
                    logger.warning(f"Domain {sender_domain} entered 24h cooling off (bounce rate: {bounce_rate:.1%})")
        elif event_type == 'complaint':
            health.complaints += 1
            # Immediate cooling off on complaint
            health.cooling_off_until = (datetime.now() + timedelta(hours=48)).isoformat()
            logger.error(f"Domain {sender_domain} entered 48h cooling off (spam complaint received)")
        elif event_type == 'unsubscribe':
            health.unsubscribes += 1
        
        health.calculate_health()
        self._save_domain_health()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current email limits status"""
        return {
            'monthly': {
                'sent': self.limits.monthly_sent,
                'limit': self.limits.monthly_limit,
                'remaining': self.limits.monthly_limit - self.limits.monthly_sent
            },
            'daily': {
                'sent': self.limits.daily_sent,
                'limit': self.limits.daily_limit,
                'remaining': self.limits.daily_limit - self.limits.daily_sent
            },
            'hourly': {
                'sent': self.limits.hourly_sent,
                'limit': self.limits.hourly_limit,
                'remaining': self.limits.hourly_limit - self.limits.hourly_sent
            },
            'warmup_mode': self.limits.warmup_mode,
            'domains': {
                domain: {
                    'health_score': h.health_score,
                    'is_healthy': h.is_healthy,
                    'total_sent': h.total_sent
                }
                for domain, h in self.domain_health.items()
            }
        }
    
    def enable_warmup_mode(self, days: int = 14):
        """Enable warmup mode for new domains"""
        self.limits.warmup_mode = True
        self.limits.warmup_days_remaining = days
        self._save_limits()
        logger.info(f"Warmup mode enabled for {days} days")
    
    def get_domain_health(self, domain: str) -> Optional[DomainHealth]:
        """Get health data for a specific domain"""
        return self.domain_health.get(domain)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_email_guard_instance: Optional[EmailDeliverabilityGuard] = None


def get_email_guard() -> EmailDeliverabilityGuard:
    """Get or create the singleton EmailDeliverabilityGuard instance."""
    global _email_guard_instance
    if _email_guard_instance is None:
        _email_guard_instance = EmailDeliverabilityGuard()
    return _email_guard_instance


# =============================================================================
# MAIN / DEMO
# =============================================================================

def main():
    """Demonstrate Email Deliverability Guard"""
    print("=" * 70)
    print("🛡️  EMAIL DELIVERABILITY GUARD")
    print("=" * 70)
    
    guard = get_email_guard()
    
    # Test 1: Check if email can be sent
    print("\n[Test 1] Can send email?")
    print("-" * 40)
    
    can_send, reason = guard.can_send_email(
        recipient="john@example.com",
        sender_domain="chiefaiofficer.com"
    )
    print(f"  Can send: {can_send}")
    print(f"  Reason: {reason}")
    
    # Test 2: Validate email content
    print("\n[Test 2] Validate good email content")
    print("-" * 40)
    
    valid, issues = guard.validate_email_content(
        subject="Quick question about your RevOps",
        body="""Hi John,

I noticed your team has been growing. We help companies like yours 
streamline revenue operations.

Would you be open to a quick call?

Best,
Chris

Reply STOP to unsubscribe"""
    )
    print(f"  Valid: {valid}")
    if issues:
        print(f"  Issues: {issues}")
    
    # Test 3: Validate spam content
    print("\n[Test 3] Validate spam email content")
    print("-" * 40)
    
    valid, issues = guard.validate_email_content(
        subject="FREE MONEY!!! ACT NOW!!!",
        body="Click here for a GUARANTEED win! Limited time offer!"
    )
    print(f"  Valid: {valid}")
    print(f"  Issues: {issues}")
    
    # Test 4: Check limits status
    print("\n[Test 4] Current limits status")
    print("-" * 40)
    
    status = guard.get_status()
    print(f"  Monthly: {status['monthly']['sent']}/{status['monthly']['limit']}")
    print(f"  Daily: {status['daily']['sent']}/{status['daily']['limit']}")
    print(f"  Hourly: {status['hourly']['sent']}/{status['hourly']['limit']}")
    print(f"  Warmup mode: {status['warmup_mode']}")
    
    print("\n" + "=" * 70)
    print("✓ Email Deliverability Guard demonstration complete")
    print("=" * 70)


if __name__ == "__main__":
    main()
