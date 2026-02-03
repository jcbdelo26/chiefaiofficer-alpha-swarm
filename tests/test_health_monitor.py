"""Tests for the unified health monitor with advanced features."""

import pytest
import asyncio
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import os

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.unified_health_monitor import (
    HealthMonitor,
    HeartbeatTracker,
    LatencyTracker,
    LatencyStats,
    AlertManager,
    AlertCondition,
    ComponentHealth,
    HealthStatus,
    RateLimitUsage,
)


# =============================================================================
# HEARTBEAT TRACKER TESTS
# =============================================================================

class TestHeartbeatTracker:
    """Tests for HeartbeatTracker class."""

    def test_record_and_get_heartbeat(self):
        """Test recording and retrieving heartbeats."""
        tracker = HeartbeatTracker(stale_threshold_seconds=60.0)
        tracker.record_heartbeat("HUNTER", {"status": "active"})
        
        last_hb = tracker.get_last_heartbeat("HUNTER")
        assert last_hb is not None
        assert (datetime.now(timezone.utc) - last_hb).total_seconds() < 1

    def test_get_heartbeat_metadata(self):
        """Test retrieving heartbeat metadata."""
        tracker = HeartbeatTracker()
        tracker.record_heartbeat("ENRICHER", {"task": "enriching"})
        
        metadata = tracker.get_heartbeat_metadata("ENRICHER")
        assert metadata == {"task": "enriching"}

    def test_is_stale_fresh_agent(self):
        """Test that recently active agent is not stale."""
        tracker = HeartbeatTracker(stale_threshold_seconds=60.0)
        tracker.record_heartbeat("HUNTER")
        
        assert tracker.is_stale("HUNTER") is False

    def test_is_stale_unknown_agent(self):
        """Test that unknown agent is considered stale."""
        tracker = HeartbeatTracker()
        assert tracker.is_stale("UNKNOWN_AGENT") is True

    def test_get_stale_agents(self):
        """Test detection of stale agents."""
        tracker = HeartbeatTracker(stale_threshold_seconds=0.1)
        tracker.record_heartbeat("AGENT_A")
        tracker.record_heartbeat("AGENT_B")
        
        time.sleep(0.15)
        
        stale = tracker.get_stale_agents()
        assert "AGENT_A" in stale
        assert "AGENT_B" in stale

    def test_get_all_heartbeats(self):
        """Test getting all heartbeat info."""
        tracker = HeartbeatTracker()
        tracker.record_heartbeat("A1", {"v": 1})
        tracker.record_heartbeat("A2", {"v": 2})
        
        all_hb = tracker.get_all_heartbeats()
        assert "A1" in all_hb
        assert "A2" in all_hb
        assert all_hb["A1"]["metadata"] == {"v": 1}


# =============================================================================
# LATENCY TRACKER TESTS
# =============================================================================

class TestLatencyTracker:
    """Tests for LatencyTracker class."""

    def test_record_latency(self):
        """Test recording latency samples."""
        tracker = LatencyTracker(window_seconds=300)
        tracker.record_latency("ghl_api", 100)
        tracker.record_latency("ghl_api", 200)
        
        stats = tracker.get_percentiles("ghl_api")
        assert stats.samples == 2

    def test_percentile_calculation_single_sample(self):
        """Test percentiles with single sample."""
        tracker = LatencyTracker()
        tracker.record_latency("comp", 150)
        
        stats = tracker.get_percentiles("comp")
        assert stats.p50_ms == 150
        assert stats.p95_ms == 150
        assert stats.p99_ms == 150

    def test_percentile_calculation_multiple_samples(self):
        """Test percentile calculations with multiple samples."""
        tracker = LatencyTracker()
        
        for i in range(1, 101):
            tracker.record_latency("test", float(i))
        
        stats = tracker.get_percentiles("test")
        assert 49 <= stats.p50_ms <= 51
        assert 94 <= stats.p95_ms <= 96
        assert 98 <= stats.p99_ms <= 100

    def test_empty_component(self):
        """Test getting percentiles for unknown component."""
        tracker = LatencyTracker()
        stats = tracker.get_percentiles("unknown")
        
        assert stats.samples == 0
        assert stats.p50_ms == 0
        assert stats.p95_ms == 0
        assert stats.p99_ms == 0

    def test_rolling_window_pruning(self):
        """Test that old samples are pruned."""
        tracker = LatencyTracker(window_seconds=0.1)
        tracker.record_latency("test", 100)
        
        time.sleep(0.15)
        tracker.record_latency("test", 200)
        
        stats = tracker.get_percentiles("test")
        assert stats.samples == 1
        assert stats.p50_ms == 200

    def test_get_all_stats(self):
        """Test getting stats for all components."""
        tracker = LatencyTracker()
        tracker.record_latency("comp1", 100)
        tracker.record_latency("comp2", 200)
        
        all_stats = tracker.get_all_stats()
        assert "comp1" in all_stats
        assert "comp2" in all_stats


