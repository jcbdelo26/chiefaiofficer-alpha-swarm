#!/usr/bin/env python3
"""
Unit tests for Swarm Coordination Module.
Tests heartbeats, auto-restart, worker concurrency, and hooks.
"""

import os
import sys
import pytest
import asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.swarm_coordination import (
    SwarmCoordinator,
    WorkerPool,
    HeartbeatMonitor,
    RecoveryManager,
    HookRegistry,
    CoordinationConfig,
    Heartbeat,
    WorkerState,
    AgentStatus,
    WorkerStatus,
    HookType
)


class TestHeartbeat:
    """Test Heartbeat data class."""
    
    def test_heartbeat_creation(self):
        """Test creating a heartbeat."""
        hb = Heartbeat(agent_id="HUNTER")
        
        assert hb.agent_id == "HUNTER"
        assert hb.status == "alive"
        assert hb.current_task is None
    
    def test_heartbeat_age(self):
        """Test heartbeat age calculation."""
        # Create heartbeat 5 seconds in the past
        past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        hb = Heartbeat(agent_id="TEST", timestamp=past)
        
        assert hb.age_seconds >= 4.9
        assert hb.age_seconds <= 6.0


class TestHeartbeatMonitor:
    """Test HeartbeatMonitor functionality."""
    
    @pytest.fixture
    def monitor(self):
        """Create a HeartbeatMonitor."""
        config = CoordinationConfig(heartbeat_interval_seconds=1)
        return HeartbeatMonitor(config)
    
    def test_record_heartbeat(self, monitor):
        """Test recording heartbeats."""
        hb = monitor.record_heartbeat("HUNTER", current_task="task_1")
        
        assert hb.agent_id == "HUNTER"
        assert hb.current_task == "task_1"
        
        # Should be retrievable
        retrieved = monitor.get_heartbeat("HUNTER")
        assert retrieved is not None
        assert retrieved.agent_id == "HUNTER"
    
    def test_is_alive(self, monitor):
        """Test alive detection."""
        # Fresh heartbeat should be alive
        monitor.record_heartbeat("HUNTER")
        assert monitor.is_alive("HUNTER") is True
        
        # Unknown agent should not be alive
        assert monitor.is_alive("UNKNOWN") is False
    
    def test_get_dead_agents(self, monitor):
        """Test dead agent detection."""
        # Record fresh heartbeat
        monitor.record_heartbeat("HUNTER")
        
        # Record old heartbeat (manually set old timestamp)
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=100)).isoformat()
        monitor._heartbeats["DEAD_AGENT"] = Heartbeat(
            agent_id="DEAD_AGENT",
            timestamp=old_time
        )
        
        dead = monitor.get_dead_agents()
        assert "DEAD_AGENT" in dead
        assert "HUNTER" not in dead
    
    def test_get_all_heartbeats(self, monitor):
        """Test getting all heartbeats."""
        monitor.record_heartbeat("HUNTER")
        monitor.record_heartbeat("ENRICHER")
        
        all_hb = monitor.get_all_heartbeats()
        assert len(all_hb) == 2
        assert "HUNTER" in all_hb
        assert "ENRICHER" in all_hb
    
    def test_get_stats(self, monitor):
        """Test statistics generation."""
        monitor.record_heartbeat("HUNTER")
        monitor.record_heartbeat("ENRICHER")
        
        stats = monitor.get_stats()
        assert stats["total_agents"] == 2
        assert stats["alive"] == 2
        assert stats["dead"] == 0


