#!/usr/bin/env python3
"""
Email Sending Adapter Interface
================================
Defines the abstract interface for email sending backends.

The CAIO Alpha Swarm supports multiple email backends through this adapter
pattern. Currently Instantly.ai is the primary backend; this interface
enables future migration to Resend.com, AWS SES, or custom SMTP without
changing upstream orchestration code.

Architecture:
    Orchestrator → EmailSendingAdapter (interface)
                        ├── InstantlyAdapter (current)
                        ├── ResendAdapter (Phase 2+)
                        └── SESAdapter (Phase 3+)

Usage:
    from core.adapters.email_sending import get_email_adapter

    adapter = get_email_adapter()  # returns configured backend
    result = await adapter.send_email(
        to="lead@company.com",
        subject="Re: scaling RevOps",
        body_html="<p>Hi there...</p>",
        from_account="josh@chiefaiofficer.com",
        campaign_id="camp_abc123"
    )
"""

import os
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EmailBackend(Enum):
    """Supported email sending backends."""
    INSTANTLY = "instantly"
    RESEND = "resend"
    SES = "ses"
    SMTP = "smtp"
    MOCK = "mock"


class DeliveryStatus(Enum):
    """Email delivery status."""
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    BOUNCED = "bounced"
    FAILED = "failed"
    OPENED = "opened"
    CLICKED = "clicked"
    REPLIED = "replied"
    UNSUBSCRIBED = "unsubscribed"


@dataclass
class SendResult:
    """Result of an email send operation."""
    success: bool
    message_id: Optional[str] = None
    backend: str = ""
    status: DeliveryStatus = DeliveryStatus.QUEUED
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    sent_at: Optional[str] = None

    def __post_init__(self):
        if self.success and not self.sent_at:
            self.sent_at = datetime.utcnow().isoformat()


@dataclass
class EmailAccount:
    """Email sending account configuration."""
    email: str
    display_name: str = ""
    daily_limit: int = 50
    sent_today: int = 0
    warmup_stage: str = "ready"  # warmup, ready, paused
    domain: str = ""
    backend: EmailBackend = EmailBackend.INSTANTLY

    @property
    def remaining_today(self) -> int:
        return max(0, self.daily_limit - self.sent_today)

    @property
    def is_available(self) -> bool:
        return self.warmup_stage == "ready" and self.remaining_today > 0


@dataclass
class DomainHealth:
    """Email domain health metrics."""
    domain: str
    spf_valid: bool = False
    dkim_valid: bool = False
    dmarc_valid: bool = False
    blacklisted: bool = False
    inbox_placement_rate: float = 0.0
    last_checked: Optional[str] = None

    @property
    def is_healthy(self) -> bool:
        return (self.spf_valid and self.dkim_valid and self.dmarc_valid
                and not self.blacklisted and self.inbox_placement_rate > 0.7)


