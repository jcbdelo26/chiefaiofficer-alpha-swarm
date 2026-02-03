"""
Tests for Workflow Simulation Framework
========================================
Comprehensive tests for workflow_simulator.py
"""

import pytest
import asyncio
from dataclasses import asdict
from unittest.mock import patch, AsyncMock

from execution.workflow_simulator import (
    SimulationMode,
    SimulatedLead,
    SimulationStep,
    SimulationResult,
    AgentSimulator,
    WorkflowSimulator,
)


class TestSimulatedLead:
    """Tests for SimulatedLead dataclass."""
    
    def test_create_single_lead(self):
        """Test creating a single lead."""
        lead = SimulatedLead(
            id="lead_001",
            email="test@example.com",
            name="Test Lead",
            company="Test Corp",
            title="VP Sales"
        )
        assert lead.id == "lead_001"
        assert lead.email == "test@example.com"
        assert lead.employee_count == 100
        assert lead.icp_score == 75
    
    def test_generate_single_lead(self):
        """Test generating a single random lead."""
        leads = SimulatedLead.generate(count=1)
        assert len(leads) == 1
        assert leads[0].id == "lead_0000"
        assert "@" in leads[0].email
    
    def test_generate_multiple_leads(self):
        """Test generating multiple random leads."""
        leads = SimulatedLead.generate(count=10)
        assert len(leads) == 10
        ids = [l.id for l in leads]
        assert len(set(ids)) == 10
    
    def test_generate_leads_have_valid_fields(self):
        """Test that generated leads have valid field values."""
        leads = SimulatedLead.generate(count=5)
        for lead in leads:
            assert lead.employee_count >= 50
            assert lead.employee_count <= 500
            assert lead.icp_score >= 60
            assert lead.icp_score <= 95
            assert lead.title in ["VP Sales", "CRO", "Director RevOps", "Head of Sales", "CEO"]
    
    def test_lead_to_dict(self):
        """Test converting lead to dictionary."""
        lead = SimulatedLead(
            id="lead_001",
            email="test@example.com",
            name="Test Lead",
            company="Test Corp",
            title="VP Sales"
        )
        d = asdict(lead)
        assert d["id"] == "lead_001"
        assert d["email"] == "test@example.com"
        assert "timezone" in d


class TestSimulationStep:
    """Tests for SimulationStep dataclass."""
    
    def test_create_step(self):
        """Test creating a simulation step."""
        step = SimulationStep(
            agent="HUNTER",
            action="scrape",
            input_data={"url": "test.com"}
        )
        assert step.agent == "HUNTER"
        assert step.success is True
        assert step.error is None
    
    def test_step_with_error(self):
        """Test creating a failed step."""
        step = SimulationStep(
            agent="ENRICHER",
            action="enrich",
            input_data={},
            success=False,
            error="API timeout"
        )
        assert step.success is False
        assert step.error == "API timeout"
    
    def test_step_has_timestamp(self):
        """Test that step has automatic timestamp."""
        step = SimulationStep(
            agent="HUNTER",
            action="scrape",
            input_data={}
        )
        assert step.timestamp is not None
        assert "T" in step.timestamp


class TestAgentSimulator:
    """Tests for AgentSimulator class."""
    
    @pytest.mark.asyncio
    async def test_simulate_hunter_happy_path(self):
        """Test hunter simulation in happy path mode."""
        sim = AgentSimulator(SimulationMode.HAPPY_PATH)
        result = await sim.simulate_hunter({})
        assert "leads_scraped" in result
        assert "profiles" in result
        assert len(result["profiles"]) == 10
    
    @pytest.mark.asyncio
    async def test_simulate_enricher_happy_path(self):
        """Test enricher simulation."""
        sim = AgentSimulator(SimulationMode.HAPPY_PATH)
        leads = [{"id": "1"}, {"id": "2"}]
        result = await sim.simulate_enricher({"leads": leads})
        assert result["enriched_count"] == 2
        assert "data" in result
    
    @pytest.mark.asyncio
    async def test_simulate_segmentor(self):
        """Test segmentor classifies leads by ICP score."""
        sim = AgentSimulator(SimulationMode.HAPPY_PATH)
        leads = [
            {"id": "1", "icp_score": 90},
            {"id": "2", "icp_score": 75},
            {"id": "3", "icp_score": 60}
        ]
        result = await sim.simulate_segmentor({"leads": leads})
        assert len(result["tier1"]) == 1
        assert len(result["tier2"]) == 1
        assert len(result["tier3"]) == 1
    
    @pytest.mark.asyncio
    async def test_simulate_scheduler_happy_path(self):
        """Test scheduler simulation."""
        sim = AgentSimulator(SimulationMode.HAPPY_PATH)
        result = await sim.simulate_scheduler({})
        assert result["meeting_booked"] is True
        assert "event_id" in result
        assert "zoom_link" in result
    
    @pytest.mark.asyncio
    async def test_simulate_researcher(self):
        """Test researcher simulation."""
        sim = AgentSimulator(SimulationMode.HAPPY_PATH)
        result = await sim.simulate_researcher({})
        assert result["brief_generated"] is True
        assert "talking_points" in result
        assert len(result["talking_points"]) > 0
    
    @pytest.mark.asyncio
    async def test_simulate_gatekeeper(self):
        """Test gatekeeper simulation."""
        sim = AgentSimulator(SimulationMode.HAPPY_PATH)
        result = await sim.simulate_gatekeeper({})
        assert "approved" in result
        assert "reason" in result
    
    def test_failure_rate_happy_path(self):
        """Test failure rate is 0 in happy path mode."""
        sim = AgentSimulator(SimulationMode.HAPPY_PATH)
        assert sim.failure_rate == 0.0
    
    def test_failure_rate_chaos_mode(self):
        """Test failure rate is set in chaos mode."""
        sim = AgentSimulator(SimulationMode.CHAOS)
        assert sim.failure_rate == 0.1


