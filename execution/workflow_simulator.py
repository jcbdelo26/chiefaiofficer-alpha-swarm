#!/usr/bin/env python3
"""
Workflow Simulation Framework
==============================
Simulates full agent workflows for testing without external APIs.

Usage:
    from execution.workflow_simulator import WorkflowSimulator
    
    sim = WorkflowSimulator()
    result = await sim.simulate_lead_to_meeting(lead_data)
"""

import asyncio
import json
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging

logger = logging.getLogger("workflow_simulator")

class SimulationMode(Enum):
    HAPPY_PATH = "happy_path"  # Everything succeeds
    CHAOS = "chaos"  # Random failures
    STRESS = "stress"  # High volume
    EDGE_CASES = "edge_cases"  # Boundary conditions

@dataclass
class SimulatedLead:
    """Simulated lead for testing."""
    id: str
    email: str
    name: str
    company: str
    title: str
    employee_count: int = 100
    icp_score: int = 75
    timezone: str = "America/New_York"
    
    @classmethod
    def generate(cls, count: int = 1) -> List["SimulatedLead"]:
        """Generate random leads."""
        titles = ["VP Sales", "CRO", "Director RevOps", "Head of Sales", "CEO"]
        companies = ["Acme Corp", "TechStart Inc", "Enterprise Co", "Growth LLC"]
        leads = []
        for i in range(count):
            leads.append(cls(
                id=f"lead_{i:04d}",
                email=f"prospect{i}@{random.choice(['acme', 'tech', 'corp'])}.com",
                name=f"Test Lead {i}",
                company=random.choice(companies),
                title=random.choice(titles),
                employee_count=random.randint(50, 500),
                icp_score=random.randint(60, 95)
            ))
        return leads

@dataclass
class SimulationStep:
    """A step in the simulation."""
    agent: str
    action: str
    input_data: Dict
    output_data: Optional[Dict] = None
    success: bool = True
    duration_ms: float = 0
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class SimulationResult:
    """Result of a workflow simulation."""
    workflow_name: str
    mode: SimulationMode
    success: bool
    steps: List[SimulationStep]
    total_duration_ms: float
    metrics: Dict[str, Any]
    errors: List[str]
    started_at: str
    completed_at: str

class AgentSimulator:
    """Simulates individual agent behavior."""
    
    def __init__(self, mode: SimulationMode = SimulationMode.HAPPY_PATH):
        self.mode = mode
        self.failure_rate = 0.0 if mode == SimulationMode.HAPPY_PATH else 0.1
        
    async def simulate_hunter(self, params: Dict) -> Dict:
        """Simulate HUNTER agent scraping."""
        await asyncio.sleep(random.uniform(0.05, 0.1))
        if self._should_fail():
            raise Exception("LinkedIn rate limit exceeded")
        return {
            "leads_scraped": random.randint(10, 50),
            "profiles": [{"id": f"li_{i}", "name": f"Lead {i}"} for i in range(10)]
        }
    
    async def simulate_enricher(self, params: Dict) -> Dict:
        """Simulate ENRICHER agent."""
        await asyncio.sleep(random.uniform(0.02, 0.05))
        if self._should_fail():
            raise Exception("Clay API error")
        return {
            "enriched_count": len(params.get("leads", [])),
            "data": {"company_size": 150, "tech_stack": ["Salesforce", "HubSpot"]}
        }
    
    async def simulate_segmentor(self, params: Dict) -> Dict:
        """Simulate SEGMENTOR agent."""
        await asyncio.sleep(random.uniform(0.01, 0.03))
        leads = params.get("leads", [])
        return {
            "tier1": [l for l in leads if l.get("icp_score", 0) >= 85],
            "tier2": [l for l in leads if 70 <= l.get("icp_score", 0) < 85],
            "tier3": [l for l in leads if l.get("icp_score", 0) < 70]
        }
    
    async def simulate_scheduler(self, params: Dict) -> Dict:
        """Simulate SCHEDULER agent."""
        await asyncio.sleep(random.uniform(0.03, 0.08))
        if self._should_fail():
            raise Exception("Calendar unavailable")
        
        base_time = datetime.now(timezone.utc) + timedelta(days=random.randint(1, 7))
        return {
            "meeting_booked": True,
            "event_id": f"event_{random.randint(1000, 9999)}",
            "scheduled_time": base_time.isoformat(),
            "zoom_link": f"https://zoom.us/j/{random.randint(100000000, 999999999)}"
        }
    
    async def simulate_researcher(self, params: Dict) -> Dict:
        """Simulate RESEARCHER agent."""
        await asyncio.sleep(random.uniform(0.05, 0.15))
        return {
            "brief_generated": True,
            "company_intel": {"industry": "SaaS", "funding": "$10M Series A"},
            "talking_points": ["Pain point 1", "Pain point 2"],
            "objection_predictions": [{"objection": "Price", "response": "ROI focus"}]
        }
    
    async def simulate_gatekeeper(self, params: Dict) -> Dict:
        """Simulate GATEKEEPER agent approval."""
        await asyncio.sleep(random.uniform(0.01, 0.02))
        return {
            "approved": random.random() > 0.1,  # 90% approval rate
            "reason": "Meets criteria" if random.random() > 0.1 else "Needs review"
        }
    
    def _should_fail(self) -> bool:
        return random.random() < self.failure_rate


