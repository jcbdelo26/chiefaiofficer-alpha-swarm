"""
Safety controls for SDR automation.
Provides kill switch, safe mode, and automatic halt triggers.
"""

import json
import os
import functools
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from core.event_log import log_event, EventType, EVENTS_FILE


class OperationType(Enum):
    CRM_WRITE = "crm_write"
    EMAIL_SEND = "email_send"
    SCRAPE = "scrape"


class KillSwitchError(Exception):
    """Raised when kill switch is active and operation is attempted."""
    pass


class SafeModeError(Exception):
    """Raised when safe mode blocks an operation (informational)."""
    pass


SAFETY_STATE_FILE = Path(".hive-mind/safety_state.json")

HALT_THRESHOLDS = {
    "bounce_rate_percent": 5.0,
    "spam_complaint_percent": 0.1,
    "error_rate_percent": 10.0,
    "compliance_failure_count": 5,
    "compliance_failure_window_hours": 1,
}


class SafetyMode:
    """
    Central safety controls for the SDR automation system.
    Reads state from environment variables and .hive-mind/safety_state.json.
    """

    _cached_state: Optional[dict[str, Any]] = None
    _cache_time: Optional[datetime] = None
    _cache_ttl_seconds: int = 5

    @classmethod
    def _load_state(cls, force: bool = False) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        if (
            not force
            and cls._cached_state is not None
            and cls._cache_time is not None
            and (now - cls._cache_time).total_seconds() < cls._cache_ttl_seconds
        ):
            return cls._cached_state

        state = {
            "safe_mode": False,
            "kill_switch": False,
            "kill_switch_reason": None,
            "activated_at": None,
        }

        if SAFETY_STATE_FILE.exists():
            try:
                with open(SAFETY_STATE_FILE, "r", encoding="utf-8") as f:
                    file_state = json.load(f)
                    state.update(file_state)
            except (json.JSONDecodeError, IOError):
                pass

        env_safe = os.environ.get("SAFE_MODE", "").lower()
        if env_safe in ("1", "true", "yes"):
            state["safe_mode"] = True
        elif env_safe in ("0", "false", "no"):
            state["safe_mode"] = False

        env_kill = os.environ.get("KILL_SWITCH", "").lower()
        if env_kill in ("1", "true", "yes"):
            state["kill_switch"] = True
        elif env_kill in ("0", "false", "no"):
            state["kill_switch"] = False

        cls._cached_state = state
        cls._cache_time = now
        return state

    @classmethod
    def _save_state(cls, state: dict[str, Any]) -> None:
        SAFETY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SAFETY_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, default=str)
        cls._cached_state = state
        cls._cache_time = datetime.now(timezone.utc)

    @classmethod
    def is_safe_mode(cls) -> bool:
        return cls._load_state().get("safe_mode", False)

    @classmethod
    def is_kill_switch_active(cls) -> bool:
        return cls._load_state().get("kill_switch", False)

    @classmethod
    def get_kill_switch_reason(cls) -> Optional[str]:
        return cls._load_state().get("kill_switch_reason")


def _log_safety_event(event_name: str, details: dict[str, Any]) -> None:
    log_event(
        EventType.SYSTEM_ERROR,
        {
            "safety_event": event_name,
            **details,
        },
        metadata={"source": "safety_module"},
    )


