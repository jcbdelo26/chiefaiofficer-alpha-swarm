"""
System Orchestrator - Central Coordination Hub
===============================================

Provides unified system management:
1. Health monitoring across all agents and APIs
2. Central rate limit coordination
3. System-wide status dashboard
4. Emergency shutdown capabilities
5. Production readiness checks
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('system_orchestrator')


class SystemStatus(Enum):
    """Overall system status"""
    HEALTHY = "healthy"           # All systems operational
    DEGRADED = "degraded"         # Some issues, can continue
    CRITICAL = "critical"         # Major issues, limited operation
    EMERGENCY = "emergency"       # System stopped, manual intervention
    MAINTENANCE = "maintenance"   # Planned downtime


class ComponentType(Enum):
    """Types of system components"""
    AGENT = "agent"
    API = "api"
    DATABASE = "database"
    QUEUE = "queue"
    CIRCUIT_BREAKER = "circuit_breaker"


@dataclass
class ComponentHealth:
    """Health status of a system component"""
    name: str
    component_type: ComponentType
    status: str  # healthy, degraded, down
    last_check: str
    last_success: Optional[str]
    failure_count: int
    error_message: Optional[str]
    metrics: Dict[str, Any] = field(default_factory=dict)
    
    def is_healthy(self) -> bool:
        return self.status == "healthy"


@dataclass
class RateLimitStatus:
    """Rate limit status for a service"""
    service: str
    current_usage: int
    limit: int
    reset_at: str
    percentage_used: float
    
    def is_near_limit(self, threshold: float = 0.8) -> bool:
        return self.percentage_used >= threshold


@dataclass
class SystemSnapshot:
    """Complete system state snapshot"""
    timestamp: str
    overall_status: SystemStatus
    components: List[ComponentHealth]
    rate_limits: List[RateLimitStatus]
    pending_actions: int
    pending_approvals: int
    circuit_breakers_open: int
    active_handoffs: int
    errors_last_hour: int
    warnings: List[str]
    recommendations: List[str]


class SystemOrchestrator:
    """
    Central orchestration hub for the entire swarm.
    
    Responsibilities:
    1. Monitor all system components
    2. Coordinate rate limits across services
    3. Provide unified status dashboard
    4. Handle emergency situations
    5. Validate production readiness
    6. Global kill switch via EMERGENCY_STOP env var
    """
    
    def __init__(self):
        self.hive_mind_path = Path(__file__).parent.parent / ".hive-mind"
        self.hive_mind_path.mkdir(exist_ok=True)
        
        # System state
        self.status = SystemStatus.HEALTHY
        self.maintenance_mode = False
        
        # Check global kill switch from environment
        # This allows stopping all outbound without code changes
        self.emergency_stop = self._check_emergency_stop()
        
        # Component registry
        self.components: Dict[str, ComponentHealth] = {}
        
        # Initialize component health tracking
        self._initialize_components()
        
        if self.emergency_stop:
            logger.warning("🚨 EMERGENCY_STOP is ACTIVE - all outbound operations blocked")
            self.status = SystemStatus.EMERGENCY
        
        logger.info("System Orchestrator initialized")
    
    def _check_emergency_stop(self) -> bool:
        """
        Check if global emergency stop is enabled via environment variable.
        
        Set EMERGENCY_STOP=true in .env to halt all outbound operations.
        This is the global kill switch for production safety.
        """
        env_value = os.getenv("EMERGENCY_STOP", "false").lower().strip()
        return env_value in ("true", "1", "yes", "on")
    
    def refresh_emergency_stop(self) -> bool:
        """
        Re-check the emergency stop flag from environment.
        Call this to pick up changes without restarting.
        """
        # Reload .env to pick up changes
        load_dotenv(override=True)
        self.emergency_stop = self._check_emergency_stop()
        
        if self.emergency_stop:
            self.status = SystemStatus.EMERGENCY
            logger.warning("🚨 EMERGENCY_STOP activated - all outbound blocked")
        else:
            self._evaluate_system_status()
            
        return self.emergency_stop
    
    def _initialize_components(self):
        """Initialize health tracking for all known components"""
        now = datetime.now().isoformat()
        
        # Agents
        agents = ['HUNTER', 'ENRICHER', 'SEGMENTOR', 'CRAFTER', 'GATEKEEPER', 'GHL_MASTER', 'QUEEN']
        for agent in agents:
            self.components[agent] = ComponentHealth(
                name=agent,
                component_type=ComponentType.AGENT,
                status="unknown",
                last_check=now,
                last_success=None,
                failure_count=0,
                error_message=None
            )
        
        # APIs
        apis = ['ghl', 'supabase', 'linkedin', 'clay', 'rb2b']
        for api in apis:
            self.components[f"api_{api}"] = ComponentHealth(
                name=api,
                component_type=ComponentType.API,
                status="unknown",
                last_check=now,
                last_success=None,
                failure_count=0,
                error_message=None
            )
        
        # Databases
        self.components['supabase_db'] = ComponentHealth(
            name="supabase_db",
            component_type=ComponentType.DATABASE,
            status="unknown",
            last_check=now,
            last_success=None,
            failure_count=0,
            error_message=None
        )
    
    def update_component_health(
        self,
        component_name: str,
        status: str,
        error_message: str = None,
        metrics: Dict = None
    ):
        """Update health status of a component"""
        now = datetime.now().isoformat()
        
        if component_name not in self.components:
            logger.warning(f"Unknown component: {component_name}")
            return
        
        component = self.components[component_name]
        component.last_check = now
        component.status = status
        component.error_message = error_message
        
        if status == "healthy":
            component.last_success = now
            component.failure_count = 0
        else:
            component.failure_count += 1
        
        if metrics:
            component.metrics.update(metrics)
        
        # Check if this affects system status
        self._evaluate_system_status()
        
        logger.debug(f"Component {component_name}: {status}")
    
    def _evaluate_system_status(self):
        """Evaluate overall system status based on component health"""
        if self.emergency_stop:
            self.status = SystemStatus.EMERGENCY
            return
        
        if self.maintenance_mode:
            self.status = SystemStatus.MAINTENANCE
            return
        
        healthy = 0
        degraded = 0
        down = 0
        
        for component in self.components.values():
            if component.status == "healthy":
                healthy += 1
            elif component.status == "degraded":
                degraded += 1
            elif component.status == "down":
                down += 1
        
        total = len(self.components)
        
        # Critical APIs that must be up
        critical_apis = ['api_ghl', 'api_supabase']
        critical_down = any(
            self.components.get(api, ComponentHealth("", ComponentType.API, "unknown", "", None, 0, None)).status == "down"
            for api in critical_apis
        )
        
        if critical_down or down >= 3:
            self.status = SystemStatus.CRITICAL
        elif degraded >= 3 or down >= 1:
            self.status = SystemStatus.DEGRADED
        else:
            self.status = SystemStatus.HEALTHY
    
    def get_rate_limits(self) -> List[RateLimitStatus]:
        """Get current rate limit status for all services"""
        limits = []
        
        # Load GHL email limits
        email_limits_file = self.hive_mind_path / "email_limits.json"
        if email_limits_file.exists():
            with open(email_limits_file) as f:
                data = json.load(f)
            
            monthly_sent = data.get('monthly_sent', 0)
            monthly_limit = data.get('monthly_limit', 3000)
            daily_sent = data.get('daily_sent', 0)
            daily_limit = data.get('daily_limit', 150)
            
            limits.append(RateLimitStatus(
                service="ghl_email_monthly",
                current_usage=monthly_sent,
                limit=monthly_limit,
                reset_at=f"{datetime.now().year}-{datetime.now().month + 1:02d}-01",
                percentage_used=(monthly_sent / monthly_limit) * 100 if monthly_limit > 0 else 0
            ))
            
            limits.append(RateLimitStatus(
                service="ghl_email_daily",
                current_usage=daily_sent,
                limit=daily_limit,
                reset_at=(datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d 00:00"),
                percentage_used=(daily_sent / daily_limit) * 100 if daily_limit > 0 else 0
            ))
        
        # Load circuit breaker states
        cb_file = self.hive_mind_path / "circuit_breakers.json"
        if cb_file.exists():
            with open(cb_file) as f:
                cb_data = json.load(f)
            
            for name, state in cb_data.items():
                # Handle both dict and list formats
                if isinstance(state, dict) and state.get('state') == 'open':
                    limits.append(RateLimitStatus(
                        service=f"circuit_{name}",
                        current_usage=state.get('failure_count', 0),
                        limit=state.get('failure_threshold', 5),
                        reset_at=state.get('last_failure_time', 'unknown'),
                        percentage_used=100.0  # Open = 100%
                    ))
        
        return limits
    
    def get_pending_counts(self) -> Tuple[int, int, int]:
        """Get counts of pending items (actions, approvals, handoffs)"""
        pending_actions = 0
        pending_approvals = 0
        pending_handoffs = 0
        
        # Check action audit log
        audit_file = self.hive_mind_path / "action_audit_log.json"
        if audit_file.exists():
            with open(audit_file) as f:
                logs = json.load(f)
            pending_approvals = sum(1 for l in logs if l.get('status') == 'pending_approval')
        
        # Check handoffs
        handoffs_dir = self.hive_mind_path / "handoffs"
        pending_file = handoffs_dir / "pending.json"
        if pending_file.exists():
            with open(pending_file) as f:
                pending_data = json.load(f)
            pending_handoffs = sum(len(v) for v in pending_data.values())
        
        return pending_actions, pending_approvals, pending_handoffs
    
    def get_circuit_breaker_status(self) -> int:
        """Get count of open circuit breakers"""
        cb_file = self.hive_mind_path / "circuit_breakers.json"
        if cb_file.exists():
            with open(cb_file) as f:
                cb_data = json.load(f)
            return sum(1 for s in cb_data.values() if isinstance(s, dict) and s.get('state') == 'open')
        return 0
    
    def get_error_count(self, hours: int = 1) -> int:
        """Get count of errors in the last N hours"""
        # Check various log files
        error_count = 0
        cutoff = datetime.now() - timedelta(hours=hours)
        
        # Check permission log
        perm_file = self.hive_mind_path / "permission_log.json"
        if perm_file.exists():
            with open(perm_file) as f:
                logs = json.load(f)
            if isinstance(logs, list):
                for log in logs:
                    if isinstance(log, dict) and log.get('granted') == False:
                        try:
                            log_time = datetime.fromisoformat(log.get('timestamp', ''))
                            if log_time > cutoff:
                                error_count += 1
                        except:
                            pass
        
        # Check audit log
        audit_file = self.hive_mind_path / "action_audit_log.json"
        if audit_file.exists():
            with open(audit_file) as f:
                logs = json.load(f)
            for log in logs:
                if log.get('status') in ['denied', 'grounding_failed']:
                    try:
                        log_time = datetime.fromisoformat(log.get('timestamp', ''))
                        if log_time > cutoff:
                            error_count += 1
                    except:
                        pass
        
        return error_count
    
    def generate_warnings(self) -> List[str]:
        """Generate warnings based on current state"""
        warnings = []
        
        # Check rate limits
        for limit in self.get_rate_limits():
            if limit.is_near_limit(0.9):
                warnings.append(f"CRITICAL: {limit.service} at {limit.percentage_used:.0f}% capacity")
            elif limit.is_near_limit(0.8):
                warnings.append(f"WARNING: {limit.service} at {limit.percentage_used:.0f}% capacity")
        
        # Check components
        for name, component in self.components.items():
            if component.status == "down":
                warnings.append(f"CRITICAL: {name} is DOWN")
            elif component.status == "degraded":
                warnings.append(f"WARNING: {name} is degraded")
            elif component.failure_count >= 3:
                warnings.append(f"WARNING: {name} has {component.failure_count} recent failures")
        
        # Check circuit breakers
        open_breakers = self.get_circuit_breaker_status()
        if open_breakers > 0:
            warnings.append(f"WARNING: {open_breakers} circuit breaker(s) OPEN")
        
        return warnings
    
    def generate_recommendations(self) -> List[str]:
        """Generate recommendations based on current state"""
        recommendations = []
        
        # Based on warnings
        for warning in self.generate_warnings():
            if "DOWN" in warning:
                recommendations.append("Check API credentials and network connectivity")
            if "circuit breaker" in warning.lower():
                recommendations.append("Review recent errors before retrying failed operations")
            if "capacity" in warning:
                recommendations.append("Consider spreading operations across time")
        
        # Production readiness
        if self.status != SystemStatus.HEALTHY:
            recommendations.append("Address system issues before running campaigns")
        
        return list(set(recommendations))  # Dedupe
    
    def get_system_snapshot(self) -> SystemSnapshot:
        """Get complete system state snapshot"""
        pending_actions, pending_approvals, pending_handoffs = self.get_pending_counts()
        
        return SystemSnapshot(
            timestamp=datetime.now().isoformat(),
            overall_status=self.status,
            components=list(self.components.values()),
            rate_limits=self.get_rate_limits(),
            pending_actions=pending_actions,
            pending_approvals=pending_approvals,
            circuit_breakers_open=self.get_circuit_breaker_status(),
            active_handoffs=pending_handoffs,
            errors_last_hour=self.get_error_count(1),
            warnings=self.generate_warnings(),
            recommendations=self.generate_recommendations()
        )
    
    def check_production_readiness(self) -> Tuple[bool, List[str], List[str]]:
        """
        Check if system is ready for production.
        
        Returns:
            (ready, passed_checks, failed_checks)
        """
        passed = []
        failed = []
        
        # 1. Check all critical APIs
        critical_apis = ['api_ghl', 'api_supabase']
        for api in critical_apis:
            if api in self.components:
                if self.components[api].status == "healthy":
                    passed.append(f"{api}: Connected")
                elif self.components[api].status == "unknown":
                    failed.append(f"{api}: Not tested - run health check")
                else:
                    failed.append(f"{api}: {self.components[api].status}")
            else:
                failed.append(f"{api}: Not configured")
        
        # 2. Check rate limits not exceeded
        for limit in self.get_rate_limits():
            if limit.percentage_used < 80:
                passed.append(f"{limit.service}: {100 - limit.percentage_used:.0f}% available")
            else:
                failed.append(f"{limit.service}: Only {100 - limit.percentage_used:.0f}% available")
        
        # 3. Check no open circuit breakers
        open_cb = self.get_circuit_breaker_status()
        if open_cb == 0:
            passed.append("Circuit breakers: All closed")
        else:
            failed.append(f"Circuit breakers: {open_cb} open")
        
        # 4. Check no pending approvals blocking
        _, pending_approvals, _ = self.get_pending_counts()
        if pending_approvals == 0:
            passed.append("Pending approvals: None")
        else:
            failed.append(f"Pending approvals: {pending_approvals} waiting")
        
        # 5. Check error rate
        errors = self.get_error_count(1)
        if errors < 5:
            passed.append(f"Error rate: {errors} in last hour (acceptable)")
        else:
            failed.append(f"Error rate: {errors} in last hour (too high)")
        
        # 6. Check system status
        if self.status == SystemStatus.HEALTHY:
            passed.append("System status: HEALTHY")
        else:
            failed.append(f"System status: {self.status.value}")
        
        ready = len(failed) == 0
        
        return ready, passed, failed
    
    def enter_maintenance_mode(self, reason: str):
        """Enter maintenance mode - stops all operations"""
        self.maintenance_mode = True
        self.status = SystemStatus.MAINTENANCE
        
        logger.warning(f"MAINTENANCE MODE ENABLED: {reason}")
        
        # Log to file
        maint_file = self.hive_mind_path / "maintenance.json"
        with open(maint_file, 'w') as f:
            json.dump({
                'enabled': True,
                'reason': reason,
                'started_at': datetime.now().isoformat()
            }, f, indent=2)
    
    def exit_maintenance_mode(self):
        """Exit maintenance mode"""
        self.maintenance_mode = False
        self._evaluate_system_status()
        
        logger.info("MAINTENANCE MODE DISABLED")
        
        maint_file = self.hive_mind_path / "maintenance.json"
        if maint_file.exists():
            maint_file.unlink()
    
    def emergency_shutdown(self, reason: str):
        """Emergency shutdown - stops all operations immediately"""
        self.emergency_stop = True
        self.status = SystemStatus.EMERGENCY
        
        logger.critical(f"EMERGENCY SHUTDOWN: {reason}")
        
        # Log to file
        emergency_file = self.hive_mind_path / "emergency.json"
        with open(emergency_file, 'w') as f:
            json.dump({
                'emergency': True,
                'reason': reason,
                'triggered_at': datetime.now().isoformat()
            }, f, indent=2)
    
    def is_operational(self) -> bool:
        """Check if system is operational (can process requests)"""
        if self.emergency_stop:
            return False
        if self.maintenance_mode:
            return False
        if self.status in [SystemStatus.EMERGENCY, SystemStatus.CRITICAL]:
            return False
        return True
    
    def print_status_dashboard(self):
        """Print a text-based status dashboard"""
        snapshot = self.get_system_snapshot()
        
        print("\n" + "=" * 70)
        print("SYSTEM ORCHESTRATOR - STATUS DASHBOARD")
        print("=" * 70)
        print(f"Timestamp: {snapshot.timestamp}")
        print(f"Overall Status: {snapshot.overall_status.value.upper()}")
        print("-" * 70)
        
        print("\n[COMPONENTS]")
        for comp in snapshot.components[:10]:  # First 10
            status_icon = "+" if comp.status == "healthy" else "-" if comp.status == "down" else "~"
            print(f"  [{status_icon}] {comp.name}: {comp.status}")
        
        print("\n[RATE LIMITS]")
        for limit in snapshot.rate_limits:
            bar_len = 20
            filled = int((limit.percentage_used / 100) * bar_len)
            bar = "#" * filled + "-" * (bar_len - filled)
            print(f"  {limit.service}: [{bar}] {limit.percentage_used:.0f}%")
        
        print("\n[QUEUES]")
        print(f"  Pending Actions: {snapshot.pending_actions}")
        print(f"  Pending Approvals: {snapshot.pending_approvals}")
        print(f"  Active Handoffs: {snapshot.active_handoffs}")
        print(f"  Circuit Breakers Open: {snapshot.circuit_breakers_open}")
        print(f"  Errors (last hour): {snapshot.errors_last_hour}")
        
        if snapshot.warnings:
            print("\n[WARNINGS]")
            for warning in snapshot.warnings[:5]:
                print(f"  ! {warning}")
        
        if snapshot.recommendations:
            print("\n[RECOMMENDATIONS]")
            for rec in snapshot.recommendations[:3]:
                print(f"  > {rec}")
        
        print("\n" + "=" * 70)


def main():
    """Demonstrate system orchestrator"""
    print("=" * 70)
    print("SYSTEM ORCHESTRATOR - Central Coordination Hub")
    print("=" * 70)
    
    orchestrator = SystemOrchestrator()
    
    # Simulate some component updates
    print("\n[1] Updating component health...")
    orchestrator.update_component_health("api_ghl", "healthy")
    orchestrator.update_component_health("api_supabase", "healthy")
    orchestrator.update_component_health("api_linkedin", "degraded", "Rate limited")
    orchestrator.update_component_health("HUNTER", "healthy")
    orchestrator.update_component_health("ENRICHER", "healthy")
    orchestrator.update_component_health("GHL_MASTER", "healthy")
    
    print("\n[2] Production Readiness Check...")
    ready, passed, failed = orchestrator.check_production_readiness()
    print(f"\n  Ready for production: {'YES' if ready else 'NO'}")
    print("\n  Passed:")
    for check in passed:
        print(f"    [+] {check}")
    if failed:
        print("\n  Failed:")
        for check in failed:
            print(f"    [-] {check}")
    
    print("\n[3] Status Dashboard...")
    orchestrator.print_status_dashboard()
    
    print("\n[4] Testing maintenance mode...")
    orchestrator.enter_maintenance_mode("Scheduled maintenance")
    print(f"  Operational: {orchestrator.is_operational()}")
    orchestrator.exit_maintenance_mode()
    print(f"  Operational: {orchestrator.is_operational()}")
    
    print("\n" + "=" * 70)
    print("System Orchestrator demonstration complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