class WorkflowSimulator:
    """
    Full workflow simulation engine.
    
    Simulates complete agent workflows for testing.
    """
    
    def __init__(self, mode: SimulationMode = SimulationMode.HAPPY_PATH):
        self.mode = mode
        self.agent_sim = AgentSimulator(mode)
        self.results: List[SimulationResult] = []
        
    async def simulate_lead_to_meeting(
        self,
        leads: List[SimulatedLead] = None,
        count: int = 10
    ) -> SimulationResult:
        """
        Simulate full lead-to-meeting workflow.
        
        Steps:
        1. HUNTER scrapes LinkedIn
        2. ENRICHER enriches with Clay
        3. SEGMENTOR classifies ICP
        4. CRAFTER creates campaign
        5. GATEKEEPER approves
        6. COMMUNICATOR sends
        7. SCHEDULER books meeting
        8. RESEARCHER preps brief
        """
        if leads is None:
            leads = SimulatedLead.generate(count)
        steps = []
        errors = []
        start = datetime.now(timezone.utc)
        
        try:
            # Step 1: Hunter
            step = await self._run_step("HUNTER", "scrape", {"url": "linkedin.com/company/test"})
            steps.append(step)
            
            # Step 2: Enricher
            step = await self._run_step("ENRICHER", "enrich", {"leads": [asdict(l) for l in leads]})
            steps.append(step)
            
            # Step 3: Segmentor
            step = await self._run_step("SEGMENTOR", "classify", {"leads": [asdict(l) for l in leads]})
            steps.append(step)
            
            # Step 4: Gatekeeper
            step = await self._run_step("GATEKEEPER", "approve", {"campaign_id": "camp_001"})
            steps.append(step)
            
            # Step 5: Scheduler
            step = await self._run_step("SCHEDULER", "book", {"lead_id": leads[0].id if leads else "test"})
            steps.append(step)
            
            # Step 6: Researcher
            step = await self._run_step("RESEARCHER", "prep", {"meeting_id": "mtg_001"})
            steps.append(step)
            
            success = all(s.success for s in steps)
            
        except Exception as e:
            errors.append(str(e))
            success = False
        
        end = datetime.now(timezone.utc)
        
        result = SimulationResult(
            workflow_name="lead_to_meeting",
            mode=self.mode,
            success=success,
            steps=steps,
            total_duration_ms=(end - start).total_seconds() * 1000,
            metrics={
                "leads_processed": len(leads),
                "steps_completed": len([s for s in steps if s.success]),
                "steps_failed": len([s for s in steps if not s.success])
            },
            errors=errors,
            started_at=start.isoformat(),
            completed_at=end.isoformat()
        )
        
        self.results.append(result)
        return result
    
    async def simulate_pipeline_scan(self) -> SimulationResult:
        """Simulate pipeline scan workflow."""
        steps = []
        start = datetime.now(timezone.utc)
        
        # Scout → Coach → Piper → Operator
        for agent in ["SCOUT", "COACH", "PIPER", "OPERATOR"]:
            step = await self._run_step(agent, "scan", {"pipeline_id": "main"})
            steps.append(step)
        
        end = datetime.now(timezone.utc)
        success = all(s.success for s in steps)
        
        result = SimulationResult(
            workflow_name="pipeline_scan",
            mode=self.mode,
            success=success,
            steps=steps,
            total_duration_ms=(end - start).total_seconds() * 1000,
            metrics={"agents_executed": len(steps)},
            errors=[s.error for s in steps if s.error],
            started_at=start.isoformat(),
            completed_at=end.isoformat()
        )
        
        self.results.append(result)
        return result
    
    async def run_stress_test(
        self,
        workflow: str = "lead_to_meeting",
        iterations: int = 100,
        concurrency: int = 10
    ) -> Dict[str, Any]:
        """Run stress test with high concurrency."""
        self.mode = SimulationMode.STRESS
        self.agent_sim = AgentSimulator(SimulationMode.STRESS)
        
        async def run_iteration():
            if workflow == "lead_to_meeting":
                return await self.simulate_lead_to_meeting(count=5)
            elif workflow == "pipeline_scan":
                return await self.simulate_pipeline_scan()
        
        start = datetime.now(timezone.utc)
        
        # Run in batches
        results = []
        for batch in range(0, iterations, concurrency):
            batch_size = min(concurrency, iterations - batch)
            batch_results = await asyncio.gather(
                *[run_iteration() for _ in range(batch_size)],
                return_exceptions=True
            )
            results.extend(batch_results)
        
        end = datetime.now(timezone.utc)
        
        successful = len([r for r in results if isinstance(r, SimulationResult) and r.success])
        failed = len([r for r in results if isinstance(r, SimulationResult) and not r.success])
        exceptions = len([r for r in results if isinstance(r, Exception)])
        
        return {
            "workflow": workflow,
            "iterations": iterations,
            "concurrency": concurrency,
            "successful": successful,
            "failed": failed,
            "exceptions": exceptions,
            "success_rate": successful / iterations * 100,
            "total_duration_seconds": (end - start).total_seconds(),
            "avg_duration_ms": sum(
                r.total_duration_ms for r in results if isinstance(r, SimulationResult)
            ) / max(1, successful + failed)
        }
    
    async def _run_step(self, agent: str, action: str, params: Dict) -> SimulationStep:
        """Run a single simulation step."""
        start = datetime.now(timezone.utc)
        
        try:
            # Map agent to simulator
            sim_fn = getattr(self.agent_sim, f"simulate_{agent.lower()}", None)
            if sim_fn:
                output = await sim_fn(params)
            else:
                await asyncio.sleep(0.01)
                output = {"simulated": True}
            
            duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            
            return SimulationStep(
                agent=agent,
                action=action,
                input_data=params,
                output_data=output,
                success=True,
                duration_ms=duration
            )
            
        except Exception as e:
            duration = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            return SimulationStep(
                agent=agent,
                action=action,
                input_data=params,
                success=False,
                duration_ms=duration,
                error=str(e)
            )
    
    def get_report(self) -> Dict[str, Any]:
        """Generate simulation report."""
        if not self.results:
            return {"message": "No simulations run"}
        
        return {
            "total_simulations": len(self.results),
            "successful": len([r for r in self.results if r.success]),
            "failed": len([r for r in self.results if not r.success]),
            "avg_duration_ms": sum(r.total_duration_ms for r in self.results) / len(self.results),
            "by_workflow": {
                workflow: {
                    "count": len([r for r in self.results if r.workflow_name == workflow]),
                    "success_rate": len([r for r in self.results if r.workflow_name == workflow and r.success]) / 
                                   max(1, len([r for r in self.results if r.workflow_name == workflow])) * 100
                }
                for workflow in set(r.workflow_name for r in self.results)
            }
        }


