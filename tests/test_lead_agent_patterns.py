#!/usr/bin/env python3
"""
Tests for Vercel Lead Agent Patterns
====================================
Tests the 4 core patterns implemented from Vercel's Lead Agent:
1. Intent Interpreter (Intent Layer)
2. Durable Workflow (Checkpoint Persistence)
3. Confidence-Based Replanning (System Two Logic)
4. Bounded Tools (Fixed Tool Boundaries)
"""

import pytest
import asyncio
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# TEST: INTENT INTERPRETER
# =============================================================================

class TestIntentInterpreter:
    """Tests for the Intent Interpreter (Intent Layer)."""
    
    def test_interpret_discover_leads(self):
        """Test interpreting a lead discovery intent."""
        from core.intent_interpreter import IntentInterpreter, ObjectiveType
        
        interpreter = IntentInterpreter(storage_dir=Path(tempfile.mkdtemp()))
        
        goal = interpreter.interpret("Find 100 new leads from Gong competitors")
        
        assert goal.objective == ObjectiveType.DISCOVER_LEADS
        assert len(goal.steps) >= 1
        assert "HUNTER" in goal.agent_sequence
        assert goal.context.get("extracted_params", {}).get("limit") == 100
    
    def test_interpret_create_campaign(self):
        """Test interpreting a campaign creation intent."""
        from core.intent_interpreter import IntentInterpreter, ObjectiveType
        
        interpreter = IntentInterpreter(storage_dir=Path(tempfile.mkdtemp()))
        
        goal = interpreter.interpret("Create a campaign for tier_1 event attendees")
        
        assert goal.objective == ObjectiveType.CREATE_CAMPAIGN
        assert goal.requires_approval == True
        assert "CRAFTER" in goal.agent_sequence
        assert goal.context.get("extracted_params", {}).get("target_tier") == "tier_1"
    
    def test_interpret_urgency_extraction(self):
        """Test extraction of urgency from input."""
        from core.intent_interpreter import IntentInterpreter
        
        interpreter = IntentInterpreter(storage_dir=Path(tempfile.mkdtemp()))
        
        # High urgency
        goal = interpreter.interpret("Send the approved emails urgently now")
        assert goal.context.get("extracted_params", {}).get("urgency") == "high"
        assert goal.priority == 1
        
        # Low urgency
        goal = interpreter.interpret("Eventually qualify the new leads")
        assert goal.context.get("extracted_params", {}).get("urgency") == "low"
        assert goal.priority == 4
    
    def test_goal_serialization(self):
        """Test that goals can be serialized to dict."""
        from core.intent_interpreter import IntentInterpreter
        
        interpreter = IntentInterpreter(storage_dir=Path(tempfile.mkdtemp()))
        goal = interpreter.interpret("Score and tier all leads")
        
        goal_dict = goal.to_dict()
        
        assert "goal_id" in goal_dict
        assert "objective" in goal_dict
        assert "steps" in goal_dict
        assert isinstance(goal_dict["steps"], list)
    
    def test_agent_sequence_property(self):
        """Test the agent_sequence property returns correct order."""
        from core.intent_interpreter import IntentInterpreter
        
        interpreter = IntentInterpreter(storage_dir=Path(tempfile.mkdtemp()))
        goal = interpreter.interpret("Find and enrich new leads")
        
        sequence = goal.agent_sequence
        
        assert isinstance(sequence, list)
        assert len(sequence) >= 1


# =============================================================================
# TEST: DURABLE WORKFLOW
# =============================================================================

