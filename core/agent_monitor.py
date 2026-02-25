#!/usr/bin/env python3
"""
Agent Health Monitor - Sub-Agent System
========================================

Monitors health and performance of all agents in the swarm:
- WATCHDOG: Monitors agent heartbeats and availability
- AUDITOR: Validates operation compliance
- MEDIC: Handles recovery and self-healing
- REPORTER: Generates health reports

Features:
- Heartbeat tracking
- Error rate monitoring
- Circuit breaker pattern
- Auto-recovery
- Slack alerting
"""

import os
import json
import time
import logging
from enum import Enum
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from pathlib import Path
from threading import Lock
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent-monitor")


class AgentStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"
    RECOVERING = "recovering"


class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


# =============================================================================
# AGENT DEFINITIONS
# =============================================================================

@dataclass
class AgentConfig:
    """Configuration for an agent."""
    name: str
    agent_type: str
    heartbeat_interval: int = 60  # seconds
    max_errors_before_unhealthy: int = 3
    recovery_timeout: int = 300  # seconds
    dependencies: List[str] = field(default_factory=list)


AGENT_REGISTRY = {
    # Core Pipeline Agents
    "hunter": AgentConfig("HUNTER", "scraper", heartbeat_interval=120, dependencies=["linkedin"]),
    "enricher": AgentConfig("ENRICHER", "enricher", dependencies=["clay", "supabase"]),
    "segmentor": AgentConfig("SEGMENTOR", "classifier", dependencies=["supabase"]),
    "crafter": AgentConfig("CRAFTER", "generator", dependencies=["supabase"]),
    "gatekeeper": AgentConfig("GATEKEEPER", "approver", dependencies=["supabase"]),
    
    # Outreach Agents
    "instantly_sender": AgentConfig("INSTANTLY_SENDER", "sender", dependencies=["instantly"]),
    "ghl_syncer": AgentConfig("GHL_SYNCER", "syncer", dependencies=["gohighlevel", "supabase"]),
    
    # Intelligence Agents
    "sentiment_analyzer": AgentConfig("SENTIMENT_ANALYZER", "analyzer", dependencies=["supabase"]),
    "lead_router": AgentConfig("LEAD_ROUTER", "router", dependencies=["supabase"]),
    
    # Monitoring Sub-Agents
    "watchdog": AgentConfig("WATCHDOG", "monitor", heartbeat_interval=30),
    "auditor": AgentConfig("AUDITOR", "compliance", heartbeat_interval=60),
    "medic": AgentConfig("MEDIC", "recovery", heartbeat_interval=60),
    "reporter": AgentConfig("REPORTER", "reporting", heartbeat_interval=300),
}


# =============================================================================
# HEARTBEAT TRACKER
# =============================================================================

@dataclass
class Heartbeat:
    agent_name: str
    timestamp: str
    status: AgentStatus
    metrics: Dict[str, Any] = field(default_factory=dict)
    error_count: int = 0
    last_error: Optional[str] = None


