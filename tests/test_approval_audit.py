
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from core.approval_engine import ApprovalEngine

@pytest.fixture
def temp_storage_dir(tmp_path):
    storage_dir = tmp_path / "approvals_audit"
    storage_dir.mkdir(parents=True, exist_ok=True)
    yield storage_dir

@pytest.fixture
def engine(temp_storage_dir):
    return ApprovalEngine(storage_dir=temp_storage_dir)

@pytest.mark.asyncio
async def test_audit_logging_on_submit(engine):
    with patch("core.approval_engine.get_audit_trail", new_callable=AsyncMock) as mock_get_audit:
        mock_audit = AsyncMock()
        mock_get_audit.return_value = mock_audit
        
        # Submit request
        req = engine.submit_request(
            requester_agent="TESTER",
            action_type="audit_test",
            payload={"foo": "bar"},
            risk_score=0.5
        )
        
        # Allow async task to run
        await asyncio.sleep(0.1)
        
        # Verify get_audit_trail was called
        mock_get_audit.assert_called()
        
        # Verify log_action was called
        mock_audit.log_action.assert_called()
        call_args = mock_audit.log_action.call_args
        assert call_args is not None
        kwargs = call_args.kwargs
        assert kwargs['action_type'] == "approval_requested"
        assert kwargs['agent_name'] == "ApprovalEngine"
        assert kwargs['details']['action_type'] == "audit_test"

@pytest.mark.asyncio
async def test_audit_logging_on_approval(engine):
    with patch("core.approval_engine.get_audit_trail", new_callable=AsyncMock) as mock_get_audit:
        mock_audit = AsyncMock()
        mock_get_audit.return_value = mock_audit
        
        # Submit first (will log submit)
        req = engine.submit_request(
            requester_agent="TESTER",
            action_type="approve_test",
            payload={},
            risk_score=0.5
        )
        
        # Reset mock to test approval specifically
        await asyncio.sleep(0.1) 
        mock_audit.log_action.reset_mock()
        
        # Approve
        engine.approve_request(req.request_id, "approver_1")
        
        # Wait
        await asyncio.sleep(0.1)
        
        # Verify log
        mock_audit.log_action.assert_called()
        kwargs = mock_audit.log_action.call_args.kwargs
        assert kwargs['action_type'] == "approval_granted"
        assert kwargs['details']['approver'] == "approver_1"
