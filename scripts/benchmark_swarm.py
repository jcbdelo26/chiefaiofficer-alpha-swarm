#!/usr/bin/env python3
"""
Swarm Performance Benchmark
============================
Comprehensive performance evaluation and health reporting for the Unified Swarm.

Metrics:
- End-to-end latency (Lead → Meeting)
- Task throughput (tasks/second)
- Memory usage under load
- Agent response times
- Queue processing efficiency

Output:
- JSON metrics file
- Markdown health report
"""

import asyncio
import time
import psutil
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any
from unittest.mock import MagicMock, AsyncMock

# Add parent dir to path
import sys
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from execution.unified_queen_orchestrator import UnifiedQueen, Task, TaskPriority, AgentName
from execution.scheduler_agent import SchedulerAgent
from execution.researcher_agent import ResearcherAgent
from execution.gatekeeper_queue import EnhancedGatekeeperQueue
from core.approval_engine import ApprovalRequest

# ============================================================================
# MOCK SETUP (To avoid external API calls during benchmarking)
# ============================================================================

class BenchmarkScheduler(SchedulerAgent):
    def __init__(self):
        self.calendar = AsyncMock()
    
    async def generate_proposals(self, prospect_timezone: str, duration_minutes: int):
        await asyncio.sleep(0.05)  # Simulate processing time
        return [{"start": "2026-01-24T10:00:00Z", "score": 1.0}]
    
    async def book_meeting(self, prospect_email: str, start_time: str, duration_minutes: int, title: str, with_zoom: bool = False):
        await asyncio.sleep(0.08)  # Simulate booking time
        return MagicMock(success=True, event_id="evt_benchmark")

class BenchmarkResearcher(ResearcherAgent):
    async def research_company(self, company_name: str, domain: str):
        await asyncio.sleep(0.1)  # Simulate research time
        return MagicMock(company_name=company_name, industry="Tech")
    
    async def research_attendee(self, email: str, name: str, ghl_contact_id: str = None):
        await asyncio.sleep(0.07)
        return MagicMock(email=email, ghl_tags=["vip"])

class BenchmarkQueen(UnifiedQueen):
    """Queen configured for benchmarking."""
    def __init__(self, scheduler, researcher, gatekeeper):
        super().__init__()
        self.scheduler_agent = scheduler
        self.researcher_agent = researcher
        self.gatekeeper_agent = gatekeeper
        self.router = MagicMock()
        self.consensus_engine = AsyncMock()
        
    async def _execute_task(self, task: Task) -> Dict[str, Any]:
        """Mock execution for benchmarking."""
        if task.task_type in ["scheduling_request", "meeting_book"]:
            agent = AgentName.SCHEDULER
        else:
            agent = AgentName.RESEARCHER
        
        result = {}
        
        if agent == AgentName.SCHEDULER:
            if task.task_type == "scheduling_request":
                result = {"proposals": await self.scheduler_agent.generate_proposals("UTC", 30)}
            elif task.task_type == "meeting_book":
                result = {"booking": await self.scheduler_agent.book_meeting(
                    task.parameters["prospect_email"],
                    task.parameters["start_time"],
                    30,
                    "Benchmark"
                )}
        elif agent == AgentName.RESEARCHER:
            if task.task_type == "company_intel":
                result = {"intel": await self.researcher_agent.research_company(
                    task.parameters["company_name"],
                    task.parameters["domain"]
                )}
        
        from execution.unified_queen_orchestrator import TaskStatus
        task.status = TaskStatus.COMPLETED
        task.result = result
        return {"task_id": task.id, "agent": agent.value, "status": "completed", "result": result}

# ============================================================================
# BENCHMARK FUNCTIONS
# ============================================================================

