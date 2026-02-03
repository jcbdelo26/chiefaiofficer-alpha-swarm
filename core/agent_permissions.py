"""
Agent Permission System - Strict access control for the swarm.

Defines what each agent CAN and CANNOT do with granular permissions,
rate limits, and platform access controls.
"""

import json
import functools
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Set, Dict, List, Optional, Callable, Any
from datetime import datetime
from pathlib import Path


class Permission(Enum):
    """Granular permission actions for agents."""
    # Lead permissions
    READ_LEADS = auto()
    WRITE_LEADS = auto()
    DELETE_LEADS = auto()
    
    # Contact permissions
    READ_CONTACTS = auto()
    WRITE_CONTACTS = auto()
    DELETE_CONTACTS = auto()
    
    # Communication permissions
    SEND_EMAIL = auto()
    SEND_SMS = auto()
    SEND_BULK = auto()
    
    # Workflow permissions
    TRIGGER_WORKFLOW = auto()
    MODIFY_WORKFLOW = auto()
    
    # Analytics permissions
    READ_ANALYTICS = auto()
    EXPORT_DATA = auto()
    
    # Campaign permissions
    APPROVE_CAMPAIGN = auto()
    REJECT_CAMPAIGN = auto()
    
    # Admin permissions
    MODIFY_CONFIG = auto()
    ADMIN_ACCESS = auto()


@dataclass
class AgentRole:
    """Defines an agent's role with permissions and constraints."""
    name: str
    permissions: Set[Permission]
    rate_limits: Dict[str, int] = field(default_factory=dict)  # action -> max per hour
    allowed_platforms: List[str] = field(default_factory=list)
    requires_approval_for: List[Permission] = field(default_factory=list)
    
    def has_permission(self, permission: Permission) -> bool:
        """Check if role has a specific permission."""
        return permission in self.permissions
    
    def get_rate_limit(self, action: str) -> Optional[int]:
        """Get rate limit for an action, None if unlimited."""
        return self.rate_limits.get(action)
    
    def can_access_platform(self, platform: str) -> bool:
        """Check if role can access a platform."""
        return platform.lower() in [p.lower() for p in self.allowed_platforms]
    
    def needs_approval(self, permission: Permission) -> bool:
        """Check if action requires approval from Gatekeeper."""
        return permission in self.requires_approval_for


# Predefined Agent Roles
PREDEFINED_ROLES: Dict[str, AgentRole] = {
    "HUNTER": AgentRole(
        name="HUNTER",
        permissions={Permission.READ_LEADS},
        rate_limits={"linkedin_search": 100, "profile_view": 50},
        allowed_platforms=["LinkedIn", "Sales Navigator"],
        requires_approval_for=[]
    ),
    
    "ENRICHER": AgentRole(
        name="ENRICHER",
        permissions={Permission.READ_LEADS, Permission.WRITE_LEADS},
        rate_limits={"enrichment_call": 500, "api_request": 1000},
        allowed_platforms=["Clay", "RB2B", "Clearbit", "Apollo"],
        requires_approval_for=[]
    ),
    
    "SEGMENTOR": AgentRole(
        name="SEGMENTOR",
        permissions={Permission.READ_LEADS, Permission.WRITE_LEADS, Permission.READ_ANALYTICS},
        rate_limits={"segment_update": 200, "batch_operation": 50},
        allowed_platforms=["Supabase", "PostgreSQL"],
        requires_approval_for=[]
    ),
    
    "CRAFTER": AgentRole(
        name="CRAFTER",
        permissions={Permission.READ_LEADS, Permission.WRITE_LEADS, Permission.READ_CONTACTS},
        rate_limits={"content_generation": 100, "template_create": 50},
        allowed_platforms=["GoHighLevel"],  # Read-only for GHL
        requires_approval_for=[Permission.SEND_EMAIL, Permission.SEND_SMS]
    ),
    
    "GATEKEEPER": AgentRole(
        name="GATEKEEPER",
        permissions={
            Permission.APPROVE_CAMPAIGN, 
            Permission.REJECT_CAMPAIGN,
            Permission.READ_LEADS,
            Permission.READ_CONTACTS,
            Permission.READ_ANALYTICS
        },
        rate_limits={"approval_decision": 500},
        allowed_platforms=["GoHighLevel", "Supabase", "All"],  # Read access everywhere
        requires_approval_for=[]
    ),
    
    "GHL_MASTER": AgentRole(
        name="GHL_MASTER",
        permissions={
            Permission.SEND_EMAIL,
            Permission.SEND_SMS,
            Permission.SEND_BULK,
            Permission.TRIGGER_WORKFLOW,
            Permission.READ_LEADS,
            Permission.WRITE_LEADS,
            Permission.READ_CONTACTS,
            Permission.WRITE_CONTACTS
        },
        rate_limits={"email_send": 500, "sms_send": 200, "bulk_send": 10},
        allowed_platforms=["GoHighLevel"],
        requires_approval_for=[Permission.SEND_BULK, Permission.MODIFY_WORKFLOW]
    ),
    
    "QUEEN": AgentRole(
        name="QUEEN",
        permissions=set(Permission),  # All permissions
        rate_limits={},  # No limits for orchestrator
        allowed_platforms=["All"],
        requires_approval_for=[]  # Queen needs no approval
    )
}


