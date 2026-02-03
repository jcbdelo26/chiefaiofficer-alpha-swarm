#!/usr/bin/env python3
"""
Approval Engine - Centralized Human-in-the-Loop Verification
============================================================

Manages sensitive actions (e.g., campaign launches, bulk data updates) 
requiring human approval. Routes requests based on risk analysis and 
handles notifications.

Key Features:
- Centralized request tracking
- Risk-based routing (Auto-approve vs Manual)
- Persistence in .hive-mind/approvals/
- Integration points for Slack/Email notifications
"""

import json
import uuid
import logging
import threading
import os
import tempfile
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from pathlib import Path
import asyncio

from core.notifications import get_notification_manager
from core.audit_trail import get_audit_trail

logger = logging.getLogger("approval_engine")

SENSITIVE_KEYS = {"api_key", "token", "password", "secret", "authorization", "credential"}


@dataclass
class ApprovalPolicyConfig:
    """Policy configuration for approval logic."""
    action_type: str = ""
    requires_approval: bool = True
    auto_approve_threshold: float = 0.3
    expiry_hours: int = 24


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"
    EXPIRED = "expired"


class ApprovalPolicy(Enum):
    """Policy for approval stringency."""
    STRICT = "strict"      # No auto-approvals
    STANDARD = "standard"  # Auto-approve low risk
    LENIENT = "lenient"    # Auto-approve medium risk

@dataclass
class ApprovalRequest:
    request_id: str
    requester_agent: str
    action_type: str
    payload: Dict[str, Any]
    risk_score: float
    status: str  # Stored as string matching ApprovalStatus values
    created_at: str
    updated_at: str
    description: str = ""
    approver_notes: Optional[str] = None
    approver_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ApprovalRequest':
        """Create from dictionary."""
        return cls(**data)

@dataclass
class ApprovalResult:
    """Result returned to calling agent."""
    request_id: str
    status: str
    auto_approved: bool
    approved: bool
    reason: Optional[str] = None

def _redact_sensitive(data: Dict[str, Any]) -> Dict[str, Any]:
    """Redact sensitive fields from payload before persistence/logging."""
    if not isinstance(data, dict):
        return data
    redacted = {}
    for k, v in data.items():
        if any(sk in k.lower() for sk in SENSITIVE_KEYS):
            redacted[k] = "[REDACTED]"
        elif isinstance(v, dict):
            redacted[k] = _redact_sensitive(v)
        else:
            redacted[k] = v
    return redacted