class TestWorkflowSimulator:
    """Tests for WorkflowSimulator class."""
    
    @pytest.mark.asyncio
    async def test_simulate_lead_to_meeting_happy_path(self):
        """Test full lead-to-meeting workflow in happy path."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        result = await sim.simulate_lead_to_meeting(count=5)
        
        assert result.success is True
        assert result.workflow_name == "lead_to_meeting"
        assert len(result.steps) == 6
        assert result.metrics["leads_processed"] == 5
    
    @pytest.mark.asyncio
    async def test_simulate_lead_to_meeting_with_custom_leads(self):
        """Test workflow with custom leads."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        custom_leads = [
            SimulatedLead(
                id="custom_001",
                email="custom@test.com",
                name="Custom Lead",
                company="Custom Corp",
                title="CEO"
            )
        ]
        result = await sim.simulate_lead_to_meeting(leads=custom_leads)
        assert result.success is True
        assert result.metrics["leads_processed"] == 1
    
    @pytest.mark.asyncio
    async def test_simulate_pipeline_scan(self):
        """Test pipeline scan workflow."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        result = await sim.simulate_pipeline_scan()
        
        assert result.success is True
        assert result.workflow_name == "pipeline_scan"
        assert len(result.steps) == 4
        agents = [s.agent for s in result.steps]
        assert agents == ["SCOUT", "COACH", "PIPER", "OPERATOR"]
    
    @pytest.mark.asyncio
    async def test_workflow_records_duration(self):
        """Test that workflow records duration."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        result = await sim.simulate_lead_to_meeting(count=1)
        
        assert result.total_duration_ms > 0
        for step in result.steps:
            assert step.duration_ms >= 0
    
    @pytest.mark.asyncio
    async def test_workflow_records_timestamps(self):
        """Test that workflow records timestamps."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        result = await sim.simulate_lead_to_meeting(count=1)
        
        assert result.started_at is not None
        assert result.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_results_are_stored(self):
        """Test that results are stored in simulator."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        await sim.simulate_lead_to_meeting(count=1)
        await sim.simulate_pipeline_scan()
        
        assert len(sim.results) == 2
    
    @pytest.mark.asyncio
    async def test_get_report_empty(self):
        """Test get_report with no simulations."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        report = sim.get_report()
        assert "message" in report
    
    @pytest.mark.asyncio
    async def test_get_report_with_results(self):
        """Test get_report after simulations."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        await sim.simulate_lead_to_meeting(count=1)
        await sim.simulate_lead_to_meeting(count=1)
        
        report = sim.get_report()
        assert report["total_simulations"] == 2
        assert report["successful"] == 2
        assert "avg_duration_ms" in report
        assert "lead_to_meeting" in report["by_workflow"]


