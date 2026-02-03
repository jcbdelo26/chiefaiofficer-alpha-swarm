"""
GHL Execution Gateway - Single Choke Point for ALL GHL Operations
===================================================================

This module is the ONLY authorized way to execute GHL actions.
All guardrails, permissions, and circuit breakers are enforced here.

NEVER bypass this gateway. Direct GHL API calls are prohibited.
"""

import os
import json
import logging
import tempfile
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ghl_gateway')

from core.agent_permissions import (
    Permission, PermissionGuard, PermissionDeniedError, get_permission_guard
)
from core.circuit_breaker import (
    CircuitBreakerError, get_registry as get_circuit_registry
)
from core.unified_guardrails import (
    ActionType, RiskLevel, ACTION_RISK_LEVELS, UnifiedGuardrails
)
from core.ghl_guardrails import EmailDeliverabilityGuard, get_email_guard
from core.audit_trail import AuditTrail, get_audit_trail
from core.system_orchestrator import SystemOrchestrator, SystemStatus


# =============================================================================
# ACTION TO PERMISSION MAPPING (Single Source of Truth)
# =============================================================================

ACTION_TO_PERMISSION: Dict[ActionType, Permission] = {
    ActionType.READ_CONTACT: Permission.READ_CONTACTS,
    ActionType.READ_PIPELINE: Permission.READ_LEADS,
    ActionType.READ_CALENDAR: Permission.READ_ANALYTICS,
    ActionType.SEARCH_CONTACTS: Permission.READ_CONTACTS,
    ActionType.CREATE_CONTACT: Permission.WRITE_CONTACTS,
    ActionType.UPDATE_CONTACT: Permission.WRITE_CONTACTS,
    ActionType.ADD_TAG: Permission.WRITE_CONTACTS,
    ActionType.UPDATE_OPPORTUNITY: Permission.WRITE_LEADS,
    ActionType.SEND_EMAIL: Permission.SEND_EMAIL,
    ActionType.SEND_SMS: Permission.SEND_SMS,
    ActionType.SCHEDULE_EMAIL: Permission.SEND_EMAIL,
    ActionType.TRIGGER_WORKFLOW: Permission.TRIGGER_WORKFLOW,
    ActionType.BULK_SEND_EMAIL: Permission.SEND_BULK,
    ActionType.DELETE_CONTACT: Permission.DELETE_CONTACTS,
    ActionType.BULK_DELETE: Permission.DELETE_CONTACTS,
}

ACTION_TO_RATE_LIMIT_KEY: Dict[ActionType, str] = {
    ActionType.READ_CONTACT: "read_contact",
    ActionType.SEARCH_CONTACTS: "read_contacts",
    ActionType.CREATE_CONTACT: "create_contact",
    ActionType.UPDATE_CONTACT: "update_contact",
    ActionType.SEND_EMAIL: "email_send",
    ActionType.SEND_SMS: "sms_send",
    ActionType.SCHEDULE_EMAIL: "email_send",
    ActionType.BULK_SEND_EMAIL: "bulk_send",
    ActionType.TRIGGER_WORKFLOW: "workflow_trigger",
}

ACTION_TO_CIRCUIT_BREAKER: Dict[ActionType, str] = {
    ActionType.SEND_EMAIL: "email_sending",
    ActionType.SEND_SMS: "ghl_api",
    ActionType.SCHEDULE_EMAIL: "email_sending",
    ActionType.BULK_SEND_EMAIL: "email_sending",
}


# =============================================================================
# ATOMIC FILE OPERATIONS
# =============================================================================

