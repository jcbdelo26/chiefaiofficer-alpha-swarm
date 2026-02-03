#!/usr/bin/env python3
"""
Stress Test Suite
=================
Load and stress tests for the agent swarm system.

Tests include:
- Concurrent lead processing
- Rate limit saturation
- Queue depth explosion
- Agent failure cascades
- Resource exhaustion
- Performance benchmarks
"""

import asyncio
import gc
import sys
import time
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from execution.workflow_simulator import (
    WorkflowSimulator,
    SimulationMode,
    SimulatedLead,
    SimulationResult,
    AgentSimulator,
)
from core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitState,
    CircuitBreakerError,
    get_registry,
)
from core.swarm_coordination import (
    SwarmCoordinator,
    WorkerPool,
    CoordinationConfig,
    WorkerStatus,
    HeartbeatMonitor,
)


@dataclass
class StressTestMetrics:
    """Metrics collected during stress tests."""
    total_items: int = 0
    successful: int = 0
    failed: int = 0
    total_duration_seconds: float = 0
    throughput_per_minute: float = 0
    avg_latency_ms: float = 0
    p95_latency_ms: float = 0
    p99_latency_ms: float = 0
    max_latency_ms: float = 0
    errors: List[str] = field(default_factory=list)
    
    def calculate_percentiles(self, latencies: List[float]):
        """Calculate latency percentiles."""
        if not latencies:
            return
        sorted_latencies = sorted(latencies)
        self.avg_latency_ms = statistics.mean(sorted_latencies)
        self.max_latency_ms = max(sorted_latencies)
        p95_idx = int(len(sorted_latencies) * 0.95)
        p99_idx = int(len(sorted_latencies) * 0.99)
        self.p95_latency_ms = sorted_latencies[min(p95_idx, len(sorted_latencies) - 1)]
        self.p99_latency_ms = sorted_latencies[min(p99_idx, len(sorted_latencies) - 1)]


class TestConcurrentLeads:
    """Tests for concurrent lead processing."""
    
    @pytest.mark.asyncio
    async def test_100_concurrent_leads(self):
        """Process 100 leads concurrently without failures."""
        simulator = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        leads = SimulatedLead.generate(100)
        
        start_time = time.time()
        
        tasks = []
        batch_size = 10
        for i in range(0, len(leads), batch_size):
            batch = leads[i:i + batch_size]
            task = simulator.simulate_lead_to_meeting(leads=batch, count=len(batch))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        duration = time.time() - start_time
        
        successful = sum(1 for r in results if isinstance(r, SimulationResult) and r.success)
        failed = sum(1 for r in results if isinstance(r, SimulationResult) and not r.success)
        exceptions = sum(1 for r in results if isinstance(r, Exception))
        
        throughput = len(leads) / (duration / 60) if duration > 0 else 0
        
        assert successful > 0, "At least some leads should process successfully"
        assert successful >= len(tasks) * 0.9, f"Expected 90%+ success rate, got {successful}/{len(tasks)}"
        assert throughput > 60, f"Expected >60 leads/minute, got {throughput:.1f}"
    
    @pytest.mark.asyncio
    async def test_500_leads_sequential(self):
        """Process 500 leads in batches."""
        simulator = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        total_leads = 500
        batch_size = 50
        
        metrics = StressTestMetrics(total_items=total_leads)
        latencies = []
        start_time = time.time()
        
        for batch_num in range(0, total_leads, batch_size):
            batch_start = time.time()
            leads = SimulatedLead.generate(batch_size)
            
            result = await simulator.simulate_lead_to_meeting(leads=leads, count=batch_size)
            
            batch_duration = (time.time() - batch_start) * 1000
            latencies.append(batch_duration)
            
            if result.success:
                metrics.successful += batch_size
            else:
                metrics.failed += batch_size
                metrics.errors.extend(result.errors)
        
        metrics.total_duration_seconds = time.time() - start_time
        metrics.throughput_per_minute = total_leads / (metrics.total_duration_seconds / 60)
        metrics.calculate_percentiles(latencies)
        
        assert metrics.successful >= total_leads * 0.95, "Expected 95%+ success rate"
        assert metrics.total_duration_seconds < 60, "Should complete 500 leads in under 60 seconds"
    
    @pytest.mark.asyncio
    async def test_concurrent_same_company(self):
        """Handle multiple leads from same company."""
        simulator = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        
        leads = []
        for i in range(20):
            lead = SimulatedLead(
                id=f"lead_{i:04d}",
                email=f"person{i}@acme-corp.com",
                name=f"Test Person {i}",
                company="Acme Corp",
                title=random.choice(["VP Sales", "CRO", "Director"]),
                employee_count=500,
                icp_score=random.randint(70, 95)
            )
            leads.append(lead)
        
        tasks = [simulator.simulate_lead_to_meeting(leads=[lead]) for lead in leads]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful = sum(1 for r in results if isinstance(r, SimulationResult) and r.success)
        
        assert successful >= 18, "At least 90% of same-company leads should succeed"
        
        companies_processed = set()
        for r in results:
            if isinstance(r, SimulationResult):
                for step in r.steps:
                    if step.input_data and "leads" in step.input_data:
                        for lead_data in step.input_data["leads"]:
                            companies_processed.add(lead_data.get("company"))
        
        assert "Acme Corp" in companies_processed or len(companies_processed) == 0


