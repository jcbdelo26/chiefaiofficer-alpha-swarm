#!/usr/bin/env python3
"""
Unified Health Monitor
======================
Real-time health monitoring for the CAIO RevOps Swarm.

Features:
- Real-time health checks for all agents, integrations, MCP servers, and guardrails
- Metric collection (success rate, latency, error count)
- Alert thresholds and notifications
- Historical metrics storage
- WebSocket server for real-time dashboard updates

Usage:
    from core.unified_health_monitor import HealthMonitor
    
    monitor = HealthMonitor()
    await monitor.start()  # Starts background health checks
    status = monitor.get_health_status()
"""

import os
import sys
import json
import time
import asyncio
import bisect
import httpx
import websockets
from enum import Enum
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, Set, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import logging

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.circuit_breaker import get_registry as get_circuit_registry, CircuitState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# COMPONENT DEFINITIONS
# =============================================================================

COMPONENTS = {
    "agents": [
        "UNIFIED_QUEEN", "HUNTER", "ENRICHER", "SEGMENTOR", "CRAFTER",
        "GATEKEEPER", "SCOUT", "OPERATOR", "COACH", "PIPER",
        "SCHEDULER", "RESEARCHER"
    ],
    "integrations": [
        "ghl", "google_calendar", "gmail", "clay", "supabase", "linkedin"
    ],
    "mcp_servers": [
        "hunter-mcp", "enricher-mcp", "ghl-mcp", "orchestrator-mcp",
        "google-calendar-mcp"
    ],
    "guardrails": [
        "circuit_breakers", "rate_limiters", "permissions"
    ]
}


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"      # All checks passing, <5% error rate
    DEGRADED = "degraded"    # Some issues, 5-20% error rate, or circuit half-open
    UNHEALTHY = "unhealthy"  # Major issues, >20% error rate, or circuit open


@dataclass
class ComponentHealth:
    """Health status for a single component."""
    name: str
    category: str
    status: HealthStatus = HealthStatus.HEALTHY
    last_check: str = ""
    success_count: int = 0
    error_count: int = 0
    total_requests: int = 0
    avg_latency_ms: float = 0
    error_rate: float = 0
    last_error: Optional[str] = None
    circuit_state: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status.value,
            "last_check": self.last_check,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "total_requests": self.total_requests,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "error_rate": round(self.error_rate * 100, 2),
            "last_error": self.last_error,
            "circuit_state": self.circuit_state,
            "metadata": self.metadata
        }


@dataclass
class AlertConfig:
    """Alert configuration."""
    error_rate_warning: float = 0.05  # 5%
    error_rate_critical: float = 0.20  # 20%
    latency_warning_ms: float = 1000
    latency_critical_ms: float = 5000
    consecutive_failures_alert: int = 3


@dataclass
class RateLimitUsage:
    """Rate limit usage tracking."""
    name: str
    current: int = 0
    limit: int = 100
    period: str = "hour"
    reset_at: Optional[str] = None

    @property
    def usage_percent(self) -> float:
        return (self.current / self.limit * 100) if self.limit > 0 else 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "current": self.current,
            "limit": self.limit,
            "period": self.period,
            "usage_percent": round(self.usage_percent, 1),
            "reset_at": self.reset_at
        }


@dataclass
class EmailLimits:
    """Email limit tracking."""
    monthly_sent: int = 0
    monthly_limit: int = 10000
    daily_sent: int = 0
    daily_limit: int = 500
    hourly_sent: int = 0
    hourly_limit: int = 50

    def to_dict(self) -> Dict[str, Any]:
        return {
            "monthly": {"sent": self.monthly_sent, "limit": self.monthly_limit, 
                       "percent": round(self.monthly_sent / self.monthly_limit * 100, 1) if self.monthly_limit > 0 else 0},
            "daily": {"sent": self.daily_sent, "limit": self.daily_limit,
                     "percent": round(self.daily_sent / self.daily_limit * 100, 1) if self.daily_limit > 0 else 0},
            "hourly": {"sent": self.hourly_sent, "limit": self.hourly_limit,
                      "percent": round(self.hourly_sent / self.hourly_limit * 100, 1) if self.hourly_limit > 0 else 0}
        }


@dataclass
class ActionLogEntry:
    """Recent action log entry."""
    timestamp: str
    agent: str
    action: str
    status: str
    details: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LatencyStats:
    """Latency percentile statistics."""
    p50_ms: float = 0
    p95_ms: float = 0
    p99_ms: float = 0
    samples: int = 0
    window_seconds: int = 300  # 5-min rolling window

    def to_dict(self) -> Dict[str, Any]:
        return {
            "p50_ms": round(self.p50_ms, 2),
            "p95_ms": round(self.p95_ms, 2),
            "p99_ms": round(self.p99_ms, 2),
            "samples": self.samples,
            "window_seconds": self.window_seconds
        }


@dataclass
class AlertCondition:
    """Represents an alertable condition."""
    condition_type: str
    component: Optional[str]
    severity: str  # "warning", "critical"
    message: str
    value: float
    threshold: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# HEARTBEAT TRACKER
# =============================================================================