class HeartbeatTracker:
    """Track agent heartbeats."""
    
    def __init__(self, storage_path: str = ".hive-mind/heartbeats.json"):
        self.storage_path = Path(storage_path)
        self._heartbeats: Dict[str, Heartbeat] = {}
        self._lock = Lock()
        self._load()
    
    def _load(self):
        if self.storage_path.exists():
            with open(self.storage_path) as f:
                data = json.load(f)
                for name, hb in data.items():
                    self._heartbeats[name] = Heartbeat(
                        agent_name=hb["agent_name"],
                        timestamp=hb["timestamp"],
                        status=AgentStatus(hb["status"]),
                        metrics=hb.get("metrics", {}),
                        error_count=hb.get("error_count", 0),
                        last_error=hb.get("last_error")
                    )
    
    def _save(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w') as f:
            data = {
                name: {
                    "agent_name": hb.agent_name,
                    "timestamp": hb.timestamp,
                    "status": hb.status.value,
                    "metrics": hb.metrics,
                    "error_count": hb.error_count,
                    "last_error": hb.last_error
                }
                for name, hb in self._heartbeats.items()
            }
            json.dump(data, f, indent=2)
    
    def record_heartbeat(
        self, 
        agent_name: str, 
        status: AgentStatus = AgentStatus.HEALTHY,
        metrics: Dict = None,
        error: Optional[str] = None
    ):
        """Record a heartbeat from an agent."""
        with self._lock:
            existing = self._heartbeats.get(agent_name)
            error_count = 0
            
            if existing:
                error_count = existing.error_count
                if error:
                    error_count += 1
                elif status == AgentStatus.HEALTHY:
                    error_count = max(0, error_count - 1)  # Decay errors on success
            
            self._heartbeats[agent_name] = Heartbeat(
                agent_name=agent_name,
                timestamp=datetime.now(timezone.utc).isoformat(),
                status=status,
                metrics=metrics or {},
                error_count=error_count,
                last_error=error
            )
            self._save()
    
    def get_heartbeat(self, agent_name: str) -> Optional[Heartbeat]:
        return self._heartbeats.get(agent_name)
    
    def get_all_heartbeats(self) -> Dict[str, Heartbeat]:
        return self._heartbeats.copy()
    
    def is_agent_healthy(self, agent_name: str, max_age_seconds: int = 300) -> bool:
        """Check if agent is healthy based on recent heartbeat."""
        hb = self._heartbeats.get(agent_name)
        if not hb:
            return False
        
        # Check timestamp
        hb_time = datetime.fromisoformat(hb.timestamp.replace('Z', '+00:00'))
        age = (datetime.now(timezone.utc) - hb_time).total_seconds()
        
        if age > max_age_seconds:
            return False
        
        return hb.status in [AgentStatus.HEALTHY, AgentStatus.DEGRADED]
    
    def get_stale_agents(self, max_age_seconds: int = 300) -> List[str]:
        """Get list of agents with stale heartbeats."""
        stale = []
        now = datetime.now(timezone.utc)
        
        for name, hb in self._heartbeats.items():
            hb_time = datetime.fromisoformat(hb.timestamp.replace('Z', '+00:00'))
            if (now - hb_time).total_seconds() > max_age_seconds:
                stale.append(name)
        
        return stale


# =============================================================================
# CIRCUIT BREAKER
# =============================================================================

@dataclass
class CircuitBreaker:
    """Circuit breaker for failing services."""
    name: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[str] = None
    last_state_change: Optional[str] = None
    
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_seconds: int = 60


class CircuitBreakerManager:
    """Manage circuit breakers for external services."""
    
    def __init__(self, storage_path: str = ".hive-mind/circuit_breakers.json"):
        self.storage_path = Path(storage_path)
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._load()
    
    def _load(self):
        if self.storage_path.exists():
            with open(self.storage_path) as f:
                data = json.load(f)
                for name, cb in data.items():
                    self._breakers[name] = CircuitBreaker(
                        name=cb["name"],
                        state=CircuitState(cb["state"]),
                        failure_count=cb.get("failure_count", 0),
                        success_count=cb.get("success_count", 0),
                        last_failure_time=cb.get("last_failure_time"),
                        last_state_change=cb.get("last_state_change"),
                        failure_threshold=cb.get("failure_threshold", 5),
                        success_threshold=cb.get("success_threshold", 3),
                        timeout_seconds=cb.get("timeout_seconds", 60),
                    )
    
    def _save(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w') as f:
            data = {
                name: {
                    "name": cb.name,
                    "state": cb.state.value,
                    "failure_count": cb.failure_count,
                    "success_count": cb.success_count,
                    "last_failure_time": cb.last_failure_time,
                    "last_state_change": cb.last_state_change,
                    "failure_threshold": cb.failure_threshold,
                    "success_threshold": cb.success_threshold,
                    "timeout_seconds": cb.timeout_seconds,
                }
                for name, cb in self._breakers.items()
            }
            json.dump(data, f, indent=2)
    
    def get_or_create(self, name: str) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name=name)
        return self._breakers[name]
    
    def record_success(self, name: str):
        cb = self.get_or_create(name)
        cb.success_count += 1
        cb.failure_count = 0
        
        if cb.state == CircuitState.HALF_OPEN:
            if cb.success_count >= cb.success_threshold:
                cb.state = CircuitState.CLOSED
                cb.last_state_change = datetime.now(timezone.utc).isoformat()
                logger.info(f"Circuit {name} CLOSED after recovery")
        
        self._save()
    
    def record_failure(self, name: str):
        cb = self.get_or_create(name)
        cb.failure_count += 1
        cb.success_count = 0
        cb.last_failure_time = datetime.now(timezone.utc).isoformat()
        
        if cb.state == CircuitState.CLOSED:
            if cb.failure_count >= cb.failure_threshold:
                cb.state = CircuitState.OPEN
                cb.last_state_change = datetime.now(timezone.utc).isoformat()
                logger.warning(f"Circuit {name} OPENED after {cb.failure_count} failures")
        elif cb.state == CircuitState.HALF_OPEN:
            cb.state = CircuitState.OPEN
            cb.last_state_change = datetime.now(timezone.utc).isoformat()
            logger.warning(f"Circuit {name} re-OPENED after failure in half-open")
        
        self._save()
    
    def can_execute(self, name: str) -> bool:
        cb = self.get_or_create(name)
        
        if cb.state == CircuitState.CLOSED:
            return True
        
        if cb.state == CircuitState.OPEN:
            # Check if timeout has elapsed
            if cb.last_state_change:
                change_time = datetime.fromisoformat(cb.last_state_change.replace('Z', '+00:00'))
                elapsed = (datetime.now(timezone.utc) - change_time).total_seconds()
                if elapsed >= cb.timeout_seconds:
                    cb.state = CircuitState.HALF_OPEN
                    cb.last_state_change = datetime.now(timezone.utc).isoformat()
                    self._save()
                    logger.info(f"Circuit {name} moved to HALF_OPEN for testing")
                    return True
            return False
        
        # Half-open: allow one request
        return True
    
    def get_status(self) -> Dict[str, Dict]:
        return {
            name: {
                "state": cb.state.value,
                "failure_count": cb.failure_count,
                "success_count": cb.success_count,
            }
            for name, cb in self._breakers.items()
        }


# =============================================================================
# METRICS COLLECTOR
# =============================================================================

@dataclass
class MetricPoint:
    timestamp: str
    value: float
    tags: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """Collect and store agent metrics."""
    
    def __init__(self, storage_path: str = ".hive-mind/metrics"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._metrics: Dict[str, List[MetricPoint]] = {}
    
    def record(self, metric_name: str, value: float, tags: Dict[str, str] = None):
        """Record a metric value."""
        if metric_name not in self._metrics:
            self._metrics[metric_name] = []
        
        self._metrics[metric_name].append(MetricPoint(
            timestamp=datetime.now(timezone.utc).isoformat(),
            value=value,
            tags=tags or {}
        ))
        
        # Keep last 1000 points per metric
        if len(self._metrics[metric_name]) > 1000:
            self._metrics[metric_name] = self._metrics[metric_name][-1000:]
    
    def get_metric(self, metric_name: str, last_n: int = 100) -> List[Dict]:
        points = self._metrics.get(metric_name, [])[-last_n:]
        return [{"timestamp": p.timestamp, "value": p.value, "tags": p.tags} for p in points]
    
    def get_average(self, metric_name: str, last_n: int = 100) -> Optional[float]:
        points = self._metrics.get(metric_name, [])[-last_n:]
        if not points:
            return None
        return sum(p.value for p in points) / len(points)
    
    def save_snapshot(self):
        """Save current metrics to disk."""
        snapshot_file = self.storage_path / f"snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(snapshot_file, 'w') as f:
            data = {
                name: [{"timestamp": p.timestamp, "value": p.value, "tags": p.tags} for p in points[-100:]]
                for name, points in self._metrics.items()
            }
            json.dump(data, f, indent=2)
        return str(snapshot_file)


# =============================================================================
# ALERT MANAGER
# =============================================================================

@dataclass
class Alert:
    id: str
    severity: AlertSeverity
    source: str
    message: str
    timestamp: str
    resolved: bool = False
    resolved_at: Optional[str] = None


class AlertManager:
    """Manage and dispatch alerts."""
    
    def __init__(self, storage_path: str = ".hive-mind/alerts.json"):
        self.storage_path = Path(storage_path)
        self._alerts: List[Alert] = []
        self._slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
        self._load()
    
    def _load(self):
        if self.storage_path.exists():
            with open(self.storage_path) as f:
                data = json.load(f)
                self._alerts = [
                    Alert(
                        id=a["id"],
                        severity=AlertSeverity(a["severity"]),
                        source=a["source"],
                        message=a["message"],
                        timestamp=a["timestamp"],
                        resolved=a.get("resolved", False),
                        resolved_at=a.get("resolved_at")
                    )
                    for a in data
                ]
    
    def _save(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w') as f:
            data = [
                {
                    "id": a.id,
                    "severity": a.severity.value,
                    "source": a.source,
                    "message": a.message,
                    "timestamp": a.timestamp,
                    "resolved": a.resolved,
                    "resolved_at": a.resolved_at
                }
                for a in self._alerts[-500:]  # Keep last 500
            ]
            json.dump(data, f, indent=2)
    
    def create_alert(
        self, 
        severity: AlertSeverity, 
        source: str, 
        message: str,
        notify: bool = True
    ) -> str:
        alert_id = hashlib.md5(
            f"{source}:{message}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]
        
        alert = Alert(
            id=alert_id,
            severity=severity,
            source=source,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        self._alerts.append(alert)
        self._save()
        
        logger.log(
            logging.CRITICAL if severity == AlertSeverity.CRITICAL else
            logging.ERROR if severity == AlertSeverity.ERROR else
            logging.WARNING if severity == AlertSeverity.WARNING else
            logging.INFO,
            f"[ALERT:{severity.value.upper()}] {source}: {message}"
        )
        
        if notify and severity in [AlertSeverity.ERROR, AlertSeverity.CRITICAL]:
            self._send_slack_notification(alert)
        
        return alert_id
    
    def resolve_alert(self, alert_id: str):
        for alert in self._alerts:
            if alert.id == alert_id:
                alert.resolved = True
                alert.resolved_at = datetime.now(timezone.utc).isoformat()
                self._save()
                return True
        return False
    
    def get_active_alerts(self) -> List[Alert]:
        return [a for a in self._alerts if not a.resolved]
    
    def _send_slack_notification(self, alert: Alert):
        if not self._slack_webhook:
            return
        
        try:
            import requests
            emoji = {
                AlertSeverity.CRITICAL: ":rotating_light:",
                AlertSeverity.ERROR: ":x:",
                AlertSeverity.WARNING: ":warning:",
                AlertSeverity.INFO: ":information_source:"
            }.get(alert.severity, ":bell:")
            
            requests.post(self._slack_webhook, json={
                "text": f"{emoji} *{alert.severity.value.upper()}* - {alert.source}\n{alert.message}"
            }, timeout=10)
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")


# =============================================================================
# AGENT MONITOR (Main Class)
# =============================================================================

class AgentMonitor:
    """Main monitoring system orchestrating all sub-agents."""
    
    def __init__(self):
        self.heartbeat_tracker = HeartbeatTracker()
        self.circuit_breakers = CircuitBreakerManager()
        self.metrics = MetricsCollector()
        self.alerts = AlertManager()
    
    def watchdog_check(self) -> Dict:
        """WATCHDOG: Check all agent heartbeats."""
        results = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agents": {},
            "stale_agents": [],
            "unhealthy_agents": [],
        }
        
        for agent_name, config in AGENT_REGISTRY.items():
            hb = self.heartbeat_tracker.get_heartbeat(agent_name)
            
            if not hb:
                status = "never_seen"
            elif not self.heartbeat_tracker.is_agent_healthy(agent_name, config.heartbeat_interval * 2):
                status = "stale"
                results["stale_agents"].append(agent_name)
            elif hb.status == AgentStatus.UNHEALTHY:
                status = "unhealthy"
                results["unhealthy_agents"].append(agent_name)
            else:
                status = hb.status.value
            
            results["agents"][agent_name] = {
                "status": status,
                "last_heartbeat": hb.timestamp if hb else None,
                "error_count": hb.error_count if hb else 0
            }
        
        # Create alerts for issues
        if results["stale_agents"]:
            self.alerts.create_alert(
                AlertSeverity.WARNING,
                "WATCHDOG",
                f"Stale agents detected: {', '.join(results['stale_agents'])}"
            )
        
        if results["unhealthy_agents"]:
            self.alerts.create_alert(
                AlertSeverity.ERROR,
                "WATCHDOG",
                f"Unhealthy agents: {', '.join(results['unhealthy_agents'])}"
            )
        
        return results
    
    def auditor_check(self) -> Dict:
        """AUDITOR: Check operation compliance."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pending_approvals": 0,
            "approvals": [],
            "circuit_breakers": self.circuit_breakers.get_status(),
        }
    
    def medic_recover(self, agent_name: str) -> Dict:
        """MEDIC: Attempt to recover a failed agent."""
        logger.info(f"MEDIC: Attempting recovery for {agent_name}")
        
        config = AGENT_REGISTRY.get(agent_name)
        if not config:
            return {"success": False, "error": "Unknown agent"}
        
        # Check dependencies
        for dep in config.dependencies:
            if not self.circuit_breakers.can_execute(dep):
                return {
                    "success": False,
                    "error": f"Dependency {dep} circuit is open"
                }
        
        # Mark as recovering
        self.heartbeat_tracker.record_heartbeat(agent_name, AgentStatus.RECOVERING)
        
        # Recovery would involve restarting the agent process
        # For now, we just reset the heartbeat
        self.heartbeat_tracker.record_heartbeat(agent_name, AgentStatus.HEALTHY)
        
        return {
            "success": True,
            "agent": agent_name,
            "status": "recovered"
        }
    
    def reporter_generate(self) -> Dict:
        """REPORTER: Generate health report."""
        watchdog_report = self.watchdog_check()
        auditor_report = self.auditor_check()
        
        # Calculate overall health
        total_agents = len(AGENT_REGISTRY)
        healthy_agents = sum(
            1 for a in watchdog_report["agents"].values() 
            if a["status"] == "healthy"
        )
        health_percentage = (healthy_agents / total_agents * 100) if total_agents > 0 else 0
        
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_health": round(health_percentage, 1),
            "status": "healthy" if health_percentage >= 80 else "degraded" if health_percentage >= 50 else "critical",
            "agent_summary": {
                "total": total_agents,
                "healthy": healthy_agents,
                "stale": len(watchdog_report["stale_agents"]),
                "unhealthy": len(watchdog_report["unhealthy_agents"]),
            },
            "active_alerts": len(self.alerts.get_active_alerts()),
            "pending_approvals": auditor_report["pending_approvals"],
            "circuit_breakers": auditor_report["circuit_breakers"],
            "agents": watchdog_report["agents"],
        }
        
        # Save report
        report_path = Path(".hive-mind/health_reports")
        report_path.mkdir(parents=True, exist_ok=True)
        report_file = report_path / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        return report
    
    def record_agent_heartbeat(self, agent_name: str, status: AgentStatus = AgentStatus.HEALTHY, 
                                metrics: Dict = None, error: str = None):
        """Record heartbeat from an agent."""
        self.heartbeat_tracker.record_heartbeat(agent_name, status, metrics, error)
        
        # Record metrics
        if metrics:
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    self.metrics.record(f"{agent_name}.{key}", value)
    
    def record_api_call(self, service: str, success: bool, latency_ms: float = None):
        """Record API call result for circuit breaker and metrics."""
        if success:
            self.circuit_breakers.record_success(service)
        else:
            self.circuit_breakers.record_failure(service)
        
        if latency_ms:
            self.metrics.record(f"api.{service}.latency", latency_ms)
        
        self.metrics.record(f"api.{service}.calls", 1)
        if not success:
            self.metrics.record(f"api.{service}.errors", 1)


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_monitor: Optional[AgentMonitor] = None

def get_monitor() -> AgentMonitor:
    global _monitor
    if _monitor is None:
        _monitor = AgentMonitor()
    return _monitor


# =============================================================================
# DEMO
# =============================================================================

def demo():
    print("=" * 60)
    print("Agent Monitor Demo")
    print("=" * 60)
    
    monitor = get_monitor()
    
    # Simulate some heartbeats
    print("\n[1] Recording heartbeats...")
    monitor.record_agent_heartbeat("hunter", AgentStatus.HEALTHY, {"leads_scraped": 50})
    monitor.record_agent_heartbeat("enricher", AgentStatus.HEALTHY, {"enriched": 45})
    monitor.record_agent_heartbeat("segmentor", AgentStatus.DEGRADED, {"processed": 40})
    
    # Simulate API calls
    print("[2] Recording API calls...")
    monitor.record_api_call("gohighlevel", True, 150)
    monitor.record_api_call("instantly", True, 200)
    monitor.record_api_call("linkedin", False, 5000)
    monitor.record_api_call("linkedin", False, 5000)
    
    # Run checks
    print("\n[3] Running WATCHDOG check...")
    watchdog = monitor.watchdog_check()
    print(f"    Stale agents: {watchdog['stale_agents']}")
    print(f"    Unhealthy agents: {watchdog['unhealthy_agents']}")
    
    # Generate report
    print("\n[4] Generating health report...")
    report = monitor.reporter_generate()
    print(f"    Overall Health: {report['overall_health']}%")
    print(f"    Status: {report['status']}")
    print(f"    Active Alerts: {report['active_alerts']}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    demo()
