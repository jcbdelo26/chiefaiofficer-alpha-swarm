#!/usr/bin/env python3
"""
Guardrails System - Prevent Harmful Agent Actions
==================================================

Protects revenue operations and client relationships by:
- Validating all operations before execution
- Rate limiting API calls
- Blocking destructive operations
- Requiring approval for high-risk actions
- Audit logging all modifications

Operation Modes:
- SHADOW_MODE: Log but don't execute
- PILOT_MODE: Execute with 10% volume cap
- PRODUCTION_MODE: Full execution with guardrails
"""

import os
import json
import logging
import hashlib
from enum import Enum
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
from functools import wraps
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("guardrails")


class OperationMode(Enum):
    SHADOW = "shadow"          # Log only, no execution
    PILOT = "pilot"            # 10% volume cap
    PRODUCTION = "production"  # Full execution


class RiskLevel(Enum):
    LOW = "low"           # Read operations
    MEDIUM = "medium"     # Single record modifications
    HIGH = "high"         # Bulk operations
    CRITICAL = "critical" # Destructive operations


class Platform(Enum):
    GHL = "gohighlevel"
    GHL_EMAIL = "ghl_email"
    GHL_SMS = "ghl_sms"
    GHL_WORKFLOW = "ghl_workflow"
    SUPABASE = "supabase"
    LINKEDIN = "linkedin"
    CLAY = "clay"


# =============================================================================
# OPERATION WHITELIST
# =============================================================================

ALLOWED_OPERATIONS = {
    Platform.GHL: {
        RiskLevel.LOW: [
            "get_contact", "get_contacts", "get_opportunity", 
            "get_pipeline", "get_calendar", "search_contacts"
        ],
        RiskLevel.MEDIUM: [
            "create_contact", "update_contact", "add_tag", 
            "remove_tag", "create_task", "update_opportunity"
        ],
        RiskLevel.HIGH: [
            "bulk_create_contacts", "bulk_update_contacts",
            "trigger_workflow", "move_pipeline_stage"
        ],
        RiskLevel.CRITICAL: [
            "delete_contact", "bulk_delete_contacts",
            "delete_opportunity", "archive_contact"
        ],
    },
    Platform.GHL_EMAIL: {
        RiskLevel.LOW: [
            "get_email_templates", "get_email_stats", "preview_email"
        ],
        RiskLevel.MEDIUM: [
            "send_email", "schedule_email", "update_email_template"
        ],
        RiskLevel.HIGH: [
            "bulk_send_email", "send_campaign_email"
        ],
        RiskLevel.CRITICAL: [
            "delete_email_template", "cancel_scheduled_emails"
        ],
    },
    Platform.GHL_SMS: {
        RiskLevel.LOW: [
            "get_sms_templates", "get_sms_stats", "preview_sms"
        ],
        RiskLevel.MEDIUM: [
            "send_sms", "schedule_sms"
        ],
        RiskLevel.HIGH: [
            "bulk_send_sms"
        ],
        RiskLevel.CRITICAL: [
            "delete_sms_template", "cancel_scheduled_sms"
        ],
    },
    Platform.GHL_WORKFLOW: {
        RiskLevel.LOW: [
            "get_workflows", "get_workflow", "get_workflow_stats"
        ],
        RiskLevel.MEDIUM: [
            "trigger_workflow", "enroll_contact_workflow"
        ],
        RiskLevel.HIGH: [
            "bulk_enroll_workflow", "update_workflow"
        ],
        RiskLevel.CRITICAL: [
            "delete_workflow", "disable_workflow"
        ],
    },
    Platform.SUPABASE: {
        RiskLevel.LOW: [
            "select", "rpc_read", "count"
        ],
        RiskLevel.MEDIUM: [
            "insert", "update", "upsert"
        ],
        RiskLevel.HIGH: [
            "bulk_insert", "bulk_update"
        ],
        RiskLevel.CRITICAL: [
            "delete", "bulk_delete", "truncate"
        ],
    },
}

# Operations that are NEVER allowed
BLOCKED_OPERATIONS = [
    "bulk_delete_all",
    "truncate_table",
    "drop_table",
    "mass_unsubscribe",
    "export_all_contacts",
    "delete_all_campaigns",
]


# =============================================================================
# RATE LIMITS
# =============================================================================

@dataclass
class RateLimitConfig:
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    bulk_threshold: int  # Operations affecting more than this need approval


