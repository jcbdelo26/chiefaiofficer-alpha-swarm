#!/usr/bin/env python3
"""
Tests for Day 23 Approval Engine
- Manual approval workflow
- Auto-approval logic
- Rejection workflow
- Persistence
"""

import pytest
import shutil
import json
from pathlib import Path
from core.approval_engine import (
    ApprovalEngine, 
    ApprovalStatus, 
    ApprovalRequest
)

@pytest.fixture
def temp_storage_dir(tmp_path):
    """Create temporary storage directory."""
    storage_dir = tmp_path / "approvals"
    storage_dir.mkdir(parents=True, exist_ok=True)
    yield storage_dir
    # Cleanup
    if storage_dir.exists():
        shutil.rmtree(storage_dir)

@pytest.fixture
def engine(temp_storage_dir):
    """Create engine instance with temp storage."""
    return ApprovalEngine(storage_dir=temp_storage_dir)

def test_submit_manual_request(engine):
    """Test submitting a high-risk request requiring manual approval."""
    req = engine.submit_request(
        requester_agent="CRAFTER",
        action_type="campaign_launch",
        payload={"campaign_id": "123"},
        description="Launch massive campaign",
        risk_score=0.8
    )
    
    assert req.status == ApprovalStatus.PENDING.value
    assert req.request_id in engine.requests
    assert len(engine.get_pending_requests()) == 1

def test_auto_approve_request(engine):
    """Test submitting a low-risk request that should be auto-approved."""
    req = engine.submit_request(
        requester_agent="SCHEDULER",
        action_type="calendar_create",
        payload={"event": "meeting"},
        description="Schedule internal sync",
        risk_score=0.1
    )
    
    assert req.status == ApprovalStatus.AUTO_APPROVED.value
    assert len(engine.get_pending_requests()) == 0

def test_high_risk_override(engine):
    """Test that HIGH_RISK_ACTIONS are not auto-approved even with low risk score."""
    req = engine.submit_request(
        requester_agent="ADMIN",
        action_type="bulk_delete",
        payload={"filter": "all"},
        description="Delete everything",
        risk_score=0.1  # Low score but dangerous action
    )
    
    assert req.status == ApprovalStatus.PENDING.value

def test_approve_workflow(engine):
    """Test approving a pending request."""
    # Submit first
    req = engine.submit_request(
        requester_agent="CRAFTER",
        action_type="content_post",
        payload={"content": "hello"},
        risk_score=0.5
    )
    
    # Approve
    approved_req = engine.approve_request(
        req.request_id,
        approver_id="USER_1",
        notes="Looks good"
    )
    
    assert approved_req.status == ApprovalStatus.APPROVED.value
    assert approved_req.approver_id == "USER_1"
    assert approved_req.approver_notes == "Looks good"
    assert len(engine.get_pending_requests()) == 0

def test_reject_workflow(engine):
    """Test rejecting a pending request."""
    req = engine.submit_request(
        requester_agent="CRAFTER",
        action_type="content_post",
        payload={"content": "bad content"},
        risk_score=0.5
    )
    
    rejected_req = engine.reject_request(
        req.request_id,
        approver_id="USER_1",
        notes="Unsafe content"
    )
    
    assert rejected_req.status == ApprovalStatus.REJECTED.value
    assert len(engine.get_pending_requests()) == 0

def test_persistence(temp_storage_dir):
    """Test that requests are saved and loaded correctly."""
    # Creates engine, saves request
    engine1 = ApprovalEngine(storage_dir=temp_storage_dir)
    req = engine1.submit_request(
        requester_agent="TESTER",
        action_type="test_action",
        payload={"foo": "bar"},
        risk_score=0.5
    )
    
    # Re-instantiate engine
    engine2 = ApprovalEngine(storage_dir=temp_storage_dir)
    loaded_req = engine2.get_request(req.request_id)
    
    assert loaded_req is not None
    assert loaded_req.action_type == "test_action"
    assert loaded_req.payload == {"foo": "bar"}
    assert loaded_req.status == ApprovalStatus.PENDING.value

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