# =============================================================================
# ALERT MANAGER TESTS
# =============================================================================

class TestAlertManager:
    """Tests for AlertManager class."""

    def test_init_loads_env_vars(self):
        """Test that AlertManager loads environment variables."""
        with patch.dict(os.environ, {"SLACK_WEBHOOK_URL": "https://hooks.slack.com/test"}):
            manager = AlertManager()
            assert manager.slack_webhook_url == "https://hooks.slack.com/test"

    def test_deduplication_key(self):
        """Test alert key generation."""
        manager = AlertManager()
        key1 = manager._get_alert_key("#channel", "message")
        key2 = manager._get_alert_key("#channel", "message")
        key3 = manager._get_alert_key("#channel", "different")
        
        assert key1 == key2
        assert key1 != key3

    def test_duplicate_detection(self):
        """Test that duplicates are detected."""
        manager = AlertManager(dedup_window_seconds=1.0)
        key = manager._get_alert_key("#test", "test msg")
        
        assert manager._is_duplicate(key) is False
        manager._mark_sent(key)
        assert manager._is_duplicate(key) is True

    def test_duplicate_expires(self):
        """Test that duplicate detection expires."""
        manager = AlertManager(dedup_window_seconds=0.1)
        key = manager._get_alert_key("#test", "test msg")
        
        manager._mark_sent(key)
        time.sleep(0.15)
        assert manager._is_duplicate(key) is False

    @pytest.mark.asyncio
    async def test_slack_alert_without_webhook(self):
        """Test Slack alert fails gracefully without webhook."""
        manager = AlertManager()
        manager.slack_webhook_url = None
        
        result = await manager.send_slack_alert("#test", "message")
        assert result is False

    @pytest.mark.asyncio
    async def test_slack_alert_success(self):
        """Test successful Slack alert sending."""
        manager = AlertManager()
        manager.slack_webhook_url = "https://hooks.slack.com/test"
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result = await manager.send_slack_alert("#test", "Alert message", "warning")
            assert result is True

    @pytest.mark.asyncio
    async def test_slack_alert_deduplication(self):
        """Test that duplicate Slack alerts are skipped."""
        manager = AlertManager()
        manager.slack_webhook_url = "https://hooks.slack.com/test"
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            result1 = await manager.send_slack_alert("#test", "Same message")
            result2 = await manager.send_slack_alert("#test", "Same message")
            
            assert result1 is True
            assert result2 is False

    @pytest.mark.asyncio
    async def test_sms_alert_without_credentials(self):
        """Test SMS alert fails gracefully without Twilio credentials."""
        manager = AlertManager()
        manager.twilio_account_sid = None
        
        result = await manager.send_sms_alert("+1234567890", "message")
        assert result is False


# =============================================================================
# RATE LIMIT HEALTH TESTS
# =============================================================================

class TestRateLimitHealth:
    """Tests for rate limit health with color coding."""

    def test_green_under_70_percent(self):
        """Test green color for usage under 70%."""
        monitor = HealthMonitor()
        monitor.rate_limits["test"] = RateLimitUsage(name="Test", current=50, limit=100)
        
        health = monitor.get_rate_limit_health()
        assert health["test"]["color"] == "green"
        assert health["test"]["level"] == "ok"

    def test_yellow_between_70_and_90(self):
        """Test yellow color for usage between 70-90%."""
        monitor = HealthMonitor()
        monitor.rate_limits["test"] = RateLimitUsage(name="Test", current=80, limit=100)
        
        health = monitor.get_rate_limit_health()
        assert health["test"]["color"] == "yellow"
        assert health["test"]["level"] == "warning"

    def test_red_over_90_percent(self):
        """Test red color for usage over 90%."""
        monitor = HealthMonitor()
        monitor.rate_limits["test"] = RateLimitUsage(name="Test", current=95, limit=100)
        
        health = monitor.get_rate_limit_health()
        assert health["test"]["color"] == "red"
        assert health["test"]["level"] == "critical"