RATE_LIMITS = {
    Platform.GHL: RateLimitConfig(
        requests_per_minute=30,
        requests_per_hour=500,
        requests_per_day=5000,
        bulk_threshold=10
    ),
    # INSTANTLY removed - GHL is exclusive email platform
    Platform.GHL_EMAIL: RateLimitConfig(
        requests_per_minute=20,
        requests_per_hour=150,  # Conservative for email deliverability
        requests_per_day=150,   # Daily limit
        bulk_threshold=10
    ),
    Platform.SUPABASE: RateLimitConfig(
        requests_per_minute=100,
        requests_per_hour=2000,
        requests_per_day=20000,
        bulk_threshold=100
    ),
}


# =============================================================================
# CONTENT SAFETY
# =============================================================================

SPAM_TRIGGER_WORDS = [
    "free money", "act now", "limited time", "click here",
    "unsubscribe", "buy now", "special offer", "winner",
    "congratulations", "urgent", "immediate action required"
]

PROFANITY_PATTERNS = [
    # Add patterns as needed - keeping minimal for production
]

BLOCKED_DOMAINS = [
    "bit.ly", "tinyurl.com", "goo.gl",  # URL shorteners (spam signal)
]


@dataclass
class ContentValidation:
    is_valid: bool
    issues: List[str] = field(default_factory=list)
    spam_score: float = 0.0
    

def validate_email_content(subject: str, body: str) -> ContentValidation:
    """Validate email content for safety and compliance."""
    issues = []
    spam_score = 0.0
    
    full_content = f"{subject} {body}".lower()
    
    # Check for spam triggers
    for trigger in SPAM_TRIGGER_WORDS:
        if trigger in full_content:
            issues.append(f"Spam trigger word: '{trigger}'")
            spam_score += 0.15
    
    # Check for blocked domains
    for domain in BLOCKED_DOMAINS:
        if domain in full_content:
            issues.append(f"Blocked URL shortener: {domain}")
            spam_score += 0.3
    
    # Check for all caps (spam signal)
    caps_ratio = sum(1 for c in subject if c.isupper()) / max(len(subject), 1)
    if caps_ratio > 0.5 and len(subject) > 10:
        issues.append("Subject line has too many capital letters")
        spam_score += 0.2
    
    # Check for excessive punctuation
    if subject.count('!') > 2 or subject.count('?') > 2:
        issues.append("Excessive punctuation in subject")
        spam_score += 0.1
    
    # Check personalization fields
    if '{' in body and '}' in body:
        # Validate personalization syntax
        import re
        fields = re.findall(r'\{(\w+)\}', body)
        allowed_fields = ['first_name', 'last_name', 'company_name', 'title', 'industry']
        for f in fields:
            if f not in allowed_fields:
                issues.append(f"Unknown personalization field: {{{f}}}")
    
    is_valid = spam_score < 0.5 and len(issues) < 3
    
    return ContentValidation(
        is_valid=is_valid,
        issues=issues,
        spam_score=min(spam_score, 1.0)
    )


# =============================================================================
# CRM PROTECTION
# =============================================================================

PROTECTED_PIPELINE_STAGES = [
    "closed_won", "closed_lost", "in_contract", 
    "negotiation", "proposal_sent"
]

PROTECTED_TAGS = [
    "vip", "do_not_contact", "legal_hold", "executive"
]


def validate_crm_operation(
    operation: str,
    contact_id: Optional[str] = None,
    contact_data: Optional[Dict] = None,
    affected_count: int = 1
) -> tuple[bool, str]:
    """Validate CRM operation against protection rules."""
    
    # Check if operation is blocked
    if operation in BLOCKED_OPERATIONS:
        return False, f"Operation '{operation}' is permanently blocked"
    
    # Check bulk threshold
    if affected_count > RATE_LIMITS[Platform.GHL].bulk_threshold:
        return False, f"Bulk operation ({affected_count} records) requires approval"
    
    # Check protected stages
    if contact_data:
        stage = contact_data.get('pipeline_stage', '').lower()
        if stage in PROTECTED_PIPELINE_STAGES:
            if operation in ['delete_contact', 'archive_contact']:
                return False, f"Cannot delete contact in '{stage}' stage"
    
    # Check protected tags
    if contact_data:
        tags = contact_data.get('tags', [])
        for tag in tags:
            if tag.lower() in PROTECTED_TAGS:
                if operation.startswith('delete') or operation.startswith('bulk_'):
                    return False, f"Contact has protected tag: {tag}"
    
    return True, "OK"


