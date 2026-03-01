#!/usr/bin/env python3
"""
HeyReach LinkedIn Dispatcher
==============================
Routes approved leads to pre-built HeyReach LinkedIn campaigns.

CRITICAL SAFETY: HeyReach auto-reactivates paused campaigns when leads are
added directly. This dispatcher uses the lead-list-first pattern:
  1. Add leads to a HeyReach lead LIST (safe, no auto-send)
  2. Move leads from list → campaign ONLY on explicit human activation

Campaigns CANNOT be created via API — they must be pre-built in HeyReach UI
and their IDs mapped in config/production.json.

Usage:
    python execution/heyreach_dispatcher.py --dry-run
    python execution/heyreach_dispatcher.py --live --tier tier_1
    python execution/heyreach_dispatcher.py --list-campaigns
"""

import os
import re
import sys
import json
import uuid
import asyncio
import argparse
import platform
import logging
import tempfile
import aiohttp
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import quote as url_quote
from dataclasses import dataclass, asdict, field

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console

_is_windows = platform.system() == "Windows"
console = Console(force_terminal=not _is_windows)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("heyreach_dispatcher")


def _atomic_json_write(file_path, data: dict, indent: int = 2) -> None:
    """Write JSON atomically: temp file + os.replace() (HR-02).

    Prevents corruption from crashes mid-write and reduces the race window
    for concurrent read-modify-write operations to a single rename syscall.
    """
    file_path = Path(file_path)
    dir_path = file_path.parent
    fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        os.replace(tmp_path, str(file_path))
    except BaseException:
        # Clean up temp file on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# =============================================================================
# HEYREACH API CLIENT
# =============================================================================