class TestDurableWorkflow:
    """Tests for Durable Workflow (Checkpoint Persistence)."""
    
    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "checkpoints.db"
    
    @pytest.mark.asyncio
    async def test_workflow_creation(self, temp_db_path):
        """Test creating a new workflow."""
        from core.durable_workflow import DurableWorkflow, CheckpointStore, WorkflowStatus
        
        store = CheckpointStore(temp_db_path)
        workflow = DurableWorkflow(
            workflow_id="test_001",
            workflow_type="lead_processing",
            store=store
        )
        
        status = workflow.get_status()
        
        assert status["workflow_id"] == "test_001"
        assert status["status"] == WorkflowStatus.IN_PROGRESS.value
    
    @pytest.mark.asyncio
    async def test_step_execution_and_checkpoint(self, temp_db_path):
        """Test that steps are checkpointed after execution."""
        from core.durable_workflow import DurableWorkflow, CheckpointStore
        
        store = CheckpointStore(temp_db_path)
        workflow = DurableWorkflow("test_002", store=store)
        
        async def mock_step(data):
            return {"result": "success", "count": 5}
        
        result = await workflow.step("research", mock_step, {"source": "gong"})
        
        assert result["count"] == 5
        
        # Verify checkpoint exists
        checkpoint_exists = await workflow.checkpoint_exists("research")
        assert checkpoint_exists == True
        
        # Verify we can retrieve checkpoint
        cached = await workflow.get_checkpoint("research")
        assert cached["count"] == 5
    
    @pytest.mark.asyncio
    async def test_workflow_resumption(self, temp_db_path):
        """Test that workflows can be resumed from checkpoint."""
        from core.durable_workflow import DurableWorkflow, CheckpointStore, WorkflowManager
        
        store = CheckpointStore(temp_db_path)
        
        # First workflow execution
        workflow1 = DurableWorkflow("test_003", store=store)
        
        async def step1(data=None):
            return {"step": 1}
        
        await workflow1.step("step_1", step1, {})
        
        # Simulate restart - create new workflow with same ID
        workflow2 = DurableWorkflow("test_003", store=store)
        
        # Step 1 should return cached result without re-executing
        call_count = 0
        
        async def step1_again(data):
            nonlocal call_count
            call_count += 1
            return {"step": 1}
        
        result = await workflow2.step("step_1", step1_again, {})
        
        # Function should NOT have been called (returned from cache)
        assert call_count == 0
        assert result["step"] == 1
    
    @pytest.mark.asyncio
    async def test_step_retry_on_failure(self, temp_db_path):
        """Test that steps retry on failure."""
        from core.durable_workflow import DurableWorkflow, CheckpointStore
        
        store = CheckpointStore(temp_db_path)
        workflow = DurableWorkflow("test_004", store=store)
        
        attempt_count = 0
        
        async def failing_then_succeeding(data=None):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise ValueError("Temporary failure")
            return {"success": True}
        
        result = await workflow.step(
            "flaky_step", 
            failing_then_succeeding, 
            {}, 
            max_retries=3
        )
        
        assert attempt_count == 2
        assert result["success"] == True
    
    @pytest.mark.asyncio
    async def test_workflow_completion(self, temp_db_path):
        """Test marking workflow as completed."""
        from core.durable_workflow import DurableWorkflow, CheckpointStore, WorkflowStatus
        
        store = CheckpointStore(temp_db_path)
        workflow = DurableWorkflow("test_005", store=store)
        
        await workflow.complete({"final_count": 10})
        
        status = workflow.get_status()
        assert status["status"] == WorkflowStatus.COMPLETED.value
    
    @pytest.mark.asyncio
    async def test_workflow_manager_list_in_progress(self, temp_db_path):
        """Test listing in-progress workflows."""
        from core.durable_workflow import WorkflowManager, CheckpointStore
        
        store = CheckpointStore(temp_db_path)
        manager = WorkflowManager(store=store)
        
        # Create multiple workflows
        wf1 = manager.create_workflow(workflow_id="wf_001")
        wf2 = manager.create_workflow(workflow_id="wf_002")
        await wf1.complete()
        
        # List in-progress
        in_progress = manager.list_in_progress()
        
        # Only wf2 should be in progress
        workflow_ids = [w["workflow_id"] for w in in_progress]
        assert "wf_002" in workflow_ids
        assert "wf_001" not in workflow_ids


# =============================================================================
# TEST: CONFIDENCE-BASED REPLANNING
# =============================================================================