# =============================================================================
# SYSTEM HEALTH SCORE TESTS
# =============================================================================

class TestSystemHealthScore:
    """Tests for system health score calculation."""

    def test_healthy_components_score(self):
        """Test that healthy components yield high score."""
        monitor = HealthMonitor()
        score = monitor.get_system_health_score()
        assert score == 100.0

    def test_degraded_components_lower_score(self):
        """Test that degraded components lower the score."""
        monitor = HealthMonitor()
        key = list(monitor.components.keys())[0]
        monitor.components[key].status = HealthStatus.DEGRADED
        
        score = monitor.get_system_health_score()
        assert score < 100.0

    def test_unhealthy_components_lowest_score(self):
        """Test that unhealthy components significantly lower score."""
        monitor = HealthMonitor()
        for comp in monitor.components.values():
            comp.status = HealthStatus.UNHEALTHY
        
        score = monitor.get_system_health_score()
        assert score == 0.0

    def test_error_rate_penalty(self):
        """Test that high error rate penalizes score."""
        monitor = HealthMonitor()
        key = list(monitor.components.keys())[0]
        monitor.components[key].error_rate = 0.3
        
        score = monitor.get_system_health_score()
        assert score < 100.0


# =============================================================================
# ALERTABLE CONDITIONS TESTS
# =============================================================================

class TestAlertableConditions:
    """Tests for alertable condition detection."""

    def test_circuit_breaker_open_condition(self):
        """Test detection of open circuit breaker."""
        monitor = HealthMonitor()
        key = list(monitor.components.keys())[0]
        monitor.components[key].circuit_state = "open"
        
        conditions = monitor.get_alertable_conditions()
        circuit_conditions = [c for c in conditions if c.condition_type == "circuit_breaker_open"]
        assert len(circuit_conditions) >= 1

    def test_high_error_rate_condition(self):
        """Test detection of high error rate."""
        monitor = HealthMonitor()
        key = list(monitor.components.keys())[0]
        monitor.components[key].error_rate = 0.25
        
        conditions = monitor.get_alertable_conditions()
        error_conditions = [c for c in conditions if c.condition_type == "high_error_rate"]
        assert len(error_conditions) >= 1

    def test_high_latency_condition(self):
        """Test detection of high p95 latency."""
        monitor = HealthMonitor()
        key = list(monitor.components.keys())[0]
        monitor.latency_tracker.record_latency(key, 6000)
        
        conditions = monitor.get_alertable_conditions()
        latency_conditions = [c for c in conditions if c.condition_type == "high_latency"]
        assert len(latency_conditions) >= 1

    def test_stale_agent_condition(self):
        """Test detection of stale agent."""
        monitor = HealthMonitor()
        monitor.heartbeat_tracker.stale_threshold = 0.05
        monitor.heartbeat_tracker.record_heartbeat("TEST_AGENT")
        
        time.sleep(0.1)
        
        stale_info = monitor.heartbeat_tracker.get_all_heartbeats()
        assert stale_info["TEST_AGENT"]["age_seconds"] > 0.05


# =============================================================================
# HEALTH MONITOR INTEGRATION TESTS
# =============================================================================

class TestHealthMonitorIntegration:
    """Integration tests for HealthMonitor with new features."""

    def test_record_heartbeat_via_monitor(self):
        """Test recording heartbeat through monitor."""
        monitor = HealthMonitor()
        monitor.record_heartbeat("HUNTER", {"status": "ok"})
        
        assert monitor.heartbeat_tracker.is_stale("HUNTER") is False

    def test_get_stale_agents_via_monitor(self):
        """Test getting stale agents through monitor."""
        monitor = HealthMonitor()
        monitor.heartbeat_tracker.stale_threshold = 0.05
        monitor.record_heartbeat("AGENT1")
        
        time.sleep(0.1)
        
        stale = monitor.get_stale_agents()
        assert "AGENT1" in stale

    def test_record_latency_via_monitor(self):
        """Test recording latency through monitor."""
        monitor = HealthMonitor()
        monitor.record_latency("agents:HUNTER", 150)
        monitor.record_latency("agents:HUNTER", 200)
        
        stats = monitor.get_latency_percentiles("agents:HUNTER")
        assert stats.samples == 2

    def test_latency_stats_to_dict(self):
        """Test LatencyStats serialization."""
        stats = LatencyStats(p50_ms=100, p95_ms=200, p99_ms=300, samples=10)
        d = stats.to_dict()
        
        assert d["p50_ms"] == 100
        assert d["p95_ms"] == 200
        assert d["p99_ms"] == 300
        assert d["samples"] == 10

    def test_alert_condition_to_dict(self):
        """Test AlertCondition serialization."""
        cond = AlertCondition(
            condition_type="test",
            component="comp",
            severity="warning",
            message="Test message",
            value=0.5,
            threshold=0.3
        )
        d = cond.to_dict()
        
        assert d["condition_type"] == "test"
        assert d["severity"] == "warning"

    def test_component_health_integration(self):
        """Test that existing ComponentHealth works with new features."""
        monitor = HealthMonitor()
        
        monitor.record_action("agents:HUNTER", True, 100, agent="HUNTER", action="search")
        monitor.record_latency("agents:HUNTER", 100)
        monitor.record_heartbeat("HUNTER")
        
        status = monitor.get_health_status()
        assert "agents" in status
        assert "HUNTER" in status["agents"]

    @pytest.mark.asyncio
    async def test_process_alerts(self):
        """Test alert processing."""
        monitor = HealthMonitor()
        monitor.alert_manager.slack_webhook_url = "https://hooks.slack.com/test"
        
        key = list(monitor.components.keys())[0]
        monitor.components[key].error_rate = 0.55
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            await monitor.process_alerts("#alerts")