class TestChaosMode:
    """Tests for chaos mode with failures."""
    
    @pytest.mark.asyncio
    async def test_chaos_mode_can_fail(self):
        """Test that chaos mode can produce failures."""
        sim = AgentSimulator(SimulationMode.CHAOS)
        sim.failure_rate = 1.0
        
        with pytest.raises(Exception):
            await sim.simulate_hunter({})
    
    @pytest.mark.asyncio
    async def test_workflow_handles_step_failure(self):
        """Test workflow handles step failures gracefully."""
        sim = WorkflowSimulator(SimulationMode.CHAOS)
        sim.agent_sim.failure_rate = 1.0
        
        result = await sim.simulate_lead_to_meeting(count=1)
        assert result.success is False
        failed_steps = [s for s in result.steps if not s.success]
        assert len(failed_steps) > 0
    
    @pytest.mark.asyncio
    async def test_failed_step_has_error_message(self):
        """Test that failed steps have error messages."""
        sim = WorkflowSimulator(SimulationMode.CHAOS)
        sim.agent_sim.failure_rate = 1.0
        
        result = await sim.simulate_lead_to_meeting(count=1)
        failed_steps = [s for s in result.steps if not s.success]
        for step in failed_steps:
            assert step.error is not None


class TestStressTest:
    """Tests for stress testing functionality."""
    
    @pytest.mark.asyncio
    async def test_stress_test_runs_iterations(self):
        """Test stress test runs specified iterations."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        result = await sim.run_stress_test(iterations=10, concurrency=5)
        
        assert result["iterations"] == 10
        assert result["successful"] + result["failed"] + result["exceptions"] == 10
    
    @pytest.mark.asyncio
    async def test_stress_test_records_metrics(self):
        """Test stress test records metrics."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        result = await sim.run_stress_test(iterations=5, concurrency=2)
        
        assert "success_rate" in result
        assert "total_duration_seconds" in result
        assert "avg_duration_ms" in result
    
    @pytest.mark.asyncio
    async def test_stress_test_pipeline_scan(self):
        """Test stress test with pipeline_scan workflow."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        result = await sim.run_stress_test(
            workflow="pipeline_scan",
            iterations=5,
            concurrency=2
        )
        
        assert result["workflow"] == "pipeline_scan"
        assert result["successful"] > 0
    
    @pytest.mark.asyncio
    async def test_stress_test_high_concurrency(self):
        """Test stress test with high concurrency."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        result = await sim.run_stress_test(iterations=20, concurrency=10)
        
        assert result["success_rate"] > 0


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""
    
    def test_generate_zero_leads(self):
        """Test generating zero leads."""
        leads = SimulatedLead.generate(count=0)
        assert leads == []
    
    @pytest.mark.asyncio
    async def test_empty_leads_list(self):
        """Test workflow with empty leads list."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        result = await sim.simulate_lead_to_meeting(leads=[])
        assert result.metrics["leads_processed"] == 0
    
    @pytest.mark.asyncio
    async def test_unknown_agent_simulation(self):
        """Test running step for unknown agent uses default."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        step = await sim._run_step("UNKNOWN_AGENT", "action", {})
        assert step.success is True
        assert step.output_data == {"simulated": True}
    
    @pytest.mark.asyncio
    async def test_segmentor_empty_leads(self):
        """Test segmentor with empty leads."""
        sim = AgentSimulator(SimulationMode.HAPPY_PATH)
        result = await sim.simulate_segmentor({"leads": []})
        assert result["tier1"] == []
        assert result["tier2"] == []
        assert result["tier3"] == []
    
    @pytest.mark.asyncio
    async def test_simulation_mode_enum(self):
        """Test all simulation modes exist."""
        assert SimulationMode.HAPPY_PATH.value == "happy_path"
        assert SimulationMode.CHAOS.value == "chaos"
        assert SimulationMode.STRESS.value == "stress"
        assert SimulationMode.EDGE_CASES.value == "edge_cases"


class TestReportGeneration:
    """Tests for report generation."""
    
    @pytest.mark.asyncio
    async def test_report_by_workflow_breakdown(self):
        """Test report includes workflow breakdown."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        await sim.simulate_lead_to_meeting(count=1)
        await sim.simulate_pipeline_scan()
        
        report = sim.get_report()
        assert "lead_to_meeting" in report["by_workflow"]
        assert "pipeline_scan" in report["by_workflow"]
    
    @pytest.mark.asyncio
    async def test_report_success_rate_calculation(self):
        """Test report calculates success rate correctly."""
        sim = WorkflowSimulator(SimulationMode.HAPPY_PATH)
        await sim.simulate_lead_to_meeting(count=1)
        await sim.simulate_lead_to_meeting(count=1)
        
        report = sim.get_report()
        assert report["by_workflow"]["lead_to_meeting"]["success_rate"] == 100.0
    
    @pytest.mark.asyncio
    async def test_report_failed_count(self):
        """Test report counts failed simulations."""
        sim = WorkflowSimulator(SimulationMode.CHAOS)
        sim.agent_sim.failure_rate = 1.0
        
        await sim.simulate_lead_to_meeting(count=1)
        
        report = sim.get_report()
        assert report["failed"] == 1