class HeartbeatTracker:
    """Tracks agent heartbeats for liveness detection."""

    def __init__(self, stale_threshold_seconds: float = 60.0):
        self.stale_threshold = stale_threshold_seconds
        self._heartbeats: Dict[str, Tuple[datetime, Optional[Dict[str, Any]]]] = {}

    def record_heartbeat(self, agent_name: str, metadata: Optional[Dict[str, Any]] = None):
        """Record a heartbeat from an agent."""
        self._heartbeats[agent_name] = (datetime.now(timezone.utc), metadata)

    def get_last_heartbeat(self, agent_name: str) -> Optional[datetime]:
        """Get the last heartbeat time for an agent."""
        if agent_name in self._heartbeats:
            return self._heartbeats[agent_name][0]
        return None

    def get_heartbeat_metadata(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Get metadata from the last heartbeat."""
        if agent_name in self._heartbeats:
            return self._heartbeats[agent_name][1]
        return None

    def is_stale(self, agent_name: str) -> bool:
        """Check if an agent is stale (no heartbeat within threshold)."""
        if agent_name not in self._heartbeats:
            return True
        last_hb = self._heartbeats[agent_name][0]
        age = (datetime.now(timezone.utc) - last_hb).total_seconds()
        return age > self.stale_threshold

    def get_stale_agents(self) -> List[str]:
        """Get list of agents that are stale."""
        now = datetime.now(timezone.utc)
        stale = []
        for agent_name, (last_hb, _) in self._heartbeats.items():
            if (now - last_hb).total_seconds() > self.stale_threshold:
                stale.append(agent_name)
        return stale

    def get_all_heartbeats(self) -> Dict[str, Dict[str, Any]]:
        """Get all heartbeat info."""
        now = datetime.now(timezone.utc)
        result = {}
        for agent_name, (last_hb, metadata) in self._heartbeats.items():
            age = (now - last_hb).total_seconds()
            result[agent_name] = {
                "last_heartbeat": last_hb.isoformat(),
                "age_seconds": round(age, 1),
                "is_stale": age > self.stale_threshold,
                "metadata": metadata
            }
        return result


# =============================================================================
# LATENCY TRACKER
# =============================================================================

class LatencyTracker:
    """Tracks latency with percentile calculations using a rolling window."""

    def __init__(self, window_seconds: int = 300):
        self.window_seconds = window_seconds
        self._samples: Dict[str, List[Tuple[datetime, float]]] = defaultdict(list)

    def record_latency(self, component_name: str, latency_ms: float):
        """Record a latency sample for a component."""
        now = datetime.now(timezone.utc)
        samples = self._samples[component_name]
        samples.append((now, latency_ms))
        self._prune_old_samples(component_name)

    def _prune_old_samples(self, component_name: str):
        """Remove samples outside the rolling window."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self.window_seconds)
        samples = self._samples[component_name]
        while samples and samples[0][0] < cutoff:
            samples.pop(0)

    def get_percentiles(self, component_name: str) -> LatencyStats:
        """Calculate p50, p95, p99 for a component."""
        self._prune_old_samples(component_name)
        samples = self._samples[component_name]
        
        if not samples:
            return LatencyStats(window_seconds=self.window_seconds)
        
        latencies = sorted([s[1] for s in samples])
        n = len(latencies)
        
        def percentile(p: float) -> float:
            if n == 1:
                return latencies[0]
            idx = (n - 1) * p
            lower = int(idx)
            upper = min(lower + 1, n - 1)
            frac = idx - lower
            return latencies[lower] * (1 - frac) + latencies[upper] * frac
        
        return LatencyStats(
            p50_ms=percentile(0.50),
            p95_ms=percentile(0.95),
            p99_ms=percentile(0.99),
            samples=n,
            window_seconds=self.window_seconds
        )

    def get_all_stats(self) -> Dict[str, LatencyStats]:
        """Get latency stats for all components."""
        return {name: self.get_percentiles(name) for name in self._samples.keys()}


# =============================================================================
# ALERT MANAGER
# =============================================================================

class AlertManager:
    """Manages alert sending with deduplication."""

    def __init__(self, dedup_window_seconds: float = 300.0):
        self.dedup_window = dedup_window_seconds
        self._sent_alerts: Dict[str, datetime] = {}
        self.slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
        self.twilio_account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        self.twilio_auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        self.twilio_from_number = os.environ.get("TWILIO_FROM_NUMBER")

    def _get_alert_key(self, channel_or_phone: str, message: str) -> str:
        """Generate a deduplication key for an alert."""
        return f"{channel_or_phone}:{hash(message)}"

    def _is_duplicate(self, key: str) -> bool:
        """Check if this alert was sent recently."""
        if key not in self._sent_alerts:
            return False
        elapsed = (datetime.now(timezone.utc) - self._sent_alerts[key]).total_seconds()
        return elapsed < self.dedup_window

    def _mark_sent(self, key: str):
        """Mark an alert as sent."""
        self._sent_alerts[key] = datetime.now(timezone.utc)
        self._cleanup_old_entries()

    def _cleanup_old_entries(self):
        """Remove old entries from dedup cache."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.dedup_window * 2)
        self._sent_alerts = {
            k: v for k, v in self._sent_alerts.items() if v > cutoff
        }

    async def send_slack_alert(
        self,
        channel: str,
        message: str,
        severity: str = "warning"
    ) -> bool:
        """Send a Slack alert via webhook."""
        if not self.slack_webhook_url:
            logger.warning("SLACK_WEBHOOK_URL not configured")
            return False

        key = self._get_alert_key(channel, message)
        if self._is_duplicate(key):
            logger.debug(f"Skipping duplicate alert: {message[:50]}...")
            return False

        color_map = {
            "info": "#36a64f",
            "warning": "#ffcc00",
            "critical": "#ff0000"
        }

        payload = {
            "channel": channel,
            "attachments": [{
                "color": color_map.get(severity, "#808080"),
                "title": f"[{severity.upper()}] Health Alert",
                "text": message,
                "ts": int(datetime.now(timezone.utc).timestamp())
            }]
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.slack_webhook_url,
                    json=payload,
                    timeout=10.0
                )
                if response.status_code == 200:
                    self._mark_sent(key)
                    logger.info(f"Slack alert sent: {message[:50]}...")
                    return True
                else:
                    logger.error(f"Slack webhook failed: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False

    async def send_sms_alert(self, phone: str, message: str) -> bool:
        """Send an SMS alert via Twilio (placeholder implementation)."""
        key = self._get_alert_key(phone, message)
        if self._is_duplicate(key):
            logger.debug(f"Skipping duplicate SMS: {message[:50]}...")
            return False

        if not all([self.twilio_account_sid, self.twilio_auth_token, self.twilio_from_number]):
            logger.warning("Twilio credentials not configured")
            return False

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_account_sid}/Messages.json",
                    auth=(self.twilio_account_sid, self.twilio_auth_token),
                    data={
                        "From": self.twilio_from_number,
                        "To": phone,
                        "Body": message[:160]
                    },
                    timeout=10.0
                )
                if response.status_code in (200, 201):
                    self._mark_sent(key)
                    logger.info(f"SMS alert sent to {phone}")
                    return True
                else:
                    logger.error(f"Twilio API failed: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Failed to send SMS: {e}")
            return False

    async def send_email_alert(self, to_email: str, subject: str, body: str) -> bool:
        """
        Send an email alert (placeholder for SMTP/SendGrid integration).
        
        Day 19: Email alerts for daily summaries.
        """
        # Check for email credentials
        smtp_host = os.environ.get("SMTP_HOST")
        smtp_user = os.environ.get("SMTP_USER")
        smtp_pass = os.environ.get("SMTP_PASSWORD")
        
        if not all([smtp_host, smtp_user, smtp_pass]):
            # Log the alert instead if email not configured
            logger.info(f"[EMAIL ALERT] To: {to_email}, Subject: {subject}")
            logger.info(f"[EMAIL BODY]\n{body[:500]}...")
            return True  # Return True since we logged it
        
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(smtp_host, int(os.environ.get("SMTP_PORT", 587))) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            
            logger.info(f"Email alert sent to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    async def send_daily_summary_email(self, to_emails: List[str]) -> bool:
        """
        Send a daily summary email with system health metrics.
        
        Day 19: Daily email summary of system health.
        """
        status = self.get_health_status()
        score = self.get_system_health_score()
        
        # Build summary
        summary = f"""
CAIO RevOps Swarm - Daily Health Summary
========================================
Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
Overall Health Score: {score}/100
System Status: {status['status'].upper()}

AGENT STATUS
------------
"""
        for agent_name, agent_data in status.get("agents", {}).items():
            summary += f"  {agent_name}: {agent_data['status']} "
            summary += f"(Requests: {agent_data['total_requests']}, "
            summary += f"Error Rate: {agent_data['error_rate']:.1f}%)\n"

        summary += f"""
INTEGRATION STATUS
------------------
"""
        for name, data in status.get("integrations", {}).items():
            summary += f"  {name}: {data['status']}\n"

        summary += f"""
RATE LIMITS
-----------
"""
        for name, data in status.get("rate_limits", {}).items():
            summary += f"  {name}: {data['current']}/{data['limit']} "
            summary += f"({data['usage_percent']:.1f}%)\n"

        summary += f"""
EMAIL LIMITS
------------
  Hourly: {status['email_limits']['hourly']['sent']}/{status['email_limits']['hourly']['limit']}
  Daily: {status['email_limits']['daily']['sent']}/{status['email_limits']['daily']['limit']}
  Monthly: {status['email_limits']['monthly']['sent']}/{status['email_limits']['monthly']['limit']}

RECENT ALERTS ({len(status.get('alerts', []))})
--------------
"""
        for alert in status.get("alerts", [])[-5:]:
            summary += f"  [{alert.get('severity', 'INFO').upper()}] {alert.get('message', '')}\n"

        subject = f"[CAIO Health] Daily Summary - Score: {score}/100 - {status['status'].upper()}"
        
        success_count = 0
        for email in to_emails:
            if await self.send_email_alert(email, subject, summary):
                success_count += 1
        
        return success_count == len(to_emails)


# =============================================================================
# QUEUE DEPTH TRACKER - Day 19
# =============================================================================

@dataclass
class QueueDepthMetric:
    """Tracks depth of a processing queue."""
    name: str
    current_depth: int = 0
    max_depth: int = 1000
    warning_threshold: int = 800
    critical_threshold: int = 950
    total_processed: int = 0
    total_dropped: int = 0
    
    @property
    def usage_percent(self) -> float:
        return (self.current_depth / self.max_depth * 100) if self.max_depth > 0 else 0
    
    @property
    def status(self) -> str:
        if self.current_depth >= self.critical_threshold:
            return "critical"
        elif self.current_depth >= self.warning_threshold:
            return "warning"
        return "healthy"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "current_depth": self.current_depth,
            "max_depth": self.max_depth,
            "usage_percent": round(self.usage_percent, 1),
            "status": self.status,
            "total_processed": self.total_processed,
            "total_dropped": self.total_dropped
        }


class QueueDepthTracker:
    """
    Tracks queue depths for various processing queues.
    
    Day 19: Queue depth monitoring for:
    - Lead processing queue
    - Email outbox queue
    - Enrichment queue
    - Campaign generation queue
    - Escalation queue
    """
    
    def __init__(self):
        self.queues: Dict[str, QueueDepthMetric] = {
            "lead_processing": QueueDepthMetric(name="Lead Processing", max_depth=1000),
            "email_outbox": QueueDepthMetric(name="Email Outbox", max_depth=500),
            "enrichment": QueueDepthMetric(name="Enrichment Queue", max_depth=200),
            "campaign_generation": QueueDepthMetric(name="Campaign Generation", max_depth=100),
            "escalation": QueueDepthMetric(name="Human Escalation", max_depth=50, warning_threshold=30),
            "consensus_voting": QueueDepthMetric(name="Consensus Voting", max_depth=20, warning_threshold=15),
        }
    
    def record_enqueue(self, queue_name: str, count: int = 1):
        """Record items added to a queue."""
        if queue_name in self.queues:
            queue = self.queues[queue_name]
            queue.current_depth = min(queue.current_depth + count, queue.max_depth)
            if queue.current_depth >= queue.max_depth:
                queue.total_dropped += count
    
    def record_dequeue(self, queue_name: str, count: int = 1):
        """Record items removed from a queue."""
        if queue_name in self.queues:
            queue = self.queues[queue_name]
            queue.current_depth = max(0, queue.current_depth - count)
            queue.total_processed += count
    
    def set_depth(self, queue_name: str, depth: int):
        """Set the current depth directly (for external queue monitoring)."""
        if queue_name in self.queues:
            self.queues[queue_name].current_depth = depth
    
    def get_all_depths(self) -> Dict[str, Dict[str, Any]]:
        """Get depth info for all queues."""
        return {name: q.to_dict() for name, q in self.queues.items()}
    
    def get_critical_queues(self) -> List[str]:
        """Get list of queues at critical level."""
        return [name for name, q in self.queues.items() if q.status == "critical"]
    
    def get_warning_queues(self) -> List[str]:
        """Get list of queues at warning level."""
        return [name for name, q in self.queues.items() if q.status == "warning"]


# =============================================================================
# REASONING BANK SIZE TRACKER - Day 19
# =============================================================================

class ReasoningBankMonitor:
    """
    Monitors the size and health of the ReasoningBank.
    
    Day 19: Track:
    - Total entries
    - Memory usage estimate
    - Lookup performance
    - Cache hit rate
    """
    
    def __init__(self, reasoning_bank_path: Optional[Path] = None):
        self.reasoning_bank_path = reasoning_bank_path or (
            PROJECT_ROOT / ".hive-mind" / "reasoning_bank.json"
        )
        self._last_check: Optional[datetime] = None
        self._cached_stats: Dict[str, Any] = {}
        
    def get_stats(self) -> Dict[str, Any]:
        """Get current ReasoningBank statistics."""
        try:
            if not self.reasoning_bank_path.exists():
                return {
                    "exists": False,
                    "entries": 0,
                    "size_bytes": 0,
                    "size_mb": 0,
                    "status": "missing"
                }
            
            # Get file size
            size_bytes = self.reasoning_bank_path.stat().st_size
            size_mb = size_bytes / (1024 * 1024)
            
            # Count entries
            entries = 0
            try:
                with open(self.reasoning_bank_path, "r") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        entries = len(data.get("entries", []))
                    elif isinstance(data, list):
                        entries = len(data)
            except:
                pass
            
            # Determine status
            status = "healthy"
            if size_mb > 50:  # > 50MB is warning
                status = "warning"
            if size_mb > 100:  # > 100MB is critical
                status = "critical"
            
            self._cached_stats = {
                "exists": True,
                "entries": entries,
                "size_bytes": size_bytes,
                "size_mb": round(size_mb, 2),
                "status": status,
                "last_modified": datetime.fromtimestamp(
                    self.reasoning_bank_path.stat().st_mtime, 
                    tz=timezone.utc
                ).isoformat(),
                "checked_at": datetime.now(timezone.utc).isoformat()
            }
            self._last_check = datetime.now(timezone.utc)
            
            return self._cached_stats
            
        except Exception as e:
            return {
                "exists": False,
                "error": str(e),
                "status": "error"
            }


# =============================================================================
# HEALTH MONITOR
# =============================================================================

class HealthMonitor:
    """
    Unified health monitoring system.
    
    Day 19 Features:
    - Heartbeats (30s default interval)
    - Rate limit status tracking
    - Circuit breaker monitoring
    - ReasoningBank size tracking
    - Queue depth monitoring
    - Error rates and latency (p50/p95/p99)
    - Alerts: Slack, SMS, Email (daily summary)
    """

    def __init__(
        self,
        check_interval: float = 30.0,
        metrics_file: Optional[Path] = None,
        websocket_port: int = 8765
    ):
        self.check_interval = check_interval
        self.metrics_file = metrics_file or (PROJECT_ROOT / ".hive-mind" / "health_metrics.json")
        self.websocket_port = websocket_port

        self.alert_config = AlertConfig()
        self.components: Dict[str, ComponentHealth] = {}
        self.rate_limits: Dict[str, RateLimitUsage] = {}
        self.email_limits = EmailLimits()
        self.recent_actions: List[ActionLogEntry] = []
        self.alerts: List[Dict[str, Any]] = []

        # Core trackers
        self.heartbeat_tracker = HeartbeatTracker(stale_threshold_seconds=60.0)
        self.latency_tracker = LatencyTracker(window_seconds=300)
        self.alert_manager = AlertManager(dedup_window_seconds=300.0)
        
        # Day 19: Queue depth and ReasoningBank monitoring
        self.queue_depth_tracker = QueueDepthTracker()
        self.reasoning_bank_monitor = ReasoningBankMonitor()

        self._running = False
        self._check_task: Optional[asyncio.Task] = None
        self._ws_server = None
        self._ws_clients: Set = set()

        self._initialize_components()
        self._load_metrics()

    def _initialize_components(self):
        """Initialize health tracking for all components."""
        for category, names in COMPONENTS.items():
            for name in names:
                key = f"{category}:{name}"
                self.components[key] = ComponentHealth(
                    name=name,
                    category=category,
                    last_check=datetime.now(timezone.utc).isoformat()
                )

        # Initialize rate limits
        self.rate_limits = {
            "ghl_api": RateLimitUsage(name="GHL API", limit=100, period="minute"),
            "email_sending": RateLimitUsage(name="Email Sending", limit=50, period="hour"),
            "linkedin_api": RateLimitUsage(name="LinkedIn API", limit=30, period="minute"),
            "supabase": RateLimitUsage(name="Supabase", limit=1000, period="minute"),
        }

    def _load_metrics(self):
        """Load persisted metrics from file."""
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file, "r") as f:
                    data = json.load(f)
                
                # Restore email limits
                if "email_limits" in data:
                    el = data["email_limits"]
                    self.email_limits = EmailLimits(
                        monthly_sent=el.get("monthly_sent", 0),
                        monthly_limit=el.get("monthly_limit", 10000),
                        daily_sent=el.get("daily_sent", 0),
                        daily_limit=el.get("daily_limit", 500),
                        hourly_sent=el.get("hourly_sent", 0),
                        hourly_limit=el.get("hourly_limit", 50)
                    )

                # Restore component metrics
                for comp_data in data.get("components", []):
                    key = f"{comp_data['category']}:{comp_data['name']}"
                    if key in self.components:
                        self.components[key].success_count = comp_data.get("success_count", 0)
                        self.components[key].error_count = comp_data.get("error_count", 0)
                        self.components[key].total_requests = comp_data.get("total_requests", 0)
                        self.components[key].avg_latency_ms = comp_data.get("avg_latency_ms", 0)

                logger.info(f"Loaded metrics from {self.metrics_file}")
            except Exception as e:
                logger.warning(f"Failed to load metrics: {e}")

    def _save_metrics(self):
        """Persist metrics to file."""
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "components": [c.to_dict() for c in self.components.values()],
            "email_limits": {
                "monthly_sent": self.email_limits.monthly_sent,
                "monthly_limit": self.email_limits.monthly_limit,
                "daily_sent": self.email_limits.daily_sent,
                "daily_limit": self.email_limits.daily_limit,
                "hourly_sent": self.email_limits.hourly_sent,
                "hourly_limit": self.email_limits.hourly_limit,
            },
            "rate_limits": {k: v.to_dict() for k, v in self.rate_limits.items()},
        }

        with open(self.metrics_file, "w") as f:
            json.dump(data, f, indent=2)

    def _calculate_status(self, component: ComponentHealth) -> HealthStatus:
        """Calculate health status based on metrics."""
        # Check circuit breaker state first
        if component.circuit_state == "open":
            return HealthStatus.UNHEALTHY
        if component.circuit_state == "half_open":
            return HealthStatus.DEGRADED

        # Check error rate
        if component.total_requests > 0:
            error_rate = component.error_count / component.total_requests
            if error_rate >= self.alert_config.error_rate_critical:
                return HealthStatus.UNHEALTHY
            if error_rate >= self.alert_config.error_rate_warning:
                return HealthStatus.DEGRADED

        # Check latency
        if component.avg_latency_ms >= self.alert_config.latency_critical_ms:
            return HealthStatus.UNHEALTHY
        if component.avg_latency_ms >= self.alert_config.latency_warning_ms:
            return HealthStatus.DEGRADED

        return HealthStatus.HEALTHY

    async def _run_health_checks(self):
        """Run periodic health checks."""
        while self._running:
            try:
                await self._check_all_components()
                self._save_metrics()
                await self._broadcast_update()
            except Exception as e:
                logger.error(f"Health check error: {e}")

            await asyncio.sleep(self.check_interval)

    async def _check_all_components(self):
        """Check health of all components."""
        now = datetime.now(timezone.utc).isoformat()

        # Get circuit breaker status
        circuit_registry = get_circuit_registry()
        circuit_status = circuit_registry.get_status()

        # Check agents
        for name in COMPONENTS["agents"]:
            key = f"agents:{name}"
            component = self.components[key]
            component.last_check = now

            # Check if agent has a circuit breaker
            breaker_key = f"agent_{name}"
            if breaker_key in circuit_status:
                component.circuit_state = circuit_status[breaker_key]["state"]

            # Calculate error rate
            if component.total_requests > 0:
                component.error_rate = component.error_count / component.total_requests

            component.status = self._calculate_status(component)

        # Check integrations
        for name in COMPONENTS["integrations"]:
            key = f"integrations:{name}"
            component = self.components[key]
            component.last_check = now

            # Map integration to circuit breaker
            breaker_map = {
                "ghl": "ghl_api",
                "linkedin": "linkedin_api",
                "supabase": "supabase",
                "clay": "clay_api",
            }
            breaker_key = breaker_map.get(name)
            if breaker_key and breaker_key in circuit_status:
                component.circuit_state = circuit_status[breaker_key]["state"]
                component.metadata["failure_count"] = circuit_status[breaker_key].get("failure_count", 0)

            component.status = self._calculate_status(component)

        # Check MCP servers
        for name in COMPONENTS["mcp_servers"]:
            key = f"mcp_servers:{name}"
            component = self.components[key]
            component.last_check = now
            component.status = self._calculate_status(component)

        # Check guardrails
        for name in COMPONENTS["guardrails"]:
            key = f"guardrails:{name}"
            component = self.components[key]
            component.last_check = now

            if name == "circuit_breakers":
                open_circuits = sum(1 for s in circuit_status.values() if s["state"] == "open")
                component.metadata["open_count"] = open_circuits
                component.status = HealthStatus.DEGRADED if open_circuits > 0 else HealthStatus.HEALTHY

            component.status = self._calculate_status(component)

    def record_action(
        self,
        component_key: str,
        success: bool,
        latency_ms: float = 0,
        error: Optional[str] = None,
        agent: Optional[str] = None,
        action: Optional[str] = None
    ):
        """Record an action result for a component."""
        if component_key in self.components:
            comp = self.components[component_key]
            comp.total_requests += 1
            if success:
                comp.success_count += 1
            else:
                comp.error_count += 1
                comp.last_error = error

            # Update rolling average latency
            if comp.avg_latency_ms == 0:
                comp.avg_latency_ms = latency_ms
            else:
                comp.avg_latency_ms = (comp.avg_latency_ms * 0.9) + (latency_ms * 0.1)

            comp.error_rate = comp.error_count / comp.total_requests if comp.total_requests > 0 else 0

        # Log recent action
        if agent and action:
            self.recent_actions.insert(0, ActionLogEntry(
                timestamp=datetime.now(timezone.utc).isoformat(),
                agent=agent,
                action=action,
                status="success" if success else "error",
                details=error if not success else None
            ))
            # Keep only last 100 actions
            self.recent_actions = self.recent_actions[:100]

    def record_email_sent(self, count: int = 1):
        """Record emails sent."""
        self.email_limits.hourly_sent += count
        self.email_limits.daily_sent += count
        self.email_limits.monthly_sent += count

    def reset_hourly_email_count(self):
        """Reset hourly email count (call on hour boundary)."""
        self.email_limits.hourly_sent = 0

    def reset_daily_email_count(self):
        """Reset daily email count (call at midnight)."""
        self.email_limits.daily_sent = 0
        self.email_limits.hourly_sent = 0

    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status of all components."""
        agents = {}
        integrations = {}
        mcp_servers = {}
        guardrails = {}

        for key, comp in self.components.items():
            category, name = key.split(":", 1)
            data = comp.to_dict()

            if category == "agents":
                agents[name] = data
            elif category == "integrations":
                integrations[name] = data
            elif category == "mcp_servers":
                mcp_servers[name] = data
            elif category == "guardrails":
                guardrails[name] = data

        # Calculate overall status
        all_statuses = [c.status for c in self.components.values()]
        if any(s == HealthStatus.UNHEALTHY for s in all_statuses):
            overall = HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in all_statuses):
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        return {
            "status": overall.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "health_score": self.get_system_health_score(),
            "agents": agents,
            "integrations": integrations,
            "mcp_servers": mcp_servers,
            "guardrails": guardrails,
            "rate_limits": {k: v.to_dict() for k, v in self.rate_limits.items()},
            "email_limits": self.email_limits.to_dict(),
            # Day 19 additions
            "queue_depths": self.queue_depth_tracker.get_all_depths(),
            "reasoning_bank": self.reasoning_bank_monitor.get_stats(),
            "heartbeats": self.heartbeat_tracker.get_all_heartbeats(),
            "latency_stats": {k: v.to_dict() for k, v in self.latency_tracker.get_all_stats().items()},
            "stale_agents": self.get_stale_agents(),
            "recent_actions": [a.to_dict() for a in self.recent_actions[:20]],
            "alerts": self.alerts[-10:],
        }

    def get_agent_status(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Get status for a specific agent."""
        key = f"agents:{agent_name}"
        if key in self.components:
            return self.components[key].to_dict()
        return None

    def get_metrics_history(self, hours: int = 24) -> Dict[str, Any]:
        """Get historical metrics (placeholder for time-series data)."""
        return {
            "period_hours": hours,
            "components": [c.to_dict() for c in self.components.values()],
            "email_limits": self.email_limits.to_dict(),
            "collected_at": datetime.now(timezone.utc).isoformat()
        }

    def add_alert(self, severity: str, message: str, component: Optional[str] = None):
        """Add an alert."""
        self.alerts.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": severity,
            "message": message,
            "component": component,
        })
        # Keep only last 100 alerts
        self.alerts = self.alerts[-100:]

    # =========================================================================
    # HEARTBEAT METHODS
    # =========================================================================

    def record_heartbeat(self, agent_name: str, metadata: Optional[Dict[str, Any]] = None):
        """Record a heartbeat from an agent."""
        self.heartbeat_tracker.record_heartbeat(agent_name, metadata)

    def get_stale_agents(self) -> List[str]:
        """Get list of agents that haven't sent a heartbeat within threshold."""
        return self.heartbeat_tracker.get_stale_agents()

    # =========================================================================
    # LATENCY METHODS
    # =========================================================================

    def record_latency(self, component_name: str, latency_ms: float):
        """Record a latency sample for percentile tracking."""
        self.latency_tracker.record_latency(component_name, latency_ms)

    def get_latency_percentiles(self, component_name: str) -> LatencyStats:
        """Get p50/p95/p99 latency stats for a component."""
        return self.latency_tracker.get_percentiles(component_name)

    # =========================================================================
    # QUEUE DEPTH METHODS - Day 19
    # =========================================================================

    def record_enqueue(self, queue_name: str, count: int = 1):
        """Record items added to a queue."""
        self.queue_depth_tracker.record_enqueue(queue_name, count)

    def record_dequeue(self, queue_name: str, count: int = 1):
        """Record items removed from a queue."""
        self.queue_depth_tracker.record_dequeue(queue_name, count)

    def get_queue_depths(self) -> Dict[str, Dict[str, Any]]:
        """Get all queue depth metrics."""
        return self.queue_depth_tracker.get_all_depths()

    def get_critical_queues(self) -> List[str]:
        """Get list of queues at critical level."""
        return self.queue_depth_tracker.get_critical_queues()

    # =========================================================================
    # REASONING BANK METHODS - Day 19
    # =========================================================================

    def get_reasoning_bank_stats(self) -> Dict[str, Any]:
        """Get ReasoningBank statistics."""
        return self.reasoning_bank_monitor.get_stats()


    # RATE LIMIT HEALTH
    # =========================================================================

    def get_rate_limit_health(self) -> Dict[str, Any]:
        """Get rate limit health with color-coded warning levels."""
        result = {}
        for key, limit in self.rate_limits.items():
            usage_pct = limit.usage_percent
            if usage_pct < 70:
                color = "green"
                level = "ok"
            elif usage_pct < 90:
                color = "yellow"
                level = "warning"
            else:
                color = "red"
                level = "critical"
            
            result[key] = {
                **limit.to_dict(),
                "color": color,
                "level": level
            }
        return result

    # =========================================================================
    # SYSTEM HEALTH SCORE
    # =========================================================================

    def get_system_health_score(self) -> float:
        """Calculate a composite health score (0-100)."""
        if not self.components:
            return 100.0

        scores = []
        for comp in self.components.values():
            if comp.status == HealthStatus.HEALTHY:
                score = 100
            elif comp.status == HealthStatus.DEGRADED:
                score = 50
            else:
                score = 0
            
            error_penalty = min(comp.error_rate * 100, 50)
            score = max(0, score - error_penalty)
            
            if comp.avg_latency_ms > self.alert_config.latency_critical_ms:
                score = max(0, score - 30)
            elif comp.avg_latency_ms > self.alert_config.latency_warning_ms:
                score = max(0, score - 15)
            
            scores.append(score)
        
        return sum(scores) / len(scores)

    # =========================================================================
    # ALERTABLE CONDITIONS
    # =========================================================================

    def get_alertable_conditions(self) -> List[AlertCondition]:
        """Get all current conditions that warrant alerts."""
        conditions = []

        for key, comp in self.components.items():
            if comp.circuit_state == "open":
                conditions.append(AlertCondition(
                    condition_type="circuit_breaker_open",
                    component=key,
                    severity="critical",
                    message=f"Circuit breaker OPEN for {comp.name}",
                    value=1,
                    threshold=0
                ))

            if comp.error_rate > 0.20:
                conditions.append(AlertCondition(
                    condition_type="high_error_rate",
                    component=key,
                    severity="critical" if comp.error_rate > 0.50 else "warning",
                    message=f"Error rate {comp.error_rate*100:.1f}% for {comp.name}",
                    value=comp.error_rate,
                    threshold=0.20
                ))

            latency_stats = self.latency_tracker.get_percentiles(key)
            if latency_stats.p95_ms > 5000:
                conditions.append(AlertCondition(
                    condition_type="high_latency",
                    component=key,
                    severity="warning",
                    message=f"p95 latency {latency_stats.p95_ms:.0f}ms for {comp.name}",
                    value=latency_stats.p95_ms,
                    threshold=5000
                ))

        stale_agents = self.heartbeat_tracker.get_stale_agents()
        for agent in stale_agents:
            hb_info = self.heartbeat_tracker.get_all_heartbeats().get(agent, {})
            age = hb_info.get("age_seconds", 0)
            if age > 120:
                conditions.append(AlertCondition(
                    condition_type="agent_stale",
                    component=f"agents:{agent}",
                    severity="critical",
                    message=f"Agent {agent} stale for {age:.0f}s",
                    value=age,
                    threshold=120
                ))

        total_error_rate = self._get_total_error_rate()
        if total_error_rate > 0.50:
            conditions.append(AlertCondition(
                condition_type="system_critical",
                component=None,
                severity="critical",
                message=f"System-wide error rate {total_error_rate*100:.1f}%",
                value=total_error_rate,
                threshold=0.50
            ))

        return conditions

    def _get_total_error_rate(self) -> float:
        """Calculate system-wide error rate."""
        total_requests = sum(c.total_requests for c in self.components.values())
        total_errors = sum(c.error_count for c in self.components.values())
        if total_requests == 0:
            return 0.0
        return total_errors / total_requests

    async def process_alerts(self, slack_channel: str = "#alerts", sms_phone: Optional[str] = None):
        """Process all alertable conditions and send notifications."""
        conditions = self.get_alertable_conditions()
        
        for cond in conditions:
            if cond.severity == "critical":
                await self.alert_manager.send_slack_alert(
                    slack_channel, cond.message, "critical"
                )
                if sms_phone and cond.condition_type in ("system_critical", "high_error_rate"):
                    if cond.condition_type == "high_error_rate" and cond.value > 0.50:
                        await self.alert_manager.send_sms_alert(sms_phone, cond.message)
                    elif cond.condition_type == "system_critical":
                        await self.alert_manager.send_sms_alert(sms_phone, cond.message)
            elif cond.severity == "warning":
                await self.alert_manager.send_slack_alert(
                    slack_channel, cond.message, "warning"
                )

    # =========================================================================
    # WEBSOCKET SERVER
    # =========================================================================

    async def _ws_handler(self, websocket, path=None):
        """Handle WebSocket connections."""
        self._ws_clients.add(websocket)
        logger.info(f"WebSocket client connected. Total: {len(self._ws_clients)}")

        try:
            # Send initial status
            await websocket.send(json.dumps({
                "type": "health_update",
                "data": self.get_health_status()
            }))

            # Keep connection alive
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get("type") == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))
                except json.JSONDecodeError:
                    pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._ws_clients.discard(websocket)
            logger.info(f"WebSocket client disconnected. Total: {len(self._ws_clients)}")

    async def _broadcast_update(self):
        """Broadcast health update to all connected clients."""
        if not self._ws_clients:
            return

        message = json.dumps({
            "type": "health_update",
            "data": self.get_health_status()
        })

        disconnected = set()
        for client in self._ws_clients:
            try:
                await client.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)

        self._ws_clients -= disconnected

    async def start(self):
        """Start the health monitor and WebSocket server."""
        if self._running:
            return

        self._running = True

        # Start WebSocket server
        self._ws_server = await websockets.serve(
            self._ws_handler,
            "0.0.0.0",
            self.websocket_port
        )
        logger.info(f"WebSocket server started on port {self.websocket_port}")

        # Start health check loop
        self._check_task = asyncio.create_task(self._run_health_checks())
        logger.info(f"Health monitor started (interval: {self.check_interval}s)")

    async def stop(self):
        """Stop the health monitor."""
        self._running = False

        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass

        if self._ws_server:
            self._ws_server.close()
            await self._ws_server.wait_closed()

        self._save_metrics()
        logger.info("Health monitor stopped")


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_monitor: Optional[HealthMonitor] = None


def get_health_monitor() -> HealthMonitor:
    """Get the global health monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = HealthMonitor()
    return _monitor


# =============================================================================
# CLI
# =============================================================================

async def main():
    """Run the health monitor standalone."""
    monitor = get_health_monitor()

    # Add some sample data for testing
    monitor.record_action("agents:HUNTER", True, 150, agent="HUNTER", action="search_contacts")
    monitor.record_action("agents:ENRICHER", True, 200, agent="ENRICHER", action="enrich_contact")
    monitor.record_action("integrations:ghl", True, 300)
    monitor.record_action("integrations:ghl", False, 0, error="API timeout")
    monitor.record_email_sent(5)

    print("\n" + "=" * 60)
    print("  Unified Health Monitor")
    print("=" * 60)
    print(f"  WebSocket: ws://localhost:8765")
    print(f"  Check interval: 30s")
    print("=" * 60 + "\n")

    await monitor.start()

    try:
        # Keep running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        await monitor.stop()


if __name__ == "__main__":
    asyncio.run(main())