# =============================================================================
# DAY 19: QUEUE DEPTH TRACKER TESTS
# =============================================================================

class TestQueueDepthTracker:
    """Tests for QueueDepthTracker class."""

    def test_record_enqueue(self):
        """Test recording items added to queue."""
        from core.unified_health_monitor import QueueDepthTracker
        tracker = QueueDepthTracker()
        tracker.record_enqueue("lead_processing", 5)
        
        depths = tracker.get_all_depths()
        assert depths["lead_processing"]["current_depth"] == 5

    def test_record_dequeue(self):
        """Test recording items removed from queue."""
        from core.unified_health_monitor import QueueDepthTracker
        tracker = QueueDepthTracker()
        tracker.record_enqueue("lead_processing", 10)
        tracker.record_dequeue("lead_processing", 3)
        
        depths = tracker.get_all_depths()
        assert depths["lead_processing"]["current_depth"] == 7
        assert depths["lead_processing"]["total_processed"] == 3

    def test_queue_status_healthy(self):
        """Test queue status is healthy under threshold."""
        from core.unified_health_monitor import QueueDepthTracker
        tracker = QueueDepthTracker()
        tracker.record_enqueue("lead_processing", 100)
        
        depths = tracker.get_all_depths()
        assert depths["lead_processing"]["status"] == "healthy"

    def test_queue_status_warning(self):
        """Test queue status is warning at threshold."""
        from core.unified_health_monitor import QueueDepthTracker
        tracker = QueueDepthTracker()
        tracker.set_depth("lead_processing", 850)  # 85% of max
        
        depths = tracker.get_all_depths()
        assert depths["lead_processing"]["status"] == "warning"

    def test_queue_status_critical(self):
        """Test queue status is critical at max."""
        from core.unified_health_monitor import QueueDepthTracker
        tracker = QueueDepthTracker()
        tracker.set_depth("lead_processing", 980)  # 98% of max
        
        depths = tracker.get_all_depths()
        assert depths["lead_processing"]["status"] == "critical"

    def test_get_critical_queues(self):
        """Test getting list of critical queues."""
        from core.unified_health_monitor import QueueDepthTracker
        tracker = QueueDepthTracker()
        tracker.set_depth("lead_processing", 980)
        tracker.set_depth("email_outbox", 100)
        
        critical = tracker.get_critical_queues()
        assert "lead_processing" in critical
        assert "email_outbox" not in critical

    def test_get_warning_queues(self):
        """Test getting list of warning queues."""
        from core.unified_health_monitor import QueueDepthTracker
        tracker = QueueDepthTracker()
        tracker.set_depth("lead_processing", 850)
        tracker.set_depth("email_outbox", 100)
        
        warning = tracker.get_warning_queues()
        assert "lead_processing" in warning
        assert "email_outbox" not in warning

    def test_dropped_items_tracking(self):
        """Test tracking of dropped items when queue is full."""
        from core.unified_health_monitor import QueueDepthTracker
        tracker = QueueDepthTracker()
        tracker.set_depth("lead_processing", 1000)  # At max
        tracker.record_enqueue("lead_processing", 10)
        
        depths = tracker.get_all_depths()
        assert depths["lead_processing"]["total_dropped"] == 10