# =============================================================================
# OUTREACH PROTECTION
# =============================================================================

@dataclass
class OutreachLimits:
    max_daily_sends_per_campaign: int = 100
    max_daily_sends_total: int = 500
    min_days_between_contact: int = 30
    max_sequence_steps: int = 5


OUTREACH_LIMITS = OutreachLimits()


class SuppressionList:
    """Manage suppression list for outreach."""
    
    def __init__(self, file_path: str = ".hive-mind/suppression_list.json"):
        self.file_path = Path(file_path)
        self._list: Dict[str, Dict] = {}
        self._load()
    
    def _load(self):
        if self.file_path.exists():
            with open(self.file_path) as f:
                self._list = json.load(f)
    
    def _save(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, 'w') as f:
            json.dump(self._list, f, indent=2)
    
    def add(self, email: str, reason: str):
        email_lower = email.lower()
        self._list[email_lower] = {
            "added_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason
        }
        self._save()
    
    def is_suppressed(self, email: str) -> bool:
        return email.lower() in self._list
    
    def get_reason(self, email: str) -> Optional[str]:
        entry = self._list.get(email.lower())
        return entry.get("reason") if entry else None


class ContactHistory:
    """Track contact history to prevent over-contacting."""
    
    def __init__(self, file_path: str = ".hive-mind/contact_history.json"):
        self.file_path = Path(file_path)
        self._history: Dict[str, List[str]] = {}
        self._load()
    
    def _load(self):
        if self.file_path.exists():
            with open(self.file_path) as f:
                self._history = json.load(f)
    
    def _save(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, 'w') as f:
            json.dump(self._history, f, indent=2)
    
    def record_contact(self, email: str, campaign_id: str):
        email_lower = email.lower()
        if email_lower not in self._history:
            self._history[email_lower] = []
        self._history[email_lower].append(datetime.now(timezone.utc).isoformat())
        self._save()
    
    def days_since_last_contact(self, email: str) -> Optional[int]:
        history = self._history.get(email.lower(), [])
        if not history:
            return None
        last_contact = datetime.fromisoformat(history[-1].replace('Z', '+00:00'))
        return (datetime.now(timezone.utc) - last_contact).days
    
    def can_contact(self, email: str) -> tuple[bool, str]:
        days = self.days_since_last_contact(email)
        if days is None:
            return True, "No prior contact"
        if days < OUTREACH_LIMITS.min_days_between_contact:
            return False, f"Contacted {days} days ago (min: {OUTREACH_LIMITS.min_days_between_contact})"
        return True, f"Last contact: {days} days ago"


def validate_outreach(
    email: str,
    campaign_id: str,
    suppression_list: SuppressionList,
    contact_history: ContactHistory
) -> tuple[bool, str]:
    """Validate outreach attempt."""
    
    # Check suppression list
    if suppression_list.is_suppressed(email):
        reason = suppression_list.get_reason(email)
        return False, f"Email suppressed: {reason}"
    
    # Check contact history
    can_contact, reason = contact_history.can_contact(email)
    if not can_contact:
        return False, reason
    
    return True, "OK to send"


# =============================================================================
# OPERATION TRACKING
# =============================================================================

class OperationTracker:
    """Track operations for rate limiting and auditing."""
    
    def __init__(self, file_path: str = ".hive-mind/operation_log.json"):
        self.file_path = Path(file_path)
        self._operations: List[Dict] = []
        self._load()
    
    def _load(self):
        if self.file_path.exists():
            with open(self.file_path) as f:
                self._operations = json.load(f)
            # Keep only last 24 hours
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            self._operations = [op for op in self._operations if op.get('timestamp', '') > cutoff]
    
    def _save(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, 'w') as f:
            json.dump(self._operations[-10000:], f)  # Keep last 10k
    
    def record(self, platform: Platform, operation: str, risk: RiskLevel, 
               affected_count: int = 1, details: Dict = None):
        self._operations.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": platform.value,
            "operation": operation,
            "risk": risk.value,
            "affected_count": affected_count,
            "details": details or {}
        })
        self._save()
    
    def count_in_window(self, platform: Platform, minutes: int) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
        return sum(1 for op in self._operations 
                   if op['platform'] == platform.value and op['timestamp'] > cutoff)
    
    def check_rate_limit(self, platform: Platform) -> tuple[bool, str]:
        limits = RATE_LIMITS.get(platform)
        if not limits:
            return True, "No limits configured"
        
        per_minute = self.count_in_window(platform, 1)
        if per_minute >= limits.requests_per_minute:
            return False, f"Rate limit: {per_minute}/{limits.requests_per_minute} per minute"
        
        per_hour = self.count_in_window(platform, 60)
        if per_hour >= limits.requests_per_hour:
            return False, f"Rate limit: {per_hour}/{limits.requests_per_hour} per hour"
        
        per_day = self.count_in_window(platform, 1440)
        if per_day >= limits.requests_per_day:
            return False, f"Rate limit: {per_day}/{limits.requests_per_day} per day"
        
        return True, "Within limits"