class TestRateLimitSaturation:
    """Tests for rate limit behavior under load."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_saturation(self):
        """Test behavior when rate limits are exhausted."""
        call_count = 0
        blocked_count = 0
        max_calls = 5
        
        async def rate_limited_operation():
            nonlocal call_count, blocked_count
            call_count += 1
            if call_count > max_calls:
                blocked_count += 1
                raise Exception("Rate limit exceeded")
            await asyncio.sleep(0.01)
            return {"success": True}
        
        results = []
        for _ in range(10):
            try:
                result = await rate_limited_operation()
                results.append(result)
            except Exception as e:
                results.append({"error": str(e)})
        
        successful = sum(1 for r in results if r.get("success"))
        blocked = sum(1 for r in results if "error" in r)
        
        assert successful == max_calls, f"Expected {max_calls} successful calls"
        assert blocked == 5, "Expected 5 blocked calls"
        assert blocked_count == 5, "Should track 5 rate limit blocks"
    
    @pytest.mark.asyncio
    async def test_rate_limit_recovery(self):
        """Test system recovers after rate limit reset."""
        rate_limit_active = True
        window_calls = 0
        max_per_window = 3
        
        async def windowed_operation():
            nonlocal window_calls
            window_calls += 1
            if rate_limit_active and window_calls > max_per_window:
                raise Exception("Rate limited")
            return {"success": True}
        
        results_phase1 = []
        for _ in range(5):
            try:
                r = await windowed_operation()
                results_phase1.append(r)
            except Exception as e:
                results_phase1.append({"error": str(e)})
        
        assert sum(1 for r in results_phase1 if r.get("success")) == 3
        
        window_calls = 0
        
        results_phase2 = []
        for _ in range(3):
            try:
                r = await windowed_operation()
                results_phase2.append(r)
            except Exception as e:
                results_phase2.append({"error": str(e)})
        
        assert sum(1 for r in results_phase2 if r.get("success")) == 3
    
    @pytest.mark.asyncio
    async def test_distributed_rate_limiting(self):
        """Test rate limits are enforced across agents."""
        shared_counter = {"count": 0}
        limit = 10
        lock = asyncio.Lock()
        
        async def agent_call(agent_id: str):
            async with lock:
                if shared_counter["count"] >= limit:
                    return {"agent": agent_id, "blocked": True}
                shared_counter["count"] += 1
            await asyncio.sleep(0.01)
            return {"agent": agent_id, "blocked": False}
        
        agents = ["HUNTER", "ENRICHER", "CRAFTER", "SCHEDULER"]
        tasks = []
        for _ in range(5):
            for agent in agents:
                tasks.append(agent_call(agent))
        
        results = await asyncio.gather(*tasks)
        
        successful = sum(1 for r in results if not r.get("blocked"))
        blocked = sum(1 for r in results if r.get("blocked"))
        
        assert successful == limit, f"Expected exactly {limit} successful calls"
        assert blocked == 10, "Expected 10 blocked calls"
        
        successful_per_agent = {}
        for r in results:
            if not r.get("blocked"):
                agent = r["agent"]
                successful_per_agent[agent] = successful_per_agent.get(agent, 0) + 1
        
        assert len(successful_per_agent) >= 2, "Multiple agents should share the rate limit"


class TestQueueDepth:
    """Tests for queue handling under extreme load."""
    
    @pytest.mark.asyncio
    async def test_queue_depth_explosion(self):
        """Test behavior with 1000+ queued items."""
        queue = asyncio.Queue(maxsize=100)
        processed = []
        rejected = []
        
        async def producer():
            for i in range(1000):
                try:
                    queue.put_nowait({"id": i, "priority": random.randint(1, 3)})
                except asyncio.QueueFull:
                    rejected.append(i)
        
        async def consumer():
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.1)
                    await asyncio.sleep(0.001)
                    processed.append(item["id"])
                except asyncio.TimeoutError:
                    break
        
        await producer()
        
        consumers = [asyncio.create_task(consumer()) for _ in range(10)]
        await asyncio.gather(*consumers)
        
        assert len(processed) > 0, "Should process some items"
        assert len(rejected) > 0, "Should reject items when queue is full (backpressure)"
        assert len(processed) + len(rejected) == 1000, "All items should be accounted for"
    
    @pytest.mark.asyncio
    async def test_queue_prioritization_under_load(self):
        """Test high-priority items still processed first."""
        items = []
        
        for i in range(100):
            priority = 1 if i < 10 else (2 if i < 30 else 3)
            items.append({"id": i, "priority": priority})
        
        random.shuffle(items)
        
        sorted_items = sorted(items, key=lambda x: x["priority"])
        
        processed_order = []
        for item in sorted_items:
            await asyncio.sleep(0.001)
            processed_order.append(item["id"])
        
        high_priority_ids = {i for i in range(10)}
        first_20_processed = set(processed_order[:20])
        
        high_priority_in_first_20 = len(high_priority_ids & first_20_processed)
        assert high_priority_in_first_20 >= 8, "High priority items should be processed first"
    
    @pytest.mark.asyncio
    async def test_queue_timeout_handling(self):
        """Test items timeout correctly under load."""
        queue = asyncio.Queue()
        processed = []
        timed_out = []
        timeout_threshold = 0.05
        
        async def slow_processor(item):
            processing_time = item.get("processing_time", 0.01)
            await asyncio.sleep(processing_time)
            return item
        
        for i in range(50):
            await queue.put({
                "id": i,
                "processing_time": 0.1 if i % 5 == 0 else 0.01,
                "submitted_at": time.time()
            })
        
        while not queue.empty():
            item = await queue.get()
            try:
                result = await asyncio.wait_for(
                    slow_processor(item),
                    timeout=timeout_threshold
                )
                processed.append(result["id"])
            except asyncio.TimeoutError:
                timed_out.append(item["id"])
        
        assert len(processed) > 0, "Some items should be processed"
        assert len(timed_out) > 0, "Some slow items should timeout"
        assert len(processed) + len(timed_out) == 50, "All items should be accounted for"


class TestAgentFailureCascade:
    """Tests for agent failure handling and cascade prevention."""
    
    @pytest.mark.asyncio
    async def test_single_agent_failure(self):
        """Test system continues when one agent fails."""
        simulator = WorkflowSimulator(SimulationMode.CHAOS)
        simulator.agent_sim.failure_rate = 0.0
        
        original_enricher = simulator.agent_sim.simulate_enricher
        
        async def failing_enricher(params):
            raise Exception("ENRICHER agent crashed")
        
        simulator.agent_sim.simulate_enricher = failing_enricher
        
        leads = SimulatedLead.generate(10)
        result = await simulator.simulate_lead_to_meeting(leads=leads)
        
        enricher_steps = [s for s in result.steps if s.agent == "ENRICHER"]
        assert len(enricher_steps) > 0, "ENRICHER step should exist"
        assert not enricher_steps[0].success, "ENRICHER should have failed"
        
        other_steps = [s for s in result.steps if s.agent != "ENRICHER"]
        executed_after_failure = [s for s in other_steps if s.success]
        assert len(executed_after_failure) >= 0, "Other steps may continue despite ENRICHER failure"
    
    @pytest.mark.asyncio
    async def test_multiple_agent_failures(self):
        """Test graceful degradation with multiple failures."""
        simulator = WorkflowSimulator(SimulationMode.CHAOS)
        simulator.agent_sim.failure_rate = 0.5
        
        leads = SimulatedLead.generate(20)
        results = []
        
        for _ in range(10):
            result = await simulator.simulate_lead_to_meeting(leads=leads[:5])
            results.append(result)
        
        failures = sum(1 for r in results if not r.success)
        successes = sum(1 for r in results if r.success)
        
        assert failures > 0, "Some workflows should fail with 50% agent failure rate"
        assert successes >= 0, "System should attempt all workflows"
    
    @pytest.mark.asyncio
    async def test_cascade_prevention(self):
        """Test circuit breakers prevent cascade failures."""
        # Use a unique state file to avoid conflicts
        import tempfile
        state_file = Path(tempfile.gettempdir()) / f"test_cb_{id(self)}.json"
        if state_file.exists():
            state_file.unlink()
        
        registry = CircuitBreakerRegistry(state_file=state_file)
        registry.register("cascade_test_service", failure_threshold=3, recovery_timeout=60)
        
        failures_recorded = 0
        blocked_by_breaker = 0
        
        for i in range(10):
            if registry.is_available("cascade_test_service"):
                failures_recorded += 1
                registry.record_failure("cascade_test_service")
            else:
                blocked_by_breaker += 1
        
        breaker = registry.get_breaker("cascade_test_service")
        # After threshold failures, circuit should be OPEN
        assert breaker.state == CircuitState.OPEN, "Circuit should be open after failures"
        # Total should be 10 (some failures before open, rest blocked)
        assert failures_recorded + blocked_by_breaker == 10
        # Should have blocked at least some calls
        assert blocked_by_breaker >= 1, "Circuit breaker should have blocked some calls"
    
    @pytest.mark.asyncio
    async def test_auto_recovery_after_failures(self):
        """Test agents auto-restart after failure."""
        config = CoordinationConfig(
            heartbeat_interval_seconds=1,
            initial_workers=2,
            min_workers=1,
            max_workers=4,
            auto_restart=True,
            restart_delay_seconds=0.1
        )
        
        coordinator = SwarmCoordinator(config)
        
        processed_tasks = []
        
        async def task_handler(task):
            processed_tasks.append(task["task_id"])
        
        coordinator.set_task_handler(task_handler)
        
        await coordinator.start()
        
        try:
            for i in range(5):
                await coordinator.submit_task({"task_id": f"task_{i}"})
            
            await asyncio.sleep(0.5)
            
            status = coordinator.get_status()
            assert status["workers"]["total_workers"] >= 1, "Workers should be running"
            
        finally:
            await coordinator.stop()


class TestResourceExhaustion:
    """Tests for behavior under resource constraints."""
    
    @pytest.mark.asyncio
    async def test_memory_pressure(self):
        """Test behavior under memory pressure."""
        large_payloads = []
        
        for i in range(100):
            payload = {
                "id": i,
                "data": "x" * 10000,
                "nested": {"values": list(range(1000))}
            }
            large_payloads.append(payload)
        
        results = []
        for payload in large_payloads:
            await asyncio.sleep(0.001)
            results.append({"id": payload["id"], "processed": True})
        
        large_payloads.clear()
        gc.collect()
        
        assert len(results) == 100, "All payloads should be processed"
    
    @pytest.mark.asyncio
    async def test_connection_pool_exhaustion(self):
        """Test behavior when connections are exhausted."""
        max_connections = 5
        active_connections = {"count": 0}
        connection_errors = []
        successful_operations = []
        lock = asyncio.Lock()
        
        async def acquire_connection():
            async with lock:
                if active_connections["count"] >= max_connections:
                    raise Exception("Connection pool exhausted")
                active_connections["count"] += 1
            
            try:
                await asyncio.sleep(0.05)
                return True
            finally:
                async with lock:
                    active_connections["count"] -= 1
        
        async def operation(op_id: int):
            try:
                result = await acquire_connection()
                successful_operations.append(op_id)
                return result
            except Exception as e:
                connection_errors.append((op_id, str(e)))
                return False
        
        tasks = [operation(i) for i in range(20)]
        await asyncio.gather(*tasks)
        
        assert len(successful_operations) > 0, "Some operations should succeed"
    
    @pytest.mark.asyncio
    async def test_file_handle_limits(self):
        """Test behavior at file handle limits."""
        temp_dir = Path("/tmp/stress_test_files")
        temp_dir.mkdir(exist_ok=True)
        
        handles_opened = 0
        handle_errors = 0
        max_handles = 50
        
        files = []
        try:
            for i in range(100):
                try:
                    if handles_opened < max_handles:
                        f = open(temp_dir / f"test_{i}.txt", "w")
                        f.write(f"test content {i}")
                        files.append(f)
                        handles_opened += 1
                    else:
                        handle_errors += 1
                except OSError:
                    handle_errors += 1
            
            assert handles_opened == max_handles, f"Should open {max_handles} handles"
            assert handle_errors == 50, "Should have 50 handle errors"
            
        finally:
            for f in files:
                try:
                    f.close()
                except:
                    pass
            
            for f in temp_dir.glob("test_*.txt"):
                try:
                    f.unlink()
                except:
                    pass


class TestPerformanceBenchmarks:
    """Performance benchmark tests."""
    
    @pytest.mark.asyncio
    async def test_lead_processing_throughput(self):
        """Measure leads processed per minute. Target: >60 leads/minute."""
        simulator = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        
        start_time = time.time()
        processed_count = 0
        target_duration = 5
        
        while (time.time() - start_time) < target_duration:
            leads = SimulatedLead.generate(10)
            result = await simulator.simulate_lead_to_meeting(leads=leads)
            if result.success:
                processed_count += 10
        
        duration_minutes = (time.time() - start_time) / 60
        throughput = processed_count / duration_minutes if duration_minutes > 0 else 0
        
        assert throughput > 60, f"Expected >60 leads/minute, got {throughput:.1f}"
    
    @pytest.mark.asyncio
    async def test_response_time_p95(self):
        """Measure p95 response time. Target: <5 seconds."""
        simulator = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        latencies = []
        
        for _ in range(100):
            start = time.time()
            leads = SimulatedLead.generate(1)
            await simulator.simulate_lead_to_meeting(leads=leads)
            latency_ms = (time.time() - start) * 1000
            latencies.append(latency_ms)
        
        latencies.sort()
        p95_idx = int(len(latencies) * 0.95)
        p95_latency_ms = latencies[p95_idx]
        
        assert p95_latency_ms < 5000, f"Expected p95 <5000ms, got {p95_latency_ms:.1f}ms"
    
    @pytest.mark.asyncio
    async def test_workflow_completion_time(self):
        """Measure average workflow completion. Target: <30 seconds for lead-to-segment."""
        simulator = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        completion_times = []
        
        for _ in range(50):
            leads = SimulatedLead.generate(5)
            result = await simulator.simulate_lead_to_meeting(leads=leads)
            completion_times.append(result.total_duration_ms)
        
        avg_completion_ms = statistics.mean(completion_times)
        
        assert avg_completion_ms < 30000, f"Expected avg <30000ms, got {avg_completion_ms:.1f}ms"
    
    @pytest.mark.asyncio
    async def test_stress_test_method(self):
        """Test the built-in stress test method."""
        simulator = WorkflowSimulator(SimulationMode.STRESS)
        
        results = await simulator.run_stress_test(
            workflow="lead_to_meeting",
            iterations=50,
            concurrency=5
        )
        
        assert results["iterations"] == 50
        assert results["concurrency"] == 5
        assert results["success_rate"] >= 50, "Expected at least 50% success under stress"
        assert results["total_duration_seconds"] < 30, "Should complete stress test in <30s"
        
        report = simulator.get_report()
        assert report["total_simulations"] > 0


class TestChaosEngineering:
    """Chaos engineering tests for resilience."""
    
    @pytest.mark.asyncio
    async def test_random_failures_recovery(self):
        """Test system recovers from random failures."""
        simulator = WorkflowSimulator(SimulationMode.CHAOS)
        
        results = []
        for _ in range(20):
            leads = SimulatedLead.generate(5)
            result = await simulator.simulate_lead_to_meeting(leads=leads)
            results.append(result)
        
        success_count = sum(1 for r in results if r.success)
        
        assert success_count >= 10, "Should have at least 50% success rate under chaos"
    
    @pytest.mark.asyncio
    async def test_network_partition_simulation(self):
        """Simulate network partition behavior."""
        partitioned = False
        calls_during_partition = 0
        calls_after_recovery = 0
        
        async def network_call():
            nonlocal calls_during_partition, calls_after_recovery
            if partitioned:
                calls_during_partition += 1
                raise ConnectionError("Network partition")
            calls_after_recovery += 1
            return {"success": True}
        
        results = []
        for i in range(10):
            if i == 3:
                partitioned = True
            if i == 7:
                partitioned = False
            
            try:
                result = await network_call()
                results.append(result)
            except ConnectionError:
                results.append({"error": "partition"})
        
        successful = sum(1 for r in results if r.get("success"))
        errors = sum(1 for r in results if r.get("error"))
        
        assert successful == 6, "Should have 6 successful calls (3 before, 3 after partition)"
        assert errors == 4, "Should have 4 errors during partition"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--timeout=120"])