def atomic_json_write(filepath: Path, data: Dict[str, Any]):
    """Write JSON atomically using temp file + rename pattern."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    temp_fd, temp_path = tempfile.mkstemp(
        suffix='.json',
        prefix='atomic_',
        dir=str(filepath.parent)
    )
    
    try:
        with os.fdopen(temp_fd, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(temp_path, filepath)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def atomic_json_read(filepath: Path, default: Dict = None) -> Dict[str, Any]:
    """Read JSON with corruption recovery."""
    filepath = Path(filepath)
    if not filepath.exists():
        return default or {}
    
    try:
        with open(filepath) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to read {filepath}: {e}. Using default.")
        return default or {}


# =============================================================================
# EXECUTION RESULT
# =============================================================================

@dataclass
class ExecutionResult:
    """Result of a gateway execution."""
    success: bool
    action_type: str
    action_id: str
    agent_name: str
    status: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    warnings: list = None
    executed_at: str = None
    
    def __post_init__(self):
        self.executed_at = self.executed_at or datetime.now().isoformat()
        self.warnings = self.warnings or []


# =============================================================================
# GHL EXECUTION GATEWAY
# =============================================================================

class GHLExecutionGateway:
    """
    Single choke point for ALL GHL operations.
    
    Enforces:
    1. Agent permissions
    2. GHL guardrails (deliverability, content, grounding)
    3. Circuit breaker status
    4. System orchestrator operational status
    5. Audit logging
    
    Usage:
        gateway = GHLExecutionGateway()
        result = await gateway.execute(
            action_type=ActionType.SEND_EMAIL,
            parameters={'contact_id': '...', 'subject': '...', 'body': '...'},
            agent_name='GHL_MASTER',
            grounding_evidence={'source': 'supabase', 'data_id': 'lead_123'}
        )
    """
    
    def __init__(self):
        self.permission_guard = get_permission_guard()
        self.circuit_registry = get_circuit_registry()
        self.unified_guardrails = UnifiedGuardrails()
        self.email_guard = get_email_guard()
        self.orchestrator = SystemOrchestrator()
        self.audit_trail = None  # Initialized async
        
        logger.info("GHL Execution Gateway initialized")
    
    def _check_system_operational(self) -> Tuple[bool, str]:
        """Check if system is operational and emergency stop is not active."""
        # Refresh emergency stop status from environment
        self.orchestrator.refresh_emergency_stop()
        
        if self.orchestrator.emergency_stop:
            return False, "🚨 EMERGENCY_STOP is active - all operations halted. Set EMERGENCY_STOP=false in .env to resume."
        
        if not self.orchestrator.is_operational():
            return False, f"System not operational: {self.orchestrator.status.value}"
        return True, ""
    
    def _check_circuit_breaker(self, action_type: ActionType) -> Tuple[bool, str]:
        """Check if circuit breaker allows operation."""
        breaker_name = ACTION_TO_CIRCUIT_BREAKER.get(action_type, "ghl_api")
        
        if not self.circuit_registry.is_available(breaker_name):
            time_until = self.circuit_registry.get_time_until_retry(breaker_name)
            return False, f"Circuit breaker '{breaker_name}' is OPEN. Retry in {time_until:.1f}s"
        
        return True, ""
    
    def _check_permission(self, agent_name: str, action_type: ActionType) -> Tuple[bool, str]:
        """Check if agent has permission for action."""
        permission = ACTION_TO_PERMISSION.get(action_type)
        
        if not permission:
            # FAIL CLOSED: deny unmapped actions for safety
            logger.warning(f"No permission mapping for {action_type} - DENIED (fail-closed)")
            return False, f"Action '{action_type.value}' has no permission mapping - denied by default"
        
        if not self.permission_guard.check_permission(agent_name, permission):
            return False, f"Agent '{agent_name}' lacks permission: {permission.name}"
        
        rate_key = ACTION_TO_RATE_LIMIT_KEY.get(action_type, action_type.value)
        if not self.permission_guard.check_rate_limit(agent_name, rate_key):
            return False, f"Rate limit exceeded for '{rate_key}'"
        
        return True, ""
    
    async def _log_audit(self, result: ExecutionResult, parameters: Dict, grounding: Optional[Dict]):
        """Log execution to audit trail."""
        if self.audit_trail is None:
            self.audit_trail = await get_audit_trail()
        
        # SECURITY FIX: Use SHA256 instead of Python hash() for stable, secure hashing
        params_json = json.dumps(parameters, sort_keys=True, default=str)
        params_hash = hashlib.sha256(params_json.encode()).hexdigest()[:16]
        
        details = {
            "action_id": result.action_id,
            "parameters_hash": params_hash,
            "has_grounding": grounding is not None,
            "grounding_source": grounding.get("source") if grounding else None,
            "error": result.error,
            "warnings": result.warnings,
        }
        
        await self.audit_trail.log(
            agent_name=result.agent_name,
            action_type=result.action_type,
            target_resource=parameters.get("contact_id", "unknown"),
            action_details=parameters,
            status="success" if result.success else "failure",
            risk_level=ACTION_RISK_LEVELS.get(
                ActionType(result.action_type), RiskLevel.MEDIUM
            ).value.upper() if result.action_type in [a.value for a in ActionType] else "MEDIUM",
            grounding_evidence=grounding,
            error_message=result.error,
        )
    
    async def execute(
        self,
        action_type: ActionType,
        parameters: Dict[str, Any],
        agent_name: str,
        grounding_evidence: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """
        Execute a GHL action through all guardrails.
        
        Args:
            action_type: The type of GHL action
            parameters: Action parameters
            agent_name: Name of the agent requesting action
            grounding_evidence: Required for high-risk actions
            
        Returns:
            ExecutionResult with success/failure and details
        """
        import uuid
        action_id = str(uuid.uuid4())[:8]
        
        logger.info(f"[{action_id}] Gateway: {agent_name} -> {action_type.value}")
        
        operational, reason = self._check_system_operational()
        if not operational:
            result = ExecutionResult(
                success=False,
                action_type=action_type.value,
                action_id=action_id,
                agent_name=agent_name,
                status="blocked_system",
                error=reason
            )
            await self._log_audit(result, parameters, grounding_evidence)
            return result
        
        cb_ok, cb_reason = self._check_circuit_breaker(action_type)
        if not cb_ok:
            result = ExecutionResult(
                success=False,
                action_type=action_type.value,
                action_id=action_id,
                agent_name=agent_name,
                status="blocked_circuit_breaker",
                error=cb_reason
            )
            await self._log_audit(result, parameters, grounding_evidence)
            return result
        
        perm_ok, perm_reason = self._check_permission(agent_name, action_type)
        if not perm_ok:
            result = ExecutionResult(
                success=False,
                action_type=action_type.value,
                action_id=action_id,
                agent_name=agent_name,
                status="blocked_permission",
                error=perm_reason
            )
            await self._log_audit(result, parameters, grounding_evidence)
            return result
        
        # Validate action with unified guardrails
        valid, reason = self.unified_guardrails.validate_action(
            agent_name=agent_name,
            action_type=action_type,
            grounding_evidence=grounding_evidence
        )
        
        warnings = []
        
        if not valid:
            result = ExecutionResult(
                success=False,
                action_type=action_type.value,
                action_id=action_id,
                agent_name=agent_name,
                status="blocked_guardrails",
                error=reason,
                warnings=warnings
            )
            await self._log_audit(result, parameters, grounding_evidence)
            return result
        
        # For email actions, also check deliverability limits
        if action_type in [ActionType.SEND_EMAIL, ActionType.SCHEDULE_EMAIL]:
            recipient = parameters.get("recipient", parameters.get("to", ""))
            sender_domain = parameters.get("sender_domain", "chiefaiofficer.com")
            
            can_send, email_reason = self.email_guard.can_send_email(recipient, sender_domain)
            if not can_send:
                result = ExecutionResult(
                    success=False,
                    action_type=action_type.value,
                    action_id=action_id,
                    agent_name=agent_name,
                    status="blocked_deliverability",
                    error=email_reason,
                    warnings=warnings
                )
                await self._log_audit(result, parameters, grounding_evidence)
                return result
            
            # Validate email content
            subject = parameters.get("subject", "")
            body = parameters.get("body", "")
            content_valid, content_issues = self.email_guard.validate_email_content(subject, body)
            
            # SECURITY FIX: Block emails missing unsubscribe - CAN-SPAM compliance
            has_unsubscribe_issue = any("unsubscribe" in issue.lower() or "opt-out" in issue.lower() for issue in content_issues)
            if has_unsubscribe_issue:
                result = ExecutionResult(
                    success=False,
                    action_type=action_type.value,
                    action_id=action_id,
                    agent_name=agent_name,
                    status="blocked_compliance",
                    error="Email blocked: Missing unsubscribe/opt-out mechanism (CAN-SPAM violation)",
                    warnings=content_issues
                )
                await self._log_audit(result, parameters, grounding_evidence)
                return result
            
            if not content_valid:
                warnings.extend(content_issues)
        
        # Check if action requires approval (CRITICAL risk level)
        risk_level = ACTION_RISK_LEVELS.get(action_type, RiskLevel.MEDIUM)
        if risk_level == RiskLevel.CRITICAL:
            result = ExecutionResult(
                success=False,
                action_type=action_type.value,
                action_id=action_id,
                agent_name=agent_name,
                status="pending_approval",
                error="Action requires human approval",
                warnings=warnings
            )
            await self._log_audit(result, parameters, grounding_evidence)
            return result
        
        rate_key = ACTION_TO_RATE_LIMIT_KEY.get(action_type, action_type.value)
        self.permission_guard.increment_action_count(agent_name, rate_key)
        
        breaker_name = ACTION_TO_CIRCUIT_BREAKER.get(action_type, "ghl_api")
        self.circuit_registry.record_success(breaker_name)
        
        self.orchestrator.update_component_health("api_ghl", "healthy")
        
        result = ExecutionResult(
            success=True,
            action_type=action_type.value,
            action_id=action_id,
            agent_name=agent_name,
            status="executed",
            data={"message": "Action validated and ready for execution"},
            warnings=warnings
        )
        
        await self._log_audit(result, parameters, grounding_evidence)
        
        logger.info(f"[{action_id}] Gateway: APPROVED - {action_type.value}")
        
        return result
    
    def execute_sync(
        self,
        action_type: ActionType,
        parameters: Dict[str, Any],
        agent_name: str,
        grounding_evidence: Optional[Dict[str, Any]] = None
    ) -> ExecutionResult:
        """Synchronous wrapper for execute."""
        import asyncio
        return asyncio.run(self.execute(action_type, parameters, agent_name, grounding_evidence))
    
    async def get_audit_log(self, limit: int = 100) -> list:
        """Get recent audit log entries."""
        if self.audit_trail is None:
            self.audit_trail = await get_audit_trail()
        return await self.audit_trail.get_logs(limit=limit)
    
    def print_status(self):
        """Print gateway status."""
        print("\n" + "=" * 60)
        print("GHL EXECUTION GATEWAY STATUS")
        print("=" * 60)
        
        print("\n[System]")
        print(f"  Operational: {self.orchestrator.is_operational()}")
        print(f"  Status: {self.orchestrator.status.value}")
        
        print("\n[Circuit Breakers]")
        for name, status in self.circuit_registry.get_status().items():
            icon = "OK" if status["state"] == "closed" else "OPEN"
            print(f"  [{icon}] {name}: {status['state']}")
        
        print("\n[Email Limits]")
        email_status = self.email_guard.get_status()
        print(f"  Monthly: {email_status['monthly']['sent']}/{email_status['monthly']['limit']}")
        print(f"  Daily: {email_status['daily']['sent']}/{email_status['daily']['limit']}")
        print(f"  Hourly: {email_status['hourly']['sent']}/{email_status['hourly']['limit']}")
        
        print("\n[Unified Guardrails]")
        guardrails_status = self.unified_guardrails.get_status()
        print(f"  GHL Email Usage: {guardrails_status.get('ghl_email_usage', 'N/A')}")
        
        print("\n" + "=" * 60)


_gateway: Optional[GHLExecutionGateway] = None


def get_gateway() -> GHLExecutionGateway:
    """Get or create the global gateway instance."""
    global _gateway
    if _gateway is None:
        _gateway = GHLExecutionGateway()
    return _gateway


async def execute_ghl_action(
    action_type: ActionType,
    parameters: Dict[str, Any],
    agent_name: str,
    grounding_evidence: Optional[Dict[str, Any]] = None
) -> ExecutionResult:
    """
    Convenience function to execute GHL action through gateway.
    
    This is the ONLY authorized way to perform GHL operations.
    """
    gateway = get_gateway()
    return await gateway.execute(action_type, parameters, agent_name, grounding_evidence)


def main():
    """Demonstrate gateway blocking unauthorized actions."""
    import asyncio
    
    print("=" * 60)
    print("GHL EXECUTION GATEWAY - Demo")
    print("=" * 60)
    
    gateway = GHLExecutionGateway()
    
    guard = get_permission_guard()
    guard.register_agent_by_role_name("hunter_test", "HUNTER")
    guard.register_agent_by_role_name("ghl_master_test", "GHL_MASTER")
    
    print("\n[Test 1] HUNTER trying to send email (should be BLOCKED)")
    result = gateway.execute_sync(
        action_type=ActionType.SEND_EMAIL,
        parameters={"contact_id": "123", "subject": "Test", "body": "Hello"},
        agent_name="hunter_test",
        grounding_evidence={"source": "supabase", "data_id": "test"}
    )
    print(f"  Result: {result.status}")
    print(f"  Error: {result.error}")
    
    print("\n[Test 2] GHL_MASTER sending email with spam content (should be BLOCKED)")
    result = gateway.execute_sync(
        action_type=ActionType.SEND_EMAIL,
        parameters={
            "contact_id": "123",
            "subject": "FREE MONEY NOW!!!",
            "body": "Act now for guaranteed results! No unsubscribe needed."
        },
        agent_name="ghl_master_test",
        grounding_evidence={"source": "supabase", "data_id": "test"}
    )
    print(f"  Result: {result.status}")
    print(f"  Error: {result.error}")
    
    print("\n[Test 3] GHL_MASTER sending valid email (should be APPROVED)")
    result = gateway.execute_sync(
        action_type=ActionType.SEND_EMAIL,
        parameters={
            "contact_id": "123",
            "subject": "Quick question about your RevOps",
            "body": "Hi, I noticed your team has been growing. Reply STOP to unsubscribe."
        },
        agent_name="ghl_master_test",
        grounding_evidence={"source": "supabase", "data_id": "lead_456", "verified": True}
    )
    print(f"  Result: {result.status}")
    print(f"  Success: {result.success}")
    
    print("\n[Test 4] BULK_DELETE without approval (should require approval)")
    result = gateway.execute_sync(
        action_type=ActionType.BULK_DELETE,
        parameters={"contact_ids": ["1", "2", "3"]},
        agent_name="ghl_master_test",
        grounding_evidence={"source": "manual", "data_id": "cleanup"}
    )
    print(f"  Result: {result.status}")
    print(f"  Error: {result.error}")
    
    print("\n" + "=" * 60)
    gateway.print_status()


if __name__ == "__main__":
    main()
