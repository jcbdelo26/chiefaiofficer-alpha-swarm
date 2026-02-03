"""Tests for the AuditTrail system with Day 18 PII redaction."""

import pytest
import asyncio
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil

from core.audit_trail import (
    AuditTrail, AuditEntry, get_audit_trail,
    PIIRedactor, PIIType, ApprovalStatus
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def audit_trail(temp_dir):
    """Create an AuditTrail instance with temp storage."""
    db_path = temp_dir / "audit.db"
    backup_dir = temp_dir / "backup"
    return AuditTrail(db_path=db_path, backup_dir=backup_dir)


@pytest.mark.asyncio
async def test_log_action_and_retrieve(audit_trail):
    """Test logging an action and retrieving it."""
    entry_id = await audit_trail.log_action(
        agent_name="TestAgent",
        action_type="email_send",
        details={"recipient": "test@example.com", "subject": "Hello"},
        status="success",
        risk_level="LOW",
        duration_ms=150.5,
        redact_pii=False  # Disable redaction for this test
    )

    assert entry_id is not None
    assert entry_id > 0

    logs = await audit_trail.get_logs(agent_name="TestAgent")
    assert len(logs) == 1
    assert logs[0]["agent_name"] == "TestAgent"
    assert logs[0]["action_type"] == "email_send"
    assert logs[0]["action_details"]["recipient"] == "test@example.com"
    assert logs[0]["status"] == "success"
    assert logs[0]["risk_level"] == "LOW"
    assert logs[0]["duration_ms"] == 150.5


@pytest.mark.asyncio
async def test_log_action_with_error(audit_trail):
    """Test logging a failed action with error message."""
    entry_id = await audit_trail.log_action(
        agent_name="FailingAgent",
        action_type="api_call",
        details={"endpoint": "/api/test"},
        status="failure",
        risk_level="HIGH",
        error="Connection timeout"
    )

    logs = await audit_trail.get_logs(agent_name="FailingAgent")
    assert len(logs) == 1
    assert logs[0]["status"] == "failure"
    assert logs[0]["error_message"] == "Connection timeout"


@pytest.mark.asyncio
async def test_log_action_with_grounding_evidence(audit_trail):
    """Test logging an action with grounding evidence."""
    evidence = {
        "source": "CRM",
        "record_id": "12345",
        "verified_at": datetime.now(timezone.utc).isoformat()
    }

    await audit_trail.log_action(
        agent_name="DataAgent",
        action_type="data_fetch",
        details={"query": "SELECT *"},
        status="success",
        risk_level="MEDIUM",
        grounding_evidence=evidence
    )

    logs = await audit_trail.get_logs(agent_name="DataAgent")
    assert logs[0]["grounding_evidence"]["source"] == "CRM"
    assert logs[0]["grounding_evidence"]["record_id"] == "12345"


@pytest.mark.asyncio
async def test_query_by_agent_name(audit_trail):
    """Test querying logs by agent name."""
    await audit_trail.log_action("Agent1", "action", {}, "success", "LOW")
    await audit_trail.log_action("Agent2", "action", {}, "success", "LOW")
    await audit_trail.log_action("Agent1", "action", {}, "success", "LOW")

    logs = await audit_trail.get_logs(agent_name="Agent1")
    assert len(logs) == 2
    assert all(log["agent_name"] == "Agent1" for log in logs)


@pytest.mark.asyncio
async def test_query_by_action_type(audit_trail):
    """Test querying logs by action type."""
    await audit_trail.log_action("Agent", "email", {}, "success", "LOW")
    await audit_trail.log_action("Agent", "sms", {}, "success", "LOW")
    await audit_trail.log_action("Agent", "email", {}, "success", "LOW")

    logs = await audit_trail.get_logs(action_type="email")
    assert len(logs) == 2
    assert all(log["action_type"] == "email" for log in logs)


@pytest.mark.asyncio
async def test_query_by_date_range(audit_trail):
    """Test querying logs by date range."""
    await audit_trail.log_action("Agent", "action", {}, "success", "LOW")

    now = datetime.now(timezone.utc)
    start = (now - timedelta(hours=1)).isoformat()
    end = (now + timedelta(hours=1)).isoformat()

    logs = await audit_trail.get_logs(start_date=start, end_date=end)
    assert len(logs) == 1

    future = (now + timedelta(days=1)).isoformat()
    logs = await audit_trail.get_logs(start_date=future)
    assert len(logs) == 0


@pytest.mark.asyncio
async def test_query_with_limit(audit_trail):
    """Test query limit parameter."""
    for i in range(10):
        await audit_trail.log_action("Agent", "action", {"i": i}, "success", "LOW")

    logs = await audit_trail.get_logs(limit=5)
    assert len(logs) == 5


@pytest.mark.asyncio
async def test_get_agent_stats(audit_trail):
    """Test getting agent statistics."""
    await audit_trail.log_action("StatsAgent", "action1", {}, "success", "LOW", duration_ms=100)
    await audit_trail.log_action("StatsAgent", "action1", {}, "success", "LOW", duration_ms=200)
    await audit_trail.log_action("StatsAgent", "action2", {}, "failure", "HIGH", duration_ms=50)
    await audit_trail.log_action("StatsAgent", "action2", {}, "success", "LOW", duration_ms=150)

    stats = await audit_trail.get_agent_stats("StatsAgent", days=7)

    assert stats["total_actions"] == 4
    assert stats["successes"] == 3
    assert stats["failures"] == 1
    assert stats["success_rate"] == 75.0
    assert stats["avg_duration"] > 0
    assert "action1" in stats["action_counts"]
    assert "action2" in stats["action_counts"]
    assert stats["action_counts"]["action1"] == 2
    assert stats["action_counts"]["action2"] == 2


@pytest.mark.asyncio
async def test_get_agent_stats_no_data(audit_trail):
    """Test agent stats with no data."""
    stats = await audit_trail.get_agent_stats("NonexistentAgent", days=7)

    assert stats["total_actions"] == 0
    assert stats["success_rate"] == 0.0
    assert stats["action_counts"] == {}


@pytest.mark.asyncio
async def test_get_daily_summary(audit_trail):
    """Test getting daily summary."""
    await audit_trail.log_action("Agent1", "email", {}, "success", "LOW")
    await audit_trail.log_action("Agent1", "sms", {}, "failure", "MEDIUM")
    await audit_trail.log_action("Agent2", "email", {}, "success", "LOW")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    summary = await audit_trail.get_daily_summary(today)

    assert summary["date"] == today
    assert summary["total_actions"] == 3
    assert summary["total_successes"] == 2
    assert summary["total_failures"] == 1
    assert "Agent1" in summary["by_agent"]
    assert "Agent2" in summary["by_agent"]
    assert "email" in summary["by_action_type"]
    assert "sms" in summary["by_action_type"]


@pytest.mark.asyncio
async def test_get_daily_summary_defaults_to_today(audit_trail):
    """Test that daily summary defaults to today."""
    await audit_trail.log_action("Agent", "action", {}, "success", "LOW")

    summary = await audit_trail.get_daily_summary()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert summary["date"] == today


@pytest.mark.asyncio
async def test_search_logs(audit_trail):
    """Test full-text search in logs."""
    await audit_trail.log_action(
        "SearchAgent", "email",
        {"content": "Hello world from test"},
        "success", "LOW"
    )
    await audit_trail.log_action(
        "SearchAgent", "sms",
        {"content": "Goodbye universe"},
        "success", "LOW"
    )

    results = await audit_trail.search_logs("world")
    assert len(results) == 1
    assert "world" in results[0]["action_details"]["content"]

    results = await audit_trail.search_logs("SearchAgent")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_search_logs_in_error_message(audit_trail):
    """Test search finds text in error messages."""
    await audit_trail.log_action(
        "Agent", "action", {},
        "failure", "HIGH",
        error="Database connection failed"
    )

    results = await audit_trail.search_logs("Database")
    assert len(results) == 1
    assert "Database" in results[0]["error_message"]


@pytest.mark.asyncio
async def test_retention_cleanup(audit_trail, temp_dir):
    """Test 90-day retention cleanup."""
    await audit_trail.initialize()

    import aiosqlite

    old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    async with aiosqlite.connect(str(audit_trail.db_path)) as db:
        await db.execute(
            """
            INSERT INTO audit_log 
            (timestamp, agent_name, action_type, action_details, status, risk_level)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (old_date, "OldAgent", "old_action", "{}", "success", "LOW")
        )
        await db.commit()

    await audit_trail.log_action("NewAgent", "new_action", {}, "success", "LOW")

    logs_before = await audit_trail.get_logs(limit=1000)
    assert len(logs_before) == 2

    result = await audit_trail.run_retention_cleanup()

    assert result["deleted_logs"] == 1

    logs_after = await audit_trail.get_logs(limit=1000)
    assert len(logs_after) == 1
    assert logs_after[0]["agent_name"] == "NewAgent"


@pytest.mark.asyncio
async def test_json_backup_creation(audit_trail, temp_dir):
    """Test JSON backup file creation."""
    await audit_trail.log_action("BackupAgent", "action", {"test": "data"}, "success", "LOW")

    backup_path = await audit_trail.create_daily_backup()

    assert backup_path.exists()
    with open(backup_path) as f:
        backup_data = json.load(f)

    assert "date" in backup_data
    assert "logs" in backup_data
    assert backup_data["count"] >= 1


@pytest.mark.asyncio
async def test_backup_directory_auto_creation(temp_dir):
    """Test that backup directory is auto-created."""
    new_backup_dir = temp_dir / "new_backup_dir"
    trail = AuditTrail(
        db_path=temp_dir / "audit.db",
        backup_dir=new_backup_dir
    )

    await trail.initialize()

    assert new_backup_dir.exists()


@pytest.mark.asyncio
async def test_weekly_report_generation(audit_trail):
    """Test weekly report generation."""
    await audit_trail.log_action("Agent1", "email", {}, "success", "LOW", duration_ms=100)
    await audit_trail.log_action("Agent1", "email", {}, "success", "LOW", duration_ms=150)
    await audit_trail.log_action("Agent2", "sms", {}, "failure", "HIGH", error="Failed to send")
    await audit_trail.log_action("Agent2", "api", {}, "success", "MEDIUM", duration_ms=200)

    report = await audit_trail.generate_weekly_report()

    assert "# Weekly Audit Report" in report
    assert "Agent1" in report
    assert "Agent2" in report
    assert "email" in report
    assert "sms" in report
    assert "Total Actions" in report
    assert "Success Rate" in report
    assert "Top 10 Errors" in report
    assert "Risk Level Distribution" in report


@pytest.mark.asyncio
async def test_weekly_report_empty_database(audit_trail):
    """Test weekly report with no data."""
    report = await audit_trail.generate_weekly_report()

    assert "# Weekly Audit Report" in report
    assert "Total Actions:** 0" in report


@pytest.mark.asyncio
async def test_thread_safety_concurrent_writes(audit_trail):
    """Test thread safety with concurrent writes."""
    async def write_log(agent_num: int, count: int):
        for i in range(count):
            await audit_trail.log_action(
                f"Agent{agent_num}",
                "concurrent_action",
                {"iteration": i},
                "success",
                "LOW"
            )

    await asyncio.gather(
        write_log(1, 20),
        write_log(2, 20),
        write_log(3, 20),
        write_log(4, 20),
        write_log(5, 20),
    )

    logs = await audit_trail.get_logs(action_type="concurrent_action", limit=1000)
    assert len(logs) == 100

    for i in range(1, 6):
        agent_logs = [l for l in logs if l["agent_name"] == f"Agent{i}"]
        assert len(agent_logs) == 20


@pytest.mark.asyncio
async def test_concurrent_reads_during_writes(audit_trail):
    """Test that reads work correctly during concurrent writes."""
    for i in range(10):
        await audit_trail.log_action("InitAgent", "init", {"i": i}, "success", "LOW")

    async def write_logs():
        for i in range(50):
            await audit_trail.log_action("WriteAgent", "write", {"i": i}, "success", "LOW")

    async def read_logs():
        results = []
        for _ in range(10):
            logs = await audit_trail.get_logs(limit=100)
            results.append(len(logs))
            await asyncio.sleep(0.01)
        return results

    write_task = asyncio.create_task(write_logs())
    read_task = asyncio.create_task(read_logs())

    await asyncio.gather(write_task, read_task)

    final_logs = await audit_trail.get_logs(limit=1000)
    assert len(final_logs) == 60


@pytest.mark.asyncio
async def test_audit_entry_dataclass():
    """Test AuditEntry dataclass with Day 18 fields."""
    entry = AuditEntry(
        timestamp="2024-01-01T00:00:00Z",
        agent_name="TestAgent",
        action_type="test",
        target_resource="lead:12345",
        action_details={"key": "value"},
        input_summary='{"email": "[EMAIL_REDACTED]"}',
        output_summary='{"status": "ok"}',
        status="success",
        approval_status="approved",
        risk_level="LOW",
        duration_ms=100.5,
        error_message=None
    )

    assert entry.timestamp == "2024-01-01T00:00:00Z"
    assert entry.agent_name == "TestAgent"
    assert entry.target_resource == "lead:12345"
    assert entry.status == "success"
    assert entry.approval_status == "approved"
    assert entry.input_summary == '{"email": "[EMAIL_REDACTED]"}'
    assert entry.duration_ms == 100.5


@pytest.mark.asyncio
async def test_get_audit_trail_factory(temp_dir):
    """Test factory function for creating AuditTrail."""
    trail = await get_audit_trail(
        db_path=temp_dir / "audit.db",
        backup_dir=temp_dir / "backup"
    )

    assert trail._initialized is True

    await trail.log_action("FactoryAgent", "action", {}, "success", "LOW")
    logs = await trail.get_logs()
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_metrics_aggregation(audit_trail):
    """Test that metrics are properly aggregated."""
    await audit_trail.log_action("MetricsAgent", "action", {}, "success", "LOW", duration_ms=100)
    await audit_trail.log_action("MetricsAgent", "action", {}, "success", "LOW", duration_ms=200)
    await audit_trail.log_action("MetricsAgent", "action", {}, "failure", "HIGH", duration_ms=50)

    stats = await audit_trail.get_agent_stats("MetricsAgent")

    assert stats["total_actions"] == 3
    assert stats["successes"] == 2
    assert stats["failures"] == 1


@pytest.mark.asyncio
async def test_risk_levels(audit_trail):
    """Test different risk levels are stored correctly."""
    risk_levels = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

    for level in risk_levels:
        await audit_trail.log_action("RiskAgent", "action", {}, "success", level)

    logs = await audit_trail.get_logs(agent_name="RiskAgent")
    stored_levels = {log["risk_level"] for log in logs}

    assert stored_levels == set(risk_levels)


@pytest.mark.asyncio
async def test_initialize_idempotent(audit_trail):
    """Test that initialize can be called multiple times safely."""
    await audit_trail.initialize()
    await audit_trail.initialize()
    await audit_trail.initialize()

    await audit_trail.log_action("Agent", "action", {}, "success", "LOW")
    logs = await audit_trail.get_logs()
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_close_cleanup(audit_trail):
    """Test close method cleans up resources."""
    await audit_trail.initialize()
    await audit_trail.start_cleanup_job()

    assert audit_trail._cleanup_task is not None

    await audit_trail.close()


@pytest.mark.asyncio
async def test_backup_archive_old_files(audit_trail, temp_dir):
    """Test that old backup files are archived during cleanup."""
    await audit_trail.initialize()

    old_date = (datetime.now(timezone.utc) - timedelta(days=100)).strftime("%Y-%m-%d")
    old_backup = audit_trail.backup_dir / f"{old_date}.json"
    with open(old_backup, "w") as f:
        json.dump({"test": "old"}, f)

    result = await audit_trail.run_retention_cleanup()

    assert result["archived_files"] == 1

    archive_dir = audit_trail.backup_dir / "archive"
    assert (archive_dir / f"{old_date}.json").exists()
    assert not old_backup.exists()


# ============================================================================
# DAY 18: PII REDACTION TESTS
# ============================================================================

class TestPIIRedactor:
    """Tests for PIIRedactor class."""

    def test_redact_email(self):
        """Test email redaction."""
        text = "Contact me at john.doe@example.com or jane@company.org"
        result = PIIRedactor.redact_string(text)
        assert "[EMAIL_REDACTED]" in result
        assert "@example.com" not in result
        assert "@company.org" not in result

    def test_redact_phone(self):
        """Test phone number redaction."""
        text = "Call me at +1-555-123-4567 or (800) 555-0199"
        result = PIIRedactor.redact_string(text)
        assert "[PHONE_REDACTED]" in result
        assert "555-123-4567" not in result

    def test_redact_ssn(self):
        """Test SSN redaction."""
        text = "SSN is 123-45-6789 or 123.45.6789"
        result = PIIRedactor.redact_string(text)
        assert "[SSN_REDACTED]" in result
        assert "123-45-6789" not in result

    def test_redact_credit_card(self):
        """Test credit card number redaction."""
        text = "Card: 4111-1111-1111-1111"
        result = PIIRedactor.redact_string(text)
        assert "[CC_REDACTED]" in result
        assert "4111-1111-1111-1111" not in result

    def test_redact_ip_address(self):
        """Test IP address redaction."""
        text = "Server at 192.168.1.1 and 10.0.0.1"
        result = PIIRedactor.redact_string(text)
        assert "[IP_REDACTED]" in result
        assert "192.168.1.1" not in result

    def test_redact_api_key(self):
        """Test API key redaction."""
        text = 'api_key=sk_dummy_abc123def456789xyz012345'
        result = PIIRedactor.redact_string(text)
        assert "[API_KEY_REDACTED]" in result
        assert "sk_dummy_abc123def456789xyz012345" not in result

    def test_preserve_partial_email(self):
        """Test partial email preservation."""
        text = "Email: user@domain.com"
        result = PIIRedactor.redact_string(text, preserve_partial=True)
        assert "@domain.com" in result
        assert "user@domain.com" not in result

    def test_redact_dict_simple(self):
        """Test dictionary redaction."""
        data = {
            "email": "test@example.com",
            "phone": "+1-555-123-4567",
            "name": "John Doe"
        }
        result = PIIRedactor.redact_dict(data)
        assert result["email"] == "[EMAIL_REDACTED]"
        assert result["phone"] == "[PHONE_REDACTED]"

    def test_redact_dict_sensitive_fields(self):
        """Test sensitive field name detection."""
        data = {
            "password": "secret123",
            "api_key": "sk-abc123",
            "normal_field": "visible"
        }
        result = PIIRedactor.redact_dict(data)
        assert result["password"] == "[SENSITIVE_REDACTED]"
        assert result["api_key"] == "[SENSITIVE_REDACTED]"
        assert result["normal_field"] == "visible"

    def test_redact_dict_nested(self):
        """Test nested dictionary redaction."""
        data = {
            "user": {
                "email": "nested@example.com",
                "profile": {
                    "phone": "+1-555-123-4567"
                }
            }
        }
        result = PIIRedactor.redact_dict(data)
        assert result["user"]["email"] == "[EMAIL_REDACTED]"
        assert result["user"]["profile"]["phone"] == "[PHONE_REDACTED]"

    def test_redact_dict_with_list(self):
        """Test dictionary with list values."""
        data = {
            "emails": ["user1@test.com", "user2@test.com"],
            "items": [{"email": "nested@test.com"}]
        }
        result = PIIRedactor.redact_dict(data)
        assert result["emails"][0] == "[EMAIL_REDACTED]"
        assert result["emails"][1] == "[EMAIL_REDACTED]"
        assert result["items"][0]["email"] == "[EMAIL_REDACTED]"

    def test_create_summary_truncation(self):
        """Test summary truncation."""
        data = {"large_field": "x" * 1000}
        summary = PIIRedactor.create_summary(data, max_length=100)
        assert len(summary) <= 100
        assert summary.endswith("...")

    def test_create_summary_with_pii(self):
        """Test summary creation with PII redaction."""
        data = {"email": "user@example.com", "name": "Public"}
        summary = PIIRedactor.create_summary(data)
        assert "[EMAIL_REDACTED]" in summary
        assert "Public" in summary


class TestApprovalStatus:
    """Tests for ApprovalStatus enum."""

    def test_approval_status_values(self):
        """Test all approval status values exist."""
        assert ApprovalStatus.APPROVED.value == "approved"
        assert ApprovalStatus.PENDING.value == "pending"
        assert ApprovalStatus.REJECTED.value == "rejected"
        assert ApprovalStatus.AUTO_APPROVED.value == "auto_approved"
        assert ApprovalStatus.ESCALATED.value == "escalated"
        assert ApprovalStatus.NOT_REQUIRED.value == "not_required"


class TestDay18AuditTrailEnhancements:
    """Tests for Day 18 audit trail enhancements."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        tmp = tempfile.mkdtemp()
        yield Path(tmp)
        shutil.rmtree(tmp, ignore_errors=True)

    @pytest.fixture
    def audit_trail(self, temp_dir):
        """Create an AuditTrail instance."""
        return AuditTrail(
            db_path=temp_dir / "audit.db",
            backup_dir=temp_dir / "backup"
        )

    @pytest.mark.asyncio
    async def test_log_with_target_resource(self, audit_trail):
        """Test logging with target_resource field."""
        await audit_trail.log_action(
            agent_name="HUNTER",
            action_type="scrape",
            details={"url": "https://linkedin.com"},
            status="success",
            risk_level="LOW",
            target_resource="linkedin.com/in/johndoe"
        )

        logs = await audit_trail.get_logs(agent_name="HUNTER")
        assert len(logs) == 1
        # Target resource should be stored (may be redacted if PII detected)
        assert logs[0]["target_resource"] is not None

    @pytest.mark.asyncio
    async def test_log_with_approval_status(self, audit_trail):
        """Test logging with approval_status field."""
        await audit_trail.log_action(
            agent_name="CRAFTER",
            action_type="campaign_create",
            details={"campaign_id": "C001"},
            status="success",
            risk_level="HIGH",
            approval_status="approved"
        )

        logs = await audit_trail.get_logs(agent_name="CRAFTER")
        assert logs[0]["approval_status"] == "approved"

    @pytest.mark.asyncio
    async def test_log_with_input_output_data(self, audit_trail):
        """Test logging with input and output data summaries."""
        await audit_trail.log_action(
            agent_name="ENRICHER",
            action_type="enrich",
            details={"lead_id": "L001"},
            status="success",
            risk_level="LOW",
            input_data={"email": "test@example.com", "company": "TechCorp"},
            output_data={"enriched": True, "revenue": "$5M"}
        )

        logs = await audit_trail.get_logs(agent_name="ENRICHER")
        assert logs[0]["input_summary"] is not None
        assert logs[0]["output_summary"] is not None
        # Email should be redacted in input summary
        assert "[EMAIL_REDACTED]" in logs[0]["input_summary"]

    @pytest.mark.asyncio
    async def test_automatic_pii_redaction(self, audit_trail):
        """Test that PII is automatically redacted."""
        await audit_trail.log_action(
            agent_name="TestAgent",
            action_type="email_send",
            details={
                "recipient": "secret@company.com",
                "phone": "+1-555-123-4567",
                "password": "supersecret"
            },
            status="success",
            risk_level="LOW",
            redact_pii=True  # Default
        )

        logs = await audit_trail.get_logs(agent_name="TestAgent")
        details = logs[0]["action_details"]
        
        assert details["recipient"] == "[EMAIL_REDACTED]"
        assert details["phone"] == "[PHONE_REDACTED]"
        assert details["password"] == "[SENSITIVE_REDACTED]"

    @pytest.mark.asyncio
    async def test_pii_redaction_disabled(self, audit_trail):
        """Test that PII redaction can be disabled."""
        await audit_trail.log_action(
            agent_name="TestAgent",
            action_type="internal",
            details={"email": "real@email.com"},
            status="success",
            risk_level="LOW",
            redact_pii=False
        )

        logs = await audit_trail.get_logs(agent_name="TestAgent")
        assert logs[0]["action_details"]["email"] == "real@email.com"

    @pytest.mark.asyncio
    async def test_target_resource_pii_redaction(self, audit_trail):
        """Test that target_resource has PII redacted."""
        await audit_trail.log_action(
            agent_name="HUNTER",
            action_type="scrape",
            details={},
            status="success",
            risk_level="LOW",
            target_resource="user@example.com"  # Email as resource
        )

        logs = await audit_trail.get_logs(agent_name="HUNTER")
        assert "[EMAIL_REDACTED]" in logs[0]["target_resource"]

    @pytest.mark.asyncio
    async def test_all_day18_fields_together(self, audit_trail):
        """Test all Day 18 fields working together."""
        await audit_trail.log_action(
            agent_name="UNIFIED_QUEEN",
            action_type="route_decision",
            details={"routing_to": "SCHEDULER", "lead_id": "L001"},
            status="success",
            risk_level="MEDIUM",
            target_resource="scheduling_request",
            input_data={"lead_email": "prospect@corp.com"},
            output_data={"selected_agent": "SCHEDULER"},
            approval_status="auto_approved",
            duration_ms=15.5,
            redact_pii=True
        )

        logs = await audit_trail.get_logs(agent_name="UNIFIED_QUEEN")
        log = logs[0]
        
        assert log["target_resource"] == "scheduling_request"
        assert log["approval_status"] == "auto_approved"
        assert "[EMAIL_REDACTED]" in log["input_summary"]
        assert log["output_summary"] is not None
        assert log["duration_ms"] == 15.5