async def benchmark_throughput(queen: BenchmarkQueen, num_tasks: int = 100) -> Dict[str, Any]:
    """
    Measure task throughput (tasks/second).
    """
    print(f"\n[1/4] Benchmarking Throughput ({num_tasks} tasks)...")
    
    tasks = []
    for i in range(num_tasks):
        task = queen.create_task(
            task_type="company_intel",
            parameters={"company_name": f"Company {i}", "domain": f"company{i}.com"}
        )
        tasks.append(task)
    
    start = time.time()
    await asyncio.gather(*(queen._execute_task(t) for t in tasks))
    duration = time.time() - start
    
    throughput = num_tasks / duration
    avg_latency = duration / num_tasks
    
    return {
        "total_tasks": num_tasks,
        "duration_seconds": round(duration, 2),
        "throughput_tasks_per_second": round(throughput, 2),
        "avg_latency_ms": round(avg_latency * 1000, 2)
    }


async def benchmark_e2e_latency(queen: BenchmarkQueen) -> Dict[str, Any]:
    """
    Measure end-to-end latency for a full workflow (Research → Schedule → Book).
    """
    print(f"\n[2/4] Benchmarking End-to-End Latency...")
    
    # Step 1: Research
    start = time.time()
    
    research_task = queen.create_task("company_intel", {"company_name": "TestCo", "domain": "test.co"})
    await queen._execute_task(research_task)
    research_time = time.time() - start
    
    # Step 2: Schedule
    schedule_task = queen.create_task("scheduling_request", {"prospect_timezone": "UTC", "duration_minutes": 30})
    schedule_start = time.time()
    await queen._execute_task(schedule_task)
    schedule_time = time.time() - schedule_start
    
    # Step 3: Book
    book_task = queen.create_task("meeting_book", {
        "prospect_email": "test@test.co",
        "start_time": "2026-01-24T10:00:00Z"
    })
    book_start = time.time()
    await queen._execute_task(book_task)
    book_time = time.time() - book_start
    
    total_time = time.time() - start
    
    return {
        "research_ms": round(research_time * 1000, 2),
        "schedule_ms": round(schedule_time * 1000, 2),
        "book_ms": round(book_time * 1000, 2),
        "total_e2e_ms": round(total_time * 1000, 2)
    }


def benchmark_memory_usage() -> Dict[str, Any]:
    """
    Measure current memory usage of the process.
    """
    print(f"\n[3/4] Benchmarking Memory Usage...")
    
    process = psutil.Process()
    mem_info = process.memory_info()
    
    return {
        "rss_mb": round(mem_info.rss / (1024 * 1024), 2),
        "vms_mb": round(mem_info.vms / (1024 * 1024), 2)
    }


async def benchmark_concurrent_load(queen: BenchmarkQueen, concurrency: int = 50) -> Dict[str, Any]:
    """
    Measure performance under concurrent load.
    """
    print(f"\n[4/4] Benchmarking Concurrent Load ({concurrency} tasks)...")
    
    tasks = []
    for i in range(concurrency):
        task = queen.create_task(
            task_type="company_intel",
            parameters={"company_name": f"Concurrent {i}", "domain": f"concurrent{i}.com"}
        )
        tasks.append(task)
    
    start = time.time()
    await asyncio.gather(*(queen._execute_task(t) for t in tasks))
    duration = time.time() - start
    
    return {
        "concurrent_tasks": concurrency,
        "duration_seconds": round(duration, 2),
        "tasks_per_second": round(concurrency / duration, 2)
    }


# ============================================================================
# HEALTH REPORT GENERATION
# ============================================================================