def safe_operation(operation_type: str) -> Callable:
    """
    Decorator that checks safety mode before executing an operation.
    
    Args:
        operation_type: One of "crm_write", "email_send", "scrape"
    
    Usage:
        @safe_operation(operation_type="email_send")
        def send_campaign_email(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if SafetyMode.is_kill_switch_active():
                reason = SafetyMode.get_kill_switch_reason() or "No reason provided"
                _log_safety_event(
                    "operation_blocked_kill_switch",
                    {
                        "operation_type": operation_type,
                        "function": func.__name__,
                        "reason": reason,
                    },
                )
                raise KillSwitchError(
                    f"Kill switch active: {reason}. Operation '{func.__name__}' blocked."
                )

            if SafetyMode.is_safe_mode():
                _log_safety_event(
                    "operation_simulated_safe_mode",
                    {
                        "operation_type": operation_type,
                        "function": func.__name__,
                        "args_preview": str(args)[:200],
                        "kwargs_preview": str(kwargs)[:200],
                    },
                )
                return {
                    "simulated": True,
                    "operation_type": operation_type,
                    "function": func.__name__,
                    "message": "Safe mode active - operation logged but not executed",
                }

            return func(*args, **kwargs)

        return wrapper

    return decorator


def check_halt_conditions(metrics: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """
    Check current metrics against halt thresholds.
    Activates kill switch if thresholds exceeded.
    
    Args:
        metrics: Dict with keys like bounce_rate, spam_complaints, error_rate.
                 If None, reads from recent events.
    
    Returns:
        Dict with check results and any triggered halts.
    """
    if metrics is None:
        metrics = _compute_metrics_from_events()

    violations = []

    bounce_rate = metrics.get("bounce_rate_percent", 0)
    if bounce_rate > HALT_THRESHOLDS["bounce_rate_percent"]:
        violations.append(f"Bounce rate {bounce_rate}% > {HALT_THRESHOLDS['bounce_rate_percent']}%")

    spam_rate = metrics.get("spam_complaint_percent", 0)
    if spam_rate > HALT_THRESHOLDS["spam_complaint_percent"]:
        violations.append(f"Spam complaint rate {spam_rate}% > {HALT_THRESHOLDS['spam_complaint_percent']}%")

    error_rate = metrics.get("error_rate_percent", 0)
    if error_rate > HALT_THRESHOLDS["error_rate_percent"]:
        violations.append(f"Error rate {error_rate}% > {HALT_THRESHOLDS['error_rate_percent']}%")

    compliance_failures = metrics.get("compliance_failure_count_1h", 0)
    if compliance_failures > HALT_THRESHOLDS["compliance_failure_count"]:
        violations.append(
            f"Compliance failures {compliance_failures} > {HALT_THRESHOLDS['compliance_failure_count']} in 1 hour"
        )

    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "thresholds": HALT_THRESHOLDS,
        "violations": violations,
        "halt_triggered": len(violations) > 0,
    }

    if violations:
        reason = "; ".join(violations)
        activate_kill_switch(reason)
        result["kill_switch_activated"] = True
        result["kill_switch_reason"] = reason

    return result


def _compute_metrics_from_events() -> dict[str, Any]:
    """Compute metrics from recent events in the event log."""
    metrics = {
        "bounce_rate_percent": 0,
        "spam_complaint_percent": 0,
        "error_rate_percent": 0,
        "compliance_failure_count_1h": 0,
    }

    if not EVENTS_FILE.exists():
        return metrics

    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)

    total_sends = 0
    bounces = 0
    spam_complaints = 0
    total_operations = 0
    errors = 0
    compliance_failures_1h = 0

    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    event_type = event.get("event_type", "")
                    timestamp_str = event.get("timestamp", "")

                    if event_type == EventType.CAMPAIGN_SENT.value:
                        total_sends += 1
                        total_operations += 1

                    if event_type == EventType.SYSTEM_ERROR.value:
                        errors += 1
                        total_operations += 1

                    payload = event.get("payload", {})
                    if payload.get("bounce"):
                        bounces += 1
                    if payload.get("spam_complaint"):
                        spam_complaints += 1

                    if event_type == EventType.COMPLIANCE_FAILED.value:
                        try:
                            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                            if ts >= one_hour_ago:
                                compliance_failures_1h += 1
                        except (ValueError, TypeError):
                            pass

                except json.JSONDecodeError:
                    continue
    except IOError:
        pass

    if total_sends > 0:
        metrics["bounce_rate_percent"] = (bounces / total_sends) * 100
        metrics["spam_complaint_percent"] = (spam_complaints / total_sends) * 100

    if total_operations > 0:
        metrics["error_rate_percent"] = (errors / total_operations) * 100

    metrics["compliance_failure_count_1h"] = compliance_failures_1h

    return metrics


def enable_safe_mode() -> dict[str, Any]:
    """Enable safe mode - external writes logged but not executed."""
    state = SafetyMode._load_state(force=True)
    state["safe_mode"] = True
    state["safe_mode_activated_at"] = datetime.now(timezone.utc).isoformat()
    SafetyMode._save_state(state)

    _log_safety_event("safe_mode_enabled", {"activated_at": state["safe_mode_activated_at"]})

    return {"safe_mode": True, "activated_at": state["safe_mode_activated_at"]}


def disable_safe_mode() -> dict[str, Any]:
    """Disable safe mode - resume normal operation."""
    state = SafetyMode._load_state(force=True)
    was_active = state.get("safe_mode", False)
    state["safe_mode"] = False
    state["safe_mode_deactivated_at"] = datetime.now(timezone.utc).isoformat()
    SafetyMode._save_state(state)

    _log_safety_event(
        "safe_mode_disabled",
        {"deactivated_at": state["safe_mode_deactivated_at"], "was_active": was_active},
    )

    return {"safe_mode": False, "deactivated_at": state["safe_mode_deactivated_at"]}


def activate_kill_switch(reason: str) -> dict[str, Any]:
    """Activate kill switch - halt all operations immediately."""
    state = SafetyMode._load_state(force=True)
    state["kill_switch"] = True
    state["kill_switch_reason"] = reason
    state["kill_switch_activated_at"] = datetime.now(timezone.utc).isoformat()
    SafetyMode._save_state(state)

    _log_safety_event(
        "kill_switch_activated",
        {"reason": reason, "activated_at": state["kill_switch_activated_at"]},
    )

    return {
        "kill_switch": True,
        "reason": reason,
        "activated_at": state["kill_switch_activated_at"],
    }


def deactivate_kill_switch() -> dict[str, Any]:
    """Deactivate kill switch - resume operations."""
    state = SafetyMode._load_state(force=True)
    was_active = state.get("kill_switch", False)
    previous_reason = state.get("kill_switch_reason")
    state["kill_switch"] = False
    state["kill_switch_reason"] = None
    state["kill_switch_deactivated_at"] = datetime.now(timezone.utc).isoformat()
    SafetyMode._save_state(state)

    _log_safety_event(
        "kill_switch_deactivated",
        {
            "deactivated_at": state["kill_switch_deactivated_at"],
            "was_active": was_active,
            "previous_reason": previous_reason,
        },
    )

    return {
        "kill_switch": False,
        "deactivated_at": state["kill_switch_deactivated_at"],
        "previous_reason": previous_reason,
    }


def get_safety_status() -> dict[str, Any]:
    """Get current safety status for dashboard display."""
    state = SafetyMode._load_state(force=True)
    return {
        "safe_mode": state.get("safe_mode", False),
        "safe_mode_activated_at": state.get("safe_mode_activated_at"),
        "kill_switch": state.get("kill_switch", False),
        "kill_switch_reason": state.get("kill_switch_reason"),
        "kill_switch_activated_at": state.get("kill_switch_activated_at"),
        "thresholds": HALT_THRESHOLDS,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