class TestConfidenceReplanning:
    """Tests for Confidence-Based Replanning (System Two Logic)."""
    
    def test_qualification_result_creation(self):
        """Test creating a QualificationResult."""
        from core.confidence_replanning import ConfidenceReplanEngine, QualificationResult
        
        engine = ConfidenceReplanEngine()
        
        lead = {
            "lead_id": "test_001",
            "name": "John Smith",
            "title": "VP of Sales",
            "email": "john@acme.com",
            "company": {
                "name": "Acme Corp",
                "employee_count": 200,
                "industry": "B2B SaaS"
            },
            "source_type": "competitor_follower"
        }
        
        result = engine.create_qualification_result(
            lead=lead,
            icp_score=85,
            tier="tier_1",
            score_breakdown={"company_size": 20, "title_seniority": 22}
        )
        
        assert result.category == "HOT_LEAD"
        assert result.tier == "tier_1"
        assert result.confidence > 0
        assert result.next_action != ""
    
    def test_confidence_calculation(self):
        """Test confidence score calculation."""
        from core.confidence_replanning import ConfidenceReplanEngine
        
        engine = ConfidenceReplanEngine()
        
        # High quality lead with all data
        complete_lead = {
            "title": "VP Sales",
            "company": {"name": "Acme", "employee_count": 200, "industry": "SaaS"},
            "email": "test@example.com",
            "intent": {"website_visits": 5, "pricing_page_visits": 1},
            "source_type": "demo_requester"
        }
        
        confidence, factors, reason = engine.calculate_qualification_confidence(
            lead=complete_lead,
            icp_score=85,
            score_breakdown={"company_size": 20, "title": 22, "industry": 15}
        )
        
        assert confidence >= 0.7  # Should be high confidence
        assert "data_completeness" in factors
        assert factors["data_completeness"] > 0.5
    
    def test_low_confidence_triggers_replan(self):
        """Test that low confidence identifies gaps."""
        from core.confidence_replanning import ConfidenceReplanEngine, QualificationResult
        
        engine = ConfidenceReplanEngine(confidence_threshold=0.85)
        
        # Incomplete lead
        incomplete_lead = {
            "title": "Manager",
            "company": {"name": "Unknown"},
            "source_type": "unknown"
        }
        
        result = engine.create_qualification_result(
            lead=incomplete_lead,
            icp_score=50,
            tier="tier_3",
            score_breakdown={"title_seniority": 8}
        )
        
        assert result.needs_replan == True
        assert len(result.enrichment_gaps) > 0
    
    @pytest.mark.asyncio
    async def test_execute_with_confidence_replan(self):
        """Test execution with confidence-based replanning."""
        from core.confidence_replanning import (
            ConfidenceReplanEngine, 
            ConfidenceResult,
            ConfidenceLevel
        )
        
        engine = ConfidenceReplanEngine(
            confidence_threshold=0.85,
            max_attempts=3
        )
        
        attempt_count = 0
        
        async def improving_decision(data):
            nonlocal attempt_count
            attempt_count += 1
            
            # Confidence improves with each attempt
            confidence = 0.5 + (attempt_count * 0.2)
            
            return ConfidenceResult(
                value={"decision": "qualify"},
                confidence=min(confidence, 0.95),
                reason=f"Attempt {attempt_count}"
            )
        
        result, history = await engine.execute_with_confidence(
            decision_fn=improving_decision,
            input_data={}
        )
        
        # Should have made multiple attempts before reaching threshold
        assert len(history) >= 2
        assert result.confidence >= 0.85
    
    def test_confidence_aware_segmentor(self):
        """Test the ConfidenceAwareSegmentor wrapper."""
        from core.confidence_replanning import ConfidenceAwareSegmentor
        
        segmentor = ConfidenceAwareSegmentor(confidence_threshold=0.85)
        
        lead = {
            "lead_id": "test_001",
            "name": "Jane Doe",
            "title": "CRO",
            "email": "jane@startup.com",
            "company": {
                "name": "Startup Inc",
                "employee_count": 75,
                "industry": "Technology"
            },
            "intent": {"content_downloads": 2}
        }
        
        result = segmentor.qualify_lead(
            lead=lead,
            icp_score=75,
            tier="tier_2",
            score_breakdown={"title_seniority": 25, "company_size": 15}
        )
        
        assert result.category in ("HOT_LEAD", "WARM_LEAD", "NURTURE", "MONITOR", "UNQUALIFIED")
        assert result.urgency >= 1 and result.urgency <= 5