class HeyReachClient:
    """
    Async HeyReach API client.

    API Reference:
    - Base URL: https://api.heyreach.io/api/public
    - Auth: X-API-KEY header
    - Rate limit: 300 req/min
    - Pagination: limit + offset (NOT cursor-based)
    """

    BASE_URL = "https://api.heyreach.io/api/public"

    # HTTP status codes safe to retry
    _RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

    # LinkedIn profile URL pattern (HR-16)
    _LINKEDIN_PROFILE_RE = re.compile(
        r"^https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9\-_.%]+/?$"
    )

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.getenv("HEYREACH_API_KEY", "")
        self._session = None
        self._max_retries = 2  # Default, overridden by config
        # Circuit breaker integration
        try:
            from core.circuit_breaker import get_registry
            self._cb_registry = get_registry()
            self._cb_registry.register("heyreach_api", failure_threshold=5, recovery_timeout=120)
        except ImportError:
            self._cb_registry = None

    async def _get_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={
                    "X-API-KEY": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(
                    total=30,       # Overall cap
                    connect=5,      # Connection timeout (HR-13)
                    sock_read=15,   # Response body read timeout (HR-13)
                ),
            )
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def _request(self, method: str, path: str, max_retries: int = None, **kwargs) -> Dict[str, Any]:
        """Make an API request with retry, circuit breaker, and error discrimination.

        Addresses: HR-04 (retry), HR-08 (error types), HR-10 (circuit breaker),
                   HR-13 (per-step timeout via session), HR-14 (JSON fallback).
        """
        max_retries = max_retries if max_retries is not None else self._max_retries

        # Circuit breaker check (HR-10)
        if self._cb_registry and not self._cb_registry.is_available("heyreach_api"):
            return {"success": False, "error": "Circuit breaker OPEN for heyreach_api", "retryable": False}

        session = await self._get_session()
        url = f"{self.BASE_URL}{path}"
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                async with session.request(method, url, **kwargs) as resp:
                    # JSON parse with fallback (HR-14)
                    try:
                        data = await resp.json()
                    except (aiohttp.ContentTypeError, json.JSONDecodeError):
                        text = await resp.text()
                        data = {"raw_response": text}

                    if resp.status < 400:
                        if self._cb_registry:
                            self._cb_registry.record_success("heyreach_api")
                        return {"success": True, "status": resp.status, "data": data}

                    # HTTP error — classify (HR-08)
                    error_msg = data.get("message", str(data)) if isinstance(data, dict) else str(data)

                    if resp.status in self._RETRYABLE_STATUSES:
                        last_error = f"HTTP {resp.status}: {error_msg}"
                        if resp.status == 429:
                            retry_after = int(resp.headers.get("Retry-After", str(2 ** attempt)))
                            wait = min(retry_after, 60)
                        else:
                            wait = 2 ** attempt
                        if attempt < max_retries:
                            logger.warning("HeyReach %s %s -> %d (attempt %d/%d, retry in %ds)",
                                           method, path, resp.status, attempt + 1, max_retries + 1, wait)
                            await asyncio.sleep(wait)
                            continue

                    # Non-retryable HTTP error or retries exhausted
                    if self._cb_registry:
                        self._cb_registry.record_failure("heyreach_api", error=Exception(error_msg))
                    return {
                        "success": False,
                        "status": resp.status,
                        "error": error_msg,
                        "retryable": resp.status in self._RETRYABLE_STATUSES,
                    }

            except asyncio.TimeoutError:
                last_error = f"Timeout on {method} {path} (attempt {attempt + 1})"
                logger.warning(last_error)
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue

            except aiohttp.ClientError as e:
                last_error = f"Connection error: {e}"
                logger.warning("HeyReach %s %s -> %s (attempt %d/%d)",
                               method, path, e, attempt + 1, max_retries + 1)
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue

            except Exception as e:
                last_error = f"Unexpected error: {e}"
                logger.error("HeyReach %s %s -> unexpected: %s", method, path, e)
                break

        # All retries exhausted
        if self._cb_registry:
            self._cb_registry.record_failure("heyreach_api", error=Exception(last_error or "unknown"))
        return {"success": False, "error": last_error or "unknown error", "retryable": True}

    # --- Authentication ---

    async def check_api_key(self) -> Dict[str, Any]:
        """Verify API key is valid."""
        return await self._request("GET", "/auth/CheckApiKey")

    # --- Campaigns ---

    async def list_campaigns(self, offset: int = 0, limit: int = 50) -> Dict[str, Any]:
        """List all campaigns. POST method (HeyReach convention)."""
        return await self._request("POST", "/campaign/GetAll", json={
            "offset": offset,
            "limit": limit,
        })

    async def get_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Get campaign details."""
        return await self._request("GET", f"/campaign/GetById?campaignId={url_quote(str(campaign_id), safe='')}")

    async def pause_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Pause a running campaign."""
        return await self._request("POST", f"/campaign/Pause?campaignId={url_quote(str(campaign_id), safe='')}")

    async def resume_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """Resume a paused campaign. WARNING: This starts sending."""
        return await self._request("POST", f"/campaign/Resume?campaignId={url_quote(str(campaign_id), safe='')}")

    # --- Lead Lists (SAFE — no auto-send) ---

    async def create_lead_list(self, name: str) -> Dict[str, Any]:
        """Create an empty lead list. Leads in lists don't trigger campaigns."""
        return await self._request("POST", "/list/CreateEmptyList", json={
            "name": name,
        })

    async def add_leads_to_list(self, list_id: str, leads: List[Dict]) -> Dict[str, Any]:
        """
        Add leads to a list (SAFE — does NOT trigger campaigns).

        Each lead needs at minimum:
        - linkedInUrl: LinkedIn profile URL
        - firstName, lastName: Contact name
        - Optional: companyName, title, customUserFields
        """
        return await self._request("POST", "/list/AddLeadsToListV2", json={
            "listId": list_id,
            "leads": leads,
        })

    # --- Leads to Campaign (DANGEROUS — can auto-reactivate) ---

    async def add_leads_to_campaign(self, campaign_id: str, leads: List[Dict]) -> Dict[str, Any]:
        """
        Add leads to a campaign.

        WARNING: Adding leads to a paused/finished campaign will AUTO-REACTIVATE it.
        Use add_leads_to_list() first, then route to campaign via HeyReach UI
        or explicit resume_campaign() after human approval.
        """
        return await self._request("POST", "/campaign/AddLeadsToCampaignV2", json={
            "campaignId": campaign_id,
            "leads": leads,
        })

    # --- LinkedIn Accounts ---

    async def list_linkedin_accounts(self) -> Dict[str, Any]:
        """List connected LinkedIn accounts."""
        return await self._request("POST", "/linkedinaccount/GetAll", json={})

    # --- Stats ---

    async def get_overall_stats(self, campaign_id: str) -> Dict[str, Any]:
        """Get campaign performance stats."""
        return await self._request("POST", "/stats/GetOverallStats", json={
            "campaignId": campaign_id,
        })

    # --- Webhooks ---

    async def create_webhook(self, url: str, event_type: str) -> Dict[str, Any]:
        """Register a webhook endpoint for an event type."""
        return await self._request("POST", "/webhook/Create", json={
            "url": url,
            "eventType": event_type,
        })

    async def list_webhooks(self) -> Dict[str, Any]:
        """List all registered webhooks."""
        return await self._request("POST", "/webhook/GetAll", json={})

    async def delete_webhook(self, webhook_id: str) -> Dict[str, Any]:
        """Delete a webhook."""
        return await self._request("POST", "/webhook/Delete", json={
            "webhookId": webhook_id,
        })


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class HeyReachDispatchResult:
    """Result of a lead list dispatch."""
    list_name: str
    list_id: Optional[str]
    leads_added: int
    tier: str
    shadow_email_ids: List[str]
    status: str  # "dispatched", "dry_run", "error"
    recipient_emails: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class HeyReachDispatchReport:
    """Summary of a HeyReach dispatch run."""
    run_id: str
    started_at: str
    completed_at: str = ""
    dry_run: bool = True
    total_approved: int = 0
    total_dispatched: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    lists_created: List[HeyReachDispatchResult] = field(default_factory=list)
    daily_limit_remaining: int = 0
    errors: List[str] = field(default_factory=list)