class TestWorkerPool:
    """Test WorkerPool functionality."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return CoordinationConfig(
            min_workers=2,
            max_workers=8,
            initial_workers=4
        )
    
    @pytest.mark.asyncio
    async def test_start_stop(self, config):
        """Test starting and stopping worker pool."""
        pool = WorkerPool(config)
        
        await pool.start()
        assert len(pool._workers) == config.initial_workers
        assert pool._running is True
        
        await pool.stop()
        assert pool._running is False
        assert len(pool._workers) == 0
    
    @pytest.mark.asyncio
    async def test_submit_task(self, config):
        """Test task submission."""
        pool = WorkerPool(config)
        processed = []
        
        async def handler(task_data):
            processed.append(task_data["task_id"])
        
        pool.set_task_handler(handler)
        
        await pool.start()
        
        try:
            # Submit tasks
            for i in range(5):
                await pool.submit_task({"task_id": f"task_{i}"})
            
            # Wait for processing
            await asyncio.sleep(0.5)
            
            assert len(processed) == 5
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_scale_up(self, config):
        """Test scaling up workers."""
        pool = WorkerPool(config)
        await pool.start()
        
        try:
            initial = len(pool._workers)
            await pool.scale_to(6)
            assert len(pool._workers) == 6
            assert len(pool._workers) > initial
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_scale_down(self, config):
        """Test scaling down workers."""
        pool = WorkerPool(config)
        await pool.start()
        
        try:
            await pool.scale_to(2)
            assert len(pool._workers) == 2
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_scale_limits(self, config):
        """Test scaling respects min/max limits."""
        pool = WorkerPool(config)
        await pool.start()
        
        try:
            # Try to scale below min
            await pool.scale_to(1)
            assert len(pool._workers) == config.min_workers
            
            # Try to scale above max
            await pool.scale_to(100)
            assert len(pool._workers) == config.max_workers
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_error_handling(self, config):
        """Test error handling in tasks."""
        pool = WorkerPool(config)
        errors = []
        
        async def handler(task_data):
            if task_data.get("should_fail"):
                raise ValueError("Intentional error")
        
        async def error_handler(task_data, error):
            errors.append((task_data["task_id"], str(error)))
        
        pool.set_task_handler(handler)
        pool.set_error_handler(error_handler)
        
        await pool.start()
        
        try:
            await pool.submit_task({"task_id": "fail_1", "should_fail": True})
            await pool.submit_task({"task_id": "ok_1", "should_fail": False})
            
            await asyncio.sleep(0.5)
            
            assert len(errors) == 1
            assert errors[0][0] == "fail_1"
        finally:
            await pool.stop()
    
    @pytest.mark.asyncio
    async def test_get_stats(self, config):
        """Test statistics generation."""
        pool = WorkerPool(config)
        await pool.start()
        
        try:
            stats = pool.get_stats()
            assert stats["total_workers"] == config.initial_workers
            assert "queue_size" in stats
            assert "statuses" in stats
        finally:
            await pool.stop()


class TestHookRegistry:
    """Test HookRegistry functionality."""
    
    def test_register_hook(self):
        """Test registering hooks."""
        registry = HookRegistry()
        
        def my_handler(**kwargs):
            return "handled"
        
        registry.register(HookType.PRE_TASK, my_handler)
        
        handlers = registry.get_handlers(HookType.PRE_TASK)
        assert len(handlers) == 1
        assert handlers[0] == my_handler
    
    def test_unregister_hook(self):
        """Test unregistering hooks."""
        registry = HookRegistry()
        
        def my_handler(**kwargs):
            pass
        
        registry.register(HookType.PRE_TASK, my_handler)
        registry.unregister(HookType.PRE_TASK, my_handler)
        
        handlers = registry.get_handlers(HookType.PRE_TASK)
        assert len(handlers) == 0
    
    @pytest.mark.asyncio
    async def test_execute_sync_hook(self):
        """Test executing synchronous hooks."""
        registry = HookRegistry()
        results = []
        
        def my_handler(task):
            results.append(task["id"])
            return task["id"]
        
        registry.register(HookType.PRE_TASK, my_handler)
        
        await registry.execute(HookType.PRE_TASK, task={"id": "test_1"})
        
        assert len(results) == 1
        assert results[0] == "test_1"
    
    @pytest.mark.asyncio
    async def test_execute_async_hook(self):
        """Test executing asynchronous hooks."""
        registry = HookRegistry()
        results = []
        
        async def my_async_handler(task):
            await asyncio.sleep(0.01)
            results.append(task["id"])
            return task["id"]
        
        registry.register(HookType.POST_TASK, my_async_handler)
        
        await registry.execute(HookType.POST_TASK, task={"id": "test_2"})
        
        assert len(results) == 1
        assert results[0] == "test_2"
    
    @pytest.mark.asyncio
    async def test_hook_error_handling(self):
        """Test that hook errors don't break execution."""
        registry = HookRegistry()
        results = []
        
        def failing_handler(**kwargs):
            raise ValueError("Intentional failure")
        
        def good_handler(**kwargs):
            results.append("success")
        
        registry.register(HookType.PRE_TASK, failing_handler)
        registry.register(HookType.PRE_TASK, good_handler)
        
        # Should not raise
        exec_results = await registry.execute(HookType.PRE_TASK, task={})
        
        # Good handler should still run
        assert "success" in results
        # Error should be captured
        assert any("error" in str(r) for r in exec_results)