# =============================================================================
# TEST: BOUNDED TOOLS
# =============================================================================

class TestBoundedTools:
    """Tests for Bounded Tools (Fixed Tool Boundaries)."""
    
    def test_tool_registration(self):
        """Test registering tools with boundaries."""
        from core.bounded_tools import BoundedToolRegistry, ToolCategory
        
        registry = BoundedToolRegistry(agent_name="TEST", max_tool_calls=10)
        
        registry.register_tool(
            name="search",
            handler=lambda x: {"result": x},
            category=ToolCategory.SEARCH,
            max_calls_per_session=5
        )
        
        available = registry.get_available_tools()
        assert "search" in available
    
    @pytest.mark.asyncio
    async def test_tool_call_counting(self):
        """Test that tool calls are counted."""
        from core.bounded_tools import BoundedToolRegistry, ToolCategory
        
        registry = BoundedToolRegistry(agent_name="TEST", max_tool_calls=10)
        
        async def mock_search(data):
            return {"found": 3}
        
        registry.register_tool(
            name="search",
            handler=mock_search,
            category=ToolCategory.SEARCH,
            max_calls_per_session=5
        )
        
        # Make some calls
        await registry.call_tool("search", {"query": "test1"})
        await registry.call_tool("search", {"query": "test2"})
        
        stats = registry.get_stats()
        
        assert stats["stats"]["total_calls"] == 2
        assert stats["tool_usage"]["search"] == 2
    
    @pytest.mark.asyncio
    async def test_max_tool_calls_enforcement(self):
        """Test that MAX_TOOL_CALLS is enforced."""
        from core.bounded_tools import BoundedToolRegistry, ToolCategory
        
        registry = BoundedToolRegistry(agent_name="TEST", max_tool_calls=3)
        
        async def mock_tool(data):
            return {"ok": True}
        
        registry.register_tool(
            name="search",
            handler=mock_tool,
            category=ToolCategory.SEARCH,
            max_calls_per_session=10  # Higher than global limit
        )
        
        # Make calls up to limit
        await registry.call_tool("search", {})
        await registry.call_tool("search", {})
        await registry.call_tool("search", {})
        
        # Next call should raise
        with pytest.raises(RuntimeError, match="Execution stopped"):
            await registry.call_tool("search", {})
    
    @pytest.mark.asyncio
    async def test_per_tool_limits(self):
        """Test per-tool call limits."""
        from core.bounded_tools import BoundedToolRegistry, ToolCategory
        
        registry = BoundedToolRegistry(agent_name="TEST", max_tool_calls=20)
        
        async def mock_tool(data):
            return {"ok": True}
        
        registry.register_tool(
            name="limited_tool",
            handler=mock_tool,
            category=ToolCategory.SEARCH,
            max_calls_per_session=2  # Only 2 calls allowed
        )
        
        # Make 2 allowed calls
        await registry.call_tool("limited_tool", {})
        await registry.call_tool("limited_tool", {})
        
        # Third call should raise (per-tool limit)
        with pytest.raises(RuntimeError, match="session limit"):
            await registry.call_tool("limited_tool", {})
    
    @pytest.mark.asyncio
    async def test_bounded_hunter_research(self):
        """Test BoundedHunterAgent research with limits."""
        from core.bounded_tools import BoundedHunterAgent
        
        hunter = BoundedHunterAgent()
        
        lead = {
            "lead_id": "test_001",
            "name": "John Smith",
            "linkedin_url": "https://linkedin.com/in/johnsmith",
            "company": {
                "name": "Acme Corp",
                "domain": "acme.com"
            }
        }
        
        report = await hunter.research(lead)
        
        assert "lead_name" in report
        assert "tools_used" in report
        assert "total_tool_calls" in report
        assert report["total_tool_calls"] <= hunter.MAX_TOOL_CALLS
    
    def test_stop_conditions(self):
        """Test various stop conditions."""
        from core.bounded_tools import (
            StepCountIs,
            ConsecutiveFailures,
            DurationExceeds,
            ExecutionStats,
            ToolCall
        )
        
        # Test StepCountIs
        step_condition = StepCountIs(5)
        stats = ExecutionStats(total_calls=5)
        assert step_condition.should_stop(stats, []) == True
        
        stats.total_calls = 4
        assert step_condition.should_stop(stats, []) == False
        
        # Test ConsecutiveFailures
        failure_condition = ConsecutiveFailures(3)
        failed_calls = [
            ToolCall("t1", 1, {}, success=False),
            ToolCall("t2", 2, {}, success=False),
            ToolCall("t3", 3, {}, success=False)
        ]
        assert failure_condition.should_stop(ExecutionStats(), failed_calls) == True
        
        # Test DurationExceeds
        duration_condition = DurationExceeds(10.0)
        stats = ExecutionStats(total_duration_ms=11000)
        assert duration_condition.should_stop(stats, []) == True
    
    def test_session_reset(self):
        """Test resetting a tool session."""
        from core.bounded_tools import BoundedToolRegistry, ToolCategory
        
        registry = BoundedToolRegistry(agent_name="TEST", max_tool_calls=10)
        
        registry.register_tool(
            name="search",
            handler=lambda x: x,
            category=ToolCategory.SEARCH
        )
        
        # Simulate some calls
        registry._stats.total_calls = 5
        registry._tool_call_counts["search"] = 3
        
        # Reset
        registry.reset_session()
        
        stats = registry.get_stats()
        assert stats["stats"]["total_calls"] == 0
        assert stats["tool_usage"]["search"] == 0


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests combining multiple patterns."""
    
    @pytest.mark.asyncio
    async def test_intent_to_workflow_integration(self):
        """Test Intent Interpreter feeding into Durable Workflow."""
        from core.intent_interpreter import IntentInterpreter, ObjectiveType
        from core.durable_workflow import DurableWorkflow, CheckpointStore
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Step 1: Interpret intent
            interpreter = IntentInterpreter(storage_dir=Path(tmpdir) / "intents")
            goal = interpreter.interpret("Find 50 new leads from competitors")
            
            # Step 2: Create workflow from goal
            store = CheckpointStore(Path(tmpdir) / "workflows.db")
            workflow = DurableWorkflow(
                workflow_id=goal.goal_id,
                workflow_type=goal.objective.value,
                store=store,
                context={"goal": goal.to_dict()}
            )
            
            # Step 3: Execute steps based on goal
            for step in goal.steps:
                async def mock_step(data=None, agent=step.agent):
                    return {"agent": agent, "completed": True}
                
                result = await workflow.step(
                    step.step_id,
                    mock_step,
                    step.inputs,
                    agent=step.agent
                )
            
            await workflow.complete()
            
            status = workflow.get_status()
            assert status["status"] == "completed"
    
    @pytest.mark.asyncio
    async def test_confidence_with_bounded_research(self):
        """Test Confidence Replanning with Bounded Hunter."""
        from core.confidence_replanning import ConfidenceAwareSegmentor
        from core.bounded_tools import BoundedHunterAgent
        
        # Step 1: Hunter researches with bounded tools
        hunter = BoundedHunterAgent()
        
        lead = {
            "lead_id": "test_integration",
            "name": "Integration Test Lead",
            "linkedin_url": "https://linkedin.com/in/test",
            "company": {"name": "Test Corp", "domain": "test.com"}
        }
        
        research_report = await hunter.research(lead)
        
        # Step 2: Segmentor qualifies with confidence
        segmentor = ConfidenceAwareSegmentor()
        
        qualification = segmentor.qualify_lead(
            lead=lead,
            icp_score=75,
            tier="tier_2",
            score_breakdown={"title": 15, "company": 10}
        )
        
        # Verify integration
        assert research_report["total_tool_calls"] <= hunter.MAX_TOOL_CALLS
        assert qualification.confidence > 0
        assert qualification.category in ("HOT_LEAD", "WARM_LEAD", "NURTURE", "MONITOR", "UNQUALIFIED")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