# =============================================================================
# DAILY CEILING TRACKER
# =============================================================================

class LinkedInDailyCeiling:
    """Tracks daily LinkedIn outreach volume (HR-03: Redis-backed, distributed).

    Primary: Redis INCRBY for atomic, distributed counting.
    Fallback: Local JSON file when Redis is unavailable.
    Local _state always kept in sync for list naming and audit.
    """

    def __init__(self):
        self.state_file = PROJECT_ROOT / ".hive-mind" / "heyreach_dispatch_state.json"
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state: Dict[str, Any] = {}
        self._redis = None
        self._redis_prefix = ""
        self._init_redis()
        self._load()

    def _init_redis(self):
        """Connect to Redis (matches shadow_queue.py pattern)."""
        try:
            import redis as redis_mod
        except ImportError:
            return
        url = (os.getenv("REDIS_URL") or "").strip()
        if not url:
            return
        try:
            self._redis = redis_mod.Redis.from_url(
                url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2,
            )
            self._redis.ping()
            self._redis_prefix = (
                os.getenv("CONTEXT_REDIS_PREFIX") or os.getenv("STATE_REDIS_PREFIX") or "caio"
            ).strip()
            logger.info("LinkedInDailyCeiling connected to Redis.")
        except Exception as exc:
            logger.warning("LinkedInDailyCeiling Redis connect failed: %s — file fallback.", exc)
            self._redis = None

    def _redis_key(self, suffix: str) -> str:
        return f"{self._redis_prefix}:ceiling:heyreach:{date.today().isoformat()}:{suffix}"

    def _load(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self._state = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._state = {}

        today_str = date.today().isoformat()
        if self._state.get("date") != today_str:
            self._state = {
                "date": today_str,
                "dispatched_count": 0,
                "dispatched_leads": [],
                "lists_created": [],
            }
            self._save()

    def _save(self):
        _atomic_json_write(self.state_file, self._state)

    def _redis_get_count(self) -> Optional[int]:
        """Read today's count from Redis. Returns None if unavailable."""
        if not self._redis:
            return None
        try:
            val = self._redis.get(self._redis_key("count"))
            return int(val) if val is not None else 0
        except Exception as exc:
            logger.warning("Redis ceiling read failed: %s", exc)
            return None

    def get_remaining(self, daily_limit: int) -> int:
        redis_count = self._redis_get_count()
        if redis_count is not None:
            return max(0, daily_limit - redis_count)
        return max(0, daily_limit - self._state.get("dispatched_count", 0))

    def record_dispatch(self, count: int, lead_ids: List[str], list_name: str):
        # Redis: atomic increment (distributed-safe)
        if self._redis:
            try:
                key = self._redis_key("count")
                self._redis.incrby(key, count)
                # 25-hour TTL — generous buffer past midnight rollover
                self._redis.expire(key, 90000)
            except Exception as exc:
                logger.warning("Redis ceiling increment failed: %s — file-only.", exc)

        # Local state: always updated (for list naming + audit)
        self._state["dispatched_count"] = self._state.get("dispatched_count", 0) + count
        self._state["dispatched_leads"].extend(lead_ids)
        self._state["lists_created"].append({
            "name": list_name,
            "leads": count,
            "at": datetime.now(timezone.utc).isoformat(),
        })
        self._save()

    def get_today_count(self) -> int:
        redis_count = self._redis_get_count()
        if redis_count is not None:
            return redis_count
        return self._state.get("dispatched_count", 0)


# =============================================================================
# MAIN DISPATCHER
# =============================================================================

class HeyReachDispatcher:
    """
    Dispatches approved leads to HeyReach lead lists for LinkedIn outreach.

    LEAD-LIST-FIRST PATTERN:
    1. Scan approved shadow emails that have linkedin_url
    2. Filter tier_1 only (LinkedIn reserved for high-value leads)
    3. Create a dated lead list in HeyReach
    4. Add leads to the list (SAFE — no auto-send)
    5. Human reviews list in HeyReach UI → moves to campaign → activates

    This avoids the auto-reactivation gotcha where adding leads to a paused
    campaign silently restarts it.
    """

    # LinkedIn daily limit (connections/day) — conservative to protect account
    DEFAULT_DAILY_LIMIT = 20

    def __init__(self):
        self.shadow_dir = PROJECT_ROOT / ".hive-mind" / "shadow_mode_emails"
        self.dispatch_log = PROJECT_ROOT / ".hive-mind" / "heyreach_dispatch_log.jsonl"
        self.ceiling = LinkedInDailyCeiling()
        self.config = self._load_config()
        self._client = None

    # HR-18: Required config keys for HeyReach dispatcher
    _REQUIRED_CONFIG_KEYS = {
        "external_apis.heyreach.enabled": bool,
    }
    _RECOMMENDED_CONFIG_KEYS = [
        "external_apis.heyreach.retry_attempts",
        "external_apis.heyreach.timeout_seconds",
    ]

    def _load_config(self) -> Dict[str, Any]:
        config_path = PROJECT_ROOT / "config" / "production.json"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            self._validate_config(config)
            return config
        return {}

    def _validate_config(self, config: Dict[str, Any]) -> None:
        """HR-18: Validate config schema at load time — warn on missing keys."""
        for dotted_key, expected_type in self._REQUIRED_CONFIG_KEYS.items():
            parts = dotted_key.split(".")
            val = config
            for part in parts:
                if not isinstance(val, dict):
                    val = None
                    break
                val = val.get(part)
            if val is None:
                logger.warning("HR-18: Required config key '%s' is missing", dotted_key)
            elif not isinstance(val, expected_type):
                logger.warning(
                    "HR-18: Config key '%s' has wrong type: expected %s, got %s",
                    dotted_key, expected_type.__name__, type(val).__name__,
                )
        for dotted_key in self._RECOMMENDED_CONFIG_KEYS:
            parts = dotted_key.split(".")
            val = config
            for part in parts:
                if not isinstance(val, dict):
                    val = None
                    break
                val = val.get(part)
            if val is None:
                logger.info("HR-18: Recommended config key '%s' not set (using defaults)", dotted_key)

    def _is_heyreach_enabled(self) -> bool:
        return self.config.get("external_apis", {}).get("heyreach", {}).get("enabled", False)

    def _get_daily_limit(self) -> int:
        """LinkedIn connection limit — much lower than email."""
        return self.DEFAULT_DAILY_LIMIT

    def _check_emergency_stop(self) -> bool:
        return os.getenv("EMERGENCY_STOP", "false").lower().strip() in ("true", "1", "yes", "on")

    async def _get_client(self) -> HeyReachClient:
        if self._client is None:
            self._client = HeyReachClient()
            # Wire config retry settings (HR-04)
            hr_config = self.config.get("external_apis", {}).get("heyreach", {})
            self._client._max_retries = hr_config.get("retry_attempts", 2)
        return self._client

    # -------------------------------------------------------------------------
    # Lead loading — only leads with LinkedIn URLs
    # -------------------------------------------------------------------------

    def _load_linkedin_eligible(
        self,
        tier_filter: Optional[str] = None,
        approved_shadow_email_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Load approved leads that have LinkedIn URLs and haven't been sent to HeyReach."""
        eligible: List[Dict[str, Any]] = []
        scope_enforced = approved_shadow_email_ids is not None
        approved_scope = {
            str(item).strip()
            for item in (approved_shadow_email_ids or [])
            if str(item).strip()
        }

        if not self.shadow_dir.exists():
            return eligible

        for email_file in sorted(self.shadow_dir.glob("*.json")):
            try:
                with open(email_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Must be approved and not already sent to HeyReach
                if data.get("status") not in ("approved", "dispatched_to_instantly"):
                    continue
                if data.get("sent_via_ghl"):
                    continue
                if data.get("heyreach_list_id"):
                    continue
                if data.get("synthetic"):
                    continue

                shadow_email_id = str(data.get("email_id") or email_file.stem)
                if scope_enforced and shadow_email_id not in approved_scope:
                    continue

                # Must have a valid LinkedIn profile URL (HR-16)
                recipient = data.get("recipient_data", {})
                linkedin_url = recipient.get("linkedin_url", "")
                if not linkedin_url:
                    continue
                if not HeyReachClient._LINKEDIN_PROFILE_RE.match(linkedin_url):
                    logger.warning("Skipping lead %s: invalid LinkedIn URL: %s",
                                   email_file.name, linkedin_url)
                    continue

                # Tier filter
                if tier_filter and data.get("tier") != tier_filter:
                    continue

                data["_file_path"] = str(email_file)
                data["_shadow_email_id"] = shadow_email_id
                eligible.append(data)
            except Exception as e:
                logger.warning("Failed to read %s: %s", email_file.name, e)

        return eligible

    # -------------------------------------------------------------------------
    # Lead mapping
    # -------------------------------------------------------------------------

    def _map_to_heyreach_lead(self, shadow_email: Dict) -> Dict[str, Any]:
        """Map shadow email to HeyReach lead format."""
        recipient = shadow_email.get("recipient_data", {})
        context = shadow_email.get("context", {})

        name = recipient.get("name", "")
        name_parts = name.split(" ", 1) if name else ["", ""]

        return {
            "linkedInUrl": recipient.get("linkedin_url", ""),
            "firstName": name_parts[0],
            "lastName": name_parts[1] if len(name_parts) > 1 else "",
            "companyName": recipient.get("company", ""),
            "customUserFields": [
                {"name": "title", "value": recipient.get("title", "")},
                {"name": "icpScore", "value": str(context.get("icp_score", ""))},
                {"name": "icpTier", "value": context.get("icp_tier", "")},
                {"name": "email", "value": shadow_email.get("to", "")},
                {"name": "shadowEmailId", "value": shadow_email.get("email_id", "")},
                {"name": "source", "value": "caio_pipeline"},
            ],
        }

    def _generate_list_name(self, tier: str) -> str:
        """Generate list name: caio_{tier}_{date}_{variant}."""
        tier_short = tier.replace("tier_", "t")
        date_str = date.today().strftime("%Y%m%d")

        existing = self.ceiling._state.get("lists_created", [])
        prefix = f"caio_{tier_short}_{date_str}"
        same_prefix = [c for c in existing if c.get("name", "").startswith(prefix)]
        variant = f"v{len(same_prefix) + 1}"

        return f"{prefix}_{variant}"

    # -------------------------------------------------------------------------
    # State tracking
    # -------------------------------------------------------------------------

    def _mark_lead_dispatched(self, shadow_email: Dict, list_id: str, list_name: str):
        """Update shadow email file with HeyReach dispatch info."""
        file_path = shadow_email.get("_file_path")
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            data["heyreach_list_id"] = list_id
            data["heyreach_list_name"] = list_name
            data["heyreach_dispatched_at"] = datetime.now(timezone.utc).isoformat()

            _atomic_json_write(file_path, data)
        except Exception as e:
            logger.error("Failed to mark lead as dispatched to HeyReach: %s", e)

    def _log_dispatch(self, result: HeyReachDispatchResult):
        """Append dispatch result to JSONL log (HR-17: atomic line write)."""
        self.dispatch_log.parent.mkdir(parents=True, exist_ok=True)
        try:
            # HR-17: Assemble complete line, write to temp, then atomic rename-append.
            # This prevents partial lines from crash mid-write.
            line = json.dumps(asdict(result), default=str) + "\n"
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self.dispatch_log.parent), suffix=".tmplog"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
                    tmp_f.write(line)
                # Append temp file content to log
                with open(self.dispatch_log, "a", encoding="utf-8") as log_f:
                    log_f.write(Path(tmp_path).read_text(encoding="utf-8"))
                os.unlink(tmp_path)
            except BaseException:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            logger.error("Failed to write HeyReach dispatch log: %s", e)

    # -------------------------------------------------------------------------
    # Main dispatch
    # -------------------------------------------------------------------------

    async def dispatch(
        self,
        tier_filter: Optional[str] = None,
        limit: Optional[int] = None,
        dry_run: bool = True,
        approved_shadow_email_ids: Optional[List[str]] = None,
    ) -> HeyReachDispatchReport:
        """
        Main dispatch: routes LinkedIn-eligible leads to HeyReach lead lists.

        Uses lead-list-first pattern — leads go to a LIST, not directly to a
        campaign. Human reviews in HeyReach UI before activating.
        """
        run_id = f"heyreach_{uuid.uuid4().hex[:8]}"
        report = HeyReachDispatchReport(
            run_id=run_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            dry_run=dry_run,
        )

        # --- SAFETY CHECKS ---

        if self._check_emergency_stop():
            report.errors.append("EMERGENCY_STOP active — HeyReach dispatch blocked")
            report.completed_at = datetime.now(timezone.utc).isoformat()
            return report

        if not self._is_heyreach_enabled() and not dry_run:
            report.errors.append("HeyReach disabled in config/production.json")
            report.completed_at = datetime.now(timezone.utc).isoformat()
            return report

        # API key check
        api_key = os.getenv("HEYREACH_API_KEY", "")
        if not api_key and not dry_run:
            report.errors.append("HEYREACH_API_KEY not set")
            report.completed_at = datetime.now(timezone.utc).isoformat()
            return report

        # Daily ceiling
        daily_limit = limit or self._get_daily_limit()
        remaining = self.ceiling.get_remaining(daily_limit)
        report.daily_limit_remaining = remaining

        if remaining <= 0:
            report.errors.append(
                f"LinkedIn daily limit reached ({self.ceiling.get_today_count()}/{daily_limit})"
            )
            report.completed_at = datetime.now(timezone.utc).isoformat()
            return report

        # --- LOAD LEADS ---

        eligible = self._load_linkedin_eligible(
            tier_filter=tier_filter,
            approved_shadow_email_ids=approved_shadow_email_ids,
        )
        report.total_approved = len(eligible)

        if not eligible:
            console.print("[dim]No LinkedIn-eligible leads to dispatch.[/dim]")
            report.completed_at = datetime.now(timezone.utc).isoformat()
            return report

        # Enforce ceiling
        if len(eligible) > remaining:
            eligible = eligible[:remaining]
            report.total_skipped = report.total_approved - len(eligible)

        # Group by tier
        tier_groups: Dict[str, List[Dict]] = {}
        for lead in eligible:
            tier = lead.get("tier", "tier_3")
            tier_groups.setdefault(tier, []).append(lead)

        # --- DISPATCH PER TIER (to lead lists, NOT campaigns) ---

        for tier, leads in tier_groups.items():
            list_name = self._generate_list_name(tier)

            result = HeyReachDispatchResult(
                list_name=list_name,
                list_id=None,
                leads_added=0,
                tier=tier,
                shadow_email_ids=[l.get("_shadow_email_id", l.get("email_id", "")) for l in leads],
                status="pending",
                recipient_emails=[l.get("to", "") for l in leads if l.get("to")],
            )

            if dry_run:
                result.status = "dry_run"
                result.leads_added = len(leads)
                report.total_dispatched += len(leads)
                console.print(
                    f"[yellow][DRY RUN][/yellow] Would create list "
                    f"'{list_name}' with {len(leads)} leads ({tier})"
                )
            else:
                try:
                    client = await self._get_client()

                    # 1. Create lead list (SAFE)
                    list_result = await client.create_lead_list(list_name)
                    if not list_result.get("success"):
                        raise Exception(f"List creation failed: {list_result.get('error')}")

                    list_id = list_result.get("data", {}).get("id")
                    if not list_id:
                        # Some API responses nest differently
                        list_id = list_result.get("data", {}).get("listId", "")
                    if not list_id:
                        raise Exception("No list ID returned")

                    result.list_id = list_id

                    # 2. Add leads to list (SAFE — no auto-send)
                    heyreach_leads = [self._map_to_heyreach_lead(l) for l in leads]
                    add_result = await client.add_leads_to_list(list_id, heyreach_leads)

                    if not add_result.get("success"):
                        raise Exception(f"Add leads failed: {add_result.get('error')}")

                    # Validate ALL leads were accepted (HR-09)
                    add_data = add_result.get("data", {})
                    added_count = (
                        add_data.get("addedCount")
                        or add_data.get("leadsAdded")
                        or add_data.get("count")
                    )
                    if added_count is not None and int(added_count) < len(heyreach_leads):
                        rejected = len(heyreach_leads) - int(added_count)
                        logger.warning(
                            "HeyReach partial success: %d/%d leads added to '%s' (%d rejected)",
                            int(added_count), len(heyreach_leads), list_name, rejected,
                        )
                        report.errors.append(
                            f"Partial add: {added_count}/{len(heyreach_leads)} leads in '{list_name}'"
                        )

                    actual_added = int(added_count) if added_count is not None else len(heyreach_leads)
                    result.leads_added = actual_added
                    result.status = "dispatched"
                    report.total_dispatched += actual_added

                    # Mark shadow emails
                    for lead in leads:
                        self._mark_lead_dispatched(lead, list_id, list_name)

                    self.ceiling.record_dispatch(
                        len(heyreach_leads),
                        [l.get("_shadow_email_id", l.get("email_id", "")) for l in leads],
                        list_name,
                    )

                    console.print(
                        f"[green]Dispatched[/green] list '{list_name}' "
                        f"({list_id}) with {len(heyreach_leads)} leads ({tier}) "
                        f"[SAFE — list only, not campaign]"
                    )

                    try:
                        from core.alerts import send_info
                        send_info(
                            f"HeyReach List Created: {list_name}",
                            f"{len(heyreach_leads)} leads added to list ({tier}). "
                            f"Review in HeyReach UI before adding to campaign.",
                            metadata={"list_id": list_id, "tier": tier, "leads": len(heyreach_leads)},
                            source="heyreach_dispatcher",
                        )
                    except ImportError:
                        pass

                except Exception as e:
                    result.status = "error"
                    result.error = str(e)
                    report.total_errors += 1
                    report.errors.append(str(e))
                    logger.error("HeyReach dispatch error for %s: %s", list_name, e)

                    try:
                        from core.alerts import send_warning
                        send_warning(
                            f"HeyReach Dispatch Error: {list_name}",
                            str(e),
                            source="heyreach_dispatcher",
                        )
                    except ImportError:
                        pass

            self._log_dispatch(result)
            report.lists_created.append(result)

        report.completed_at = datetime.now(timezone.utc).isoformat()
        report.daily_limit_remaining = self.ceiling.get_remaining(daily_limit)

        if self._client:
            await self._client.close()
            self._client = None

        return report


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="HeyReach LinkedIn Dispatcher")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Simulate without API calls (default)")
    parser.add_argument("--live", action="store_true",
                        help="Actually dispatch (overrides --dry-run)")
    parser.add_argument("--tier", type=str,
                        help="Filter by ICP tier (tier_1, tier_2, tier_3)")
    parser.add_argument("--limit", type=int,
                        help="Override daily limit")
    parser.add_argument("--list-campaigns", action="store_true",
                        help="List HeyReach campaigns")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON")
    args = parser.parse_args()

    if args.list_campaigns:
        async def _list():
            client = HeyReachClient()
            result = await client.list_campaigns()
            print(json.dumps(result, indent=2))
            await client.close()
        asyncio.run(_list())
        return

    dry_run = not args.live
    dispatcher = HeyReachDispatcher()
    report = asyncio.run(dispatcher.dispatch(
        tier_filter=args.tier,
        limit=args.limit,
        dry_run=dry_run,
    ))

    if args.json:
        print(json.dumps(asdict(report), indent=2, default=str))
    else:
        mode = "[DRY RUN]" if dry_run else "[LIVE]"
        console.print(f"\n{mode} HeyReach Dispatch Report: {report.run_id}")
        console.print(f"  LinkedIn-eligible: {report.total_approved}")
        console.print(f"  Dispatched:        {report.total_dispatched}")
        console.print(f"  Skipped:           {report.total_skipped}")
        console.print(f"  Errors:            {report.total_errors}")
        console.print(f"  Daily remaining:   {report.daily_limit_remaining}")
        for r in report.lists_created:
            color = (
                "green" if r.status == "dispatched"
                else "yellow" if r.status == "dry_run"
                else "red"
            )
            console.print(
                f"    [{color}]{r.list_name}[/{color}]: "
                f"{r.leads_added} leads ({r.status})"
            )
        if report.errors:
            for err in report.errors:
                console.print(f"    [red]ERROR: {err}[/red]")


if __name__ == "__main__":
    main()
