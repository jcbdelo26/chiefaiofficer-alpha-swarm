#!/usr/bin/env python3
"""
Unified Integration Gateway
============================
Centralizes ALL external API management for the unified swarm.

Architecture:
┌──────────────────────────────────────────────────────────────────┐
│                 UNIFIED INTEGRATION GATEWAY                       │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│  │    GHL     │  │  Google    │  │   Gmail    │  │   Clay     │  │
│  │   Adapter  │  │  Calendar  │  │  Adapter   │  │  Adapter   │  │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│  │  LinkedIn  │  │  Supabase  │  │   Zoom     │  │  Webhook   │  │
│  │   Adapter  │  │  Adapter   │  │  Adapter   │  │  Ingress   │  │
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘  │
└──────────────────────────────────────────────────────────────────┘

Usage:
    from core.unified_integration_gateway import get_gateway
    
    gateway = get_gateway()
    result = await gateway.execute("ghl", "send_email", params, agent="GATEKEEPER")
"""

import os
import sys
import json
import time
import hmac
import hashlib
import asyncio
import logging
import tempfile
import threading
from abc import ABC, abstractmethod
from enum import Enum
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Type, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("integration_gateway")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.circuit_breaker import CircuitBreakerRegistry, get_registry
from core.unified_guardrails import UnifiedGuardrails, ActionType, RiskLevel, ACTION_RISK_LEVELS
from core.trace_envelope import (
    emit_tool_trace,
    get_current_case_id,
    get_current_correlation_id,
)


class IntegrationStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class RateLimitConfig:
    """Rate limit configuration for an integration."""
    per_minute: int = 60
    per_hour: int = 1000
    per_day: int = 10000
    min_delay_ms: int = 100


@dataclass
class AdapterHealth:
    """Health status for an adapter."""
    status: IntegrationStatus = IntegrationStatus.UNKNOWN
    last_check: Optional[str] = None
    latency_ms: float = 0
    error_rate: float = 0
    consecutive_failures: int = 0
    last_error: Optional[str] = None


@dataclass 
class ExecutionResult:
    """Result from gateway execution."""
    success: bool
    integration: str
    action: str
    agent: str
    data: Optional[Any] = None
    error: Optional[str] = None
    latency_ms: float = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


class IntegrationAdapter(ABC):
    """
    Abstract base class for all integration adapters.
    Each external API (GHL, Google Calendar, etc.) has its own adapter.
    """
    
    def __init__(
        self,
        name: str,
        base_url: str,
        rate_limits: Optional[RateLimitConfig] = None,
        api_key_env: Optional[str] = None
    ):
        self.name = name
        self.base_url = base_url
        self.rate_limits = rate_limits or RateLimitConfig()
        self.api_key = os.getenv(api_key_env) if api_key_env else None
        self.health = AdapterHealth()
        self._request_times: List[float] = []
        self._action_counts: Dict[str, int] = defaultdict(int)
        self._error_counts: Dict[str, int] = defaultdict(int)
    
    @abstractmethod
    async def execute(self, action: str, params: Dict[str, Any]) -> Any:
        """Execute an action on this integration."""
        pass
    
    @abstractmethod
    async def health_check(self) -> AdapterHealth:
        """Check health of this integration."""
        pass
    
    def get_actions(self) -> List[str]:
        """Return list of supported actions."""
        return []
    
    async def _execute_with_retry(
        self,
        func: Callable,
        max_retries: int = 3,
        base_delay: float = 1.0
    ) -> Any:
        """Execute with exponential backoff retry."""
        last_error = None
        for attempt in range(max_retries):
            try:
                return await func()
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"{self.name}: Retry {attempt+1}/{max_retries} after {delay}s")
                    await asyncio.sleep(delay)
        raise last_error
    
    def _record_request(self, success: bool, latency_ms: float = 0):
        """Record request metrics."""
        now = time.time()
        self._request_times.append(now)
        self._request_times = [t for t in self._request_times if now - t < 3600]
        
        if success:
            self.health.consecutive_failures = 0
        else:
            self.health.consecutive_failures += 1
            self._error_counts[datetime.utcnow().strftime("%Y-%m-%d-%H")] += 1
        
        self.health.latency_ms = latency_ms
        self.health.last_check = datetime.utcnow().isoformat()