class PermissionDeniedError(Exception):
    """Raised when an agent attempts an unauthorized action."""
    def __init__(self, agent_name: str, permission: Permission, message: str = None):
        self.agent_name = agent_name
        self.permission = permission
        self.message = message or f"Agent '{agent_name}' denied permission: {permission.name}"
        super().__init__(self.message)


class PermissionGuard:
    """Guards agent actions with permission checks and logging."""
    
    def __init__(self, log_dir: str = ".hive-mind"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "permission_log.json"
        self.agent_roles: Dict[str, AgentRole] = {}
        self.violations: Dict[str, List[Dict]] = {}
        self._action_counts: Dict[str, Dict[str, int]] = {}  # agent -> action -> count
        self._hour_start: Dict[str, datetime] = {}
        
        # Load existing logs
        self._load_logs()
    
    def _load_logs(self):
        """Load existing permission logs."""
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r') as f:
                    data = json.load(f)
                    self.violations = data.get("violations", {})
            except (json.JSONDecodeError, IOError):
                self.violations = {}
    
    def _save_logs(self):
        """Save permission logs to file."""
        data = {
            "violations": self.violations,
            "last_updated": datetime.now().isoformat()
        }
        with open(self.log_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def register_agent(self, agent_name: str, role: AgentRole):
        """Register an agent with a specific role."""
        self.agent_roles[agent_name] = role
        self._action_counts[agent_name] = {}
        self._hour_start[agent_name] = datetime.now()
    
    def register_agent_by_role_name(self, agent_name: str, role_name: str):
        """Register an agent using a predefined role name."""
        if role_name not in PREDEFINED_ROLES:
            raise ValueError(f"Unknown role: {role_name}")
        self.register_agent(agent_name, PREDEFINED_ROLES[role_name])
    
    def get_agent_role(self, agent_name: str) -> Optional[AgentRole]:
        """Get the role for an agent."""
        return self.agent_roles.get(agent_name)
    
    def check_permission(self, agent_name: str, permission: Permission) -> bool:
        """Check if agent has permission (non-throwing)."""
        role = self.agent_roles.get(agent_name)
        if not role:
            result = False
        else:
            result = role.has_permission(permission)
        
        self.log_permission_check(agent_name, permission, result)
        return result
    
    def require_permission(self, agent_name: str, permission: Permission):
        """Require permission, raise if denied."""
        if not self.check_permission(agent_name, permission):
            self._record_violation(agent_name, permission)
            raise PermissionDeniedError(agent_name, permission)
    
    def check_rate_limit(self, agent_name: str, action: str) -> bool:
        """Check if agent is within rate limits."""
        role = self.agent_roles.get(agent_name)
        if not role:
            return False
        
        limit = role.get_rate_limit(action)
        if limit is None:
            return True  # No limit set
        
        # Reset counts if hour has passed
        now = datetime.now()
        if agent_name in self._hour_start:
            elapsed = (now - self._hour_start[agent_name]).total_seconds()
            if elapsed >= 3600:
                self._action_counts[agent_name] = {}
                self._hour_start[agent_name] = now
        
        current_count = self._action_counts.get(agent_name, {}).get(action, 0)
        return current_count < limit
    
    def increment_action_count(self, agent_name: str, action: str):
        """Increment the action count for rate limiting."""
        if agent_name not in self._action_counts:
            self._action_counts[agent_name] = {}
        current = self._action_counts[agent_name].get(action, 0)
        self._action_counts[agent_name][action] = current + 1
    
    def get_agent_limits(self, agent_name: str) -> Dict[str, int]:
        """Get rate limits for an agent."""
        role = self.agent_roles.get(agent_name)
        if not role:
            return {}
        return role.rate_limits.copy()
    
    def get_remaining_quota(self, agent_name: str, action: str) -> Optional[int]:
        """Get remaining quota for an action."""
        role = self.agent_roles.get(agent_name)
        if not role:
            return 0
        
        limit = role.get_rate_limit(action)
        if limit is None:
            return None  # Unlimited
        
        current = self._action_counts.get(agent_name, {}).get(action, 0)
        return max(0, limit - current)
    
    def log_permission_check(self, agent_name: str, permission: Permission, result: bool):
        """Log a permission check."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "permission": permission.name,
            "granted": result
        }
        
        # Append to log file
        logs = []
        log_file = self.log_dir / "permission_checks.json"
        if log_file.exists():
            try:
                with open(log_file, 'r') as f:
                    logs = json.load(f)
            except (json.JSONDecodeError, IOError):
                logs = []
        
        logs.append(log_entry)
        
        # Keep last 1000 entries
        logs = logs[-1000:]
        
        with open(log_file, 'w') as f:
            json.dump(logs, f, indent=2)
    
    def _record_violation(self, agent_name: str, permission: Permission):
        """Record a permission violation."""
        if agent_name not in self.violations:
            self.violations[agent_name] = []
        
        self.violations[agent_name].append({
            "timestamp": datetime.now().isoformat(),
            "permission": permission.name,
            "message": f"Attempted unauthorized action: {permission.name}"
        })
        
        self._save_logs()
    
    def get_violations(self, agent_name: str) -> List[Dict]:
        """Get list of violations for an agent."""
        return self.violations.get(agent_name, [])
    
    def get_all_violations(self) -> Dict[str, List[Dict]]:
        """Get all violations across agents."""
        return self.violations.copy()
    
    def clear_violations(self, agent_name: str = None):
        """Clear violations for an agent or all agents."""
        if agent_name:
            self.violations[agent_name] = []
        else:
            self.violations = {}
        self._save_logs()
    
    def check_platform_access(self, agent_name: str, platform: str) -> bool:
        """Check if agent can access a platform."""
        role = self.agent_roles.get(agent_name)
        if not role:
            return False
        return role.can_access_platform(platform)
    
    def needs_approval(self, agent_name: str, permission: Permission) -> bool:
        """Check if action needs Gatekeeper approval."""
        role = self.agent_roles.get(agent_name)
        if not role:
            return True  # Unknown agents need approval for everything
        return role.needs_approval(permission)


# Global permission guard instance
_guard: Optional[PermissionGuard] = None


def get_permission_guard() -> PermissionGuard:
    """Get or create the global permission guard."""
    global _guard
    if _guard is None:
        _guard = PermissionGuard()
    return _guard


def requires_permission(*permissions: Permission):
    """Decorator to require permissions for a function.
    
    Usage:
        @requires_permission(Permission.SEND_EMAIL)
        def send_campaign_email(agent_name: str, ...):
            ...
    
    The decorated function must have 'agent_name' as its first argument.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Get agent_name from args or kwargs
            agent_name = kwargs.get('agent_name') or (args[0] if args else None)
            
            if not agent_name:
                raise ValueError("requires_permission: agent_name must be provided")
            
            guard = get_permission_guard()
            
            for permission in permissions:
                guard.require_permission(agent_name, permission)
                
                # Check rate limit if action matches permission
                action = permission.name.lower()
                if not guard.check_rate_limit(agent_name, action):
                    raise PermissionDeniedError(
                        agent_name, 
                        permission, 
                        f"Rate limit exceeded for {action}"
                    )
                guard.increment_action_count(agent_name, action)
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def requires_platform(platform: str):
    """Decorator to require platform access for a function."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            agent_name = kwargs.get('agent_name') or (args[0] if args else None)
            
            if not agent_name:
                raise ValueError("requires_platform: agent_name must be provided")
            
            guard = get_permission_guard()
            
            if not guard.check_platform_access(agent_name, platform):
                raise PermissionDeniedError(
                    agent_name,
                    Permission.ADMIN_ACCESS,
                    f"Agent '{agent_name}' cannot access platform: {platform}"
                )
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


# Example usage functions
@requires_permission(Permission.SEND_EMAIL)
def send_email(agent_name: str, to: str, subject: str, body: str) -> Dict:
    """Send an email (requires SEND_EMAIL permission)."""
    return {"status": "sent", "to": to, "subject": subject}


@requires_permission(Permission.SEND_BULK)
def send_bulk_campaign(agent_name: str, campaign_id: str, recipients: List[str]) -> Dict:
    """Send bulk campaign (requires SEND_BULK permission)."""
    return {"status": "queued", "campaign_id": campaign_id, "count": len(recipients)}


@requires_permission(Permission.APPROVE_CAMPAIGN)
def approve_campaign(agent_name: str, campaign_id: str) -> Dict:
    """Approve a campaign (requires APPROVE_CAMPAIGN permission)."""
    return {"status": "approved", "campaign_id": campaign_id}


@requires_platform("GoHighLevel")
@requires_permission(Permission.TRIGGER_WORKFLOW)
def trigger_ghl_workflow(agent_name: str, workflow_id: str, contact_id: str) -> Dict:
    """Trigger a GHL workflow (requires platform access and permission)."""
    return {"status": "triggered", "workflow_id": workflow_id}


def main():
    """Demo showing each agent's permissions."""
    print("=" * 60)
    print("AGENT PERMISSION SYSTEM DEMO")
    print("=" * 60)
    
    guard = get_permission_guard()
    
    # Register all agents with their roles
    agents = [
        ("hunter_agent", "HUNTER"),
        ("enricher_agent", "ENRICHER"),
        ("segmentor_agent", "SEGMENTOR"),
        ("crafter_agent", "CRAFTER"),
        ("gatekeeper_agent", "GATEKEEPER"),
        ("ghl_master_agent", "GHL_MASTER"),
        ("queen_agent", "QUEEN"),
    ]
    
    for agent_name, role_name in agents:
        guard.register_agent_by_role_name(agent_name, role_name)
    
    # Display each agent's permissions
    print("\n[AGENT PERMISSIONS OVERVIEW]\n")
    
    for agent_name, role_name in agents:
        role = guard.get_agent_role(agent_name)
        print(f"[AGENT] {agent_name} ({role_name})")
        print(f"   Permissions: {', '.join(p.name for p in role.permissions)}")
        print(f"   Platforms: {', '.join(role.allowed_platforms)}")
        if role.rate_limits:
            print(f"   Rate Limits: {role.rate_limits}")
        if role.requires_approval_for:
            print(f"   Needs Approval: {', '.join(p.name for p in role.requires_approval_for)}")
        print()
    
    # Demo permission checks
    print("=" * 60)
    print("PERMISSION CHECK DEMOS")
    print("=" * 60)
    
    test_cases = [
        ("hunter_agent", Permission.READ_LEADS, "Hunter reading leads"),
        ("hunter_agent", Permission.SEND_EMAIL, "Hunter sending email"),
        ("crafter_agent", Permission.WRITE_LEADS, "Crafter writing leads"),
        ("crafter_agent", Permission.SEND_EMAIL, "Crafter sending email"),
        ("ghl_master_agent", Permission.SEND_EMAIL, "GHL Master sending email"),
        ("gatekeeper_agent", Permission.APPROVE_CAMPAIGN, "Gatekeeper approving"),
        ("queen_agent", Permission.ADMIN_ACCESS, "Queen admin access"),
    ]
    
    print("\n[Permission Checks]\n")
    for agent, perm, desc in test_cases:
        result = guard.check_permission(agent, perm)
        status = "[GRANTED]" if result else "[DENIED]"
        print(f"   {desc}: {status}")
    
    # Demo platform access
    print("\n[Platform Access]\n")
    platform_tests = [
        ("hunter_agent", "LinkedIn"),
        ("hunter_agent", "GoHighLevel"),
        ("enricher_agent", "Clay"),
        ("ghl_master_agent", "GoHighLevel"),
        ("queen_agent", "All"),
    ]
    
    for agent, platform in platform_tests:
        result = guard.check_platform_access(agent, platform)
        status = "[ALLOWED]" if result else "[BLOCKED]"
        print(f"   {agent} -> {platform}: {status}")
    
    # Demo decorated functions
    print("\n[Decorated Function Demos]\n")
    
    # GHL Master can send email
    try:
        result = send_email("ghl_master_agent", "test@example.com", "Hello", "Body")
        print(f"   GHL Master send_email: [OK] {result}")
    except PermissionDeniedError as e:
        print(f"   GHL Master send_email: [DENIED] {e.message}")
    
    # Hunter cannot send email
    try:
        result = send_email("hunter_agent", "test@example.com", "Hello", "Body")
        print(f"   Hunter send_email: [OK] {result}")
    except PermissionDeniedError as e:
        print(f"   Hunter send_email: [DENIED] {e.message}")
    
    # Gatekeeper can approve
    try:
        result = approve_campaign("gatekeeper_agent", "camp_123")
        print(f"   Gatekeeper approve: [OK] {result}")
    except PermissionDeniedError as e:
        print(f"   Gatekeeper approve: [DENIED] {e.message}")
    
    # Show violations
    print("\n[Recorded Violations]\n")
    all_violations = guard.get_all_violations()
    for agent, violations in all_violations.items():
        if violations:
            print(f"   {agent}: {len(violations)} violation(s)")
            for v in violations[-3:]:  # Show last 3
                print(f"      - {v['permission']} at {v['timestamp']}")
    
    # Show rate limits
    print("\n[Rate Limits Example (GHL Master)]\n")
    limits = guard.get_agent_limits("ghl_master_agent")
    for action, limit in limits.items():
        remaining = guard.get_remaining_quota("ghl_master_agent", action)
        print(f"   {action}: {remaining}/{limit} remaining")
    
    print("\n" + "=" * 60)
    print("Permission logs saved to: .hive-mind/permission_log.json")
    print("=" * 60)


if __name__ == "__main__":
    main()