class TestRecoveryManager:
    """Test RecoveryManager functionality."""
    
    @pytest.fixture
    def manager(self):
        """Create a RecoveryManager."""
        config = CoordinationConfig(
            auto_restart=True,
            max_restart_attempts=3,
            restart_delay_seconds=0.1
        )
        return RecoveryManager(config)
    
    @pytest.mark.asyncio
    async def test_successful_recovery(self, manager):
        """Test successful recovery."""
        def recovery_handler(agent_id):
            return True
        
        manager.register_recovery_handler("HUNTER", recovery_handler)
        
        result = await manager.attempt_recovery("HUNTER")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_failed_recovery(self, manager):
        """Test failed recovery."""
        def recovery_handler(agent_id):
            return False
        
        manager.register_recovery_handler("HUNTER", recovery_handler)
        
        result = await manager.attempt_recovery("HUNTER")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_max_attempts(self, manager):
        """Test max restart attempts."""
        call_count = 0
        
        def recovery_handler(agent_id):
            nonlocal call_count
            call_count += 1
            return False  # Always fail
        
        manager.register_recovery_handler("HUNTER", recovery_handler)
        
        # Try multiple times
        for _ in range(5):
            await manager.attempt_recovery("HUNTER")
        
        # Should stop at max attempts
        assert manager._restart_attempts["HUNTER"] >= manager.config.max_restart_attempts
    
    def test_reset_attempts(self, manager):
        """Test resetting restart attempts."""
        manager._restart_attempts["HUNTER"] = 3
        manager.reset_attempts("HUNTER")
        assert manager._restart_attempts["HUNTER"] == 0
    
    @pytest.mark.asyncio
    async def test_auto_restart_disabled(self):
        """Test with auto-restart disabled."""
        config = CoordinationConfig(auto_restart=False)
        manager = RecoveryManager(config)
        
        result = await manager.attempt_recovery("HUNTER")
        assert result is False