class GHLAdapter(IntegrationAdapter):
    """GoHighLevel API adapter."""
    
    def __init__(self):
        super().__init__(
            name="ghl",
            base_url="https://rest.gohighlevel.com/v1",
            rate_limits=RateLimitConfig(per_minute=30, per_hour=150, per_day=3000),
            api_key_env="GHL_API_KEY"
        )
        self._actions = [
            "read_contact", "create_contact", "update_contact",
            "send_email", "send_sms", "add_tag", "remove_tag",
            "trigger_workflow", "read_pipeline", "update_opportunity"
        ]
    
    def get_actions(self) -> List[str]:
        return self._actions
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Any:
        start = time.time()
        try:
            # Placeholder - actual implementation calls GHL API
            result = {"action": action, "status": "executed", "params": params}
            self._record_request(True, (time.time() - start) * 1000)
            return result
        except Exception as e:
            self._record_request(False, (time.time() - start) * 1000)
            self.health.last_error = str(e)
            raise
    
    async def health_check(self) -> AdapterHealth:
        try:
            start = time.time()
            # Simple health check - would call /v1/custom-values or similar
            await asyncio.sleep(0.01)  # Simulate API call
            latency = (time.time() - start) * 1000
            
            self.health.status = IntegrationStatus.HEALTHY
            self.health.latency_ms = latency
            self.health.last_check = datetime.utcnow().isoformat()
        except Exception as e:
            self.health.status = IntegrationStatus.UNHEALTHY
            self.health.last_error = str(e)
        
        return self.health


class GoogleCalendarAdapter(IntegrationAdapter):
    """Google Calendar API adapter."""
    
    def __init__(self):
        super().__init__(
            name="google_calendar",
            base_url="https://www.googleapis.com/calendar/v3",
            rate_limits=RateLimitConfig(per_minute=100, per_hour=1000, per_day=10000),
            api_key_env="GOOGLE_CALENDAR_API_KEY"
        )
        self._actions = [
            "get_availability", "create_event", "update_event", 
            "delete_event", "get_events", "find_available_slots"
        ]
    
    def get_actions(self) -> List[str]:
        return self._actions
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Any:
        start = time.time()
        try:
            result = {"action": action, "status": "executed", "params": params}
            self._record_request(True, (time.time() - start) * 1000)
            return result
        except Exception as e:
            self._record_request(False, (time.time() - start) * 1000)
            self.health.last_error = str(e)
            raise
    
    async def health_check(self) -> AdapterHealth:
        try:
            self.health.status = IntegrationStatus.HEALTHY
            self.health.last_check = datetime.utcnow().isoformat()
        except Exception as e:
            self.health.status = IntegrationStatus.UNHEALTHY
            self.health.last_error = str(e)
        return self.health


class GmailAdapter(IntegrationAdapter):
    """Gmail API adapter."""
    
    def __init__(self):
        super().__init__(
            name="gmail",
            base_url="https://gmail.googleapis.com/gmail/v1",
            rate_limits=RateLimitConfig(per_minute=60, per_hour=500, per_day=2000),
            api_key_env="GMAIL_API_KEY"
        )
        self._actions = [
            "send_email", "get_thread", "parse_thread", 
            "extract_intent", "list_messages", "get_message"
        ]
    
    def get_actions(self) -> List[str]:
        return self._actions
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Any:
        start = time.time()
        try:
            result = {"action": action, "status": "executed", "params": params}
            self._record_request(True, (time.time() - start) * 1000)
            return result
        except Exception as e:
            self._record_request(False, (time.time() - start) * 1000)
            self.health.last_error = str(e)
            raise
    
    async def health_check(self) -> AdapterHealth:
        self.health.status = IntegrationStatus.HEALTHY
        self.health.last_check = datetime.utcnow().isoformat()
        return self.health


