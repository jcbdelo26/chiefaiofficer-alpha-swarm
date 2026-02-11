#!/usr/bin/env python3
"""
Unified Guardrails System
=========================
Enterprise-grade protection layer for the Unified CAIO RevOps Swarm.

Integrates:
- Circuit breaker patterns (from circuit_breaker.py)
- Rate limiting (from guardrails.py, ghl_guardrails.py)
- Permission matrix for 12 agents
- Grounding evidence validation
- Action validation framework
- Pre/post execution hooks

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    UNIFIED GUARDRAILS                        │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
    │  │ CircuitBreaker│  │ RateLimiter │  │PermissionMgr│       │
    │  └──────────────┘  └──────────────┘  └──────────────┘       │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
    │  │ GroundingVal │  │ ActionValid │  │  HookSystem  │       │
    │  └──────────────┘  └──────────────┘  └──────────────┘       │
    └─────────────────────────────────────────────────────────────┘

Usage:
    from core.unified_guardrails import UnifiedGuardrails, ActionType
    
    guardrails = UnifiedGuardrails()
    
    # Validate and execute action
    result = await guardrails.execute_with_guardrails(
        agent_name="CRAFTER",
        action_type=ActionType.SEND_EMAIL,
        parameters={"contact_id": "123", "subject": "Hello"},
        grounding_evidence={"source": "supabase", "data_id": "lead_123"}
    )
"""

import os
import sys
import json
import time
import asyncio
import functools
import logging
import tempfile
import threading
import uuid
from enum import Enum
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.circuit_breaker import (
    CircuitBreakerRegistry, 
    CircuitBreakerError, 
    CircuitState,
    get_registry as get_circuit_registry
)
from core.audit_trail import AuditTrail, get_audit_trail
from core.trace_envelope import (
    emit_tool_trace,
    get_current_case_id,
    get_current_correlation_id,
)

try:
    import redis
except Exception:  # pragma: no cover - optional dependency in some test environments
    redis = None

logger = logging.getLogger("unified_guardrails")

# Import MultiLayerFailsafe for enhanced protection
try:
    from core.multi_layer_failsafe import (
        MultiLayerFailsafe,
        get_failsafe,
        InputValidator,
        FieldSchema,
        FailsafeLayer,
        ConsensusVote
    )
    MULTI_LAYER_FAILSAFE_AVAILABLE = True
except ImportError:
    MULTI_LAYER_FAILSAFE_AVAILABLE = False

# Path to permissions JSON config
PERMISSIONS_CONFIG_PATH = Path(__file__).parent / "agent_action_permissions.json"


class ActionType(Enum):
    """All action types across the unified swarm."""
    # Read operations (LOW risk)
    READ_CONTACT = "read_contact"
    READ_PIPELINE = "read_pipeline"
    READ_CALENDAR = "read_calendar"
    SEARCH_CONTACTS = "search_contacts"
    GET_TEMPLATES = "get_templates"
    
    # CRM operations (MEDIUM risk)
    CREATE_CONTACT = "create_contact"
    UPDATE_CONTACT = "update_contact"
    ADD_TAG = "add_tag"
    REMOVE_TAG = "remove_tag"
    CREATE_TASK = "create_task"
    UPDATE_OPPORTUNITY = "update_opportunity"
    
    # Outreach operations (HIGH risk - require grounding)
    SEND_EMAIL = "send_email"
    SEND_SMS = "send_sms"
    SCHEDULE_EMAIL = "schedule_email"
    TRIGGER_WORKFLOW = "trigger_workflow"
    
    # Calendar operations (MEDIUM risk)
    CREATE_CALENDAR_EVENT = "create_calendar_event"
    UPDATE_CALENDAR_EVENT = "update_calendar_event"
    DELETE_CALENDAR_EVENT = "delete_calendar_event"
    
    # Bulk operations (CRITICAL risk - require approval)
    BULK_CREATE_CONTACTS = "bulk_create_contacts"
    BULK_UPDATE_CONTACTS = "bulk_update_contacts"
    BULK_SEND_EMAIL = "bulk_send_email"
    
    # Destructive operations (BLOCKED by default)
    DELETE_CONTACT = "delete_contact"
    BULK_DELETE = "bulk_delete"


class RiskLevel(Enum):
    """Risk levels for operations."""
    LOW = "low"           # Read-only operations
    MEDIUM = "medium"     # Single record modifications
    HIGH = "high"         # Outreach/bulk operations
    CRITICAL = "critical" # Requires human approval


class AgentName(Enum):
    """All 12 agents in the unified swarm."""
    UNIFIED_QUEEN = "UNIFIED_QUEEN"
    HUNTER = "HUNTER"
    ENRICHER = "ENRICHER"
    SEGMENTOR = "SEGMENTOR"
    CRAFTER = "CRAFTER"
    GATEKEEPER = "GATEKEEPER"
    SCOUT = "SCOUT"
    OPERATOR = "OPERATOR"
    COACH = "COACH"
    PIPER = "PIPER"
    SCHEDULER = "SCHEDULER"
    RESEARCHER = "RESEARCHER"