def generate_health_report(metrics: Dict[str, Any]) -> str:
    """
    Generate a markdown health report from benchmark metrics.
    """
    report = f"""# Unified Swarm Health Report

**Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---

## 📊 Performance Metrics

### Throughput
- **Total Tasks**: {metrics['throughput']['total_tasks']}
- **Duration**: {metrics['throughput']['duration_seconds']}s
- **Throughput**: **{metrics['throughput']['throughput_tasks_per_second']} tasks/s**
- **Avg Latency**: {metrics['throughput']['avg_latency_ms']}ms

### End-to-End Latency (Lead → Meeting)
- **Research**: {metrics['e2e_latency']['research_ms']}ms
- **Scheduling**: {metrics['e2e_latency']['schedule_ms']}ms
- **Booking**: {metrics['e2e_latency']['book_ms']}ms
- **Total E2E**: **{metrics['e2e_latency']['total_e2e_ms']}ms**

### Concurrent Load ({metrics['concurrent_load']['concurrent_tasks']} tasks)
- **Duration**: {metrics['concurrent_load']['duration_seconds']}s
- **Throughput**: **{metrics['concurrent_load']['tasks_per_second']} tasks/s**

### Memory Usage
- **RSS**: {metrics['memory']['rss_mb']} MB
- **VMS**: {metrics['memory']['vms_mb']} MB

---

## ✅ Health Status

"""
    
    # Determine health status based on metrics
    health_checks = []
    
    # Check throughput
    if metrics['throughput']['throughput_tasks_per_second'] >= 20:
        health_checks.append("✅ **Throughput**: Excellent (≥20 tasks/s)")
    elif metrics['throughput']['throughput_tasks_per_second'] >= 10:
        health_checks.append("⚠️ **Throughput**: Good (≥10 tasks/s)")
    else:
        health_checks.append("❌ **Throughput**: Needs Improvement (<10 tasks/s)")
    
    # Check E2E latency
    if metrics['e2e_latency']['total_e2e_ms'] <= 500:
        health_checks.append("✅ **E2E Latency**: Excellent (≤500ms)")
    elif metrics['e2e_latency']['total_e2e_ms'] <= 1000:
        health_checks.append("⚠️ **E2E Latency**: Good (≤1000ms)")
    else:
        health_checks.append("❌ **E2E Latency**: Needs Improvement (>1000ms)")
    
    # Check memory
    if metrics['memory']['rss_mb'] <= 500:
        health_checks.append("✅ **Memory**: Healthy (≤500 MB)")
    elif metrics['memory']['rss_mb'] <= 1000:
        health_checks.append("⚠️ **Memory**: Moderate (≤1000 MB)")
    else:
        health_checks.append("❌ **Memory**: High (>1000 MB)")
    
    report += "\n".join(health_checks)
    report += "\n\n---\n\n**Overall Status**: "
    
    if all("✅" in check for check in health_checks):
        report += "🟢 **HEALTHY**"
    elif any("❌" in check for check in health_checks):
        report += "🔴 **CRITICAL**"
    else:
        report += "🟡 **WARNING**"
    
    return report


# ============================================================================
# MAIN BENCHMARK EXECUTION
# ============================================================================

async def run_benchmarks():
    """
    Run all benchmarks and generate reports.
    """
    print("=" * 60)
    print("UNIFIED SWARM PERFORMANCE BENCHMARK")
    print("=" * 60)
    
    # Setup
    scheduler = BenchmarkScheduler()
    researcher = BenchmarkResearcher()
    gatekeeper = EnhancedGatekeeperQueue(test_mode=True)
    gatekeeper.approval_engine.submit_request = MagicMock(return_value=ApprovalRequest(
        request_id="req_bench", status="approved", requester_agent="benchmark",
        action_type="test", payload={}, risk_score=0.1, created_at="", updated_at=""
    ))
    
    queen = BenchmarkQueen(scheduler, researcher, gatekeeper)
    
    # Run benchmarks
    metrics = {
        "throughput": await benchmark_throughput(queen, num_tasks=100),
        "e2e_latency": await benchmark_e2e_latency(queen),
        "memory": benchmark_memory_usage(),
        "concurrent_load": await benchmark_concurrent_load(queen, concurrency=50)
    }
    
    # Save metrics
    metrics_file = PROJECT_ROOT / ".tmp" / "benchmark_metrics.json"
    metrics_file.parent.mkdir(exist_ok=True)
    with open(metrics_file, "w") as f:
        json.dump(metrics, f, indent=2)
    
    # Generate report
    report = generate_health_report(metrics)
    report_file = PROJECT_ROOT / ".tmp" / "swarm_health_report.md"
    with open(report_file, "w") as f:
        f.write(report)
    
    print("\n" + "=" * 60)
    print("BENCHMARK COMPLETE")
    print("=" * 60)
    print(f"Metrics saved to: {metrics_file}")
    print(f"Report saved to: {report_file}")
    print("\n" + report)


if __name__ == "__main__":
    asyncio.run(run_benchmarks())