# =============================================================================
# DAY 19: REASONING BANK MONITOR TESTS
# =============================================================================

class TestReasoningBankMonitor:
    """Tests for ReasoningBankMonitor class."""

    def test_missing_file_stats(self):
        """Test stats when reasoning bank file doesn't exist."""
        from core.unified_health_monitor import ReasoningBankMonitor
        from pathlib import Path
        
        monitor = ReasoningBankMonitor(reasoning_bank_path=Path("/nonexistent/path.json"))
        stats = monitor.get_stats()
        
        assert stats["exists"] is False
        assert stats["status"] == "missing"

    def test_stats_structure(self):
        """Test that stats have all expected fields."""
        from core.unified_health_monitor import ReasoningBankMonitor
        monitor = ReasoningBankMonitor()
        stats = monitor.get_stats()
        
        assert "exists" in stats
        assert "status" in stats


# =============================================================================
# DAY 19: EMAIL ALERT TESTS
# =============================================================================

class TestEmailAlerts:
    """Tests for email alert functionality."""

    @pytest.mark.asyncio
    async def test_send_email_alert_logs_when_no_smtp(self):
        """Test that email alert logs when SMTP not configured."""
        from core.unified_health_monitor import AlertManager
        manager = AlertManager()
        
        result = await manager.send_email_alert(
            "test@example.com",
            "Test Subject",
            "Test Body"
        )
        # Returns True since it logs the alert
        assert result is True

    @pytest.mark.asyncio
    async def test_send_daily_summary_email(self):
        """Test daily summary email generation - placeholder test."""
        # send_daily_summary_email is in AlertManager but needs HealthMonitor context
        # This test just verifies the method exists on AlertManager
        from core.unified_health_monitor import AlertManager
        manager = AlertManager()
        assert hasattr(manager, 'send_daily_summary_email')


# =============================================================================
# DAY 19: HEALTH MONITOR QUEUE/REASONING INTEGRATION
# =============================================================================

class TestDay19Integration:
    """Integration tests for Day 19 features."""

    def test_health_status_includes_queue_depths(self):
        """Test that get_health_status includes queue depths."""
        monitor = HealthMonitor()
        monitor.record_enqueue("lead_processing", 5)
        
        status = monitor.get_health_status()
        assert "queue_depths" in status
        assert "lead_processing" in status["queue_depths"]

    def test_health_status_includes_reasoning_bank(self):
        """Test that get_health_status includes reasoning bank stats."""
        monitor = HealthMonitor()
        status = monitor.get_health_status()
        
        assert "reasoning_bank" in status
        assert "status" in status["reasoning_bank"]

    def test_health_status_includes_latency_stats(self):
        """Test that get_health_status includes latency stats."""
        monitor = HealthMonitor()
        monitor.record_latency("test_component", 100)
        
        status = monitor.get_health_status()
        assert "latency_stats" in status

    def test_health_status_includes_stale_agents(self):
        """Test that get_health_status includes stale agents."""
        monitor = HealthMonitor()
        status = monitor.get_health_status()
        
        assert "stale_agents" in status

    def test_health_status_includes_health_score(self):
        """Test that get_health_status includes health score."""
        monitor = HealthMonitor()
        status = monitor.get_health_status()
        
        assert "health_score" in status
        assert 0 <= status["health_score"] <= 100

    def test_record_enqueue_via_monitor(self):
        """Test enqueue recording through monitor."""
        monitor = HealthMonitor()
        monitor.record_enqueue("lead_processing", 10)
        
        depths = monitor.get_queue_depths()
        assert depths["lead_processing"]["current_depth"] == 10

    def test_record_dequeue_via_monitor(self):
        """Test dequeue recording through monitor."""
        monitor = HealthMonitor()
        monitor.record_enqueue("lead_processing", 10)
        monitor.record_dequeue("lead_processing", 5)
        
        depths = monitor.get_queue_depths()
        assert depths["lead_processing"]["current_depth"] == 5

    def test_get_reasoning_bank_stats_via_monitor(self):
        """Test getting reasoning bank stats through monitor."""
        monitor = HealthMonitor()
        stats = monitor.get_reasoning_bank_stats()
        
        assert "status" in stats

    def test_get_critical_queues_via_monitor(self):
        """Test getting critical queues through monitor."""
        monitor = HealthMonitor()
        monitor.queue_depth_tracker.set_depth("lead_processing", 980)
        
        critical = monitor.get_critical_queues()
        assert "lead_processing" in critical

