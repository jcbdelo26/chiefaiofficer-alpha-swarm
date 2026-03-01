#!/usr/bin/env python3
"""
Health Dashboard - FastAPI Web Server
=====================================
Real-time health monitoring dashboard for the CAIO RevOps Swarm.

Endpoints:
- GET  /api/health       - Current health status
- GET  /api/metrics      - Historical metrics
- GET  /api/agents       - Agent status
- GET  /api/integrations - Integration status
- WS   /ws               - Real-time updates

Usage:
    uvicorn dashboard.health_app:app --host 0.0.0.0 --port 8080 --reload
"""

import os
import re
import sys
import json
import hmac
import asyncio
import logging
import tempfile
from contextlib import asynccontextmanager, suppress
from uuid import uuid4
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Depends, Body, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.unified_health_monitor import get_health_monitor, HealthMonitor
from core.precision_scorecard import get_scorecard, reset_scorecard
from core.messaging_strategy import MessagingStrategy
from core.signal_detector import SignalDetector
from core.ghl_outreach import OutreachConfig, GHLOutreachClient, EmailTemplate, OutreachType
from core.ghl_send_proof import GHLSendProofEngine
from core.deliverability_guard import DeliverabilityGuard
from core.feedback_loop import FeedbackLoop
from core.email_signature import enforce_text_signature
from core.task_routing_policy import get_task_routes, routes_ready
from core.runtime_reliability import get_runtime_dependency_health
from core.trace_envelope import (
    set_current_case_id,
    reset_current_case_id,
    set_current_correlation_id,
    reset_current_correlation_id,
)
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger("health_app")
INNGEST_ROUTE_MOUNTED = False
DASHBOARD_TOKEN_QUERY_PARAM = "token"
DASHBOARD_TOKEN_HEADER = "X-Dashboard-Token"
_AUTH_WARNING_EMITTED = False

# Structured rejection taxonomy for HoS review decisions.
# Keys are stable identifiers used in analytics/training.
REJECTION_TAGS: Dict[str, str] = {
    "personalization_mismatch": "Personalization mismatch",
    "icp_mismatch": "ICP mismatch",
    "campaign_mismatch": "Campaign mismatch",
    "tone_style_issue": "Tone/style issue",
    "factual_inaccuracy": "Factual inaccuracy",
    "weak_subject": "Weak subject line",
    "weak_cta": "Weak CTA",
    "length_issue": "Length/structure issue",
    "compliance_issue": "Compliance issue",
    "placeholder_or_rendering_issue": "Placeholder/rendering issue",
    "queue_hygiene_non_actionable": "Queue hygiene non-actionable",
    "other": "Other",
}


def _validate_rejection_tag(rejection_tag: Optional[str]) -> str:
    if isinstance(rejection_tag, str):
        normalized = rejection_tag.strip().lower()
    else:
        normalized = ""
    if not normalized:
        allowed = ", ".join(sorted(REJECTION_TAGS.keys()))
        raise HTTPException(
            status_code=422,
            detail=f"rejection_tag is required. Allowed tags: {allowed}",
        )
    if normalized not in REJECTION_TAGS:
        allowed = ", ".join(sorted(REJECTION_TAGS.keys()))
        raise HTTPException(
            status_code=422,
            detail=f"Invalid rejection_tag '{normalized}'. Allowed tags: {allowed}",
        )
    return normalized


def _validate_rejection_reason(reason: Optional[str]) -> str:
    normalized = str(reason or "").strip()
    if not normalized:
        raise HTTPException(
            status_code=422,
            detail="reason is required for rejected emails",
        )
    return normalized


def _categorize_rejection(reason: str) -> str:
    """Categorize rejection reason for ML training patterns."""
    reason_lower = (reason or "").lower()
    
    if any(word in reason_lower for word in ["tone", "formal", "casual", "aggressive"]):
        return "tone_issue"
    elif any(word in reason_lower for word in ["wrong", "incorrect", "inaccurate", "fact"]):
        return "accuracy_issue"
    elif any(word in reason_lower for word in ["long", "short", "verbose", "brief"]):
        return "length_issue"
    elif any(word in reason_lower for word in ["personal", "generic", "template"]):
        return "personalization_issue"
    elif any(word in reason_lower for word in ["subject", "headline", "title"]):
        return "subject_issue"
    elif any(word in reason_lower for word in ["cta", "call to action", "ask"]):
        return "cta_issue"
    else:
        return "other"


def _priority_to_tier(priority: Optional[str]) -> str:
    p = (priority or "").strip().lower()
    if p == "high":
        return "tier_1"
    if p == "medium":
        return "tier_2"
    return "tier_3"