class TestSwarmCoordinator:
    """Test SwarmCoordinator integration."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return CoordinationConfig(
            heartbeat_interval_seconds=1,
            min_workers=2,
            max_workers=8,
            initial_workers=4,
            auto_restart=True
        )
    
    @pytest.mark.asyncio
    async def test_start_stop(self, config):
        """Test starting and stopping coordinator."""
        coordinator = SwarmCoordinator(config)
        
        await coordinator.start()
        assert coordinator._running is True
        
        await coordinator.stop()
        assert coordinator._running is False
    
    @pytest.mark.asyncio
    async def test_heartbeat_recording(self, config):
        """Test heartbeat recording through coordinator."""
        coordinator = SwarmCoordinator(config)
        
        await coordinator.start()
        
        try:
            coordinator.record_heartbeat("HUNTER", current_task="task_1")
            
            hb = coordinator.heartbeat_monitor.get_heartbeat("HUNTER")
            assert hb is not None
            assert hb.current_task == "task_1"
        finally:
            await coordinator.stop()
    
    @pytest.mark.asyncio
    async def test_task_submission(self, config):
        """Test task submission through coordinator."""
        coordinator = SwarmCoordinator(config)
        processed = []
        
        async def handler(task_data):
            processed.append(task_data["task_id"])
        
        coordinator.set_task_handler(handler)
        
        await coordinator.start()
        
        try:
            for i in range(5):
                await coordinator.submit_task({"task_id": f"task_{i}"})
            
            await asyncio.sleep(0.5)
            
            assert len(processed) == 5
        finally:
            await coordinator.stop()
    
    @pytest.mark.asyncio
    async def test_hook_registration(self, config):
        """Test hook registration."""
        coordinator = SwarmCoordinator(config)
        hook_calls = []
        
        async def pre_task_hook(task):
            hook_calls.append(("pre", task["task_id"]))
        
        coordinator.register_hook("pre_task", pre_task_hook)
        coordinator.set_task_handler(lambda t: None)
        
        await coordinator.start()
        
        try:
            await coordinator.submit_task({"task_id": "test_1"})
            await asyncio.sleep(0.2)
            
            assert len(hook_calls) >= 1
            assert hook_calls[0] == ("pre", "test_1")
        finally:
            await coordinator.stop()
    
    @pytest.mark.asyncio
    async def test_worker_scaling(self, config):
        """Test manual worker scaling."""
        coordinator = SwarmCoordinator(config)
        
        await coordinator.start()
        
        try:
            initial = len(coordinator.worker_pool._workers)
            await coordinator.scale_workers(6)
            
            assert len(coordinator.worker_pool._workers) == 6
        finally:
            await coordinator.stop()
    
    @pytest.mark.asyncio
    async def test_get_status(self, config):
        """Test status retrieval."""
        coordinator = SwarmCoordinator(config)
        
        await coordinator.start()
        
        try:
            status = coordinator.get_status()
            
            assert "running" in status
            assert status["running"] is True
            assert "workers" in status
            assert "heartbeats" in status
            assert "config" in status
        finally:
            await coordinator.stop()


class TestIntegration:
    """Integration tests for swarm coordination."""
    
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete workflow with all components."""
        config = CoordinationConfig(
            heartbeat_interval_seconds=1,
            initial_workers=4,
            min_workers=2,
            max_workers=8
        )
        
        coordinator = SwarmCoordinator(config)
        
        processed = []
        errors = []
        hooks_called = []
        
        async def task_handler(task_data):
            if task_data.get("should_fail"):
                raise ValueError("Test error")
            processed.append(task_data["task_id"])
        
        def pre_hook(task):
            hooks_called.append(("pre", task.get("task_id")))
        
        def error_hook(task, error):
            errors.append((task.get("task_id"), error))
        
        coordinator.set_task_handler(task_handler)
        coordinator.register_hook("pre_task", pre_hook)
        coordinator.register_hook("on_error", error_hook)
        
        await coordinator.start()
        
        try:
            # Record heartbeats
            for agent in ["HUNTER", "ENRICHER", "CRAFTER"]:
                coordinator.record_heartbeat(agent)
            
            # Submit tasks
            await coordinator.submit_task({"task_id": "ok_1"})
            await coordinator.submit_task({"task_id": "ok_2"})
            await coordinator.submit_task({"task_id": "fail_1", "should_fail": True})
            await coordinator.submit_task({"task_id": "ok_3"})
            
            await asyncio.sleep(1)
            
            # Verify
            assert len(processed) == 3
            assert len(errors) == 1
            assert len(hooks_called) >= 4
            
            # Check status
            status = coordinator.get_status()
            assert status["heartbeats"]["total_agents"] == 3
            assert status["workers"]["total_processed"] >= 3
            
        finally:
            await coordinator.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