class ClayAdapter(IntegrationAdapter):
    """Clay enrichment API adapter."""
    
    def __init__(self):
        super().__init__(
            name="clay",
            base_url="https://api.clay.com/v1",
            rate_limits=RateLimitConfig(per_minute=60, per_hour=500, per_day=5000),
            api_key_env="CLAY_API_KEY"
        )
        self._actions = ["enrich_contact", "enrich_company", "get_workbook_data"]
        self._enricher: Optional["ClayDirectEnrichment"] = None
    
    def _get_enricher(self) -> "ClayDirectEnrichment":
        """Lazy load ClayDirectEnrichment to avoid circular imports."""
        if self._enricher is None:
            from core.clay_direct_enrichment import ClayDirectEnrichment
            self._enricher = ClayDirectEnrichment()
        return self._enricher
    
    def get_actions(self) -> List[str]:
        return self._actions
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Any:
        start = time.time()
        try:
            enricher = self._get_enricher()
            
            if action == "enrich_contact":
                email = params.get("email")
                if not email:
                    raise ValueError("email is required for enrich_contact")
                visitor_data = {
                    "visitor_id": params.get("visitor_id", f"contact_{email}"),
                    "email": email,
                    "first_name": params.get("first_name"),
                    "last_name": params.get("last_name"),
                    "company": {
                        "name": params.get("company_name"),
                        "domain": params.get("company_domain")
                    }
                }
                result = await enricher.enrich_visitor(visitor_data)
                result_data = {
                    "request_id": result.request_id,
                    "status": result.status.value,
                    "email": result.email,
                    "first_name": result.first_name,
                    "last_name": result.last_name,
                    "job_title": result.job_title,
                    "company_name": result.company_name,
                    "company_domain": result.company_domain,
                    "icp_fit_score": result.icp_fit_score,
                    "priority_tier": result.priority_tier
                }
            
            elif action == "enrich_company":
                domain = params.get("domain")
                if not domain:
                    raise ValueError("domain is required for enrich_company")
                visitor_data = {
                    "visitor_id": f"company_{domain}",
                    "company": {
                        "name": params.get("company_name"),
                        "domain": domain
                    }
                }
                result = await enricher.enrich_visitor(visitor_data)
                result_data = {
                    "request_id": result.request_id,
                    "status": result.status.value,
                    "company_name": result.company_name,
                    "company_domain": result.company_domain,
                    "company_industry": result.company_industry,
                    "company_size": result.company_size,
                    "company_revenue": result.company_revenue,
                    "icp_fit_score": result.icp_fit_score,
                    "priority_tier": result.priority_tier
                }
            
            elif action == "get_workbook_data":
                status = enricher.get_status()
                result_data = {
                    "action": action,
                    "status": "executed",
                    "workbook_status": status
                }
            
            else:
                raise ValueError(f"Unknown action: {action}")
            
            self._record_request(True, (time.time() - start) * 1000)
            return result_data
        except Exception as e:
            self._record_request(False, (time.time() - start) * 1000)
            self.health.last_error = str(e)
            raise
    
    async def health_check(self) -> AdapterHealth:
        try:
            enricher = self._get_enricher()
            status = enricher.get_status()
            self.health.status = IntegrationStatus.HEALTHY if status.get("webhook_configured") else IntegrationStatus.DEGRADED
            self.health.last_check = datetime.utcnow().isoformat()
        except Exception as e:
            self.health.status = IntegrationStatus.UNHEALTHY
            self.health.last_error = str(e)
        return self.health


class LinkedInAdapter(IntegrationAdapter):
    """LinkedIn via ProxyCurl adapter."""
    
    def __init__(self):
        super().__init__(
            name="linkedin",
            base_url="https://nubela.co/proxycurl/api/v2",
            rate_limits=RateLimitConfig(per_minute=10, per_hour=100, per_day=1000),
            api_key_env="PROXYCURL_API_KEY"
        )
        self._actions = ["get_profile", "get_company", "search_people", "get_connections"]
    
    def get_actions(self) -> List[str]:
        return self._actions
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Any:
        start = time.time()
        try:
            result = {"action": action, "status": "executed", "params": params}
            self._record_request(True, (time.time() - start) * 1000)
            return result
        except Exception as e:
            self._record_request(False, (time.time() - start) * 1000)
            raise
    
    async def health_check(self) -> AdapterHealth:
        self.health.status = IntegrationStatus.HEALTHY
        self.health.last_check = datetime.utcnow().isoformat()
        return self.health