class ApprovalEngine:
    """
    Central engine for managing approval workflows.
    """
    
    # Actions that can be auto-approved if risk is low
    # SECURITY FIX: Removed send_email and bulk_email - all outbound must require human approval
    # in production/shadow/assisted phases per production.json require_approval: true
    AUTO_APPROVABLE_ACTIONS = {
        "calendar_create", 
        "crm_update",
        "task_creation",
        # "email_send",  # DISABLED - requires human approval
        # "send_email",  # DISABLED - requires human approval
        # "bulk_email",  # DISABLED - requires human approval
    }
    
    # Actions that ALWAYS require manual review regardless of risk
    HIGH_RISK_ACTIONS = {
        "campaign_launch",
        "bulk_delete",
        "contract_send",
        "pricing_change",
        "system_configuration"
    }
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or Path(".hive-mind/approvals")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.requests_file = self.storage_dir / "requests.json"
        
        self._lock = threading.Lock()
        self.requests: Dict[str, ApprovalRequest] = {}
        self._load_requests()

    async def request_approval(
        self,
        action_type: str,
        agent_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> ApprovalResult:
        """Compatibility method for Gatekeeper integration."""
        # Calculate risk based on urgency in context
        risk_score = 0.1
        if context and 'urgency' in context:
            urgency = context['urgency']
            if urgency == "critical":
                risk_score = 0.9
            elif urgency == "urgent":
                risk_score = 0.7
            elif urgency == "normal":
                risk_score = 0.1

        # Map parameters to engine format
        req = self.submit_request(
            requester_agent=agent_name,
            action_type=action_type,
            payload=parameters,
            description=f"{action_type} requested by {agent_name}",
            risk_score=risk_score,
            metadata=context
        )
        
        return ApprovalResult(
            request_id=req.request_id,
            status=req.status,
            auto_approved=req.status == ApprovalStatus.AUTO_APPROVED.value,
            approved=req.status == ApprovalStatus.APPROVED.value or req.status == ApprovalStatus.AUTO_APPROVED.value,
            reason=req.approver_notes
        )

    def get_policy(self, action_type: str) -> ApprovalPolicyConfig:
        """Get approval policy configuration for an action type."""
        requires_approval = action_type not in self.AUTO_APPROVABLE_ACTIONS
        return ApprovalPolicyConfig(
            action_type=action_type,
            requires_approval=requires_approval,
            auto_approve_threshold=0.3 if action_type in self.AUTO_APPROVABLE_ACTIONS else 0.0,
            expiry_hours=24
        )
        
    def _load_requests(self):
        """Load requests from persistence."""
        if not self.requests_file.exists():
            return
            
        try:
            with open(self.requests_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for req_data in data:
                    try:
                        req = ApprovalRequest.from_dict(req_data)
                        self.requests[req.request_id] = req
                    except (KeyError, TypeError) as e:
                        logger.warning(f"Skipping malformed request: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted requests file, backing up: {e}")
            backup = self.requests_file.with_suffix(".json.bak")
            self.requests_file.rename(backup)
        except OSError as e:
            logger.error(f"Failed to load requests file: {e}")
            
    def _save_requests(self):
        """Save requests to persistence with atomic write."""
        with self._lock:
            try:
                data = [_redact_sensitive(req.to_dict()) for req in self.requests.values()]
                fd, tmp_path = tempfile.mkstemp(
                    dir=self.storage_dir, suffix=".tmp", prefix="requests_"
                )
                try:
                    with os.fdopen(fd, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, sort_keys=True)
                    os.replace(tmp_path, self.requests_file)
                except Exception:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    raise
            except OSError as e:
                logger.exception(f"Failed to save requests: {e}")
                raise

    def should_auto_approve(self, action_type: str, risk_score: float) -> bool:
        """
        Determine if a request can be auto-approved.
        
        Rules:
        1. Must be in AUTO_APPROVABLE_ACTIONS
        2. Must NOT be in HIGH_RISK_ACTIONS
        3. Risk score must be low (< 0.3)
        """
        if action_type in self.HIGH_RISK_ACTIONS:
            return False
            
        if action_type not in self.AUTO_APPROVABLE_ACTIONS:
            return False
            
        return risk_score < 0.3

    def submit_request(
        self, 
        requester_agent: str, 
        action_type: str, 
        payload: Dict[str, Any],
        description: str = "",
        risk_score: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ApprovalRequest:
        """
        Submit a new approval request.
        
        Args:
            requester_agent: Agent submitting the request (e.g., "CRAFTER")
            action_type: Type of action (e.g., "campaign_launch")
            payload: Data required to execute the action
            description: Human-readable description
            risk_score: assessed risk (0.0 - 1.0)
            metadata: Additional context
            
        Returns:
            Created ApprovalRequest
        """
        now = datetime.now(timezone.utc).isoformat()
        request_id = f"req_{uuid.uuid4().hex[:8]}"
        
        # Determine initial status
        if self.should_auto_approve(action_type, risk_score):
            status = ApprovalStatus.AUTO_APPROVED.value
        else:
            status = ApprovalStatus.PENDING.value
            
        request = ApprovalRequest(
            request_id=request_id,
            requester_agent=requester_agent,
            action_type=action_type,
            payload=payload,
            risk_score=risk_score,
            status=status,
            created_at=now,
            updated_at=now,
            description=description,
            metadata=metadata or {}
        )
        
        self.requests[request_id] = request
        self._save_requests()
        
        if status == ApprovalStatus.PENDING.value:
            self._notify_approvers(request)
        
        self._dispatch_audit(request, "approval_requested", {"status": status})
        return request
    
    def _dispatch_audit(self, request: ApprovalRequest, event_type: str, extra: Dict[str, Any]):
        """Dispatch async audit logging, falling back to sync log if no event loop."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._log_audit_async(request, event_type, extra))
        except RuntimeError:
            logger.info(f"Audit[{event_type}]: request_id={request.request_id}, status={request.status}")

    def approve_request(
        self, 
        request_id: str, 
        approver_id: str, 
        notes: str = ""
    ) -> ApprovalRequest:
        """
        Approve a pending request.
        """
        if request_id not in self.requests:
            raise ValueError(f"Request {request_id} not found")
            
        request = self.requests[request_id]
        
        # Can only approve pending requests
        if request.status != ApprovalStatus.PENDING.value:
            raise ValueError(f"Request {request_id} is in status {request.status}, cannot approve")
            
        request.status = ApprovalStatus.APPROVED.value
        request.approver_id = approver_id
        request.approver_notes = notes
        request.updated_at = datetime.now(timezone.utc).isoformat()
        
        self._save_requests()
        self._execute_approved_action(request)
        self._dispatch_audit(request, "approval_granted", {"approver": approver_id, "notes": notes})
        return request

    def reject_request(
        self, 
        request_id: str, 
        approver_id: str, 
        notes: str = ""
    ) -> ApprovalRequest:
        """
        Reject a pending request.
        """
        if request_id not in self.requests:
            raise ValueError(f"Request {request_id} not found")
            
        request = self.requests[request_id]
        
        if request.status != ApprovalStatus.PENDING.value:
            raise ValueError(f"Request {request_id} is in status {request.status}, cannot reject")
            
        request.status = ApprovalStatus.REJECTED.value
        request.approver_id = approver_id
        request.approver_notes = notes
        request.updated_at = datetime.now(timezone.utc).isoformat()
        
        self._save_requests()
        self._dispatch_audit(request, "approval_rejected", {"approver": approver_id, "notes": notes})
        return request

    async def process_approval(
        self,
        request_id: str,
        approved: bool,
        approver: str,
        reason: str = ""
    ) -> ApprovalRequest:
        """
        Process an approval decision (approve or reject).
        
        Async wrapper for approve_request/reject_request for gatekeeper compatibility.
        """
        if approved:
            return self.approve_request(request_id, approver, reason)
        else:
            return self.reject_request(request_id, approver, reason)

    def get_pending_requests(self) -> List[ApprovalRequest]:
        """Get all requests requiring approval."""
        return [
            req for req in self.requests.values() 
            if req.status == ApprovalStatus.PENDING.value
        ]

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        """Get a specific request."""
        return self.requests.get(request_id)

    async def _notify_async(self, request: ApprovalRequest):
        """Async helper to send notifications."""
        try:
            manager = get_notification_manager()
            # Map request to notification schema if needed, but Manager is now generic
            # Ensure critical items are escalated
            level = 1
            if request.risk_score >= 0.7:
                level = 2
            if request.risk_score >= 0.9:
                level = 3
                
            await manager.escalate(request, level=level)
            logger.info(f"Notification sent for {request.request_id}")
        except Exception as e:
            logger.error(f"Failed to send async notification for {request.request_id}: {e}")

    async def _log_audit_async(self, request: ApprovalRequest, event_type: str, extra_details: Dict[str, Any]):
        """Log approval event to audit trail."""
        try:
            audit = await get_audit_trail()
            await audit.log_action(
                agent_name="ApprovalEngine",
                action_type=event_type,
                details={**request.to_dict(), **extra_details},
                status="success",
                risk_level="MEDIUM", # Default for generic approval log
                target_resource=request.action_type,
                approval_status=request.status
            )
        except Exception as e:
            logger.error(f"Failed to log audit event for {request.request_id}: {e}")

    def _notify_approvers(self, request: ApprovalRequest):
        """
        Send notification to approvers (Slack/Email).
        Dispatches to async handler if event loop is running.
        """
        logger.info(f"NOTIFICATION: New approval request {request.request_id} from {request.requester_agent}: {request.description}")
        
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._notify_async(request))
        except RuntimeError:
            logger.warning(f"No running event loop - skipping async notification for {request.request_id}")


    def _execute_approved_action(self, request: ApprovalRequest):
        """
        Execute the action after approval.
        
        Writes approved request to execution queue for OPERATOR agent to pick up.
        This decouples approval from execution and allows async processing.
        """
        logger.info(f"EXECUTION: Queuing approved action {request.action_type} for {request.request_id}")
        
        # Write to execution queue
        execution_queue_dir = self.storage_dir.parent / "execution_queue"
        execution_queue_dir.mkdir(parents=True, exist_ok=True)
        
        queue_file = execution_queue_dir / f"{request.request_id}.json"
        
        execution_item = {
            "request_id": request.request_id,
            "action_type": request.action_type,
            "payload": _redact_sensitive(request.payload),
            "requester_agent": request.requester_agent,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "approver_id": request.approver_id,
            "approver_notes": request.approver_notes,
            "status": "pending_execution",
            "execution_attempts": 0
        }
        
        with open(queue_file, 'w', encoding='utf-8') as f:
            json.dump(execution_item, f, indent=2)
        
        logger.info(f"Approved action queued for execution: {queue_file}")
    
    def get_pending_executions(self) -> List[Dict[str, Any]]:
        """Get all approved actions pending execution."""
        execution_queue_dir = self.storage_dir.parent / "execution_queue"
        if not execution_queue_dir.exists():
            return []
        
        pending = []
        for queue_file in execution_queue_dir.glob("*.json"):
            try:
                with open(queue_file, 'r', encoding='utf-8') as f:
                    item = json.load(f)
                if item.get("status") == "pending_execution":
                    item["queue_file"] = str(queue_file)
                    pending.append(item)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Error reading queue file {queue_file}: {e}")
        
        return pending
    
    def mark_executed(self, request_id: str, success: bool, result: Optional[Dict] = None):
        """Mark an approved action as executed."""
        execution_queue_dir = self.storage_dir.parent / "execution_queue"
        queue_file = execution_queue_dir / f"{request_id}.json"
        
        if not queue_file.exists():
            logger.warning(f"Execution queue file not found: {request_id}")
            return
        
        try:
            with open(queue_file, 'r', encoding='utf-8') as f:
                item = json.load(f)
            
            item["status"] = "executed" if success else "failed"
            item["executed_at"] = datetime.now(timezone.utc).isoformat()
            item["execution_result"] = result or {}
            item["execution_attempts"] = item.get("execution_attempts", 0) + 1
            
            with open(queue_file, 'w', encoding='utf-8') as f:
                json.dump(item, f, indent=2)
            
            logger.info(f"Marked {request_id} as {'executed' if success else 'failed'}")
            
        except Exception as e:
            logger.error(f"Error marking execution status for {request_id}: {e}")

_engine_instance: Optional[ApprovalEngine] = None
_engine_lock = threading.Lock()


def get_approval_engine() -> ApprovalEngine:
    """Get thread-safe singleton instance of ApprovalEngine."""
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = ApprovalEngine()
    return _engine_instance