def _atomic_json_write(file_path, data: dict, indent: int = 2) -> None:
    """Write JSON atomically: temp file + os.replace() to prevent corruption (XS-06)."""
    file_path = Path(file_path)
    dir_path = file_path.parent
    dir_path.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        os.replace(tmp_path, str(file_path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _pending_queue_max_age_hours() -> Optional[float]:
    raw = (os.getenv("PENDING_QUEUE_MAX_AGE_HOURS") or "72").strip()
    try:
        value = float(raw)
    except Exception:
        value = 72.0
    if value <= 0:
        return None
    return value


def _pending_queue_placeholder_tokens() -> Set[str]:
    raw = (os.getenv("PENDING_QUEUE_PLACEHOLDER_BODIES") or "no body content").strip()
    tokens = {token.strip().lower() for token in raw.split(",") if token.strip()}
    tokens.add("")
    return tokens


def _pending_queue_should_merge_filesystem(redis_connected: bool) -> bool:
    """
    Decide whether to merge file-backed queue items into pending approvals.

    Default: Redis-first source of truth. Filesystem merge is only used when
    Redis is unavailable. Set PENDING_QUEUE_ALWAYS_MERGE_FILES=true to force
    merge behavior for migration/debug scenarios.
    """
    if _env_bool("PENDING_QUEUE_ALWAYS_MERGE_FILES", False):
        return True
    return not redis_connected


def _pending_queue_include_non_dispatchable_default() -> bool:
    """
    Whether to include non-dispatchable training/canary cards in /api/pending-emails.

    Default is false so supervised live-send queue stays clean/actionable.
    """
    return _env_bool("PENDING_QUEUE_INCLUDE_NON_DISPATCHABLE", False)


def _phase1_llm_routes() -> Dict[str, Dict[str, str]]:
    return get_task_routes()


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _get_active_pending_queue_tier_filter() -> Optional[str]:
    """
    Return active tier filter for pending queue display.

    Priority:
      1. Explicit env override `PENDING_QUEUE_TIER_FILTER`.
      2. Active OPERATOR ramp tier filter (if enforcement enabled).
    """
    explicit = (os.getenv("PENDING_QUEUE_TIER_FILTER") or "").strip().lower()
    if explicit:
        return explicit

    if not _env_bool("PENDING_QUEUE_ENFORCE_RAMP_TIER", True):
        return None

    operator = globals().get("_operator")
    if operator is None:
        return None
    try:
        status = operator.get_status()
        ramp = status.get("ramp", {})
        if ramp.get("active"):
            tier_filter = str(ramp.get("tier_filter") or "").strip().lower()
            if tier_filter:
                return tier_filter
    except Exception as exc:
        logger.debug("Failed to load operator ramp tier for pending queue filter: %s", exc)
    return None


def _pending_email_exclusion_reasons(
    email_data: Dict[str, Any],
    *,
    now_utc: datetime,
    tier_filter: Optional[str],
    max_age_hours: Optional[float],
    placeholder_tokens: Set[str],
    seen_dedupe_keys: Set[str],
    include_non_dispatchable: bool,
) -> List[str]:
    reasons: List[str] = []

    status = str(email_data.get("status") or "pending").strip().lower()
    if status != "pending":
        reasons.append(f"status:{status}")
        return reasons

    if not include_non_dispatchable:
        if bool(email_data.get("_do_not_dispatch")):
            reasons.append("non_dispatchable:_do_not_dispatch")
            return reasons
        if bool(email_data.get("canary_training")):
            reasons.append("non_dispatchable:canary_training")
            return reasons

    tier = str(email_data.get("tier") or "").strip().lower()
    if tier_filter and tier and tier != tier_filter:
        reasons.append(f"tier_mismatch:{tier}")

    body = str(email_data.get("body") or email_data.get("body_preview") or "").strip()
    body_normalized = body.lower()
    if body_normalized in placeholder_tokens:
        reasons.append("placeholder_body")
    elif re.fullmatch(r"\{\{[^{}]+\}\}", body_normalized):
        reasons.append("unrendered_placeholder_body")

    if max_age_hours is not None:
        ts = _parse_iso_datetime(email_data.get("timestamp") or email_data.get("created_at"))
        if ts is not None and ts < (now_utc - timedelta(hours=max_age_hours)):
            reasons.append(f"stale_gt_{int(max_age_hours)}h")

    to_addr = str(email_data.get("to") or "").strip().lower()
    subject = str(email_data.get("subject") or "").strip().lower()
    if to_addr and subject:
        dedupe_key = f"{to_addr}|{subject}"
        if dedupe_key in seen_dedupe_keys:
            reasons.append("duplicate_recipient_subject")
        else:
            seen_dedupe_keys.add(dedupe_key)

    return reasons


def _get_default_tier_routing_targets() -> Dict[str, List[str]]:
    return {
        "tier_1": ["instantly", "heyreach"],
        "tier_2": ["instantly", "heyreach"],
        "tier_3": ["instantly"],
    }


def _get_tier_routing_targets_by_tier() -> Dict[str, List[str]]:
    """
    Best-effort load of tier routing configuration used by OPERATOR.
    Falls back to deterministic defaults when OPERATOR context isn't available.
    """
    default_targets = _get_default_tier_routing_targets()
    operator = globals().get("_operator")
    if operator is None:
        return default_targets

    try:
        status = operator.get_status()
        config = status.get("config", {})
        routing = config.get("tier_routing", {})
        if not isinstance(routing, dict):
            return default_targets
        normalized: Dict[str, List[str]] = {}
        for tier, channels in routing.items():
            key = str(tier or "").strip().lower()
            if not key:
                continue
            if isinstance(channels, list):
                normalized[key] = [str(ch).strip().lower() for ch in channels if str(ch).strip()]
        if normalized:
            return normalized
    except Exception as exc:
        logger.debug("Failed to load tier routing config from OPERATOR: %s", exc)

    return default_targets


def _infer_pending_email_classifier(
    email_data: Dict[str, Any],
    *,
    tier_routing_targets: Dict[str, List[str]],
) -> Dict[str, Any]:
    """
    Build deterministic classification metadata for pending-approval cards.

    This makes queue intent explicit (origin, outbound/inbound, target platform,
    and campaign mapping state) so operators can reconcile dashboard cards with
    Instantly/GHL views.
    """
    source = str(email_data.get("source") or "").strip().lower()
    status = str(email_data.get("status") or "").strip().lower()
    context = email_data.get("context", {})
    if not isinstance(context, dict):
        context = {}
    if not source:
        source = str(context.get("source") or "").strip().lower()

    tier = str(email_data.get("tier") or context.get("icp_tier") or "").strip().lower() or "tier_3"
    routing_targets = tier_routing_targets.get(tier, [])

    # Direction is message-level (email draft/reply), not lead-source.
    direction = str(
        email_data.get("direction")
        or context.get("direction")
        or "outbound"
    ).strip().lower()
    if direction not in {"outbound", "inbound"}:
        direction = "outbound"

    # Lead-source class captures where the lead signal originated.
    source_type = str(context.get("source_type") or "").strip().lower()
    inbound_sources = {
        "website_intent_monitor",
        "gatekeeper_queue_sync",
        "rb2b",
        "webhook",
    }
    lead_source_class = "inbound_signal" if (source in inbound_sources or source_type in {"website_visitor", "inbound"}) else "outbound_prospecting"

    explicit_platform = str(
        email_data.get("delivery_platform")
        or context.get("delivery_platform")
        or context.get("platform")
        or ""
    ).strip().lower()
    if explicit_platform not in {"instantly", "ghl", "heyreach"}:
        explicit_platform = ""

    is_non_dispatchable_training = bool(
        email_data.get("_do_not_dispatch")
        or email_data.get("canary_training")
        or email_data.get("canary")
        or (source.startswith("canary_") if source else False)
    )

    if is_non_dispatchable_training:
        target_platform = "training"
        target_platform_reason = "non_dispatchable_training"
    elif explicit_platform:
        target_platform = explicit_platform
        target_platform_reason = "explicit_metadata"
    elif status in {"sent_via_ghl"} or email_data.get("sent_via_ghl"):
        target_platform = "ghl"
        target_platform_reason = "delivery_status"
    elif status in {"sent_via_instantly"}:
        target_platform = "instantly"
        target_platform_reason = "delivery_status"
    elif status in {"sent_via_heyreach"}:
        target_platform = "heyreach"
        target_platform_reason = "delivery_status"
    elif "instantly" in source:
        target_platform = "instantly"
        target_platform_reason = "source"
    elif "heyreach" in source or "linkedin" in source:
        target_platform = "heyreach"
        target_platform_reason = "source"
    elif source in {"pipeline", "nurture_engine", "website_intent_monitor", "gatekeeper_queue_sync"}:
        # Current dashboard approve path sends via GHL unless dispatch is delegated.
        target_platform = "ghl"
        target_platform_reason = "dashboard_approve_path"
    else:
        target_platform = "unknown"
        target_platform_reason = "insufficient_metadata"

    campaign_ref = {
        "internal_id": (
            email_data.get("campaign_id")
            or context.get("campaign_id")
            or context.get("cadence_id")
            or ("canary_training" if is_non_dispatchable_training else "")
            or ""
        ),
        "internal_type": (
            email_data.get("campaign_type")
            or context.get("campaign_type")
            or context.get("campaign_template")
            or (source if is_non_dispatchable_training else "")
            or ""
        ),
        "internal_name": (
            email_data.get("campaign_name")
            or context.get("campaign_name")
            or ""
        ),
        "pipeline_run_id": context.get("pipeline_run_id") or email_data.get("pipeline_run_id") or "",
        "external_provider": (
            email_data.get("external_provider")
            or context.get("external_provider")
            or ("instantly" if (context.get("instantly_campaign_id") or context.get("instantly_campaign_name")) else "")
        ),
        "external_campaign_id": (
            email_data.get("external_campaign_id")
            or context.get("external_campaign_id")
            or context.get("instantly_campaign_id")
            or ""
        ),
        "external_campaign_name": (
            email_data.get("external_campaign_name")
            or context.get("external_campaign_name")
            or context.get("instantly_campaign_name")
            or ""
        ),
    }

    if target_platform == "instantly":
        sync_state = "external_campaign_mapped" if (campaign_ref["external_campaign_id"] or campaign_ref["external_campaign_name"]) else "pending_external_campaign_mapping"
    elif target_platform == "ghl":
        sync_state = "n/a_ghl_direct_path"
    elif target_platform == "heyreach":
        sync_state = "n/a_linkedin_path"
    elif target_platform == "training":
        sync_state = "non_dispatchable_training"
    else:
        sync_state = "unknown"

    return {
        "queue_stage": "approval_pending",
        "queue_origin": source or "unknown",
        "message_direction": direction,
        "lead_source_class": lead_source_class,
        "target_platform": target_platform,
        "target_platform_reason": target_platform_reason,
        "routing_targets": routing_targets,
        "sync_state": sync_state,
        "campaign_ref": campaign_ref,
    }


def _sync_gatekeeper_queue_to_shadow(project_root: Path) -> int:
    """
    Ensure gatekeeper queue items are mirrored into shadow_mode_emails.

    Uses shadow_queue.push() when available so synced items reach Redis too.
    Returns number of queue items synced.
    """
    gatekeeper_dir = project_root / ".hive-mind" / "gatekeeper_queue"
    shadow_dir = project_root / ".hive-mind" / "shadow_mode_emails"
    shadow_dir.mkdir(parents=True, exist_ok=True)

    if not gatekeeper_dir.exists():
        return 0

    shadow_push = None
    shadow_get = None
    try:
        from core.shadow_queue import push as shadow_push, get_email as shadow_get
    except Exception:
        shadow_push = None
        shadow_get = None

    synced_count = 0
    terminal_statuses = {
        "approved",
        "rejected",
        "sent",
        "sent_via_ghl",
        "sent_via_instantly",
        "sent_via_heyreach",
    }
    for queue_file in gatekeeper_dir.glob("*.json"):
        try:
            with open(queue_file, "r", encoding="utf-8") as f:
                queue_data = json.load(f)

            queue_status = str(queue_data.get("status") or "").strip().lower()
            if queue_status and queue_status != "pending":
                continue

            email_id = queue_data.get("queue_id") or queue_file.stem
            existing_shadow = None
            if shadow_get:
                try:
                    existing_shadow = shadow_get(email_id, shadow_dir=shadow_dir)
                except Exception:
                    existing_shadow = None
            if existing_shadow is None:
                shadow_file = shadow_dir / f"{email_id}.json"
                if shadow_file.exists():
                    try:
                        with open(shadow_file, "r", encoding="utf-8") as fp:
                            existing_shadow = json.load(fp)
                    except Exception:
                        existing_shadow = None
            if existing_shadow:
                existing_status = str(existing_shadow.get("status") or "pending").strip().lower()
                if existing_status == "pending" or existing_status in terminal_statuses:
                    continue

            visitor = queue_data.get("visitor", {})
            email = queue_data.get("email", {})
            context = queue_data.get("context", {})
            created_at = (
                queue_data.get("created_at")
                or queue_data.get("timestamp")
                or datetime.now(timezone.utc).isoformat()
            )

            shadow_payload = {
                "email_id": email_id,
                "status": "pending",
                "to": visitor.get("email") or queue_data.get("to") or "unknown@example.com",
                "subject": email.get("subject") or queue_data.get("subject") or "No Subject",
                "body": email.get("body") or queue_data.get("body") or "No Body Content",
                "direction": "outbound",
                "delivery_platform": "ghl",
                "delivery_path": "dashboard_approval_direct",
                "tier": context.get("icp_tier") or _priority_to_tier(queue_data.get("priority")),
                "angle": (context.get("triggers") or ["general"])[0],
                "recipient_data": {
                    "name": visitor.get("name"),
                    "company": visitor.get("company"),
                    "title": visitor.get("title"),
                },
                "context": context,
                "priority": queue_data.get("priority", "medium"),
                "source": "gatekeeper_queue_sync",
                "created_at": created_at,
                "timestamp": created_at,
                "synced_at": datetime.now(timezone.utc).isoformat(),
            }

            wrote = False
            if shadow_push:
                try:
                    wrote = bool(shadow_push(shadow_payload, shadow_dir=shadow_dir))
                except Exception as exc:
                    logger.warning("Failed to sync queue item %s through shadow_queue: %s", email_id, exc)

            if not wrote:
                shadow_file = shadow_dir / f"{email_id}.json"
                with open(shadow_file, "w", encoding="utf-8") as f:
                    json.dump(shadow_payload, f, indent=2)

            synced_count += 1
        except Exception as exc:
            logger.warning("Failed to sync gatekeeper queue file %s: %s", queue_file, exc)

    return synced_count


def _read_pending_from_shadow_files(shadow_log: Path) -> List[Dict[str, Any]]:
    """Read pending email payloads directly from shadow_mode_emails files."""
    if not shadow_log.exists():
        return []

    pending: List[Dict[str, Any]] = []
    for email_file in shadow_log.glob("*.json"):
        try:
            with open(email_file, "r", encoding="utf-8") as f:
                email_data = json.load(f)
            current_status = str(email_data.get("status", "pending")).strip().lower()
            if current_status == "pending":
                email_data["email_id"] = email_data.get("email_id") or email_file.stem
                pending.append(email_data)
        except Exception as exc:
            logger.warning("Failed to read pending email file %s: %s", email_file, exc)

    pending.sort(
        key=lambda item: str(item.get("timestamp") or item.get("created_at") or ""),
        reverse=True,
    )
    return pending

# =============================================================================
# CORRELATION ID MIDDLEWARE
# =============================================================================

class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds correlation IDs to all requests for request tracing.

    - Checks for existing X-Correlation-ID header
    - Generates new UUID if not present
    - Adds correlation ID to response headers
    - Stores in request state for access in route handlers
    """

    async def dispatch(self, request: Request, call_next):
        # Get or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid4())
        case_id = request.headers.get("X-Replay-Case-ID") or request.headers.get("X-Case-ID")

        # Store in request state for route handlers
        request.state.correlation_id = correlation_id
        request.state.case_id = case_id
        correlation_token = set_current_correlation_id(correlation_id)
        case_token = set_current_case_id(case_id) if case_id else None

        try:
            response = await call_next(request)
        finally:
            reset_current_correlation_id(correlation_token)
            if case_token is not None:
                reset_current_case_id(case_token)

        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id
        if case_id:
            response.headers["X-Replay-Case-ID"] = case_id

        return response


# =============================================================================
# AUTHENTICATION
# =============================================================================

_DEFAULT_UNAUTHENTICATED_API_ALLOWLIST: Set[str] = {
    "/api/health",
    "/api/health/ready",
    "/api/health/live",
}


def _normalize_path(path: str) -> str:
    normalized = (path or "/").strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if normalized != "/":
        normalized = normalized.rstrip("/")
    return normalized


def _load_api_auth_allowlist() -> Set[str]:
    allowlist = set(_DEFAULT_UNAUTHENTICATED_API_ALLOWLIST)
    raw = (os.getenv("DASHBOARD_AUTH_ALLOWLIST") or "").strip()
    if not raw:
        return allowlist
    for value in raw.split(","):
        token = value.strip()
        if token:
            allowlist.add(_normalize_path(token))
    return allowlist


API_AUTH_ALLOWLIST = _load_api_auth_allowlist()


def _is_token_strict_mode() -> bool:
    strict_raw = (os.getenv("DASHBOARD_AUTH_STRICT") or "").strip().lower()
    if strict_raw in {"1", "true", "yes", "on"}:
        return True
    if strict_raw in {"0", "false", "no", "off"}:
        return False
    environment = (os.getenv("ENVIRONMENT") or "").strip().lower()
    return environment in {"production", "staging"}


def _is_query_token_enabled() -> bool:
    """
    Whether ?token= query auth is accepted for protected APIs.

    Default remains enabled for backwards compatibility. Prefer header token.
    """
    raw = (os.getenv("DASHBOARD_QUERY_TOKEN_ENABLED") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return True


def _auth_error_detail() -> str:
    if _is_query_token_enabled():
        return (
            "Unauthorized. Provide dashboard token via "
            f"?{DASHBOARD_TOKEN_QUERY_PARAM}=... or {DASHBOARD_TOKEN_HEADER} header."
        )
    return (
        "Unauthorized. Query-token auth is disabled. "
        f"Provide dashboard token via {DASHBOARD_TOKEN_HEADER} header."
    )


def _extract_dashboard_token(request: Request) -> Optional[str]:
    header_token = (
        request.headers.get(DASHBOARD_TOKEN_HEADER)
        or request.headers.get(DASHBOARD_TOKEN_HEADER.lower())
    )
    if header_token:
        return header_token
    if _is_query_token_enabled():
        query_token = request.query_params.get(DASHBOARD_TOKEN_QUERY_PARAM)
        if query_token:
            return query_token
    return None


def _token_is_valid(token: Optional[str]) -> bool:
    global _AUTH_WARNING_EMITTED
    configured_token = (os.getenv("DASHBOARD_AUTH_TOKEN") or "").strip()
    if not configured_token:
        if _is_token_strict_mode():
            return False
        if not _AUTH_WARNING_EMITTED:
            logger.warning("DASHBOARD_AUTH_TOKEN not configured; protected API routes are in non-strict mode.")
            _AUTH_WARNING_EMITTED = True
        return True
    if not token:
        return False
    return hmac.compare_digest(token, configured_token)


def _is_auth_exempt_path(path: str) -> bool:
    normalized_path = _normalize_path(path)
    return normalized_path in API_AUTH_ALLOWLIST


def require_auth(request: Request) -> bool:
    token = _extract_dashboard_token(request)
    if _token_is_valid(token):
        return True
    # Fall back to session cookie auth for browser-originated requests
    session = getattr(request, "session", {})
    if session.get("authenticated"):
        return True
    raise HTTPException(
        status_code=401,
        detail=_auth_error_detail(),
    )


class APIAuthMiddleware(BaseHTTPMiddleware):
    """Enforce token auth for protected /api routes."""

    async def dispatch(self, request: Request, call_next):
        path = _normalize_path(request.url.path)
        if request.method.upper() == "OPTIONS":
            return await call_next(request)
        if path.startswith("/api/") and not _is_auth_exempt_path(path):
            token = _extract_dashboard_token(request)
            if not _token_is_valid(token):
                # Fall back to session cookie auth for browser-originated API calls
                session = getattr(request, "session", {})
                if not session.get("authenticated"):
                    return JSONResponse(
                        status_code=401,
                        content={"detail": _auth_error_detail()},
                    )
        return await call_next(request)


class DashboardAuthMiddleware(BaseHTTPMiddleware):
    """Gate HTML dashboard pages behind login session."""

    _EXEMPT_PREFIXES = ("/login", "/logout", "/static/", "/webhooks/", "/api/", "/ws", "/inngest")
    _EXEMPT_EXACT = {"/favicon.ico"}

    async def dispatch(self, request: Request, call_next):
        path = _normalize_path(request.url.path)

        # Skip exempt paths
        if path in self._EXEMPT_EXACT:
            return await call_next(request)
        for prefix in self._EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Check session
        session = getattr(request, "session", {})
        if session.get("authenticated"):
            return await call_next(request)

        # Redirect to login with next= for post-login redirect
        next_url = request.url.path
        query = request.url.query
        if query:
            next_url = f"{next_url}?{query}"
        return RedirectResponse(url=f"/login?next={next_url}", status_code=302)


# In-memory login rate limiter (IP -> list of failure timestamps)
_LOGIN_FAIL_TRACKER: Dict[str, List[float]] = {}
_LOGIN_RATE_LIMIT = 5          # max failures
_LOGIN_RATE_WINDOW = 300.0     # 5-minute window


def _check_login_rate_limit(ip: str) -> bool:
    """Return True if the IP is rate-limited (too many failures)."""
    import time
    now = time.time()
    failures = _LOGIN_FAIL_TRACKER.get(ip, [])
    # Prune old entries
    failures = [t for t in failures if now - t < _LOGIN_RATE_WINDOW]
    _LOGIN_FAIL_TRACKER[ip] = failures
    return len(failures) >= _LOGIN_RATE_LIMIT


def _record_login_failure(ip: str) -> None:
    import time
    failures = _LOGIN_FAIL_TRACKER.setdefault(ip, [])
    failures.append(time.time())


def _clear_login_failures(ip: str) -> None:
    _LOGIN_FAIL_TRACKER.pop(ip, None)


def _get_cors_allowed_origins() -> List[str]:
    raw = (os.getenv("CORS_ALLOWED_ORIGINS") or "").strip()
    if not raw:
        return [
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or ["http://localhost:8080"]


def _get_cors_allowed_methods() -> List[str]:
    """
    Return explicit CORS methods.

    Default is least-privilege for dashboard/API usage.
    Override with CORS_ALLOWED_METHODS=GET,POST,OPTIONS if needed.
    """
    raw = (os.getenv("CORS_ALLOWED_METHODS") or "GET,POST,OPTIONS").strip()
    methods = [method.strip().upper() for method in raw.split(",") if method.strip()]
    return methods or ["GET", "POST", "OPTIONS"]


def _get_cors_allowed_headers() -> List[str]:
    """
    Return explicit CORS headers.

    Default keeps protected API auth functional without wildcard exposure.
    Override with CORS_ALLOWED_HEADERS=Content-Type,X-Dashboard-Token
    """
    raw = (os.getenv("CORS_ALLOWED_HEADERS") or "Content-Type,X-Dashboard-Token").strip()
    headers = [header.strip() for header in raw.split(",") if header.strip()]
    return headers or ["Content-Type", "X-Dashboard-Token"]

# =============================================================================
# APP SETUP
# =============================================================================

@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """
    Start/stop background monitor tasks using FastAPI lifespan.

    Replaces deprecated startup/shutdown event handlers.
    """
    monitor = get_health_monitor()
    monitor_task = asyncio.create_task(monitor.start())
    broadcast_task = asyncio.create_task(health_broadcast_loop())

    app.state.health_monitor_task = monitor_task
    app.state.health_broadcast_task = broadcast_task

    try:
        yield
    finally:
        await monitor.stop()
        for task in (broadcast_task, monitor_task):
            if task and not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title="CAIO Swarm Health Dashboard",
    description="Real-time health monitoring for the unified agent swarm",
    version="1.0.0",
    lifespan=app_lifespan,
)

# Middleware ordering: Starlette processes LAST-added as OUTERMOST.
# Desired request flow: CORS -> Session -> DashboardAuth -> APIAuth -> CorrelationID -> Route
# So we add them in reverse order (innermost first).

# Add correlation ID middleware for request tracing (innermost)
app.add_middleware(CorrelationIDMiddleware)

# Enforce dashboard token for protected /api routes
app.add_middleware(APIAuthMiddleware)

# Gate HTML dashboard pages behind login session
app.add_middleware(DashboardAuthMiddleware)

# Session middleware (signed cookies — populates request.session)
_session_secret = (os.getenv("SESSION_SECRET_KEY") or os.getenv("DASHBOARD_AUTH_TOKEN") or "change-me-in-production").strip()
_session_https_only = (os.getenv("ENVIRONMENT") or "").strip().lower() in ("production", "staging")
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    session_cookie="caio_session",
    max_age=14 * 24 * 60 * 60,  # 14 days
    same_site="lax",
    https_only=_session_https_only,
)

# CORS (outermost — processes first)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=_get_cors_allowed_methods(),
    allow_headers=_get_cors_allowed_headers(),
)

# Serve static files
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# =============================================================================
# WEBSOCKET MANAGER
# =============================================================================

class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as exc:
                logger.warning("Failed to broadcast websocket message: %s", exc)
                disconnected.append(connection)
        
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


# =============================================================================
# BACKGROUND TASKS
# =============================================================================

async def health_broadcast_loop():
    """Broadcast health updates to WebSocket clients."""
    monitor = get_health_monitor()
    
    while True:
        await asyncio.sleep(5)  # Update every 5 seconds
        
        if manager.active_connections:
            try:
                status = monitor.get_health_status()
                await manager.broadcast({
                    "type": "health_update",
                    "data": status
                })
            except Exception as e:
                logger.error("Broadcast error: %s", e)


# =============================================================================
# API ROUTES
# =============================================================================

@app.get("/")
async def root():
    """Serve the dashboard HTML."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>Health Dashboard</h1><p>Static files not found.</p>")


# =============================================================================
# LOGIN / LOGOUT
# =============================================================================

_LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Login - CAIO Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #0a0f1a;
    color: #f9fafb;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .login-card {
    background: #111827;
    border: 1px solid #374151;
    border-radius: 12px;
    padding: 40px;
    width: 100%;
    max-width: 400px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.4);
  }
  .login-title {
    font-size: 20px;
    font-weight: 600;
    margin-bottom: 8px;
    text-align: center;
  }
  .login-subtitle {
    font-size: 14px;
    color: #9ca3af;
    text-align: center;
    margin-bottom: 28px;
  }
  label {
    display: block;
    font-size: 13px;
    color: #9ca3af;
    margin-bottom: 6px;
  }
  input[type="password"] {
    width: 100%;
    padding: 10px 14px;
    background: #1f2937;
    border: 1px solid #374151;
    border-radius: 8px;
    color: #f9fafb;
    font-size: 14px;
    outline: none;
    transition: border-color 0.2s;
  }
  input[type="password"]:focus {
    border-color: #3b82f6;
  }
  button {
    width: 100%;
    padding: 10px 14px;
    margin-top: 20px;
    background: #3b82f6;
    color: #fff;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
  }
  button:hover { background: #2563eb; }
  .error-msg {
    margin-top: 16px;
    padding: 10px 14px;
    background: rgba(239,68,68,0.1);
    border: 1px solid rgba(239,68,68,0.3);
    border-radius: 8px;
    color: #ef4444;
    font-size: 13px;
    text-align: center;
  }
</style>
</head>
<body>
<div class="login-card">
  <div class="login-title">CAIO Swarm Dashboard</div>
  <div class="login-subtitle">Enter your dashboard token to continue</div>
  <form method="POST" action="/login">
    <input type="hidden" name="next" value="{next_url}">
    <label for="token">Dashboard Token</label>
    <input type="password" id="token" name="token" placeholder="Paste token here" autofocus required>
    <button type="submit">Log In</button>
  </form>
  {error_html}
</div>
</body>
</html>"""


def _render_login_page(next_url: str = "/sales", error: str = "") -> HTMLResponse:
    error_html = f'<div class="error-msg">{error}</div>' if error else ""
    # Sanitize next_url to prevent open redirect — only allow relative paths
    if not next_url.startswith("/"):
        next_url = "/sales"
    # Use .replace() instead of .format() to avoid conflicts with CSS curly braces
    html = _LOGIN_PAGE_HTML.replace("{next_url}", next_url).replace("{error_html}", error_html)
    return HTMLResponse(html)


@app.get("/login")
async def login_page(request: Request, next: str = "/sales"):
    """Serve the login form. If already authenticated, redirect to target."""
    session = getattr(request, "session", {})
    if session.get("authenticated"):
        target = next if next.startswith("/") else "/sales"
        return RedirectResponse(url=target, status_code=302)
    return _render_login_page(next_url=next)


@app.post("/login")
async def login_submit(request: Request):
    """Validate token and create session."""
    form = await request.form()
    token = (form.get("token") or "").strip()
    next_url = (form.get("next") or "/sales").strip()
    if not next_url.startswith("/"):
        next_url = "/sales"

    client_ip = request.client.host if request.client else "unknown"

    # Rate limit check
    if _check_login_rate_limit(client_ip):
        return HTMLResponse(
            '<html><body style="background:#0a0f1a;color:#ef4444;display:flex;'
            'align-items:center;justify-content:center;height:100vh;font-family:sans-serif">'
            "<h2>Too many login attempts. Try again in a few minutes.</h2></body></html>",
            status_code=429,
        )

    if _token_is_valid(token):
        _clear_login_failures(client_ip)
        request.session["authenticated"] = True
        request.session["login_at"] = datetime.now(timezone.utc).isoformat()
        return RedirectResponse(url=next_url, status_code=303)

    _record_login_failure(client_ip)
    return _render_login_page(next_url=next_url, error="Invalid token. Please try again.")


@app.get("/logout")
@app.post("/logout")
async def logout(request: Request):
    """Clear session and redirect to login."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


# =============================================================================
# ADMIN HELPER ENDPOINTS
# =============================================================================

@app.post("/api/admin/seed_queue")
async def seed_queue(
    count: int = Query(5, ge=1, le=20, description="Number of training emails to generate"),
    tier: Optional[str] = Query(None, description="Filter by tier (tier_1, tier_2, tier_3)"),
    auth: bool = Depends(require_auth),
):
    """Seed the pending queue with pre-built training emails.

    No LLM or external API calls. Instant generation.
    All emails are marked synthetic=true for safety.
    """
    try:
        from core.seed_queue import generate_seed_emails

        emails = generate_seed_emails(count=count, tier_filter=tier)
        return {
            "status": "ok",
            "seeded": len(emails),
            "email_ids": [e["email_id"] for e in emails],
            "note": "All seeded emails are synthetic (canary=true). OPERATOR will not dispatch them.",
        }
    except Exception as exc:
        logger.error("seed_queue failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Seed failed: {exc}")


@app.get("/api/admin/webhook_captures")
async def get_webhook_captures(auth: bool = Depends(require_auth)):
    """Read captured HeyReach webhook payloads from Redis (HR-05 debug).

    Temporary endpoint — remove after webhook schema is validated.
    """
    try:
        from webhooks.heyreach_webhook import _read_captures_from_redis
        captures = _read_captures_from_redis()
        return {"captures": captures, "count": len(captures)}
    except Exception as exc:
        logger.error("webhook_captures failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/admin/regenerate_queue")
async def regenerate_queue(auth: bool = Depends(require_auth)):
    """
    Trigger regeneration of all pending emails in the queue.
    Uses new MessagingStrategy templates.
    """
    try:
        updated_count = 0
        shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
        
        if not shadow_dir.exists():
            return {"status": "error", "message": "Shadow email directory not found"}
        
        # Init strategies
        messaging = MessagingStrategy()
        detector = SignalDetector()
        
        for email_file in shadow_dir.glob("*.json"):
            try:
                with open(email_file, "r") as f:
                    data = json.load(f)
                
                if data.get("status") != "pending":
                    continue
                
                # Reconstruct context for regeneration
                recipient = data.get("recipient_data", {})
                
                # Tech stack extraction
                tech_stack_str = "your tech stack"
                if "context" in data:
                     # Attempt to extract from context if available
                     context_triggers = data["context"].get("triggers", [])
                     # This is imperfect as we don't store raw tech stack in dashboard json usually
                     # But we can try to infer or just use generic placeholders which is better than nothing
                
                contact_info = {
                    "first_name": recipient.get("name", "").split(" ")[0],
                    "company_name": recipient.get("company"),
                    "job_title": recipient.get("title"),
                    "tier": 1 if data.get("priority") == "high" else 3
                }
                
                # Run Detection (Simulated based on Tier)
                # Since we don't have raw signals, we use the tier to pick best available logic
                # For high priority (Tier 1), we check if we can detect intent
                
                # Detect signals from available data
                signals = detector.detect_signals(contact_info)
                primary_signal = detector.get_primary_signal(signals)
                
                # Select Template
                template_id, subject_tmpl, body_tmpl = messaging.select_template(contact_info, primary_signal)
                
                # Format
                formatted_subject = subject_tmpl.format(
                    first_name=contact_info["first_name"] or "there",
                    company=contact_info["company_name"] or "your company",
                    industry="your industry",
                    title=contact_info["job_title"] or "Leader",
                    tech_stack=tech_stack_str
                )
                
                formatted_body = body_tmpl.format(
                    first_name=contact_info["first_name"] or "there",
                    company=contact_info["company_name"] or "your company",
                    industry="your industry",
                    title=contact_info["job_title"] or "Leader",
                    tech_stack=tech_stack_str
                )
                
                # Update File
                data["subject"] = formatted_subject
                data["body"] = formatted_body
                data["template_id"] = template_id
                data["regenerated_at"] = datetime.now(timezone.utc).isoformat()
                data["regeneration_note"] = "Applied Email Overhaul v2"
                
                with open(email_file, "w") as f:
                    json.dump(data, f, indent=2)
                
                updated_count += 1
                
            except Exception as e:
                print(f"Error updating {email_file}: {e}")
                continue
        
        return {
            "status": "success", 
            "updated_count": updated_count,
            "message": f"Successfully regenerated {updated_count} emails using new strategies."
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    """Get current health status of all components."""
    monitor = get_health_monitor()
    status = monitor.get_health_status()
    status["runtime_dependencies"] = get_runtime_dependency_health(
        check_connections=False,
        inngest_route_mounted=INNGEST_ROUTE_MOUNTED,
    )
    return status


@app.get("/api/runtime/dependencies")
async def get_runtime_dependencies(auth: bool = Depends(require_auth)):
    """Runtime reliability health for Redis/Inngest dependency checks."""
    payload = get_runtime_dependency_health(
        check_connections=True,
        inngest_route_mounted=INNGEST_ROUTE_MOUNTED,
    )
    payload["auth"] = {
        "strict_mode": _is_token_strict_mode(),
        "query_token_enabled": _is_query_token_enabled(),
        "token_header": DASHBOARD_TOKEN_HEADER,
    }
    routes = _phase1_llm_routes()
    payload["llm_routing"] = {
        "task_routes": routes,
        "ready": routes_ready(routes),
    }
    return payload


@app.get("/api/metrics")
async def get_metrics(hours: int = 24) -> Dict[str, Any]:
    """Get historical metrics."""
    monitor = get_health_monitor()
    return monitor.get_metrics_history(hours)


@app.get("/api/agents")
async def get_agents() -> Dict[str, Any]:
    """Get status of all agents."""
    monitor = get_health_monitor()
    status = monitor.get_health_status()
    return {
        "agents": status.get("agents", {}),
        "timestamp": status.get("timestamp")
    }


@app.get("/api/agents/{agent_name}")
async def get_agent(agent_name: str) -> Dict[str, Any]:
    """Get status of a specific agent."""
    monitor = get_health_monitor()
    agent_status = monitor.get_agent_status(agent_name)
    
    if not agent_status:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    
    return agent_status


@app.get("/api/integrations")
async def get_integrations() -> Dict[str, Any]:
    """Get status of all integrations."""
    monitor = get_health_monitor()
    status = monitor.get_health_status()
    return {
        "integrations": status.get("integrations", {}),
        "timestamp": status.get("timestamp")
    }


@app.get("/api/mcp-servers")
async def get_mcp_servers() -> Dict[str, Any]:
    """Get status of all MCP servers."""
    monitor = get_health_monitor()
    status = monitor.get_health_status()
    return {
        "mcp_servers": status.get("mcp_servers", {}),
        "timestamp": status.get("timestamp")
    }


@app.get("/api/guardrails")
async def get_guardrails() -> Dict[str, Any]:
    """Get status of guardrails."""
    monitor = get_health_monitor()
    status = monitor.get_health_status()
    return {
        "guardrails": status.get("guardrails", {}),
        "rate_limits": status.get("rate_limits", {}),
        "email_limits": status.get("email_limits", {}),
        "timestamp": status.get("timestamp")
    }


@app.get("/api/actions")
async def get_recent_actions(limit: int = 20) -> Dict[str, Any]:
    """Get recent actions."""
    monitor = get_health_monitor()
    status = monitor.get_health_status()
    actions = status.get("recent_actions", [])
    return {
        "actions": actions[:limit],
        "total": len(actions),
        "timestamp": status.get("timestamp")
    }


@app.get("/api/alerts")
async def get_alerts() -> Dict[str, Any]:
    """Get recent alerts."""
    monitor = get_health_monitor()
    status = monitor.get_health_status()
    return {
        "alerts": status.get("alerts", []),
        "timestamp": status.get("timestamp")
    }


# =============================================================================
# FRONTEND ERROR REPORTING (for debug-mcp correlation)
# =============================================================================

@app.post("/api/errors/frontend")
async def report_frontend_error(
    request: Request,
    error_data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Receive frontend/browser errors for correlation with backend failures.

    This endpoint should be called by the dashboard's JavaScript error handler
    to report console errors, unhandled exceptions, and React error boundaries.

    Expected payload:
    {
        "message": "Error message",
        "stack": "Stack trace (optional)",
        "url": "Page URL where error occurred",
        "type": "error|warning|exception",
        "user_agent": "Browser user agent (optional)"
    }

    The correlation ID from the request header is automatically attached.
    """
    # Get correlation ID from request state
    correlation_id = getattr(request.state, "correlation_id", None)

    # Build error entry
    error_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": error_data.get("message", "Unknown error"),
        "stack": error_data.get("stack"),
        "url": error_data.get("url"),
        "console_type": error_data.get("type", "error"),
        "user_agent": error_data.get("user_agent"),
        "correlation_id": correlation_id,
        "source": "frontend"
    }

    # Write to frontend errors log
    frontend_log = PROJECT_ROOT / ".hive-mind" / "frontend_errors.jsonl"
    frontend_log.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(frontend_log, "a") as f:
            f.write(json.dumps(error_entry) + "\n")
    except Exception as e:
        print(f"Failed to log frontend error: {e}")

    return {
        "status": "logged",
        "correlation_id": correlation_id,
        "timestamp": error_entry["timestamp"]
    }


@app.get("/api/debug/correlation-id")
async def get_correlation_id(request: Request) -> Dict[str, Any]:
    """
    Get the current request's correlation ID.

    Useful for debugging and for the frontend to know which
    correlation ID to attach to error reports.
    """
    correlation_id = getattr(request.state, "correlation_id", None)
    return {
        "correlation_id": correlation_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/debug/filesystem")
async def debug_filesystem(path: str = ".hive-mind/shadow_mode_emails"):
    """
    Debug: List files in a directory relative to project root.
    """
    target_dir = PROJECT_ROOT / path
    if not target_dir.exists():
        return {"exists": False, "path": str(target_dir), "files": []}
    
    files = []
    for f in target_dir.iterdir():
        stats = f.stat()
        files.append({
            "name": f.name,
            "size": stats.st_size,
            "modified": datetime.fromtimestamp(stats.st_mtime).isoformat()
        })
    return {"exists": True, "path": str(target_dir), "file_count": len(files), "files": files}


@app.post("/api/actions/record")
async def record_action(
    component: str,
    success: bool,
    latency_ms: float = 0,
    error: Optional[str] = None,
    agent: Optional[str] = None,
    action: Optional[str] = None
) -> Dict[str, Any]:
    """Record an action for a component."""
    monitor = get_health_monitor()
    monitor.record_action(component, success, latency_ms, error, agent, action)
    return {"status": "recorded"}


@app.post("/api/email/record")
async def record_email(count: int = 1) -> Dict[str, Any]:
    """Record emails sent."""
    monitor = get_health_monitor()
    monitor.record_email_sent(count)
    return {"status": "recorded", "count": count}


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)
    
    # Send initial status
    monitor = get_health_monitor()
    try:
        await websocket.send_json({
            "type": "health_update",
            "data": monitor.get_health_status()
        })
        
        # Keep connection alive and handle messages
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30.0)
                
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif data.get("type") == "refresh":
                    await websocket.send_json({
                        "type": "health_update",
                        "data": monitor.get_health_status()
                    })
            except asyncio.TimeoutError:
                # Send heartbeat
                await websocket.send_json({"type": "heartbeat"})
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# =============================================================================
# PRECISION SCORECARD ENDPOINTS
# =============================================================================

@app.get("/api/scorecard")
async def get_scorecard_summary():
    """
    Get the Precision Scorecard summary.
    
    Returns the 12 key metrics, organized by category, plus the current constraint.
    Inspired by Precision.co: "The only scorecard that tells you what to fix."
    """
    scorecard = get_scorecard()
    return scorecard.get_summary()


@app.post("/api/scorecard/refresh")
async def refresh_scorecard():
    """
    Force refresh all scorecard metrics from data sources.
    """
    scorecard = get_scorecard()
    scorecard.refresh()
    return {"status": "refreshed", "timestamp": datetime.now().isoformat()}


@app.get("/api/scorecard/constraint")
async def get_constraint():
    """
    Get just the current constraint (the ONE thing to fix).
    """
    scorecard = get_scorecard()
    constraint = scorecard.get_constraint()
    
    if constraint:
        return constraint.to_dict()
    else:
        return {"constraint": None, "message": "All metrics on track"}


@app.get("/api/scorecard/markdown")
async def get_scorecard_markdown():
    """
    Get the scorecard as a markdown report (for email/Slack).
    """
    scorecard = get_scorecard()
    return {"markdown": scorecard.to_markdown_report()}


@app.get("/scorecard")
async def scorecard_dashboard():
    """
    Serve the Precision Scorecard HTML dashboard.
    """
    scorecard_html = Path(__file__).parent / "scorecard.html"
    if scorecard_html.exists():
        return FileResponse(str(scorecard_html))
    raise HTTPException(status_code=404, detail="Scorecard dashboard not found")


@app.get("/sales")
async def sales_dashboard():
    """
    Serve the Head of Sales Dashboard.
    
    This is the primary dashboard for Dani Apgar to:
    - Review and approve pending emails
    - See the 4 key conversion metrics
    - View the #1 constraint to fix
    - Monitor recent activity
    """
    hos_html = Path(__file__).parent / "hos_dashboard.html"
    if hos_html.exists():
        return FileResponse(str(hos_html))
    raise HTTPException(status_code=404, detail="Sales dashboard not found")


@app.get("/ChiefAIOfficer", include_in_schema=False)
async def legacy_sales_dashboard_redirect(request: Request):
    """
    Backward-compatible route for older bookmarks.

    Some operators still open `/ChiefAIOfficer`; canonical dashboard route is `/sales`.
    Preserve query params (including `token`) when redirecting.
    """
    query = request.url.query
    target = "/sales"
    if query:
        target = f"{target}?{query}"
    return RedirectResponse(url=target, status_code=307)


@app.get("/chiefaiofficer", include_in_schema=False)
async def legacy_sales_dashboard_redirect_lower(request: Request):
    query = request.url.query
    target = "/sales"
    if query:
        target = f"{target}?{query}"
    return RedirectResponse(url=target, status_code=307)


@app.get("/leads")
async def leads_dashboard():
    """
    Serve the Lead Signal Loop & Activity Timeline dashboard.
    Monaco-inspired unified lead view with pipeline flow visualization.
    """
    leads_html = Path(__file__).parent / "leads_dashboard.html"
    if leads_html.exists():
        return FileResponse(str(leads_html))
    raise HTTPException(status_code=404, detail="Leads dashboard not found")


@app.get("/api/pending-emails")
async def get_pending_emails(
    response: Response,
    include_non_dispatchable: bool = False,
    auth: bool = Depends(require_auth),
):
    """
    Get pending emails awaiting approval.

    Reads from Redis (shared with local pipeline) first, filesystem fallback.
    This bridges the local-vs-Railway filesystem gap: pipeline writes to Redis
    from any machine, dashboard reads from the same Redis on Railway.
    """
    # Prevent stale browser/proxy caches for queue polling
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"

    # Keep shadow queue in sync with gatekeeper queue for resilience
    synced_count = _sync_gatekeeper_queue_to_shadow(PROJECT_ROOT)

    shadow_log = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"

    # Redis-backed shadow queue (handles Redis-first + filesystem fallback)
    pending = []
    sq_debug = {}
    try:
        from core.shadow_queue import list_pending, _prefix, _get_redis
        sq_debug["prefix"] = _prefix()
        sq_debug["redis_connected"] = _get_redis() is not None
        pending = list_pending(limit=20, shadow_dir=shadow_log)
        sq_debug["redis_returned"] = len(pending)
    except Exception as exc:
        logger.warning("shadow_queue.list_pending failed, falling back to filesystem: %s", exc)
        sq_debug["error"] = str(exc)

    merge_filesystem = _pending_queue_should_merge_filesystem(
        bool(sq_debug.get("redis_connected"))
    )
    file_pending = (
        _read_pending_from_shadow_files(shadow_log)
        if merge_filesystem
        else []
    )
    sq_debug["filesystem_pending"] = len(file_pending)
    sq_debug["filesystem_merge_enabled"] = merge_filesystem
    pending_map: Dict[str, Dict[str, Any]] = {}
    merged: List[Dict[str, Any]] = []
    for item in pending:
        email_id = str(item.get("email_id") or item.get("id") or "").strip()
        if email_id:
            pending_map[email_id] = item
            merged.append(item)
            continue
        merged.append(item)
    for item in file_pending:
        email_id = str(item.get("email_id") or item.get("id") or "").strip()
        if email_id and email_id in pending_map:
            continue
        merged.append(item)
    merged.sort(
        key=lambda item: str(item.get("timestamp") or item.get("created_at") or ""),
        reverse=True,
    )
    sq_debug["merged_count"] = len(merged)

    # Queue hygiene filter: hide non-actionable backlog items from approval UI.
    # This prevents stale placeholders and duplicate drafts from crowding valid approvals.
    now_utc = datetime.now(timezone.utc)
    tier_filter = _get_active_pending_queue_tier_filter()
    max_age_hours = _pending_queue_max_age_hours()
    include_non_dispatchable_effective = (
        include_non_dispatchable or _pending_queue_include_non_dispatchable_default()
    )
    placeholder_tokens = _pending_queue_placeholder_tokens()
    seen_dedupe_keys: Set[str] = set()

    pending = []
    excluded_reasons_count: Dict[str, int] = {}
    excluded_items_count = 0
    excluded_examples: List[Dict[str, Any]] = []
    for item in merged:
        reasons = _pending_email_exclusion_reasons(
            item,
            now_utc=now_utc,
            tier_filter=tier_filter,
            max_age_hours=max_age_hours,
            placeholder_tokens=placeholder_tokens,
            seen_dedupe_keys=seen_dedupe_keys,
            include_non_dispatchable=include_non_dispatchable_effective,
        )
        if reasons:
            excluded_items_count += 1
            for reason in reasons:
                excluded_reasons_count[reason] = excluded_reasons_count.get(reason, 0) + 1
            if len(excluded_examples) < 5:
                excluded_examples.append(
                    {
                        "email_id": item.get("email_id") or item.get("id"),
                        "tier": item.get("tier"),
                        "to": item.get("to"),
                        "timestamp": item.get("timestamp") or item.get("created_at"),
                        "reasons": reasons,
                    }
                )
            continue
        pending.append(item)
        if len(pending) >= 20:
            break

    sq_debug["queue_tier_filter"] = tier_filter
    sq_debug["queue_max_age_hours"] = max_age_hours
    sq_debug["include_non_dispatchable"] = include_non_dispatchable_effective
    sq_debug["excluded_non_actionable_count"] = excluded_items_count
    sq_debug["excluded_non_actionable_reasons"] = excluded_reasons_count
    sq_debug["excluded_non_actionable_examples"] = excluded_examples

    tier_routing_targets = _get_tier_routing_targets_by_tier()

    # Sanitize and classify all emails for frontend display
    for email_data in pending:
        email_data["timestamp"] = email_data.get("timestamp", "Unknown")
        email_data["recipient_data"] = email_data.get("recipient_data", {})
        email_data["to"] = email_data.get("to") or "unknown@example.com"
        email_data["subject"] = email_data.get("subject") or "No Subject"
        raw_body = email_data.get("body") or email_data.get("body_preview") or "No Body Content"
        email_data["body"] = enforce_text_signature(raw_body)
        email_data["tier"] = email_data.get("tier", "tier_3")
        email_data["angle"] = email_data.get("angle", "General")
        classifier = _infer_pending_email_classifier(
            email_data,
            tier_routing_targets=tier_routing_targets,
        )
        email_data["classifier"] = {
            key: value for key, value in classifier.items() if key != "campaign_ref"
        }
        email_data["campaign_ref"] = classifier.get("campaign_ref", {})
        email_data["proof_status"] = email_data.get("proof_status") or "not_started"
        email_data["proof_source"] = email_data.get("proof_source") or "none"
        email_data["proof_timestamp"] = email_data.get("proof_timestamp")
        email_data["proof_evidence_id"] = email_data.get("proof_evidence_id")
        email_data["deliverability_risk"] = email_data.get("deliverability_risk") or "unknown"
        email_data["deliverability_reasons"] = email_data.get("deliverability_reasons") or []
        email_data["model_route"] = (
            email_data.get("model_route")
            or email_data.get("routing_model")
            or "unknown"
        )

        # P0: Backend compliance checks — single source of truth for UI
        body_text = email_data.get("body") or ""
        body_lower = body_text.lower()
        email_data["compliance_checks"] = {
            "reply_stop_present": "reply stop to unsubscribe" in body_lower,
            "signature_present": "dani apgar" in body_lower,
            "cta_present": ("schedule a call with caio" in body_lower) or ("caio.cx/ai-exec-briefing-call" in body_lower),
            "footer_present": "support@chiefaiofficer.com" in body_lower,
            "normalization_version": "v3.0",
        }

    return {
        "pending_emails": pending,
        "count": len(pending),
        "synced_from_gatekeeper": synced_count,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "_shadow_queue_debug": sq_debug,
    }


@app.get("/api/emails/history")
async def get_email_history(
    limit: int = Query(20, ge=1, le=100, description="Max emails to return"),
    auth: bool = Depends(require_auth),
):
    """Return recently reviewed (approved/rejected) emails from shadow queue (Redis + file fallback)."""
    reviewed = []
    try:
        from core.shadow_queue import _prefix, _get_redis
        prefix = _prefix()
        r = _get_redis()
        if r:
            import json as _json
            for key in r.scan_iter(f"{prefix}:shadow:email:*"):
                try:
                    raw = r.get(key)
                    if not raw:
                        continue
                    data = _json.loads(raw)
                    status = (data.get("status") or "").lower()
                    if status not in ("approved", "rejected"):
                        continue
                    reviewed.append({
                        "email_id": data.get("email_id", ""),
                        "to": data.get("to", ""),
                        "subject": data.get("subject", ""),
                        "status": status,
                        "reviewed_at": data.get("approved_at") or data.get("rejected_at") or data.get("timestamp", ""),
                        "reviewer": data.get("approved_by") or data.get("rejected_by") or "",
                        "feedback": data.get("feedback"),
                        "rejection_reason": data.get("rejection_reason"),
                        "rejection_tag": data.get("rejection_tag"),
                        "campaign_ref": data.get("campaign_ref") or {},
                        "classifier": data.get("classifier") or {},
                    })
                except Exception:
                    continue
    except Exception as exc:
        logger.warning("get_email_history error: %s", exc)
    # File fallback for local/dev scenarios when Redis is unavailable or sparse.
    if len(reviewed) < limit:
        shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
        if shadow_dir.exists():
            for f in shadow_dir.glob("*.json"):
                try:
                    with open(f, "r", encoding="utf-8") as fp:
                        data = json.load(fp)
                    status = (data.get("status") or "").lower()
                    if status not in ("approved", "rejected"):
                        continue
                    email_id = data.get("email_id") or f.stem
                    if any(item.get("email_id") == email_id for item in reviewed):
                        continue
                    reviewed.append({
                        "email_id": email_id,
                        "to": data.get("to", ""),
                        "subject": data.get("subject", ""),
                        "status": status,
                        "reviewed_at": data.get("approved_at") or data.get("rejected_at") or data.get("timestamp", ""),
                        "reviewer": data.get("approved_by") or data.get("rejected_by") or "",
                        "feedback": data.get("feedback"),
                        "rejection_reason": data.get("rejection_reason"),
                        "rejection_tag": data.get("rejection_tag"),
                        "campaign_ref": data.get("campaign_ref") or {},
                        "classifier": data.get("classifier") or {},
                    })
                except Exception:
                    continue
    # Sort by reviewed_at descending
    reviewed.sort(key=lambda x: x.get("reviewed_at", ""), reverse=True)
    reviewed = reviewed[:limit]
    return {"emails": reviewed, "count": len(reviewed)}


@app.post("/api/emails/{email_id}/approve")
async def approve_email(
    email_id: str,
    approver: str = Query("dashboard_user", description="Who is approving"),
    auth: bool = Depends(require_auth),
    edited_body: Optional[str] = Body(None),
    feedback: Optional[str] = Body(None)
):
    """
    Approve an email for sending, optionally with edits and feedback.
    
    1. If edited_body is provided, updates the email content.
    2. Logs any feedback for agent training.
    3. CHECKS CONFIG for 'actually_send'.
    4. If true, dispatches to GHL API.
    5. Updates status and queues for send.
    """
    shadow_log = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
    shadow_log.mkdir(parents=True, exist_ok=True)

    email_file = None
    email_data = None

    # Try Redis first (handles Railway where filesystem is empty)
    try:
        from core.shadow_queue import get_email as sq_get
        email_data = sq_get(email_id, shadow_dir=shadow_log)
    except Exception:
        pass

    # Filesystem search (sets email_file for later disk write)
    for f in shadow_log.glob("*.json"):
        try:
            with open(f) as fp:
                data = json.load(fp)
                if data.get("email_id") == email_id or f.stem == email_id:
                    email_file = f
                    if email_data is None:
                        email_data = data
                    break
        except Exception:
            continue

    if not email_data:
        raise HTTPException(status_code=404, detail=f"Email {email_id} not found in queue")

    if email_data.get("status") == "approved":
        raise HTTPException(status_code=400, detail="Email already approved")

    # Capture original body BEFORE overwriting for training logs
    original_body = email_data.get("body") if edited_body else None
    
    # Always enforce canonical signature/footer contract at approval boundary.
    # If user edited body, enforce on edited content; otherwise normalize queued body.
    if edited_body:
        email_data["body"] = enforce_text_signature(edited_body)
        email_data["was_edited"] = True
    else:
        email_data["body"] = enforce_text_signature(email_data.get("body") or "")
    
    # =========================================================================
    # LIVE SENDING LOGIC
    # =========================================================================
    
    # Load config to check if we should send
    project_config = {}
    try:
        config_path = PROJECT_ROOT / "config" / "production.json"
        if config_path.exists():
            with open(config_path) as cp:
                project_config = json.load(cp)
    except Exception as e:
        print(f"Warning: Could not load config: {e}")
    
    actually_send = project_config.get("email_behavior", {}).get("actually_send", False)
    
    formatted_response = "Email approved (simulated)"
    final_status = "approved"
    email_data.setdefault("sent_via_ghl", False)
    email_data.setdefault("proof_status", "not_started")
    email_data.setdefault("proof_source", "none")
    email_data.setdefault("proof_timestamp", None)
    email_data.setdefault("proof_evidence_id", None)
    email_data.setdefault("deliverability_risk", "unknown")
    email_data.setdefault("deliverability_reasons", [])
    email_data.setdefault("model_route", _phase1_llm_routes()["daily"]["primary"])
    
    if actually_send:
        try:
            # Extract limits from loaded config
            # Default to 150/3000 if not found in config
            # Note: config structure is guardrails -> email_limits
            email_limits = project_config.get("guardrails", {}).get("email_limits", {})

            outreach_config = OutreachConfig(
                monthly_limit=email_limits.get("monthly_limit", 3000),
                daily_limit=email_limits.get("daily_limit", 150),
                min_delay_seconds=email_limits.get("min_delay_seconds", 60)
            )

            # Load GHL credentials from environment
            api_key = os.getenv("GHL_API_KEY") or os.getenv("GHL_PROD_API_KEY")
            location_id = os.getenv("GHL_LOCATION_ID")

            if api_key and location_id:
                client = GHLOutreachClient(api_key, location_id, config=outreach_config)
                try:
                    contact_id = str(email_data.get("contact_id") or "").strip()
                    recipient_email = str(email_data.get("to") or "").strip().lower()
                    non_dispatchable_training = bool(
                        email_data.get("_do_not_dispatch")
                        or email_data.get("canary_training")
                        or email_data.get("canary")
                    )

                    # Guard against synthetic/test data in live mode
                    if non_dispatchable_training:
                        email_data["send_skipped_reason"] = "non_dispatchable_training"
                        email_data["sent_via_ghl"] = False
                        formatted_response = "Email approved (Training/Non-dispatchable skipped)"
                    elif email_data.get("synthetic") or contact_id.startswith("synthetic_"):
                        formatted_response = "Email approved (Synthetic/Test skipped)"
                    else:
                        guard = DeliverabilityGuard(
                            fail_closed=_env_bool("DELIVERABILITY_FAIL_CLOSED", True)
                        )
                        verdict = guard.evaluate(recipient_email)
                        email_data["deliverability_risk"] = verdict.get("risk_level", "unknown")
                        email_data["deliverability_reasons"] = verdict.get("reasons", [])
                        email_data["deliverability_recommended_tag"] = verdict.get("recommended_tag")
                        if not verdict.get("allow_send", True):
                            final_status = "blocked_deliverability"
                            email_data["sent_via_ghl"] = False
                            email_data["send_error"] = (
                                f"Deliverability blocked: {', '.join(email_data['deliverability_reasons'])}"
                            )
                            formatted_response = "Blocked by deliverability guard"
                            # Do not attempt outbound on blocked recipients.
                            contact_id = ""

                        # Auto resolve/create GHL contact for real sends.
                        if final_status != "blocked_deliverability" and not contact_id and recipient_email:
                            recipient_data = email_data.get("recipient_data", {})
                            full_name = str(recipient_data.get("name") or "").strip()
                            first_name = full_name.split(None, 1)[0] if full_name else ""
                            last_name = full_name.split(None, 1)[1] if full_name and len(full_name.split(None, 1)) > 1 else ""
                            resolve_result = await client.resolve_or_create_contact_by_email(
                                email=recipient_email,
                                name=full_name,
                                first_name=first_name,
                                last_name=last_name,
                                company=str(recipient_data.get("company") or "").strip(),
                            )
                            if resolve_result.get("success"):
                                contact_id = str(resolve_result.get("contact_id") or "").strip()
                                if contact_id:
                                    email_data["contact_id"] = contact_id
                                    email_data["contact_resolution"] = {
                                        "resolved": True,
                                        "created": bool(resolve_result.get("created")),
                                        "resolved_at": datetime.now().isoformat(),
                                    }
                            else:
                                err = resolve_result.get("error") or "unknown_upsert_error"
                                email_data["contact_resolution"] = {
                                    "resolved": False,
                                    "error": str(err),
                                    "resolved_at": datetime.now().isoformat(),
                                }
                                email_data["send_error"] = f"GHL contact upsert failed: {err}"

                        if final_status != "blocked_deliverability" and contact_id:
                            # Create temp template from the approved content
                            temp_template = EmailTemplate(
                                id=f"approved_{email_id}",
                                name="Approved Dashboard Email",
                                subject=email_data.get("subject", ""),
                                body=email_data.get("body", ""),
                                type=OutreachType.WARM
                            )

                            # Send!
                            result = await client.send_email(contact_id, temp_template)

                            if result.get("success"):
                                email_data["sent_via_ghl"] = True
                                email_data["ghl_message_id"] = result.get("message_id")
                                # XS-06: Persist sent_via_ghl immediately — before proof engine.
                                # If proof or later steps crash, file still records the send.
                                if email_file:
                                    try:
                                        _atomic_json_write(email_file, email_data)
                                    except Exception:
                                        logger.warning("XS-06: Failed to persist sent_via_ghl for %s", email_id)
                                proof_engine = GHLSendProofEngine(
                                    proof_sla_seconds=int(os.getenv("PROOF_SLA_SECONDS", "900") or "900"),
                                    poll_fallback_enabled=_env_bool("PROOF_POLL_FALLBACK_ENABLED", True),
                                    evidence_file=PROJECT_ROOT / ".hive-mind" / "ghl_webhook_events.jsonl",
                                )
                                try:
                                    proof = await proof_engine.resolve_proof(
                                        client=client,
                                        shadow_email_id=email_id,
                                        recipient_email=recipient_email,
                                        contact_id=contact_id,
                                        send_result=result,
                                    )
                                except Exception:
                                    proof = {
                                        "proof_status": "unresolved",
                                        "proof_source": "none",
                                        "proof_timestamp": datetime.now(timezone.utc).isoformat(),
                                        "proof_evidence_id": None,
                                    }

                                email_data["proof_status"] = proof.get("proof_status", "unresolved")
                                email_data["proof_source"] = proof.get("proof_source", "none")
                                email_data["proof_timestamp"] = proof.get("proof_timestamp")
                                email_data["proof_evidence_id"] = proof.get("proof_evidence_id")

                                if email_data["proof_status"] == "proved":
                                    final_status = "sent_proved"
                                    formatted_response = (
                                        f"Email sent and proved via GHL ({email_data['proof_source']})"
                                    )
                                else:
                                    final_status = "sent_unresolved"
                                    formatted_response = "Email sent via GHL (proof unresolved)"
                            else:
                                error_msg = result.get("error", "Unknown error")
                                if "limit reached" in str(error_msg):
                                    # Rate limit hit - Queue it!
                                    email_data["sent_via_ghl"] = False
                                    email_data["queued_for_send"] = True
                                    email_data["send_error"] = f"Rate Limit Hit: {error_msg}"
                                    formatted_response = "Email approved & Queued (Rate Limit Hit)"
                                else:
                                    # Other error - Fail hard
                                    raise Exception(f"GHL Send Failed: {error_msg}")
                        elif final_status != "blocked_deliverability":
                            formatted_response = "Email approved (GHL contact unresolved)"
                finally:
                    await client.close()
            else:
                print("Warning: GHL Config missing, skipping send.")
                formatted_response = "Email approved (Config Missing)"
        except Exception as e:
            # If sending fails, we should generally Notify user
            print(f"Critical Error sending email: {e}")
            # For now, we allow approval to proceed but log the error
            email_data["send_error"] = str(e)
            formatted_response = f"Approved but Send Failed: {str(e)}"

    # =========================================================================
    
    # Update status
    email_data["status"] = final_status
    email_data["approved_at"] = datetime.now().isoformat()
    email_data["approved_by"] = approver
    email_data["feedback"] = feedback
    
    # Save updated data — Redis + filesystem
    try:
        from core.shadow_queue import update_status as sq_update
        sq_update(email_id, final_status, shadow_dir=shadow_log, extra_fields={
            "approved_at": email_data.get("approved_at"),
            "approved_by": approver,
            "contact_id": email_data.get("contact_id"),
            "contact_resolution": email_data.get("contact_resolution"),
            "sent_via_ghl": email_data.get("sent_via_ghl"),
            "ghl_message_id": email_data.get("ghl_message_id"),
            "queued_for_send": email_data.get("queued_for_send"),
            "send_error": email_data.get("send_error"),
            "proof_status": email_data.get("proof_status"),
            "proof_source": email_data.get("proof_source"),
            "proof_timestamp": email_data.get("proof_timestamp"),
            "proof_evidence_id": email_data.get("proof_evidence_id"),
            "deliverability_risk": email_data.get("deliverability_risk"),
            "deliverability_reasons": email_data.get("deliverability_reasons"),
            "deliverability_recommended_tag": email_data.get("deliverability_recommended_tag"),
            "model_route": email_data.get("model_route"),
        })
    except Exception:
        pass  # Redis sync is best-effort; file is authoritative
    if email_file:
        try:
            _atomic_json_write(email_file, email_data)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save approval: {e}")

    # Log to Audit Log
    audit_log = PROJECT_ROOT / ".hive-mind" / "audit" / "email_approvals.jsonl"
    audit_log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(audit_log, "a") as fp:
            fp.write(json.dumps({
                "email_id": email_id,
                "action": "approved",
                "approver": approver,
                "sent_real": actually_send,
                "timestamp": datetime.now().isoformat(),
                "recipient": email_data.get("to"),
                "subject": email_data.get("subject"),
                "was_edited": bool(edited_body),
                "feedback": feedback
            }) + "\n")
    except Exception:
        logger.warning("Failed to append email approval audit event for %s", email_id)

    # Log to Training Feedback Log - ALWAYS log for learning, not just when edited
    training_log = PROJECT_ROOT / ".hive-mind" / "audit" / "agent_feedback.jsonl"
    training_log.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Build comprehensive learning record
        learning_record = {
            "email_id": email_id,
            "action": "approved_with_edits" if edited_body else ("approved_with_feedback" if feedback else "approved"),
            "feedback": feedback,
            "original_body": original_body,  # Preserved before overwrite
            "edited_body": edited_body,
            "subject": email_data.get("subject"),
            "recipient": email_data.get("to"),
            "tier": email_data.get("tier"),
            "angle": email_data.get("angle"),
            "approver": approver,
            "timestamp": datetime.now().isoformat(),
            "learning_signals": {
                "was_edited": bool(edited_body),
                "had_feedback": bool(feedback),
                "edit_type": "minor_tweak" if edited_body and len(edited_body) - len(original_body or "") < 100 else "major_rewrite" if edited_body else None
            }
        }
        with open(training_log, "a") as fp:
            fp.write(json.dumps(learning_record) + "\n")
    except Exception as e:
        print(f"Warning: Failed to log training feedback: {e}")

    # Persist deterministic learning tuple for optimizer/replay.
    try:
        loop = FeedbackLoop(storage_dir=PROJECT_ROOT / ".hive-mind" / "feedback_loop")
        loop.record_email_outcome(
            email_data=email_data,
            outcome=final_status,
            action="approve_email",
            metadata={
                "email_id": email_id,
                "approver": approver,
                "actually_send": bool(actually_send),
                "edited": bool(edited_body),
                "had_feedback": bool(feedback),
            },
        )
    except Exception as exc:
        logger.warning("Failed to persist feedback loop event on approval for %s: %s", email_id, exc)
    
    return {
        "status": "approved",
        "email_id": email_id,
        "edited": bool(edited_body),
        "message": formatted_response
    }


@app.post("/api/emails/{email_id}/reject")
async def reject_email(
    email_id: str,
    reason: Optional[str] = Query(None, description="Reason for rejection"),
    rejection_tag: Optional[str] = Query(None, description="Structured rejection taxonomy tag"),
    approver: str = Query("dashboard_user", description="Who is rejecting"),
    auth: bool = Depends(require_auth)
):
    """
    Reject an email.

    Finds the email and marks it as rejected with reason.
    Logs the rejection for agent training.
    """
    shadow_log = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
    shadow_log.mkdir(parents=True, exist_ok=True)

    email_file = None
    email_data = None

    # Try Redis first (handles Railway where filesystem is empty)
    try:
        from core.shadow_queue import get_email as sq_get
        email_data = sq_get(email_id, shadow_dir=shadow_log)
    except Exception:
        pass

    # Filesystem search
    for f in shadow_log.glob("*.json"):
        try:
            with open(f) as fp:
                data = json.load(fp)
                if data.get("email_id") == email_id or f.stem == email_id:
                    email_file = f
                    if email_data is None:
                        email_data = data
                    break
        except Exception:
            continue

    if not email_data:
        raise HTTPException(status_code=404, detail=f"Email {email_id} not found in queue")

    if email_data.get("status") == "rejected":
        raise HTTPException(status_code=400, detail="Email already rejected")

    validated_reason = _validate_rejection_reason(reason)
    validated_tag = _validate_rejection_tag(rejection_tag)

    # Update status
    email_data["status"] = "rejected"
    email_data["rejected_at"] = datetime.now().isoformat()
    email_data["rejected_by"] = approver
    email_data["rejection_reason"] = validated_reason
    email_data["rejection_tag"] = validated_tag
    email_data["feedback"] = validated_reason

    # Save updated data — Redis + filesystem
    try:
        from core.shadow_queue import update_status as sq_update
        sq_update(email_id, "rejected", shadow_dir=shadow_log, extra_fields={
            "rejected_at": email_data.get("rejected_at"),
            "rejected_by": approver,
            "rejection_reason": validated_reason,
            "rejection_tag": validated_tag,
        })
    except Exception:
        pass
    if email_file:
        try:
            with open(email_file, "w") as fp:
                json.dump(email_data, fp, indent=2)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save rejection: {e}")

    # Log to Training Feedback Log - comprehensive learning record
    training_log = PROJECT_ROOT / ".hive-mind" / "audit" / "agent_feedback.jsonl"
    training_log.parent.mkdir(parents=True, exist_ok=True)
    try:
        learning_record = {
            "email_id": email_id,
            "action": "rejected",
            "feedback": validated_reason,
            "original_body": email_data.get("body"),
            "subject": email_data.get("subject"),
            "recipient": email_data.get("to"),
            "tier": email_data.get("tier"),
            "angle": email_data.get("angle"),
            "approver": approver,
            "timestamp": datetime.now().isoformat(),
            "learning_signals": {
                "was_edited": False,
                "had_feedback": True,
                "rejection_tag": validated_tag,
                "rejection_category": validated_tag,
                "rejection_category_heuristic": _categorize_rejection(validated_reason),
            }
        }
        with open(training_log, "a") as fp:
            fp.write(json.dumps(learning_record) + "\n")
    except Exception as e:
        print(f"Warning: Failed to log training feedback: {e}")

    # Persist deterministic learning tuple for optimizer/replay.
    try:
        loop = FeedbackLoop(storage_dir=PROJECT_ROOT / ".hive-mind" / "feedback_loop")
        loop.record_email_outcome(
            email_data=email_data,
            outcome="rejected",
            action="reject_email",
            metadata={
                "email_id": email_id,
                "approver": approver,
                "rejection_tag": validated_tag,
            },
        )
    except Exception as exc:
        logger.warning("Failed to persist feedback loop event on rejection for %s: %s", email_id, exc)
    
    # Log the rejection
    audit_log = PROJECT_ROOT / ".hive-mind" / "audit" / "email_approvals.jsonl"
    audit_log.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(audit_log, "a") as fp:
            fp.write(json.dumps({
                "email_id": email_id,
                "action": "rejected",
                "approver": approver,
                "reason": validated_reason,
                "rejection_tag": validated_tag,
                "timestamp": datetime.now().isoformat(),
                "recipient": email_data.get("to"),
                "subject": email_data.get("subject")
            }) + "\n")
    except Exception:
        logger.warning("Failed to append rejection audit event for %s", email_id)

    # Record per-lead rejection memory for repeat prevention
    try:
        from core.rejection_memory import record_rejection as rm_record
        rm_record(
            lead_email=email_data.get("to", ""),
            rejection_tag=validated_tag,
            subject=email_data.get("subject", ""),
            body=email_data.get("body", ""),
            feedback_text=validated_reason,
            template_id=email_data.get("template_version", email_data.get("template", "")),
        )
    except Exception as exc:
        logger.warning("Failed to record rejection memory for %s: %s", email_id, exc)

    return {
        "status": "rejected",
        "email_id": email_id,
        "reason": validated_reason,
        "rejection_tag": validated_tag,
        "approver": approver,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/rejection-tags")
async def get_rejection_tags(auth: bool = Depends(require_auth)):
    """Return supported structured rejection tags for UI and tooling."""
    return {
        "tags": [{"id": key, "label": label} for key, label in REJECTION_TAGS.items()]
    }


@app.get("/api/queue-status")
async def get_queue_status(auth: bool = Depends(require_auth)):
    """
    Get the status of all email queues for pipeline monitoring.
    
    Returns counts from:
    - shadow_mode_emails (dashboard approvals)
    - gatekeeper_queue (backup/audit)
    - Daily email counts
    """
    shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
    gatekeeper_dir = PROJECT_ROOT / ".hive-mind" / "gatekeeper_queue"
    metrics_file = PROJECT_ROOT / ".hive-mind" / "metrics" / "daily_email_counts.json"
    intent_log = PROJECT_ROOT / ".hive-mind" / "logs" / "intent_queue.jsonl"
    
    # Shadow mode emails breakdown
    shadow_pending = 0
    shadow_approved = 0
    shadow_rejected = 0
    shadow_total = 0
    
    if shadow_dir.exists():
        for f in shadow_dir.glob("*.json"):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    status = data.get("status", "pending")
                    shadow_total += 1
                    if status == "pending":
                        shadow_pending += 1
                    elif status == "approved":
                        shadow_approved += 1
                    elif status == "rejected":
                        shadow_rejected += 1
            except Exception as exc:
                logger.warning("Failed to parse queue file %s: %s", f, exc)
    
    # Gatekeeper queue count
    gatekeeper_count = 0
    if gatekeeper_dir.exists():
        gatekeeper_count = len(list(gatekeeper_dir.glob("*.json")))
    
    # Daily counts
    daily_counts = {"date": "N/A", "queued": 0, "sent": 0}
    if metrics_file.exists():
        try:
            with open(metrics_file) as f:
                daily_counts = json.load(f)
        except Exception as exc:
            logger.warning("Failed to read daily metrics file %s: %s", metrics_file, exc)
    
    # Recent intent queue events (last 10)
    recent_events = []
    if intent_log.exists():
        try:
            with open(intent_log) as f:
                lines = f.readlines()
                for line in lines[-10:]:
                    try:
                        recent_events.append(json.loads(line.strip()))
                    except Exception as exc:
                        logger.debug("Skipping malformed intent log line: %s", exc)
        except Exception as exc:
            logger.warning("Failed to read intent log %s: %s", intent_log, exc)
    
    return {
        "shadow_mode_emails": {
            "total": shadow_total,
            "pending": shadow_pending,
            "approved": shadow_approved,
            "rejected": shadow_rejected
        },
        "gatekeeper_queue": {
            "total": gatekeeper_count
        },
        "daily_limits": {
            "date": daily_counts.get("date", "N/A"),
            "queued_today": daily_counts.get("queued", 0),
            "sent_today": daily_counts.get("sent", 0),
            "limit": 25,
            "remaining": max(0, 25 - daily_counts.get("queued", 0)),
            "last_queued_at": daily_counts.get("last_queued_at")
        },
        "recent_queue_events": recent_events[-5:],
        "pipeline_healthy": shadow_pending > 0 or gatekeeper_count > 0 or daily_counts.get("queued", 0) > 0
    }


@app.get("/api/health/ready")
async def readiness_probe():
    """
    Kubernetes readiness probe endpoint.
    
    Returns 200 if the service is ready to accept traffic.
    """
    try:
        monitor = get_health_monitor()
        status = monitor.get_health_status()
        runtime_health = get_runtime_dependency_health(
            check_connections=True,
            inngest_route_mounted=INNGEST_ROUTE_MOUNTED,
        )

        if not runtime_health.get("ready", False):
            failures = runtime_health.get("required_failures", [])
            raise HTTPException(
                status_code=503,
                detail=f"Runtime dependencies not ready: {', '.join(failures)}"
            )
        
        # Check critical dependencies
        integrations = status.get("integrations", {})
        critical_integrations = [
            name.strip()
            for name in os.getenv("CRITICAL_INTEGRATIONS", "ghl,supabase,clay").split(",")
            if name.strip()
        ]
        unhealthy = [
            name for name in critical_integrations
            if integrations.get(name, {}).get("status") == "unhealthy"
        ]

        if unhealthy:
            raise HTTPException(
                status_code=503,
                detail=f"Critical integrations unhealthy: {', '.join(unhealthy)}"
            )
        
        return {
            "status": "ready",
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "health_monitor": "ok",
                "integrations": "ok",
                "runtime_dependencies": runtime_health.get("status", "unknown")
            },
            "runtime_dependencies": runtime_health,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Readiness check failed: {e}")



# =============================================================================
# CALL PREP AGENT ENDPOINTS
# =============================================================================

@app.post("/api/call-prep/{contact_id}")
async def prepare_contact_for_call(
    contact_id: str,
    dry_run: bool = Query(False, description="If true, don't update GHL"),
    auth: bool = Depends(require_auth)
):
    """
    Prepare a contact for an upcoming call by enriching custom fields.
    
    Populates:
    - call_prep_summary: One-paragraph briefing
    - pain_points: Detected pain points
    - warm_connections: Team connections
    - recommended_approach: Conversation angle
    - objection_prep: Likely objections and responses
    """
    try:
        from core.call_prep_agent import get_call_prep_agent
        agent = get_call_prep_agent()
        result = await agent.prepare_contact_for_call(
            contact_id=contact_id,
            update_ghl=not dry_run
        )
        return {
            "status": "success",
            "contact_id": contact_id,
            "contact_name": result.contact_name,
            "company_name": result.company_name,
            "summary": result.summary,
            "pain_points": result.pain_points,
            "warm_connections": result.warm_connections,
            "recommended_approach": result.recommended_approach,
            "objection_prep": result.objection_prep,
            "confidence_score": result.confidence_score,
            "ghl_updated": not dry_run
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Call prep failed: {e}")


@app.post("/api/call-prep/batch")
async def prepare_hot_leads_batch(
    limit: int = Query(10, description="Max leads to prepare"),
    auth: bool = Depends(require_auth)
):
    """
    Prepare all hot leads in queue for upcoming calls.
    """
    try:
        from core.call_prep_agent import get_call_prep_agent
        agent = get_call_prep_agent()
        results = await agent.prepare_hot_leads_batch(limit=limit)
        return {
            "status": "success",
            "prepared_count": len(results),
            "leads": [
                {
                    "contact_id": r.contact_id,
                    "name": r.contact_name,
                    "company": r.company_name,
                    "confidence": r.confidence_score
                }
                for r in results
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch prep failed: {e}")


# =============================================================================
# CLAY ENRICHMENT CALLBACK (pipeline + legacy)
# =============================================================================

def _clay_redis_prefix() -> str:
    """Redis prefix consistent with shadow_queue (CONTEXT_REDIS_PREFIX first)."""
    return (os.getenv("CONTEXT_REDIS_PREFIX") or os.getenv("STATE_REDIS_PREFIX") or "caio").strip()


def _normalize_linkedin_url(url: str) -> str:
    """Normalize LinkedIn URL for consistent hashing."""
    import hashlib
    u = url.lower().strip().rstrip("/")
    for pfx in ("https://www.", "http://www.", "https://", "http://"):
        if u.startswith(pfx):
            u = u[len(pfx):]
            break
    return u


@app.post("/api/clay-callback")
async def clay_enrichment_callback(request: Request):
    """
    Receives Clay workbook callback and stores result in Redis for pipeline pickup.

    Pipeline flow:
    1. Local pipeline sends lead to Clay workbook webhook, stores correlation
       in Redis as {prefix}:clay:pipeline:{linkedin_hash} → {lead_id, request_id, ...}
    2. Clay enriches and fires HTTP API callback to this endpoint
    3. This handler extracts linkedin_url, looks up correlation, stores enriched
       data in Redis as {prefix}:clay:result:{request_id}
    4. Local pipeline polling loop picks up the result
    """
    import hashlib

    data = await request.json()
    logger.info("Clay callback received: %s", json.dumps(data)[:200])

    # Extract LinkedIn URL from Clay response for correlation lookup
    linkedin_url = (
        data.get("linkedin_url") or data.get("person_linkedin_url") or ""
    ).strip()

    if not linkedin_url:
        logger.warning("Clay callback missing linkedin_url — cannot correlate to pipeline lead")
        return {"status": "received", "correlated": False, "reason": "no_linkedin_url"}

    prefix = _clay_redis_prefix()
    normalized = _normalize_linkedin_url(linkedin_url)
    linkedin_hash = hashlib.sha256(normalized.encode()).hexdigest()[:32]
    correlation_key = f"{prefix}:clay:pipeline:{linkedin_hash}"

    # Try to get Redis client (same pattern as shadow_queue)
    try:
        import redis as _redis_mod
        redis_url = (os.getenv("REDIS_URL") or "").strip()
        if not redis_url:
            logger.warning("Clay callback: REDIS_URL not set")
            return {"status": "received", "correlated": False, "reason": "no_redis"}
        r = _redis_mod.Redis.from_url(redis_url, decode_responses=True, socket_timeout=3)
    except Exception as exc:
        logger.error("Clay callback: Redis connect failed: %s", exc)
        return {"status": "received", "correlated": False, "reason": "redis_error"}

    # Look up correlation
    try:
        raw_correlation = r.get(correlation_key)
    except Exception as exc:
        logger.error("Clay callback: Redis GET failed: %s", exc)
        return {"status": "received", "correlated": False, "reason": "redis_get_error"}

    if not raw_correlation:
        logger.info("Clay callback: no pipeline correlation for %s (may be RB2B visitor)", linkedin_url[:60])
        return {"status": "received", "correlated": False, "reason": "no_correlation_found"}

    try:
        correlation = json.loads(raw_correlation)
    except Exception:
        logger.error("Clay callback: corrupt correlation data")
        return {"status": "received", "correlated": False, "reason": "corrupt_correlation"}

    request_id = correlation.get("request_id", "")
    if not request_id:
        logger.error("Clay callback: correlation missing request_id")
        return {"status": "received", "correlated": False, "reason": "no_request_id"}

    # Store enriched result for pipeline polling
    result_key = f"{prefix}:clay:result:{request_id}"
    try:
        r.setex(result_key, 600, json.dumps(data))
    except Exception as exc:
        logger.error("Clay callback: failed to store result: %s", exc)
        return {"status": "received", "correlated": False, "reason": "redis_set_error"}

    logger.info("Clay callback correlated: request_id=%s, lead_id=%s", request_id, correlation.get("lead_id"))
    return {
        "status": "received",
        "correlated": True,
        "request_id": request_id,
        "lead_id": correlation.get("lead_id"),
    }


# =============================================================================
# LEAD SIGNAL LOOP & ACTIVITY TIMELINE (Monaco-inspired)
# =============================================================================

try:
    from core.lead_signals import LeadStatusManager
    from core.activity_timeline import ActivityTimeline

    _lead_status_mgr = LeadStatusManager()
    _activity_timeline = ActivityTimeline()

    @app.get("/api/leads")
    async def get_leads():
        """Get all tracked leads with current status and engagement data."""
        return _activity_timeline.get_all_leads_summary()

    @app.get("/api/leads/funnel")
    async def get_leads_funnel():
        """Get pipeline funnel counts for visualization."""
        return _activity_timeline.get_funnel_summary()

    @app.get("/api/leads/status-summary")
    async def get_leads_status_summary():
        """Get count of leads by engagement status."""
        return _lead_status_mgr.get_status_summary()

    @app.get("/api/leads/{email}/timeline")
    async def get_lead_timeline(email: str):
        """Get unified activity timeline for a specific lead."""
        timeline = _activity_timeline.get_lead_timeline(email)
        status = _lead_status_mgr.get_lead_status(email)
        return {
            "email": email,
            "current_status": status,
            "timeline": timeline,
            "event_count": len(timeline),
        }

    @app.post("/api/leads/detect-decay")
    async def detect_engagement_decay():
        """Run ghosting/stall detection across all leads."""
        results = _lead_status_mgr.detect_engagement_decay()
        return {
            "ghosted": len(results["ghosted"]),
            "stalled": len(results["stalled"]),
            "engaged_not_replied": len(results["engaged_not_replied"]),
            "details": results,
        }

    @app.post("/api/leads/bootstrap")
    async def bootstrap_lead_statuses():
        """Seed lead status records from existing shadow emails."""
        count = _lead_status_mgr.bootstrap_from_shadow_emails()
        return {"created": count, "message": f"Bootstrapped {count} lead status records"}

    logger.info("✓ Lead Signal Loop & Activity Timeline endpoints mounted")
except Exception as e:
    logger.warning("Lead Signal Loop could not be mounted: %s", e)

# =============================================================================
# OPERATOR AGENT ENDPOINTS
# =============================================================================

try:
    from execution.operator_outbound import OperatorOutbound
    from execution.operator_revival_scanner import RevivalScanner
    from dataclasses import asdict as _op_asdict

    _operator = OperatorOutbound()
    _revival_scanner = RevivalScanner()

    @app.get("/api/operator/status")
    async def operator_status():
        """Get current OPERATOR status: warmup schedule, today's counts, limits."""
        return _operator.get_status()

    @app.get("/api/operator/revival-candidates")
    async def operator_revival_candidates(limit: int = Query(default=20, le=50)):
        """Preview revival candidates without dispatching."""
        candidates = _revival_scanner.scan(limit=limit)
        return {
            "candidates": [_op_asdict(c) for c in candidates],
            "count": len(candidates),
        }

    @app.post("/api/operator/trigger")
    async def operator_trigger(request: Request):
        """Trigger OPERATOR dispatch (outbound + revival)."""
        try:
            body = await request.json()
        except Exception:
            body = {}

        dry_run = body.get("dry_run", True)
        motion = body.get("motion", "all")

        if motion == "outbound":
            report = await _operator.dispatch_outbound(dry_run=dry_run)
        elif motion == "revival":
            report = await _operator.dispatch_revival(dry_run=dry_run)
        else:
            report = await _operator.dispatch_all(dry_run=dry_run)

        return _op_asdict(report)

    @app.get("/api/operator/history")
    async def operator_history(limit: int = Query(default=50, le=200)):
        """Get recent OPERATOR dispatch history."""
        return _operator.get_dispatch_history(limit=limit)

    @app.get("/api/operator/pending-batch")
    async def operator_pending_batch():
        """Get the current pending dispatch batch (if any)."""
        from dataclasses import asdict as _batch_asdict
        batch = _operator.get_pending_batch()
        if not batch:
            return {"status": "no_pending_batch", "message": "No dispatch batch awaiting approval"}
        return _batch_asdict(batch)

    @app.post("/api/operator/approve-batch/{batch_id}")
    async def operator_approve_batch(batch_id: str, request: Request):
        """Approve a dispatch batch for execution."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        approved_by = body.get("approved_by", "dashboard")
        try:
            from dataclasses import asdict as _batch_asdict
            batch = _operator.approve_batch(batch_id, approved_by=approved_by)
            return {"status": "approved", "batch": _batch_asdict(batch)}
        except FileNotFoundError:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=404, content={"error": f"Batch {batch_id} not found"})
        except ValueError as e:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=400, content={"error": str(e)})

    @app.post("/api/operator/reject-batch/{batch_id}")
    async def operator_reject_batch(batch_id: str, request: Request):
        """Reject a dispatch batch."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        reason = body.get("reason", "")
        try:
            from dataclasses import asdict as _batch_asdict
            batch = _operator.reject_batch(batch_id, reason=reason)
            return {"status": "rejected", "batch": _batch_asdict(batch)}
        except FileNotFoundError:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=404, content={"error": f"Batch {batch_id} not found"})

    logger.info("✓ OPERATOR Agent endpoints mounted (incl. GATEKEEPER batch approval)")
except Exception as e:
    logger.warning("OPERATOR endpoints could not be mounted: %s", e)

# =============================================================================
# CADENCE ENGINE ENDPOINTS
# =============================================================================

try:
    from execution.cadence_engine import CadenceEngine
    _cadence = CadenceEngine()

    @app.get("/api/cadence/summary")
    async def cadence_summary():
        """Cadence engine summary: enrolled, active, completed, due today."""
        return _cadence.get_cadence_summary()

    @app.get("/api/cadence/due")
    async def cadence_due_actions():
        """List cadence actions due today."""
        from dataclasses import asdict
        actions = _cadence.get_due_actions()
        return [{
            "email": a.email,
            "step": a.step.step,
            "day": a.step.day,
            "channel": a.step.channel,
            "action": a.step.action,
            "description": a.step.description,
            "tier": a.tier,
        } for a in actions]

    @app.get("/api/cadence/leads")
    async def cadence_lead_list(status: str = None):
        """List all cadence states, optionally filtered by status."""
        from dataclasses import asdict
        states = _cadence.get_all_cadence_states()
        if status:
            states = [s for s in states if s.status == status]
        return [asdict(s) for s in states]

    @app.post("/api/cadence/sync")
    async def cadence_sync_signals():
        """Sync cadence with signal loop (auto-exit replied/bounced leads)."""
        return _cadence.sync_signals()

    logger.info("✓ Cadence Engine endpoints mounted")
except Exception as e:
    logger.warning("Cadence endpoints could not be mounted: %s", e)

# =============================================================================
# WEBHOOKS INTEGRATION
# =============================================================================

try:
    from core.inngest_scheduler import get_inngest_serve
    get_inngest_serve(app)
    INNGEST_ROUTE_MOUNTED = True
    logger.info("✓ Inngest route mounted at /inngest")
except Exception as e:
    INNGEST_ROUTE_MOUNTED = False
    logger.warning("Inngest route could not be mounted: %s", e)

try:
    from webhooks.rb2b_webhook import router as rb2b_router
    app.include_router(rb2b_router)
    logger.info("✓ RB2B Webhook mounted")
except Exception as e:
    logger.warning("RB2B Webhook could not be mounted: %s", e)

try:
    from webhooks.instantly_webhook import router as instantly_router
    app.include_router(instantly_router)
    logger.info("✓ Instantly Webhook + Campaign Management mounted")
except Exception as e:
    logger.warning("Instantly webhook router could not be mounted: %s", e)

try:
    from webhooks.heyreach_webhook import router as heyreach_router
    app.include_router(heyreach_router)
    logger.info("✓ HeyReach Webhook mounted")
except Exception as e:
    logger.warning("HeyReach webhook router could not be mounted: %s", e)

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  CAIO Swarm Health Dashboard")
    print("=" * 60)
    print("  HTTP:      http://localhost:8080")
    print("  WebSocket: ws://localhost:8080/ws")
    print("  API:       http://localhost:8080/api/health")
    print("  Webhook:   http://localhost:8080/webhooks/rb2b")
    print("=" * 60 + "\n")
    
    uvicorn.run(
        "health_app:app",
        host="0.0.0.0",
        port=8080,
        reload=True
    )