class EmailSendingAdapter(ABC):
    """
    Abstract interface for email sending backends.

    All email sending in CAIO goes through this adapter, enabling backend
    swaps without changing orchestration logic. Implementations must handle:
    - Email sending with rate limiting
    - Account rotation
    - Domain health monitoring
    - Campaign management
    - Delivery tracking
    """

    @abstractmethod
    async def send_email(
        self,
        to: str,
        subject: str,
        body_html: str,
        from_account: Optional[str] = None,
        campaign_id: Optional[str] = None,
        reply_to: Optional[str] = None,
        cc: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        """Send a single email."""
        ...

    @abstractmethod
    async def send_batch(
        self,
        emails: List[Dict[str, Any]],
        campaign_id: Optional[str] = None,
    ) -> List[SendResult]:
        """Send a batch of emails. Each dict must have 'to', 'subject', 'body_html'."""
        ...

    @abstractmethod
    async def create_campaign(
        self,
        name: str,
        from_accounts: List[str],
        schedule: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new email campaign. Returns campaign metadata including ID."""
        ...

    @abstractmethod
    async def add_leads_to_campaign(
        self,
        campaign_id: str,
        leads: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Add leads to an existing campaign."""
        ...

    @abstractmethod
    async def get_campaign_stats(
        self,
        campaign_id: str,
    ) -> Dict[str, Any]:
        """Get delivery/engagement stats for a campaign."""
        ...

    @abstractmethod
    async def list_accounts(self) -> List[EmailAccount]:
        """List all sending accounts with their current daily usage."""
        ...

    @abstractmethod
    async def check_domain_health(self, domain: str) -> DomainHealth:
        """Check DNS and deliverability health for a sending domain."""
        ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check backend connectivity and return status."""
        ...

    # ── Shared logic (non-abstract) ──────────────────────────────────

    async def select_best_account(self) -> Optional[EmailAccount]:
        """Select the sending account with the most remaining daily capacity."""
        accounts = await self.list_accounts()
        available = [a for a in accounts if a.is_available]
        if not available:
            logger.warning("No sending accounts available (all at daily limit)")
            return None
        return max(available, key=lambda a: a.remaining_today)


class MockEmailAdapter(EmailSendingAdapter):
    """Mock adapter for testing. Simulates all operations without real sends."""

    def __init__(self):
        self.sent_emails: List[Dict[str, Any]] = []
        self.campaigns: Dict[str, Dict[str, Any]] = {}
        self._daily_count = 0

    async def send_email(self, to, subject, body_html, from_account=None,
                         campaign_id=None, reply_to=None, cc=None, metadata=None) -> SendResult:
        self._daily_count += 1
        record = {
            "to": to, "subject": subject, "from": from_account or "mock@test.com",
            "campaign_id": campaign_id, "sent_at": datetime.utcnow().isoformat()
        }
        self.sent_emails.append(record)
        return SendResult(
            success=True,
            message_id=f"mock_{len(self.sent_emails)}",
            backend="mock",
            status=DeliveryStatus.SENT,
        )

    async def send_batch(self, emails, campaign_id=None) -> List[SendResult]:
        results = []
        for email in emails:
            r = await self.send_email(
                to=email["to"], subject=email["subject"],
                body_html=email["body_html"], campaign_id=campaign_id
            )
            results.append(r)
        return results

    async def create_campaign(self, name, from_accounts, schedule=None) -> Dict[str, Any]:
        cid = f"mock_camp_{len(self.campaigns) + 1}"
        self.campaigns[cid] = {"name": name, "accounts": from_accounts, "status": "active"}
        return {"campaign_id": cid, "name": name}

    async def add_leads_to_campaign(self, campaign_id, leads) -> Dict[str, Any]:
        return {"campaign_id": campaign_id, "leads_added": len(leads)}

    async def get_campaign_stats(self, campaign_id) -> Dict[str, Any]:
        return {"campaign_id": campaign_id, "sent": 0, "opened": 0, "replied": 0}

    async def list_accounts(self) -> List[EmailAccount]:
        return [EmailAccount(
            email="mock@test.com", display_name="Mock Account",
            daily_limit=50, sent_today=self._daily_count,
            warmup_stage="ready", backend=EmailBackend.MOCK
        )]

    async def check_domain_health(self, domain) -> DomainHealth:
        return DomainHealth(
            domain=domain, spf_valid=True, dkim_valid=True,
            dmarc_valid=True, inbox_placement_rate=0.95,
            last_checked=datetime.utcnow().isoformat()
        )

    async def health_check(self) -> Dict[str, Any]:
        return {"status": "healthy", "backend": "mock", "accounts": 1}


# ── Factory ──────────────────────────────────────────────────────────

def get_email_adapter(backend: Optional[str] = None) -> EmailSendingAdapter:
    """
    Factory: returns the configured email sending adapter.

    Priority:
    1. Explicit backend parameter
    2. EMAIL_BACKEND env var
    3. Default: "instantly" if INSTANTLY_API_KEY exists, else "mock"
    """
    backend = backend or os.getenv("EMAIL_BACKEND", "").lower()

    if not backend:
        if os.getenv("INSTANTLY_API_KEY"):
            backend = "instantly"
        else:
            backend = "mock"

    if backend == "mock":
        return MockEmailAdapter()
    elif backend == "instantly":
        # Lazy import to avoid circular deps
        try:
            from core.adapters.instantly_adapter import InstantlyEmailAdapter
            return InstantlyEmailAdapter()
        except ImportError:
            logger.warning("InstantlyEmailAdapter not yet implemented, falling back to mock")
            return MockEmailAdapter()
    elif backend == "resend":
        try:
            from core.adapters.resend_adapter import ResendEmailAdapter
            return ResendEmailAdapter()
        except ImportError:
            logger.warning("ResendEmailAdapter not yet implemented, falling back to mock")
            return MockEmailAdapter()
    elif backend == "ses":
        try:
            from core.adapters.ses_adapter import SESEmailAdapter
            return SESEmailAdapter()
        except ImportError:
            logger.warning("SESEmailAdapter not yet implemented, falling back to mock")
            return MockEmailAdapter()
    else:
        logger.warning(f"Unknown email backend '{backend}', using mock")
        return MockEmailAdapter()