# =============================================================================
# APPROVAL QUEUE
# =============================================================================

@dataclass
class ApprovalRequest:
    id: str
    platform: Platform
    operation: str
    risk_level: RiskLevel
    affected_count: int
    details: Dict
    requested_at: str
    status: str = "pending"  # pending, approved, rejected
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None


class ApprovalQueue:
    """Queue for high-risk operations requiring human approval."""
    
    def __init__(self, file_path: str = ".hive-mind/approval_queue.json"):
        self.file_path = Path(file_path)
        self._queue: List[Dict] = []
        self._load()
    
    def _load(self):
        if self.file_path.exists():
            with open(self.file_path) as f:
                self._queue = json.load(f)
    
    def _save(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, 'w') as f:
            json.dump(self._queue, f, indent=2)
    
    def submit(self, platform: Platform, operation: str, risk: RiskLevel,
               affected_count: int, details: Dict) -> str:
        request_id = hashlib.md5(
            f"{platform.value}:{operation}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]
        
        request = {
            "id": request_id,
            "platform": platform.value,
            "operation": operation,
            "risk_level": risk.value,
            "affected_count": affected_count,
            "details": details,
            "requested_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending"
        }
        self._queue.append(request)
        self._save()
        
        logger.warning(f"Approval required: {request_id} - {operation} ({affected_count} records)")
        return request_id
    
    def get_pending(self) -> List[Dict]:
        return [r for r in self._queue if r['status'] == 'pending']
    
    def approve(self, request_id: str, reviewer: str) -> bool:
        for req in self._queue:
            if req['id'] == request_id:
                req['status'] = 'approved'
                req['reviewed_by'] = reviewer
                req['reviewed_at'] = datetime.now(timezone.utc).isoformat()
                self._save()
                return True
        return False
    
    def reject(self, request_id: str, reviewer: str, reason: str = "") -> bool:
        for req in self._queue:
            if req['id'] == request_id:
                req['status'] = 'rejected'
                req['reviewed_by'] = reviewer
                req['reviewed_at'] = datetime.now(timezone.utc).isoformat()
                req['rejection_reason'] = reason
                self._save()
                return True
        return False


# =============================================================================
# GUARDRAILS DECORATOR
# =============================================================================

# Global instances
_operation_tracker = OperationTracker()
_approval_queue = ApprovalQueue()
_suppression_list = SuppressionList()
_contact_history = ContactHistory()


def get_operation_mode() -> OperationMode:
    """Get current operation mode from environment."""
    mode = os.getenv("OPERATION_MODE", "shadow").lower()
    return OperationMode(mode) if mode in [m.value for m in OperationMode] else OperationMode.SHADOW


def guardrail(
    platform: Platform,
    operation: str,
    risk_level: RiskLevel = RiskLevel.MEDIUM,
    require_approval_above: int = None
):
    """
    Decorator to wrap operations with guardrails.
    
    Usage:
        @guardrail(Platform.GHL, "create_contact", RiskLevel.MEDIUM)
        def create_contact(data: Dict) -> Dict:
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            mode = get_operation_mode()
            
            # Get affected count from kwargs if provided
            affected_count = kwargs.get('affected_count', 1)
            if hasattr(args[0] if args else None, '__len__'):
                affected_count = len(args[0])
            
            # Check if operation is blocked
            if operation in BLOCKED_OPERATIONS:
                logger.error(f"BLOCKED: {operation} is not allowed")
                raise PermissionError(f"Operation '{operation}' is permanently blocked")
            
            # Check rate limits
            within_limits, limit_msg = _operation_tracker.check_rate_limit(platform)
            if not within_limits:
                logger.warning(f"RATE LIMITED: {limit_msg}")
                raise RuntimeError(f"Rate limit exceeded: {limit_msg}")
            
            # Check if approval required
            threshold = require_approval_above or RATE_LIMITS.get(platform, RateLimitConfig(0,0,0,10)).bulk_threshold
            if affected_count > threshold and risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                request_id = _approval_queue.submit(
                    platform, operation, risk_level, affected_count,
                    {"args": str(args)[:200], "kwargs": str(kwargs)[:200]}
                )
                logger.warning(f"APPROVAL REQUIRED: {request_id}")
                raise PermissionError(f"Operation requires approval: {request_id}")
            
            # Shadow mode - log only
            if mode == OperationMode.SHADOW:
                logger.info(f"[SHADOW] Would execute: {platform.value}.{operation} ({affected_count} records)")
                _operation_tracker.record(platform, operation, risk_level, affected_count)
                return {"shadow_mode": True, "operation": operation, "would_affect": affected_count}
            
            # Pilot mode - 10% volume
            if mode == OperationMode.PILOT:
                if affected_count > 1:
                    pilot_count = max(1, affected_count // 10)
                    logger.info(f"[PILOT] Reducing {affected_count} to {pilot_count} records")
                    # Modify args/kwargs to reduce volume
                    if isinstance(args[0] if args else None, list):
                        args = (args[0][:pilot_count],) + args[1:]
                        affected_count = pilot_count
            
            # Execute operation
            try:
                result = func(*args, **kwargs)
                _operation_tracker.record(platform, operation, risk_level, affected_count)
                logger.info(f"[{mode.value.upper()}] Executed: {platform.value}.{operation} ({affected_count} records)")
                return result
            except Exception as e:
                logger.error(f"FAILED: {platform.value}.{operation} - {e}")
                raise
        
        return wrapper
    return decorator


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def validate_before_send(email: str, subject: str, body: str, campaign_id: str) -> tuple[bool, List[str]]:
    """
    Comprehensive validation before sending an email.
    
    Returns (is_valid, list_of_issues)
    """
    issues = []
    
    # Check suppression
    if _suppression_list.is_suppressed(email):
        issues.append(f"Email is suppressed: {_suppression_list.get_reason(email)}")
    
    # Check contact history
    can_contact, reason = _contact_history.can_contact(email)
    if not can_contact:
        issues.append(reason)
    
    # Validate content
    content_validation = validate_email_content(subject, body)
    if not content_validation.is_valid:
        issues.extend(content_validation.issues)
    
    return len(issues) == 0, issues


def record_send(email: str, campaign_id: str):
    """Record that an email was sent."""
    _contact_history.record_contact(email, campaign_id)


def suppress_email(email: str, reason: str):
    """Add email to suppression list."""
    _suppression_list.add(email, reason)


def get_pending_approvals() -> List[Dict]:
    """Get pending approval requests."""
    return _approval_queue.get_pending()


def approve_operation(request_id: str, reviewer: str) -> bool:
    """Approve a pending operation."""
    return _approval_queue.approve(request_id, reviewer)


def reject_operation(request_id: str, reviewer: str, reason: str = "") -> bool:
    """Reject a pending operation."""
    return _approval_queue.reject(request_id, reviewer, reason)


# =============================================================================
# DEMO
# =============================================================================

def demo():
    print("=" * 60)
    print("Guardrails System Demo")
    print("=" * 60)
    
    # Test content validation
    print("\n[1] Content Validation:")
    result = validate_email_content(
        "FREE MONEY!!! Act Now!!!",
        "Click here to claim your prize at bit.ly/scam"
    )
    print(f"    Valid: {result.is_valid}")
    print(f"    Spam Score: {result.spam_score}")
    print(f"    Issues: {result.issues}")
    
    # Test good content
    result2 = validate_email_content(
        "{first_name}, your AI strategy",
        "Hi {first_name}, I help {industry} companies automate operations."
    )
    print(f"\n    Good content valid: {result2.is_valid}")
    
    # Test operation mode
    print(f"\n[2] Current Mode: {get_operation_mode().value}")
    
    # Test send validation
    print("\n[3] Send Validation:")
    valid, issues = validate_before_send(
        "test@example.com",
        "Quick question",
        "Hi, I wanted to reach out about...",
        "campaign_123"
    )
    print(f"    Valid to send: {valid}")
    if issues:
        print(f"    Issues: {issues}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    demo()