@dataclass
class GroundingEvidence:
    """Evidence required for high-risk actions."""
    source: str  # e.g., "supabase", "ghl", "clay"
    data_id: str  # e.g., "lead_123", "contact_456"
    verified_at: str  # ISO timestamp
    additional_context: Optional[Dict[str, Any]] = None
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'GroundingEvidence':
        # SECURITY FIX: Require explicit verified_at - don't default to "now"
        # This prevents forged grounding evidence
        verified_at = d.get("verified_at")
        if not verified_at:
            raise ValueError("Grounding evidence must include explicit 'verified_at' timestamp")
        
        # Validate source is from allowed list
        ALLOWED_SOURCES = {"supabase", "ghl", "clay", "rb2b", "manual", "canary_test", "internal"}
        source = d.get("source", "unknown")
        if source not in ALLOWED_SOURCES:
            raise ValueError(f"Grounding source '{source}' not in allowed list: {ALLOWED_SOURCES}")
        
        return cls(
            source=source,
            data_id=d.get("data_id", "unknown"),
            verified_at=verified_at,
            additional_context=d.get("additional_context")
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def is_valid(self) -> bool:
        """Check if evidence is recent (within 1 hour)."""
        try:
            verified = datetime.fromisoformat(self.verified_at.replace('Z', '+00:00'))
            if verified.tzinfo is None:
                verified = verified.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - verified
            return age < timedelta(hours=1)
        except Exception as exc:
            logger.warning("Grounding evidence validation failed: %s", exc)
            return False


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    per_minute: int = 30
    per_hour: int = 150
    per_day: int = 3000
    min_delay_seconds: float = 0.5


@dataclass
class ActionResult:
    """Result of a guarded action execution."""
    success: bool
    action_type: str
    agent: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result: Optional[Any] = None
    error: Optional[str] = None
    blocked_reason: Optional[str] = None
    execution_time_ms: float = 0
    grounding_verified: bool = False


# =============================================================================
# PERMISSION MATRIX
# =============================================================================

ACTION_RISK_LEVELS: Dict[ActionType, RiskLevel] = {
    # LOW risk
    ActionType.READ_CONTACT: RiskLevel.LOW,
    ActionType.READ_PIPELINE: RiskLevel.LOW,
    ActionType.READ_CALENDAR: RiskLevel.LOW,
    ActionType.SEARCH_CONTACTS: RiskLevel.LOW,
    ActionType.GET_TEMPLATES: RiskLevel.LOW,
    
    # MEDIUM risk
    ActionType.CREATE_CONTACT: RiskLevel.MEDIUM,
    ActionType.UPDATE_CONTACT: RiskLevel.MEDIUM,
    ActionType.ADD_TAG: RiskLevel.MEDIUM,
    ActionType.REMOVE_TAG: RiskLevel.MEDIUM,
    ActionType.CREATE_TASK: RiskLevel.MEDIUM,
    ActionType.UPDATE_OPPORTUNITY: RiskLevel.MEDIUM,
    ActionType.CREATE_CALENDAR_EVENT: RiskLevel.MEDIUM,
    ActionType.UPDATE_CALENDAR_EVENT: RiskLevel.MEDIUM,
    ActionType.DELETE_CALENDAR_EVENT: RiskLevel.MEDIUM,
    
    # HIGH risk (require grounding)
    ActionType.SEND_EMAIL: RiskLevel.HIGH,
    ActionType.SEND_SMS: RiskLevel.HIGH,
    ActionType.SCHEDULE_EMAIL: RiskLevel.HIGH,
    ActionType.TRIGGER_WORKFLOW: RiskLevel.HIGH,
    
    # CRITICAL risk (require approval)
    ActionType.BULK_CREATE_CONTACTS: RiskLevel.CRITICAL,
    ActionType.BULK_UPDATE_CONTACTS: RiskLevel.CRITICAL,
    ActionType.BULK_SEND_EMAIL: RiskLevel.CRITICAL,
    ActionType.DELETE_CONTACT: RiskLevel.CRITICAL,
    ActionType.BULK_DELETE: RiskLevel.CRITICAL,
}

# Agent permissions: what actions each agent can perform
AGENT_PERMISSIONS: Dict[AgentName, List[ActionType]] = {
    AgentName.UNIFIED_QUEEN: list(ActionType),  # All actions
    
    AgentName.HUNTER: [
        ActionType.READ_CONTACT, ActionType.SEARCH_CONTACTS,
        ActionType.CREATE_CONTACT, ActionType.UPDATE_CONTACT,
        ActionType.ADD_TAG,
    ],
    
    AgentName.ENRICHER: [
        ActionType.READ_CONTACT, ActionType.UPDATE_CONTACT,
        ActionType.ADD_TAG,
    ],
    
    AgentName.SEGMENTOR: [
        ActionType.READ_CONTACT, ActionType.READ_PIPELINE,
        ActionType.UPDATE_CONTACT, ActionType.ADD_TAG, ActionType.REMOVE_TAG,
    ],
    
    AgentName.CRAFTER: [
        ActionType.READ_CONTACT, ActionType.GET_TEMPLATES,
        ActionType.CREATE_TASK,
    ],
    
    AgentName.GATEKEEPER: [
        ActionType.READ_CONTACT, ActionType.READ_PIPELINE,
        ActionType.SEND_EMAIL, ActionType.SEND_SMS,
        ActionType.SCHEDULE_EMAIL, ActionType.TRIGGER_WORKFLOW,
        ActionType.BULK_SEND_EMAIL,  # Only GATEKEEPER can approve bulk sends
    ],
    
    AgentName.SCOUT: [
        ActionType.READ_CONTACT, ActionType.READ_PIPELINE,
        ActionType.SEARCH_CONTACTS,
    ],
    
    AgentName.OPERATOR: [
        ActionType.READ_CONTACT, ActionType.READ_PIPELINE,
        ActionType.UPDATE_OPPORTUNITY, ActionType.TRIGGER_WORKFLOW,
    ],
    
    AgentName.COACH: [
        ActionType.READ_CONTACT, ActionType.READ_PIPELINE,
        ActionType.UPDATE_CONTACT, ActionType.ADD_TAG,
    ],
    
    AgentName.PIPER: [
        ActionType.READ_CONTACT, ActionType.READ_PIPELINE,
        ActionType.UPDATE_OPPORTUNITY,
    ],
    
    AgentName.SCHEDULER: [
        ActionType.READ_CALENDAR, ActionType.CREATE_CALENDAR_EVENT,
        ActionType.UPDATE_CALENDAR_EVENT, ActionType.DELETE_CALENDAR_EVENT,
        ActionType.READ_CONTACT,
    ],
    
    AgentName.RESEARCHER: [
        ActionType.READ_CONTACT, ActionType.SEARCH_CONTACTS,
        ActionType.READ_PIPELINE,
    ],
}

# Blocked operations (never allowed)
BLOCKED_ACTIONS: List[ActionType] = [
    ActionType.BULK_DELETE,
]


# =============================================================================
# PERMISSIONS CONFIG LOADER
# =============================================================================

class PermissionsConfigLoader:
    """
    Loads and manages agent permissions from JSON configuration.
    
    The JSON config provides:
    - Agent-specific permissions and rate limits
    - Action definitions with risk levels
    - Approval rules for high-risk operations
    - Blocked operations list
    """
    
    _instance: Optional['PermissionsConfigLoader'] = None
    _config: Optional[Dict[str, Any]] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
            self._load_config()
    
    def _load_config(self):
        """Load permissions from JSON config file."""
        if PERMISSIONS_CONFIG_PATH.exists():
            try:
                with open(PERMISSIONS_CONFIG_PATH) as f:
                    self._config = json.load(f)
            except json.JSONDecodeError as e:
                print(f"[PermissionsConfig] Failed to load config: {e}")
                self._config = {}
        else:
            self._config = {}
    
    def reload(self):
        """Reload config from disk."""
        self._load_config()
    
    @property
    def config(self) -> Dict[str, Any]:
        return self._config or {}
    
    def get_agent_config(self, agent_name: str) -> Dict[str, Any]:
        """Get configuration for a specific agent."""
        return self.config.get("agents", {}).get(agent_name, {})
    
    def get_agent_allowed_actions(self, agent_name: str) -> List[str]:
        """Get allowed actions for an agent from config."""
        agent_config = self.get_agent_config(agent_name)
        allowed = agent_config.get("allowed_actions", [])
        if "*" in allowed:
            # All actions allowed except explicitly denied
            denied = set(agent_config.get("denied_actions", []))
            return [a for a in ActionType if a.value not in denied]
        return allowed
    
    def get_agent_denied_actions(self, agent_name: str) -> List[str]:
        """Get denied actions for an agent."""
        return self.get_agent_config(agent_name).get("denied_actions", [])
    
    def get_agent_rate_limits(self, agent_name: str) -> Dict[str, int]:
        """Get rate limits for an agent."""
        defaults = {"per_minute": 30, "per_hour": 150, "per_day": 1500}
        agent_config = self.get_agent_config(agent_name)
        return agent_config.get("rate_limits", defaults)
    
    def can_agent_approve(self, agent_name: str) -> bool:
        """Check if an agent can approve actions."""
        return self.get_agent_config(agent_name).get("can_approve", False)
    
    def get_agent_approval_weight(self, agent_name: str) -> int:
        """Get approval weight for an agent (higher = more authority)."""
        return self.get_agent_config(agent_name).get("approval_weight", 1)
    
    def get_action_definition(self, action_name: str) -> Dict[str, Any]:
        """Get definition for an action type."""
        return self.config.get("action_definitions", {}).get(action_name, {})
    
    def get_action_risk_level(self, action_name: str) -> str:
        """Get risk level for an action from config."""
        action_def = self.get_action_definition(action_name)
        return action_def.get("risk_level", "MEDIUM")
    
    def is_action_blocked(self, action_name: str) -> Tuple[bool, Optional[str]]:
        """Check if an action is blocked globally."""
        # Check action definition
        action_def = self.get_action_definition(action_name)
        if action_def.get("blocked", False):
            return True, action_def.get("blocked_reason", "Action is blocked")
        
        # Check blocked operations list
        for blocked in self.config.get("blocked_operations", []):
            if blocked.get("action") == action_name:
                return True, blocked.get("reason", "Action is blocked")
        
        return False, None
    
    def get_approval_rules(self, rule_type: str) -> Dict[str, Any]:
        """Get approval rules for a specific type."""
        return self.config.get("approval_rules", {}).get(rule_type, {})
    
    def get_rate_limit_defaults(self, service: str) -> Dict[str, int]:
        """Get default rate limits for a service."""
        return self.config.get("rate_limit_defaults", {}).get(service, {})
    
    def get_all_agents(self) -> List[str]:
        """Get list of all configured agents."""
        return list(self.config.get("agents", {}).keys())
    
    def validate_config(self) -> Tuple[bool, List[str]]:
        """Validate the loaded configuration."""
        errors = []
        
        # Check required sections
        required_sections = ["agents", "action_definitions", "risk_levels"]
        for section in required_sections:
            if section not in self.config:
                errors.append(f"Missing required section: {section}")
        
        # Validate each agent has required fields
        for agent_name, agent_config in self.config.get("agents", {}).items():
            if "allowed_actions" not in agent_config:
                errors.append(f"Agent {agent_name} missing 'allowed_actions'")
            if "role" not in agent_config:
                errors.append(f"Agent {agent_name} missing 'role'")
        
        return len(errors) == 0, errors


# Global config loader instance
def get_permissions_config() -> PermissionsConfigLoader:
    """Get the global permissions config loader."""
    return PermissionsConfigLoader()


# =============================================================================
# RATE LIMITER
# =============================================================================

class UnifiedRateLimiter:
    """Unified rate limiter for all agents and services."""
    
    DEFAULT_LIMITS = RateLimitConfig(per_minute=30, per_hour=150, per_day=3000)
    
    GHL_LIMITS = RateLimitConfig(per_minute=20, per_hour=20, per_day=150)
    EMAIL_LIMITS = RateLimitConfig(per_minute=2, per_hour=20, per_day=150)
    _WINDOWS = (
        ("minute", 60, "per_minute"),
        ("hour", 3600, "per_hour"),
        ("day", 86400, "per_day"),
    )
    
    def __init__(
        self,
        storage_path: Optional[Path] = None,
        redis_url: Optional[str] = None,
        redis_namespace: str = "caio:ratelimit",
    ):
        self.storage_path = storage_path or PROJECT_ROOT / ".hive-mind" / "rate_limits.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        
        self.redis_namespace = os.getenv("RATE_LIMIT_REDIS_NAMESPACE", redis_namespace)
        self._redis = None
        self._use_redis = False
        configured_redis_url = os.getenv("REDIS_URL") if redis_url is None else redis_url
        self._initialize_redis(configured_redis_url)
        
        self.counters: Dict[str, Dict[str, List[float]]] = defaultdict(
            lambda: {"minute": [], "hour": [], "day": []}
        )
        if not self._use_redis:
            self._load_state()
    
    def _initialize_redis(self, redis_url: Optional[str]) -> None:
        if not redis_url or redis is None:
            return
        try:
            self._redis = redis.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            self._redis.ping()
            self._use_redis = True
            logger.info("UnifiedRateLimiter configured with Redis backend")
        except Exception as exc:
            self._use_redis = False
            self._redis = None
            logger.warning(
                "Redis unavailable for UnifiedRateLimiter (%s), using file fallback.",
                exc,
            )
    
    def _redis_key(self, key: str, window_name: str) -> str:
        normalized = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in key)
        return f"{self.redis_namespace}:{window_name}:{normalized}"
    
    def _load_state(self):
        if not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, encoding="utf-8") as f:
                data = json.load(f)
            for key, counters in data.get("counters", {}).items():
                if isinstance(counters, dict):
                    self.counters[key] = {
                        "minute": list(counters.get("minute", [])),
                        "hour": list(counters.get("hour", [])),
                        "day": list(counters.get("day", [])),
                    }
        except Exception as exc:
            logger.warning("Failed to load rate-limit state from %s: %s", self.storage_path, exc)
    
    def _save_state_locked(self):
        data = {
            "counters": dict(self.counters),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        fd = None
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(
                suffix=".json",
                prefix="rate_limits_",
                dir=str(self.storage_path.parent),
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fd = None
                json.dump(data, f)
            os.replace(temp_path, self.storage_path)
            temp_path = None
        finally:
            if fd is not None:
                os.close(fd)
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
    
    def _clean_old_timestamps(self, key: str):
        """Remove timestamps outside windows."""
        now = time.time()
        counters = self.counters[key]
        counters["minute"] = [t for t in counters["minute"] if now - t < 60]
        counters["hour"] = [t for t in counters["hour"] if now - t < 3600]
        counters["day"] = [t for t in counters["day"] if now - t < 86400]
    
    def _get_redis_counts(self, key: str) -> Optional[Dict[str, int]]:
        if not self._use_redis or not self._redis:
            return None
        now = time.time()
        try:
            pipe = self._redis.pipeline(transaction=True)
            for window_name, window_seconds, _ in self._WINDOWS:
                redis_key = self._redis_key(key, window_name)
                pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
                pipe.zcard(redis_key)
            results = pipe.execute()
            counts: Dict[str, int] = {}
            idx = 0
            for window_name, _, _ in self._WINDOWS:
                idx += 1  # skip zremrangebyscore result
                counts[window_name] = int(results[idx])
                idx += 1
            return counts
        except Exception as exc:
            logger.warning("Redis check_limit failed, falling back to file backend: %s", exc)
            self._use_redis = False
            self._redis = None
            return None
    
    def check_limit(self, key: str, limits: Optional[RateLimitConfig] = None) -> Tuple[bool, Optional[str]]:
        """Check if rate limit allows action. Returns (allowed, reason)."""
        limits = limits or self.DEFAULT_LIMITS
        
        counts = self._get_redis_counts(key)
        if counts is not None:
            if counts["minute"] >= limits.per_minute:
                return False, f"Rate limit: {limits.per_minute}/minute exceeded"
            if counts["hour"] >= limits.per_hour:
                return False, f"Rate limit: {limits.per_hour}/hour exceeded"
            if counts["day"] >= limits.per_day:
                return False, f"Rate limit: {limits.per_day}/day exceeded"
            return True, None
        
        with self._lock:
            self._clean_old_timestamps(key)
            counters = self.counters[key]
            
            if len(counters["minute"]) >= limits.per_minute:
                return False, f"Rate limit: {limits.per_minute}/minute exceeded"
            if len(counters["hour"]) >= limits.per_hour:
                return False, f"Rate limit: {limits.per_hour}/hour exceeded"
            if len(counters["day"]) >= limits.per_day:
                return False, f"Rate limit: {limits.per_day}/day exceeded"
            
            return True, None
    
    def record_action(self, key: str):
        """Record an action timestamp."""
        now = time.time()
        
        if self._use_redis and self._redis:
            try:
                pipe = self._redis.pipeline(transaction=True)
                member = f"{now}:{uuid.uuid4().hex}"
                for window_name, window_seconds, _ in self._WINDOWS:
                    redis_key = self._redis_key(key, window_name)
                    pipe.zadd(redis_key, {member: now})
                    pipe.expire(redis_key, window_seconds + 120)
                pipe.execute()
                return
            except Exception as exc:
                logger.warning("Redis record_action failed, falling back to file backend: %s", exc)
                self._use_redis = False
                self._redis = None
        
        with self._lock:
            self._clean_old_timestamps(key)
            self.counters[key]["minute"].append(now)
            self.counters[key]["hour"].append(now)
            self.counters[key]["day"].append(now)
            self._save_state_locked()
    
    def get_usage(self, key: str, limits: Optional[RateLimitConfig] = None) -> Dict[str, Any]:
        """Get current usage for a key."""
        limits = limits or self.DEFAULT_LIMITS
        
        counts = self._get_redis_counts(key)
        if counts is None:
            with self._lock:
                self._clean_old_timestamps(key)
                counters = self.counters[key]
                counts = {
                    "minute": len(counters["minute"]),
                    "hour": len(counters["hour"]),
                    "day": len(counters["day"]),
                }
        
        return {
            "minute": {"used": counts["minute"], "limit": limits.per_minute},
            "hour": {"used": counts["hour"], "limit": limits.per_hour},
            "day": {"used": counts["day"], "limit": limits.per_day},
        }


# =============================================================================
# HOOK SYSTEM
# =============================================================================

@dataclass
class Hook:
    """Pre/post execution hook."""
    name: str
    callback: Callable
    priority: int = 0  # Higher = runs first


class HookSystem:
    """Pre and post execution hooks."""
    
    def __init__(self):
        self.pre_hooks: List[Hook] = []
        self.post_hooks: List[Hook] = []
        self.error_hooks: List[Hook] = []
    
    def register_pre_hook(self, name: str, callback: Callable, priority: int = 0):
        self.pre_hooks.append(Hook(name, callback, priority))
        self.pre_hooks.sort(key=lambda h: -h.priority)
    
    def register_post_hook(self, name: str, callback: Callable, priority: int = 0):
        self.post_hooks.append(Hook(name, callback, priority))
        self.post_hooks.sort(key=lambda h: -h.priority)
    
    def register_error_hook(self, name: str, callback: Callable, priority: int = 0):
        self.error_hooks.append(Hook(name, callback, priority))
        self.error_hooks.sort(key=lambda h: -h.priority)
    
    async def run_pre_hooks(self, context: Dict[str, Any]) -> Dict[str, Any]:
        for hook in self.pre_hooks:
            try:
                result = hook.callback(context)
                if asyncio.iscoroutine(result):
                    result = await result
                if isinstance(result, dict):
                    context.update(result)
            except Exception as e:
                context["hook_errors"] = context.get("hook_errors", [])
                context["hook_errors"].append(f"{hook.name}: {e}")
        return context
    
    async def run_post_hooks(self, context: Dict[str, Any], result: ActionResult):
        for hook in self.post_hooks:
            try:
                res = hook.callback(context, result)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                context["hook_errors"] = context.get("hook_errors", [])
                context["hook_errors"].append(f"{hook.name}: {e}")
                logger.error("Post-hook '%s' failed: %s", hook.name, e)
    
    async def run_error_hooks(self, context: Dict[str, Any], error: Exception):
        for hook in self.error_hooks:
            try:
                res = hook.callback(context, error)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as hook_error:
                context["hook_errors"] = context.get("hook_errors", [])
                context["hook_errors"].append(f"{hook.name}: {hook_error}")
                logger.error("Error-hook '%s' failed: %s", hook.name, hook_error)


# =============================================================================
# EXPONENTIAL BACKOFF
# =============================================================================

class ExponentialBackoff:
    """Exponential backoff with jitter."""
    
    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        jitter: float = 0.1
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter
        self.attempts: Dict[str, int] = {}
    
    def get_delay(self, key: str) -> float:
        """Get delay for next retry."""
        attempts = self.attempts.get(key, 0)
        delay = min(self.base_delay * (self.multiplier ** attempts), self.max_delay)
        
        # Add jitter
        import random
        jitter_range = delay * self.jitter
        delay += random.uniform(-jitter_range, jitter_range)
        
        return max(0, delay)
    
    def record_attempt(self, key: str):
        """Record a failed attempt."""
        self.attempts[key] = self.attempts.get(key, 0) + 1
    
    def reset(self, key: str):
        """Reset attempts on success."""
        self.attempts.pop(key, None)
    
    def get_attempts(self, key: str) -> int:
        return self.attempts.get(key, 0)


# =============================================================================
# UNIFIED GUARDRAILS
# =============================================================================

class UnifiedGuardrails:
    """
    Main entry point for the unified guardrails system.
    
    Combines circuit breakers, rate limiting, permission checks,
    grounding validation, and hook system into a single interface.
    """
    
    def __init__(
        self,
        storage_path: Optional[Path] = None,
        circuit_failure_threshold: int = 3,
        circuit_recovery_timeout: int = 300,  # 5 minutes
        use_json_config: bool = True
    ):
        self.storage_path = storage_path or PROJECT_ROOT / ".hive-mind"
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize subsystems
        self.circuit_registry = get_circuit_registry()
        self.rate_limiter = UnifiedRateLimiter(self.storage_path / "rate_limits.json")
        self.hook_system = HookSystem()
        self.backoff = ExponentialBackoff()
        
        # Load permissions from JSON config
        self.use_json_config = use_json_config
        self.permissions_config = get_permissions_config() if use_json_config else None
        
        # Register per-agent circuit breakers
        for agent in AgentName:
            self.circuit_registry.register(
                f"agent_{agent.value}",
                failure_threshold=circuit_failure_threshold,
                recovery_timeout=circuit_recovery_timeout
            )
        
        # Audit trail (SQLite-based)
        self.audit_trail: Optional[AuditTrail] = None
        
        # Register default hooks
        self._register_default_hooks()
    
    def _register_default_hooks(self):
        """Register default pre/post hooks."""
        
        def log_action_pre(context: Dict[str, Any]) -> Dict[str, Any]:
            context["start_time"] = time.time()
            return context
        
        async def log_action_post(context: Dict[str, Any], result: ActionResult):
            await self._log_audit(context, result)
        
        self.hook_system.register_pre_hook("timing", log_action_pre, priority=100)
        self.hook_system.register_post_hook("audit", log_action_post, priority=100)
    
    async def _ensure_audit_trail(self) -> AuditTrail:
        """Lazily initialize and return the audit trail."""
        if self.audit_trail is None:
            self.audit_trail = await get_audit_trail()
        return self.audit_trail
    
    async def _log_audit(self, context: Dict[str, Any], result: ActionResult):
        """Log action to audit trail (SQLite)."""
        try:
            trail = await self._ensure_audit_trail()
            
            # Determine risk level from action type
            action_type_str = result.action_type
            risk_level = "MEDIUM"
            try:
                action_enum = ActionType(action_type_str)
                risk = ACTION_RISK_LEVELS.get(action_enum, RiskLevel.MEDIUM)
                risk_level = risk.value.upper()
            except ValueError:
                pass
            
            details = {
                "grounding_verified": result.grounding_verified,
                "blocked_reason": result.blocked_reason,
            }
            
            await trail.log_action(
                agent_name=result.agent,
                action_type=result.action_type,
                details=details,
                status="success" if result.success else "failure",
                risk_level=risk_level,
                duration_ms=result.execution_time_ms,
                error=result.error
            )
        except Exception as exc:
            logger.error("Audit trail write failed: %s", exc)
    
    def _emit_execution_trace(self, context: Dict[str, Any], result: ActionResult):
        """Emit deterministic trace envelope for guardrail execution."""
        try:
            grounding = context.get("grounding_evidence") or {}
            context_refs: List[str] = []
            if isinstance(grounding, dict):
                data_id = grounding.get("data_id")
                if data_id:
                    context_refs.append(str(data_id))
            
            error_message = result.error or result.blocked_reason
            error_code = None
            if result.blocked_reason:
                error_code = "GUARDRAIL_BLOCKED"
            elif result.error:
                error_code = "ACTION_EXECUTION_ERROR"
            
            emit_tool_trace(
                correlation_id=context.get("correlation_id"),
                case_id=context.get("case_id"),
                agent=result.agent,
                tool_name=f"UnifiedGuardrails.execute:{result.action_type}",
                tool_input=context.get("parameters"),
                tool_output=result.result if result.success else {"error": error_message},
                retrieved_context_refs=context_refs,
                status="success" if result.success else "failure",
                duration_ms=result.execution_time_ms,
                error_code=error_code,
                error_message=error_message,
            )
        except Exception as exc:
            logger.warning("Failed to emit guardrail trace: %s", exc)
    
    async def get_audit_log(self, limit: int = 100) -> List[Dict]:
        """Query recent audit log entries."""
        trail = await self._ensure_audit_trail()
        return await trail.get_logs(limit=limit)
    
    def get_agent_permissions(self, agent_name: str) -> List[ActionType]:
        """Get allowed actions for an agent."""
        # Try JSON config first if enabled
        if self.use_json_config and self.permissions_config:
            allowed = self.permissions_config.get_agent_allowed_actions(agent_name)
            if allowed:
                # Convert string action names to ActionType enums
                result = []
                for action in allowed:
                    if isinstance(action, ActionType):
                        result.append(action)
                    else:
                        try:
                            result.append(ActionType(action))
                        except ValueError:
                            pass
                return result
        
        # Fall back to hardcoded permissions
        try:
            agent = AgentName(agent_name)
            return AGENT_PERMISSIONS.get(agent, [])
        except ValueError:
            return []
    
    def get_agent_config(self, agent_name: str) -> Dict[str, Any]:
        """Get full configuration for an agent from JSON config."""
        if self.use_json_config and self.permissions_config:
            return self.permissions_config.get_agent_config(agent_name)
        return {}
    
    def can_agent_approve(self, agent_name: str) -> bool:
        """Check if an agent has approval authority."""
        if self.use_json_config and self.permissions_config:
            return self.permissions_config.can_agent_approve(agent_name)
        return agent_name in ["UNIFIED_QUEEN", "GATEKEEPER"]
    
    def get_agent_approval_weight(self, agent_name: str) -> int:
        """Get approval weight for Byzantine consensus voting."""
        if self.use_json_config and self.permissions_config:
            return self.permissions_config.get_agent_approval_weight(agent_name)
        return 3 if agent_name == "UNIFIED_QUEEN" else 1
    
    def validate_action(
        self,
        agent_name: str,
        action_type: ActionType,
        grounding_evidence: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate if an agent can perform an action.
        
        Returns (is_valid, reason_if_invalid)
        """
        # Check if action is globally blocked (JSON config first)
        if self.use_json_config and self.permissions_config:
            blocked, reason = self.permissions_config.is_action_blocked(action_type.value)
            if blocked:
                return False, reason
        elif action_type in BLOCKED_ACTIONS:
            return False, f"Action {action_type.value} is blocked globally"
        
        # Check agent permissions (uses JSON config if enabled)
        try:
            agent = AgentName(agent_name)
        except ValueError:
            return False, f"Unknown agent: {agent_name}"
        
        allowed_actions = self.get_agent_permissions(agent_name)
        if action_type not in allowed_actions:
            return False, f"Agent {agent_name} not permitted to perform {action_type.value}"
        
        # Check denied actions from JSON config
        if self.use_json_config and self.permissions_config:
            denied = self.permissions_config.get_agent_denied_actions(agent_name)
            if action_type.value in denied:
                return False, f"Action {action_type.value} explicitly denied for {agent_name}"
        
        # Check risk level and grounding requirements
        if self.use_json_config and self.permissions_config:
            risk_str = self.permissions_config.get_action_risk_level(action_type.value)
            risk = RiskLevel(risk_str.lower()) if risk_str else RiskLevel.MEDIUM
        else:
            risk = ACTION_RISK_LEVELS.get(action_type, RiskLevel.MEDIUM)
        
        if risk in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            if not grounding_evidence:
                return False, f"High-risk action {action_type.value} requires grounding evidence"
            
            evidence = GroundingEvidence.from_dict(grounding_evidence)
            if not evidence.is_valid():
                return False, "Grounding evidence is stale (>1 hour old)"
        
        # Check circuit breaker
        breaker_key = f"agent_{agent_name}"
        if not self.circuit_registry.is_available(breaker_key):
            retry_in = self.circuit_registry.get_time_until_retry(breaker_key)
            return False, f"Circuit breaker open for {agent_name}, retry in {retry_in:.0f}s"
        
        return True, None
    
    def check_rate_limits(
        self,
        agent_name: str,
        action_type: ActionType
    ) -> Tuple[bool, Optional[str]]:
        """Check all applicable rate limits."""
        # Agent-level limit
        agent_key = f"agent_{agent_name}"
        allowed, reason = self.rate_limiter.check_limit(agent_key)
        if not allowed:
            return False, f"Agent {agent_name}: {reason}"
        
        # Action-type limit (stricter for email/SMS)
        if action_type in [ActionType.SEND_EMAIL, ActionType.SCHEDULE_EMAIL]:
            email_key = "ghl_email"
            allowed, reason = self.rate_limiter.check_limit(
                email_key, 
                UnifiedRateLimiter.EMAIL_LIMITS
            )
            if not allowed:
                return False, f"Email: {reason}"
        
        # GHL global limit
        if action_type.value.startswith(("send_", "create_", "update_", "trigger_")):
            ghl_key = "ghl_global"
            allowed, reason = self.rate_limiter.check_limit(
                ghl_key,
                UnifiedRateLimiter.GHL_LIMITS
            )
            if not allowed:
                return False, f"GHL: {reason}"
        
        return True, None
    
    def redact_pii(self, text: str) -> str:
        """
        Redact personally identifiable information from text.
        
        Redacts:
        - Email addresses
        - SSN (XXX-XX-XXXX)
        - Credit cards
        - Phone numbers
        """
        import re
        
        # Email
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL_REDACTED]', text)
        
        # SSN
        text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[SSN_REDACTED]', text)
        
        # Credit card
        text = re.sub(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b', '[CARD_REDACTED]', text)
        
        # Phone numbers
        text = re.sub(r'\(\d{3}\)\s?\d{3}-\d{4}', '[PHONE_REDACTED]', text)
        text = re.sub(r'\b\d{3}-\d{4}\b', '[PHONE_REDACTED]', text)
        
        return text
    
    def assess_risk(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Assess risk level of an action.
        
        Args:
            action: Dict with "type", "operation", "target" keys
        
       Returns:
            Dict with "level" (RiskLevel), "requires_approval" (bool)
        """
        action_type = action.get("type")
        operation = action.get("operation", "").upper()
        
        # Handle generic action types (for testing)
        if isinstance(action_type, str):
            # Map generic types to risk levels
            if "DATABASE_WRITE" in str(action_type) or "DELETE" in operation:
                risk_level = RiskLevel.HIGH
            elif "DATABASE_READ" in str(action_type) or "SELECT" in operation:
                risk_level = RiskLevel.LOW
            else:
                risk_level = RiskLevel.MEDIUM
        elif isinstance(action_type, ActionType):
            risk_level = ACTION_RISK_LEVELS.get(action_type, RiskLevel.MEDIUM)
        else:
            risk_level = RiskLevel.MEDIUM
        
        requires_approval = risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        
        return {
            "level": risk_level,
            "requires_approval": requires_approval
        }
    
    def check_rate_limit(self, api_name: str, limit: int, window: int) -> bool:
        """
        Check if an API call is within rate limit.
        
        Args:
            api_name: Name of the API
            limit: Maximum calls allowed
            window: Time window in seconds
        
        Returns:
            True if allowed, False if rate limited
        """
        # Create custom config for this check
        if window == 3600:  # Hourly
            config = RateLimitConfig(per_minute=999999, per_hour=limit, per_day=999999)
        elif window == 60:  # Per minute
            config = RateLimitConfig(per_minute=limit, per_hour=999999, per_day=999999)
        else:  # Daily
            config = RateLimitConfig(per_minute=999999, per_hour=999999, per_day=limit)
        
        allowed, _ = self.rate_limiter.check_limit(api_name, config)
        
        if allowed:
            self.rate_limiter.record_action(api_name)
        
        return allowed
    
    async def execute_with_guardrails(
        self,
        agent_name: str,
        action_type: ActionType,
        action_fn: Callable,
        parameters: Optional[Dict[str, Any]] = None,
        grounding_evidence: Optional[Dict[str, Any]] = None
    ) -> ActionResult:
        """
        Execute an action with full guardrail protection.
        
        Args:
            agent_name: Name of the agent performing the action
            action_type: Type of action being performed
            action_fn: The function to execute
            parameters: Parameters to pass to the function
            grounding_evidence: Required for high-risk actions
        
        Returns:
            ActionResult with success/failure details
        """
        parameters = parameters or {}
        start_time = time.time()
        
        context = {
            "agent_name": agent_name,
            "action_type": action_type,
            "parameters": parameters,
            "grounding_evidence": grounding_evidence,
            "correlation_id": get_current_correlation_id(),
            "case_id": get_current_case_id(),
        }
        
        # Run pre-hooks
        context = await self.hook_system.run_pre_hooks(context)
        
        # Validate action
        valid, reason = self.validate_action(agent_name, action_type, grounding_evidence)
        if not valid:
            result = ActionResult(
                success=False,
                action_type=action_type.value,
                agent=agent_name,
                blocked_reason=reason,
                execution_time_ms=(time.time() - start_time) * 1000
            )
            await self.hook_system.run_post_hooks(context, result)
            self._emit_execution_trace(context, result)
            return result
        
        # Check rate limits
        allowed, limit_reason = self.check_rate_limits(agent_name, action_type)
        if not allowed:
            result = ActionResult(
                success=False,
                action_type=action_type.value,
                agent=agent_name,
                blocked_reason=limit_reason,
                execution_time_ms=(time.time() - start_time) * 1000
            )
            await self.hook_system.run_post_hooks(context, result)
            self._emit_execution_trace(context, result)
            return result
        
        # Check backoff
        backoff_key = f"{agent_name}_{action_type.value}"
        if self.backoff.get_attempts(backoff_key) > 0:
            delay = self.backoff.get_delay(backoff_key)
            if delay > 0:
                await asyncio.sleep(delay)
        
        # Execute action
        breaker_key = f"agent_{agent_name}"
        try:
            if asyncio.iscoroutinefunction(action_fn):
                action_result = await action_fn(**parameters)
            else:
                action_result = action_fn(**parameters)
            
            # Record success
            self.circuit_registry.record_success(breaker_key)
            self.rate_limiter.record_action(f"agent_{agent_name}")
            self.backoff.reset(backoff_key)
            
            # Record for email/GHL limits
            if action_type in [ActionType.SEND_EMAIL, ActionType.SCHEDULE_EMAIL]:
                self.rate_limiter.record_action("ghl_email")
            if action_type.value.startswith(("send_", "create_", "update_", "trigger_")):
                self.rate_limiter.record_action("ghl_global")
            
            result = ActionResult(
                success=True,
                action_type=action_type.value,
                agent=agent_name,
                result=action_result,
                execution_time_ms=(time.time() - start_time) * 1000,
                grounding_verified=grounding_evidence is not None
            )
            
        except Exception as e:
            # Record failure
            self.circuit_registry.record_failure(breaker_key, e)
            self.backoff.record_attempt(backoff_key)
            
            await self.hook_system.run_error_hooks(context, e)
            
            result = ActionResult(
                success=False,
                action_type=action_type.value,
                agent=agent_name,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000
            )
        
        # Run post-hooks
        await self.hook_system.run_post_hooks(context, result)
        self._emit_execution_trace(context, result)
        
        return result
    
    def get_status(self) -> Dict[str, Any]:
        """Get overall guardrails status."""
        circuit_status = self.circuit_registry.get_status()
        
        agent_status = {}
        for agent in AgentName:
            breaker_key = f"agent_{agent.value}"
            agent_status[agent.value] = {
                "circuit_state": circuit_status.get(breaker_key, {}).get("state", "unknown"),
                "rate_usage": self.rate_limiter.get_usage(f"agent_{agent.value}"),
                "backoff_attempts": self.backoff.get_attempts(f"{agent.value}_send_email")
            }
        
        return {
            "agents": agent_status,
            "ghl_email_usage": self.rate_limiter.get_usage("ghl_email", UnifiedRateLimiter.EMAIL_LIMITS),
            "ghl_global_usage": self.rate_limiter.get_usage("ghl_global", UnifiedRateLimiter.GHL_LIMITS),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    
    def force_trip_circuit(self, agent_name: str):
        """Manually trip an agent's circuit breaker."""
        self.circuit_registry.force_open(f"agent_{agent_name}")
    
    def reset_circuit(self, agent_name: str):
        """Manually reset an agent's circuit breaker."""
        self.circuit_registry.force_close(f"agent_{agent_name}")
    
    async def execute_with_multi_layer_failsafe(
        self,
        agent_name: str,
        action_type: ActionType,
        action_fn: Callable,
        parameters: Optional[Dict[str, Any]] = None,
        grounding_evidence: Optional[Dict[str, Any]] = None,
        input_schema: Optional[List] = None,
        layers: Optional[List[int]] = None,
        require_consensus: bool = False,
        consensus_voters: Optional[List] = None
    ) -> ActionResult:
        """
        Execute an action with multi-layer failsafe protection.
        
        This method combines UnifiedGuardrails with MultiLayerFailsafe for
        enterprise-grade protection across all 4 layers:
        - Layer 1: Input Validation (type check, sanitize, injection detection)
        - Layer 2: Circuit Breaker (per-agent, exponential backoff)
        - Layer 3: Fallback Chain (primary → secondary → human escalation)
        - Layer 4: Byzantine Consensus (2/3 weighted agreement)
        
        Args:
            agent_name: Name of the agent performing the action
            action_type: Type of action being performed
            action_fn: The function to execute
            parameters: Parameters to pass to the function
            grounding_evidence: Required for high-risk actions
            input_schema: Optional schema for Layer 1 input validation
            layers: Which failsafe layers to apply (default: [1, 2])
            require_consensus: If True, requires Layer 4 Byzantine consensus
            consensus_voters: Pre-defined voters for quick consensus
        
        Returns:
            ActionResult with success/failure details
        """
        if not MULTI_LAYER_FAILSAFE_AVAILABLE:
            return await self.execute_with_guardrails(
                agent_name, action_type, action_fn, parameters, grounding_evidence
            )
        
        parameters = parameters or {}
        layers = layers or [1, 2]
        start_time = time.time()
        
        context = {
            "agent_name": agent_name,
            "action_type": action_type,
            "parameters": parameters,
            "grounding_evidence": grounding_evidence,
            "correlation_id": get_current_correlation_id(),
            "case_id": get_current_case_id(),
        }
        
        context = await self.hook_system.run_pre_hooks(context)
        
        valid, reason = self.validate_action(agent_name, action_type, grounding_evidence)
        if not valid:
            result = ActionResult(
                success=False,
                action_type=action_type.value,
                agent=agent_name,
                blocked_reason=reason,
                execution_time_ms=(time.time() - start_time) * 1000
            )
            await self.hook_system.run_post_hooks(context, result)
            self._emit_execution_trace(context, result)
            return result
        
        allowed, limit_reason = self.check_rate_limits(agent_name, action_type)
        if not allowed:
            result = ActionResult(
                success=False,
                action_type=action_type.value,
                agent=agent_name,
                blocked_reason=limit_reason,
                execution_time_ms=(time.time() - start_time) * 1000
            )
            await self.hook_system.run_post_hooks(context, result)
            self._emit_execution_trace(context, result)
            return result
        
        failsafe = get_failsafe()
        
        failsafe_result = await failsafe.execute_with_failsafe(
            agent_name=agent_name,
            operation=action_fn,
            input_data=parameters,
            input_schema=input_schema,
            layers=layers,
            require_consensus=require_consensus,
            consensus_voters=consensus_voters,
            operation_name=action_type.value
        )
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        if failsafe_result.get("success"):
            breaker_key = f"agent_{agent_name}"
            self.circuit_registry.record_success(breaker_key)
            self.rate_limiter.record_action(f"agent_{agent_name}")
            
            if action_type in [ActionType.SEND_EMAIL, ActionType.SCHEDULE_EMAIL]:
                self.rate_limiter.record_action("ghl_email")
            if action_type.value.startswith(("send_", "create_", "update_", "trigger_")):
                self.rate_limiter.record_action("ghl_global")
            
            result = ActionResult(
                success=True,
                action_type=action_type.value,
                agent=agent_name,
                result=failsafe_result.get("result"),
                execution_time_ms=execution_time_ms,
                grounding_verified=grounding_evidence is not None
            )
        else:
            breaker_key = f"agent_{agent_name}"
            error_msg = failsafe_result.get("error", "Unknown error")
            
            if failsafe_result.get("layer_blocked"):
                blocked_reason = f"Layer {failsafe_result['layer_blocked']}: {error_msg}"
            else:
                blocked_reason = error_msg
                self.circuit_registry.record_failure(breaker_key, Exception(error_msg))
            
            result = ActionResult(
                success=False,
                action_type=action_type.value,
                agent=agent_name,
                error=error_msg,
                blocked_reason=blocked_reason,
                execution_time_ms=execution_time_ms
            )
        
        await self.hook_system.run_post_hooks(context, result)
        self._emit_execution_trace(context, result)
        
        return result
    
    def get_multi_layer_failsafe_status(self) -> Dict[str, Any]:
        """Get MultiLayerFailsafe status if available."""
        if not MULTI_LAYER_FAILSAFE_AVAILABLE:
            return {"available": False}
        
        failsafe = get_failsafe()
        return {
            "available": True,
            "metrics": failsafe.get_metrics()
        }


# =============================================================================
# DECORATORS
# =============================================================================

def require_grounding(action_type: ActionType):
    """
    Decorator to require grounding evidence for a function.
    
    Usage:
        @require_grounding(ActionType.SEND_EMAIL)
        async def send_campaign_email(contact_id: str, grounding_evidence: dict):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, grounding_evidence: Optional[Dict] = None, **kwargs):
            if not grounding_evidence:
                raise ValueError(f"Action {action_type.value} requires grounding evidence")
            
            evidence = GroundingEvidence.from_dict(grounding_evidence)
            if not evidence.is_valid():
                raise ValueError("Grounding evidence is stale (>1 hour old)")
            
            return await func(*args, grounding_evidence=grounding_evidence, **kwargs)
        
        return wrapper
    return decorator


# =============================================================================
# DEMO / CLI
# =============================================================================

async def demo():
    """Demonstrate unified guardrails functionality."""
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    console.print("\n[bold blue]Unified Guardrails Demo[/bold blue]\n")
    
    guardrails = UnifiedGuardrails()
    
    # Show agent permissions
    table = Table(title="Agent Permissions Sample")
    table.add_column("Agent", style="cyan")
    table.add_column("Allowed Actions", style="green")
    
    for agent in [AgentName.CRAFTER, AgentName.GATEKEEPER, AgentName.SCHEDULER]:
        actions = guardrails.get_agent_permissions(agent.value)
        table.add_row(agent.value, ", ".join(a.value for a in actions[:4]) + "...")
    
    console.print(table)
    
    # Test action validation
    console.print("\n[bold]Action Validation Tests:[/bold]")
    
    tests = [
        ("CRAFTER", ActionType.READ_CONTACT, None, "Should pass"),
        ("CRAFTER", ActionType.SEND_EMAIL, None, "Should fail (no permission)"),
        ("GATEKEEPER", ActionType.SEND_EMAIL, None, "Should fail (needs grounding)"),
        ("GATEKEEPER", ActionType.SEND_EMAIL, {"source": "supabase", "data_id": "123", "verified_at": datetime.now(timezone.utc).isoformat()}, "Should pass"),
    ]
    
    for agent, action, evidence, expected in tests:
        valid, reason = guardrails.validate_action(agent, action, evidence)
        status = "✅" if valid else "❌"
        console.print(f"  {status} {agent}.{action.value}: {reason or 'Allowed'} ({expected})")
    
    # Test execution with guardrails
    console.print("\n[bold]Execution Tests:[/bold]")
    
    async def mock_read_contact(contact_id: str):
        return {"id": contact_id, "name": "John Doe"}
    
    result = await guardrails.execute_with_guardrails(
        agent_name="ENRICHER",
        action_type=ActionType.READ_CONTACT,
        action_fn=mock_read_contact,
        parameters={"contact_id": "test_123"}
    )
    console.print(f"  Read contact: {'✅' if result.success else '❌'} ({result.execution_time_ms:.2f}ms)")
    
    # Test rate limiting
    console.print("\n[bold]Rate Limit Status:[/bold]")
    status = guardrails.get_status()
    console.print(f"  GHL Email: {status['ghl_email_usage']}")
    
    console.print("\n[green]Demo complete![/green]")


if __name__ == "__main__":
    asyncio.run(demo())