class SupabaseAdapter(IntegrationAdapter):
    """Supabase database adapter."""
    
    def __init__(self):
        super().__init__(
            name="supabase",
            base_url=os.getenv("SUPABASE_URL", "https://your-project.supabase.co"),
            rate_limits=RateLimitConfig(per_minute=500, per_hour=5000, per_day=50000),
            api_key_env="SUPABASE_KEY"
        )
        self._actions = ["query", "insert", "update", "delete", "upsert", "rpc"]
    
    def get_actions(self) -> List[str]:
        return self._actions
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Any:
        start = time.time()
        try:
            result = {"action": action, "status": "executed", "params": params}
            self._record_request(True, (time.time() - start) * 1000)
            return result
        except Exception as e:
            self._record_request(False, (time.time() - start) * 1000)
            raise
    
    async def health_check(self) -> AdapterHealth:
        self.health.status = IntegrationStatus.HEALTHY
        self.health.last_check = datetime.utcnow().isoformat()
        return self.health


class ZoomAdapter(IntegrationAdapter):
    """Zoom API adapter for meeting links."""
    
    def __init__(self):
        super().__init__(
            name="zoom",
            base_url="https://api.zoom.us/v2",
            rate_limits=RateLimitConfig(per_minute=30, per_hour=200, per_day=2000),
            api_key_env="ZOOM_API_KEY"
        )
        self._actions = ["create_meeting", "update_meeting", "delete_meeting", "get_meeting"]
    
    def get_actions(self) -> List[str]:
        return self._actions
    
    async def execute(self, action: str, params: Dict[str, Any]) -> Any:
        start = time.time()
        try:
            result = {"action": action, "status": "executed", "params": params}
            self._record_request(True, (time.time() - start) * 1000)
            return result
        except Exception as e:
            self._record_request(False, (time.time() - start) * 1000)
            raise
    
    async def health_check(self) -> AdapterHealth:
        self.health.status = IntegrationStatus.HEALTHY
        self.health.last_check = datetime.utcnow().isoformat()
        return self.health


@dataclass
class WebhookEvent:
    """Incoming webhook event."""
    source: str
    event_type: str
    payload: Dict[str, Any]
    signature: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    processed: bool = False