async def demo():
    """Demonstrate workflow simulator."""
    print("\n" + "=" * 60)
    print("WORKFLOW SIMULATOR - Demo")
    print("=" * 60)
    
    sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
    
    # Single workflow
    print("\n[Simulating Lead-to-Meeting Workflow]")
    result = await sim.simulate_lead_to_meeting(count=5)
    print(f"  Success: {result.success}")
    print(f"  Steps: {len(result.steps)}")
    print(f"  Duration: {result.total_duration_ms:.2f}ms")
    
    # Pipeline scan
    print("\n[Simulating Pipeline Scan]")
    result = await sim.simulate_pipeline_scan()
    print(f"  Success: {result.success}")
    print(f"  Agents: {[s.agent for s in result.steps]}")
    
    # Stress test
    print("\n[Running Stress Test - 50 iterations, 10 concurrent]")
    stress = await sim.run_stress_test(iterations=50, concurrency=10)
    print(f"  Success Rate: {stress['success_rate']:.1f}%")
    print(f"  Avg Duration: {stress['avg_duration_ms']:.2f}ms")
    print(f"  Total Time: {stress['total_duration_seconds']:.2f}s")
    
    # Report
    print("\n[Simulation Report]")
    report = sim.get_report()
    print(f"  Total: {report['total_simulations']}")
    print(f"  Successful: {report['successful']}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(demo())