class WebhookIngress:
    """
    Centralized webhook handler for all integrations.
    Routes incoming webhooks to appropriate handlers.
    """
    
    def __init__(self):
        self._handlers: Dict[str, Dict[str, Callable]] = defaultdict(dict)
        self._secrets: Dict[str, str] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._processed_count = 0
    
    def register_handler(self, source: str, event_type: str, handler: Callable):
        """Register a handler for a webhook event type."""
        self._handlers[source][event_type] = handler
        logger.info(f"Registered webhook handler: {source}/{event_type}")
    
    def set_secret(self, source: str, secret: str):
        """Set HMAC secret for a webhook source."""
        self._secrets[source] = secret
    
    def validate_signature(self, source: str, payload: bytes, signature: str) -> bool:
        """Validate webhook signature using HMAC."""
        secret = self._secrets.get(source)
        if not secret:
            return True  # No secret configured, skip validation
        
        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(f"sha256={expected}", signature)
    
    async def process(self, event: WebhookEvent) -> bool:
        """Process a webhook event."""
        handler = self._handlers.get(event.source, {}).get(event.event_type)
        if not handler:
            handler = self._handlers.get(event.source, {}).get("*")
        
        if handler:
            try:
                await handler(event.payload)
                event.processed = True
                self._processed_count += 1
                return True
            except Exception as e:
                logger.error(f"Webhook handler error: {e}")
                return False
        
        logger.warning(f"No handler for webhook: {event.source}/{event.event_type}")
        return False
    
    async def enqueue(self, event: WebhookEvent):
        """Add event to processing queue."""
        await self._queue.put(event)
    
    async def process_queue(self):
        """Process queued webhooks."""
        while True:
            event = await self._queue.get()
            await self.process(event)
            self._queue.task_done()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get webhook processing stats."""
        return {
            "queue_size": self._queue.qsize(),
            "processed_count": self._processed_count,
            "registered_handlers": {
                source: list(handlers.keys()) 
                for source, handlers in self._handlers.items()
            }
        }


class UnifiedIntegrationGateway:
    """
    Centralized gateway for ALL external API integrations.
    
    Features:
    - Dynamic adapter registration
    - Centralized circuit breakers
    - Per-adapter rate limiting
    - Unified audit trail
    - Health aggregation
    - Guardrails integration
    """
    
    def __init__(self):
        self._adapters: Dict[str, IntegrationAdapter] = {}
        self._circuit_registry = get_registry()
        self._guardrails = UnifiedGuardrails()
        self._webhook_ingress = WebhookIngress()
        
        self._hive_mind = PROJECT_ROOT / ".hive-mind"
        self._hive_mind.mkdir(exist_ok=True)
        self._audit_file = self._hive_mind / "integration_audit.json"
        self._audit_lock = threading.RLock()
        
        # Register default adapters
        self._register_default_adapters()
        
        logger.info("Unified Integration Gateway initialized")
    
    def _register_default_adapters(self):
        """Register all default adapters."""
        adapters = [
            GHLAdapter(),
            GoogleCalendarAdapter(),
            GmailAdapter(),
            ClayAdapter(),
            LinkedInAdapter(),
            SupabaseAdapter(),
            ZoomAdapter(),
        ]
        for adapter in adapters:
            self.register_adapter(adapter)
    
    def register_adapter(self, adapter: IntegrationAdapter):
        """Register an integration adapter."""
        self._adapters[adapter.name] = adapter
        self._circuit_registry.register(
            f"integration_{adapter.name}",
            failure_threshold=3,
            recovery_timeout=300
        )
        logger.info(f"Registered adapter: {adapter.name}")
    
    def unregister_adapter(self, name: str):
        """Unregister an integration adapter."""
        if name in self._adapters:
            del self._adapters[name]
            logger.info(f"Unregistered adapter: {name}")
    
    def get_adapter(self, name: str) -> Optional[IntegrationAdapter]:
        """Get an adapter by name."""
        return self._adapters.get(name)
    
    def _check_rate_limit(self, adapter: IntegrationAdapter) -> Tuple[bool, Optional[str]]:
        """Check if request is within rate limits."""
        now = time.time()
        recent = [t for t in adapter._request_times if now - t < 60]
        
        if len(recent) >= adapter.rate_limits.per_minute:
            return False, f"Rate limit exceeded: {adapter.rate_limits.per_minute}/min"
        
        hourly = [t for t in adapter._request_times if now - t < 3600]
        if len(hourly) >= adapter.rate_limits.per_hour:
            return False, f"Rate limit exceeded: {adapter.rate_limits.per_hour}/hour"
        
        return True, None
    
    def _log_audit(self, result: ExecutionResult):
        """Log execution to audit trail."""
        try:
            with self._audit_lock:
                audit = {"entries": []}
                if self._audit_file.exists():
                    try:
                        audit = json.loads(self._audit_file.read_text(encoding="utf-8"))
                    except Exception as exc:
                        logger.warning("Integration audit file read failed, resetting file: %s", exc)
                        audit = {"entries": []}
                
                audit["entries"].append(asdict(result))
                audit["entries"] = audit["entries"][-10000:]  # Keep last 10k
                audit["last_updated"] = datetime.utcnow().isoformat()
                
                fd = None
                temp_path = None
                try:
                    fd, temp_path = tempfile.mkstemp(
                        suffix=".json",
                        prefix="integration_audit_",
                        dir=str(self._audit_file.parent),
                    )
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        fd = None
                        json.dump(audit, f, indent=2, default=str)
                    os.replace(temp_path, self._audit_file)
                    temp_path = None
                finally:
                    if fd is not None:
                        os.close(fd)
                    if temp_path and os.path.exists(temp_path):
                        try:
                            os.unlink(temp_path)
                        except OSError:
                            pass
        except Exception as e:
            logger.error(f"Audit log error: {e}")
    
    def _emit_execution_trace(
        self,
        *,
        result: ExecutionResult,
        params: Dict[str, Any],
        correlation_id: Optional[str],
        case_id: Optional[str],
        error_code: Optional[str] = None,
    ) -> None:
        """Emit standardized tool trace for gateway execution."""
        context_refs: List[str] = []
        refs = params.get("retrieved_context_refs")
        if isinstance(refs, list):
            context_refs = [str(v) for v in refs]
        
        try:
            emit_tool_trace(
                correlation_id=correlation_id,
                case_id=case_id,
                agent=result.agent,
                tool_name=f"UnifiedIntegrationGateway.execute:{result.integration}.{result.action}",
                tool_input=params,
                tool_output=result.data if result.success else {"error": result.error},
                retrieved_context_refs=context_refs,
                status="success" if result.success else "failure",
                duration_ms=result.latency_ms,
                error_code=error_code,
                error_message=result.error,
            )
        except Exception as exc:
            logger.warning("Trace emission failed for gateway execution: %s", exc)
    
    async def execute(
        self,
        integration: str,
        action: str,
        params: Dict[str, Any],
        agent: str = "UNKNOWN",
        grounding_evidence: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """
        Execute an action through the gateway.
        
        Args:
            integration: Name of the integration (ghl, google_calendar, etc.)
            action: Action to perform
            params: Parameters for the action
            agent: Name of the requesting agent
            grounding_evidence: Required for high-risk actions
        
        Returns:
            ExecutionResult with success/failure details
        """
        start = time.time()
        params = params or {}
        correlation_id = get_current_correlation_id()
        case_id = get_current_case_id()
        if not case_id:
            candidate_case_id = params.get("case_id") or params.get("replay_case_id")
            if candidate_case_id:
                case_id = str(candidate_case_id)
        
        def finalize(result: ExecutionResult, error_code: Optional[str] = None) -> ExecutionResult:
            if result.latency_ms <= 0:
                result.latency_ms = (time.time() - start) * 1000
            self._log_audit(result)
            self._emit_execution_trace(
                result=result,
                params=params,
                correlation_id=correlation_id,
                case_id=case_id,
                error_code=error_code,
            )
            return result
        
        # Get adapter
        adapter = self._adapters.get(integration)
        if not adapter:
            return finalize(ExecutionResult(
                success=False,
                integration=integration,
                action=action,
                agent=agent,
                error=f"Unknown integration: {integration}",
                latency_ms=(time.time() - start) * 1000,
            ), "UNKNOWN_INTEGRATION")
        
        # Check circuit breaker
        breaker_key = f"integration_{integration}"
        if not self._circuit_registry.is_available(breaker_key):
            return finalize(ExecutionResult(
                success=False,
                integration=integration,
                action=action,
                agent=agent,
                error=f"Circuit breaker OPEN for {integration}",
                latency_ms=(time.time() - start) * 1000,
            ), "CIRCUIT_OPEN")
        
        # Check rate limits
        allowed, reason = self._check_rate_limit(adapter)
        if not allowed:
            return finalize(ExecutionResult(
                success=False,
                integration=integration,
                action=action,
                agent=agent,
                error=reason,
                latency_ms=(time.time() - start) * 1000,
            ), "RATE_LIMIT_EXCEEDED")
        
        # Map to ActionType for guardrails if applicable
        action_type_map = {
            "send_email": ActionType.SEND_EMAIL,
            "send_sms": ActionType.SEND_SMS,
            "create_contact": ActionType.CREATE_CONTACT,
            "update_contact": ActionType.UPDATE_CONTACT,
            "create_event": ActionType.CREATE_CALENDAR_EVENT,
            "trigger_workflow": ActionType.TRIGGER_WORKFLOW,
        }
        
        action_type = action_type_map.get(action)
        if action_type:
            risk = ACTION_RISK_LEVELS.get(action_type, RiskLevel.LOW)
            if risk in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
                valid, reason = self._guardrails.validate_action(
                    agent, action_type, grounding_evidence
                )
                if not valid:
                    return finalize(ExecutionResult(
                        success=False,
                        integration=integration,
                        action=action,
                        agent=agent,
                        error=f"Guardrails blocked: {reason}",
                        latency_ms=(time.time() - start) * 1000,
                    ), "GUARDRAIL_BLOCKED")
        
        # Execute action
        try:
            result_data = await adapter.execute(action, params)
            self._circuit_registry.record_success(breaker_key)
            
            result = ExecutionResult(
                success=True,
                integration=integration,
                action=action,
                agent=agent,
                data=result_data,
                latency_ms=(time.time() - start) * 1000
            )
        except Exception as e:
            self._circuit_registry.record_failure(breaker_key, e)
            
            result = ExecutionResult(
                success=False,
                integration=integration,
                action=action,
                agent=agent,
                error=str(e),
                latency_ms=(time.time() - start) * 1000
            )
            return finalize(result, "ADAPTER_EXECUTION_ERROR")
        
        return finalize(result)
    
    async def health_check_all(self) -> Dict[str, AdapterHealth]:
        """Run health check on all adapters."""
        results = {}
        for name, adapter in self._adapters.items():
            results[name] = await adapter.health_check()
        return results
    
    def get_status(self) -> Dict[str, Any]:
        """Get overall gateway status."""
        adapters_status = {}
        for name, adapter in self._adapters.items():
            breaker_key = f"integration_{name}"
            adapters_status[name] = {
                "health": adapter.health.status.value,
                "latency_ms": adapter.health.latency_ms,
                "circuit_state": self._circuit_registry.get_status().get(breaker_key, {}).get("state", "unknown"),
                "request_count_hour": len([
                    t for t in adapter._request_times 
                    if time.time() - t < 3600
                ]),
                "actions": adapter.get_actions()
            }
        
        return {
            "integrations": adapters_status,
            "webhook_stats": self._webhook_ingress.get_stats(),
            "updated_at": datetime.utcnow().isoformat()
        }
    
    @property
    def webhook_ingress(self) -> WebhookIngress:
        """Get webhook ingress handler."""
        return self._webhook_ingress


# Singleton instance
_gateway: Optional[UnifiedIntegrationGateway] = None


def get_gateway() -> UnifiedIntegrationGateway:
    """Get or create the global gateway instance."""
    global _gateway
    if _gateway is None:
        _gateway = UnifiedIntegrationGateway()
    return _gateway


async def demo():
    """Demonstrate unified integration gateway."""
    print("\n" + "=" * 60)
    print("UNIFIED INTEGRATION GATEWAY - Demo")
    print("=" * 60)
    
    gateway = get_gateway()
    
    # Show registered integrations
    print("\n[Registered Integrations]")
    status = gateway.get_status()
    for name, info in status["integrations"].items():
        print(f"  - {name}: {info['circuit_state']} ({len(info['actions'])} actions)")
    
    # Execute some actions
    print("\n[Executing Actions]")
    
    result = await gateway.execute(
        integration="ghl",
        action="read_contact",
        params={"contact_id": "test_123"},
        agent="HUNTER"
    )
    print(f"  GHL read_contact: {'✅' if result.success else '❌'} ({result.latency_ms:.2f}ms)")
    
    result = await gateway.execute(
        integration="google_calendar",
        action="get_availability",
        params={"calendar_id": "primary", "start": "2026-01-22", "end": "2026-01-23"},
        agent="SCHEDULER"
    )
    print(f"  Calendar availability: {'✅' if result.success else '❌'} ({result.latency_ms:.2f}ms)")
    
    # Try high-risk action without grounding (should fail)
    result = await gateway.execute(
        integration="ghl",
        action="send_email",
        params={"contact_id": "123", "subject": "Test"},
        agent="GATEKEEPER"
    )
    print(f"  Send email (no grounding): {'✅' if result.success else '❌'} - {result.error or 'OK'}")
    
    # With grounding evidence
    result = await gateway.execute(
        integration="ghl",
        action="send_email",
        params={"contact_id": "123", "subject": "Test"},
        agent="GATEKEEPER",
        grounding_evidence={
            "source": "supabase",
            "data_id": "lead_123",
            "verified_at": datetime.utcnow().isoformat()
        }
    )
    print(f"  Send email (with grounding): {'✅' if result.success else '❌'}")
    
    # Health check
    print("\n[Health Check]")
    health = await gateway.health_check_all()
    for name, h in health.items():
        print(f"  {name}: {h.status.value}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(demo())
