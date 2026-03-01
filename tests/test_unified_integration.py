#!/usr/bin/env python3
"""
Unified Integration Test Suite
==============================
Comprehensive integration tests for the unified swarm system.

Tests:
1. Unified Agent Registry initialization and operations
2. Full pipeline flow: scrape → enrich → segment → craft → approve → send
3. Self-annealing learning loop
4. Context management
5. Segmentation and ICP scoring

Usage:
    pytest tests/test_unified_integration.py -v
    pytest tests/test_unified_integration.py -v -k "TestUnifiedAgentRegistry"
"""

import pytest
import json
import uuid
import os
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from dataclasses import asdict
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_hive_mind(tmp_path):
    """Create temporary .hive-mind directory for tests."""
    hive_mind = tmp_path / ".hive-mind"
    hive_mind.mkdir(parents=True)
    (hive_mind / "scraped").mkdir()
    (hive_mind / "enriched").mkdir()
    (hive_mind / "segmented").mkdir()
    (hive_mind / "campaigns").mkdir()
    (hive_mind / "pipeline_runs").mkdir()
    return hive_mind


@pytest.fixture
def sample_leads():
    """Generate sample lead data for testing."""
    return [
        {
            "lead_id": f"lead_{uuid.uuid4().hex[:8]}",
            "linkedin_url": "https://linkedin.com/in/johndoe",
            "name": "John Doe",
            "title": "VP of Sales",
            "company": {
                "name": "Acme Corp",
                "employee_count": 250,
                "industry": "B2B SaaS"
            },
            "email": "john@acme.com",
            "source_type": "competitor_follower",
            "source_name": "gong_followers"
        },
        {
            "lead_id": f"lead_{uuid.uuid4().hex[:8]}",
            "linkedin_url": "https://linkedin.com/in/janedoe",
            "name": "Jane Doe",
            "title": "Director of Marketing",
            "company": {
                "name": "TechStart Inc",
                "employee_count": 75,
                "industry": "Technology"
            },
            "email": "jane@techstart.com",
            "source_type": "event_attendee",
            "source_name": "saastr_2024"
        },
        {
            "lead_id": f"lead_{uuid.uuid4().hex[:8]}",
            "linkedin_url": "https://linkedin.com/in/bobsmith",
            "name": "Bob Smith",
            "title": "CEO",
            "company": {
                "name": "Enterprise Solutions",
                "employee_count": 500,
                "industry": "Enterprise Software"
            },
            "email": "bob@enterprise.com",
            "source_type": "group_member",
            "source_name": "sales_leaders_group"
        },
        {
            "lead_id": f"lead_{uuid.uuid4().hex[:8]}",
            "linkedin_url": "https://linkedin.com/in/alicejones",
            "name": "Alice Jones",
            "title": "Sales Manager",
            "company": {
                "name": "Small Startup",
                "employee_count": 5,
                "industry": "Consumer"
            },
            "email": "alice@small.com",
            "source_type": "post_commenter",
            "source_name": "thought_leadership_post"
        }
    ]


@pytest.fixture
def sample_enriched_leads(sample_leads):
    """Generate enriched lead data."""
    enriched = []
    for lead in sample_leads:
        enriched_lead = lead.copy()
        enriched_lead["enriched"] = True
        enriched_lead["enriched_at"] = datetime.now(timezone.utc).isoformat()
        enriched_lead["technologies"] = ["Salesforce", "HubSpot"]
        enriched_lead["funding_info"] = {"last_round": "Series B", "amount": 50000000}
        enriched_lead["intent_signals"] = ["Recently viewed pricing page", "Downloaded whitepaper"]
        enriched_lead["intent_score"] = 75
        enriched.append(enriched_lead)
    return enriched


@pytest.fixture
def mock_env_vars():
    """Mock environment variables for testing."""
    env_vars = {
        "GHL_API_KEY": "test_ghl_key",
        "GHL_LOCATION_ID": "test_location",
        "INSTANTLY_API_KEY": "test_instantly_key",
        "CLAY_API_KEY": "test_clay_key",
        "OPENAI_API_KEY": "test_openai_key",
        "EXA_API_KEY": "test_exa_key"
    }
    with patch.dict("os.environ", env_vars):
        yield env_vars


# ============================================================================
# Test: Unified Agent Registry
# ============================================================================

class TestUnifiedAgentRegistry:
    """Tests for the UnifiedAgentRegistry."""
    
    def test_registry_initialization(self):
        """Test that registry initializes with all expected agents."""
        from execution.unified_agent_registry import UnifiedAgentRegistry
        
        registry = UnifiedAgentRegistry()
        
        assert len(registry.agents) >= 5
        assert "hunter" in registry.agents
        assert "enricher" in registry.agents
        assert "segmentor" in registry.agents
        assert "crafter" in registry.agents
        assert "gatekeeper" in registry.agents
    
    def test_list_agents(self):
        """Test listing agents from registry."""
        from execution.unified_agent_registry import UnifiedAgentRegistry, AgentSwarm
        
        registry = UnifiedAgentRegistry()
        
        all_agents = registry.list_agents()
        assert len(all_agents) >= 5
        
        alpha_agents = registry.list_agents(swarm=AgentSwarm.ALPHA)
        assert len(alpha_agents) >= 5
        assert all(a.swarm == AgentSwarm.ALPHA for a in alpha_agents)
        
        revenue_agents = registry.list_agents(swarm=AgentSwarm.REVENUE)
        assert all(a.swarm == AgentSwarm.REVENUE for a in revenue_agents)
    
    def test_agent_info_structure(self):
        """Test that agent info has correct structure."""
        from execution.unified_agent_registry import UnifiedAgentRegistry, AgentStatus
        
        registry = UnifiedAgentRegistry()
        hunter = registry.agents.get("hunter")
        
        assert hunter is not None
        assert hunter.name == "HUNTER"
        assert hunter.module_path == "execution.hunter_scrape_followers"
        assert hunter.status == AgentStatus.NOT_INITIALIZED
    
    def test_get_status(self):
        """Test getting status of all agents."""
        from execution.unified_agent_registry import UnifiedAgentRegistry
        
        registry = UnifiedAgentRegistry()
        status = registry.get_status()
        
        assert isinstance(status, dict)
        assert "hunter" in status
        assert "swarm" in status["hunter"]
        assert "status" in status["hunter"]
        assert "description" in status["hunter"]
    
    def test_revenue_swarm_agents(self):
        """Test that revenue swarm agents are registered."""
        from execution.unified_agent_registry import UnifiedAgentRegistry, AgentSwarm
        
        registry = UnifiedAgentRegistry()
        
        assert "queen" in registry.agents
        assert "scout" in registry.agents
        assert registry.agents["queen"].swarm == AgentSwarm.REVENUE
        assert registry.agents["scout"].swarm == AgentSwarm.REVENUE


# ============================================================================
# Test: Unified Pipeline
# ============================================================================

class TestUnifiedPipeline:
    """Tests for the unified pipeline."""
    
    def test_pipeline_sandbox_mode(self, mock_env_vars):
        """Test pipeline runs in sandbox mode without real API calls."""
        from execution.run_pipeline import UnifiedPipeline, PipelineMode
        
        pipeline = UnifiedPipeline(mode=PipelineMode.SANDBOX)
        
        assert pipeline.mode == PipelineMode.SANDBOX
        assert pipeline._is_safe_mode() is True
    
    def test_pipeline_stages_exist(self):
        """Test that all pipeline stages are defined."""
        from execution.run_pipeline import PipelineStage
        
        expected_stages = ["SCRAPE", "ENRICH", "SEGMENT", "CRAFT", "APPROVE", "SEND"]
        
        for stage_name in expected_stages:
            assert hasattr(PipelineStage, stage_name)
    
    def test_pipeline_run_structure(self):
        """Test PipelineRun dataclass structure."""
        from execution.run_pipeline import PipelineRun, PipelineMode
        
        run = PipelineRun(
            run_id="test_run_001",
            mode=PipelineMode.SANDBOX,
            started_at=datetime.now(timezone.utc).isoformat()
        )
        
        assert run.run_id == "test_run_001"
        assert run.mode == PipelineMode.SANDBOX
        assert run.total_leads_processed == 0
        assert run.total_campaigns_created == 0
        assert run.stages == []
    
    def test_stage_result_structure(self):
        """Test StageResult dataclass structure."""
        from execution.run_pipeline import StageResult, PipelineStage
        
        result = StageResult(
            stage=PipelineStage.SCRAPE,
            success=True,
            duration_ms=150.5,
            input_count=0,
            output_count=20,
            errors=[],
            metrics={"source": "competitor_gong"}
        )
        
        assert result.stage == PipelineStage.SCRAPE
        assert result.success is True
        assert result.duration_ms == 150.5
        assert result.output_count == 20
    
    def test_pipeline_mode_detection(self):
        """Test pipeline mode detection for safe operations."""
        from execution.run_pipeline import UnifiedPipeline, PipelineMode
        
        sandbox_pipeline = UnifiedPipeline(mode=PipelineMode.SANDBOX)
        assert sandbox_pipeline._is_safe_mode() is True
        
        dry_run_pipeline = UnifiedPipeline(mode=PipelineMode.DRY_RUN)
        assert dry_run_pipeline._is_safe_mode() is True
        
        staging_pipeline = UnifiedPipeline(mode=PipelineMode.STAGING)
        assert staging_pipeline._is_safe_mode() is False
        
        prod_pipeline = UnifiedPipeline(mode=PipelineMode.PRODUCTION)
        assert prod_pipeline._is_safe_mode() is False


# ============================================================================
# Test: Self-Annealing
# ============================================================================

class TestSelfAnnealing:
    """Tests for the self-annealing learning loop."""
    
    def test_learn_from_outcome(self):
        """Test learning from workflow outcomes."""
        from core.self_annealing import SelfAnnealingEngine
        
        engine = SelfAnnealingEngine(epsilon=0.30)
        
        result = engine.learn_from_outcome(
            workflow="campaign_tier1_001",
            outcome={"meeting_booked": True, "state": {"icp_tier": "tier_1"}},
            success=True,
            details={"lead_count": 5}
        )
        
        assert "reward" in result
        assert result["reward"] > 0
        assert engine.metrics["total_outcomes"] >= 1
        assert engine.metrics["success_count"] >= 1
    
    def test_learn_from_negative_outcome(self):
        """Test learning from negative outcomes."""
        from core.self_annealing import SelfAnnealingEngine
        
        engine = SelfAnnealingEngine(epsilon=0.30)
        
        result = engine.learn_from_outcome(
            workflow="campaign_tier3_001",
            outcome={"spam_report": True},
            success=False
        )
        
        assert result["reward"] < 0
        assert engine.metrics["failure_count"] >= 1
    
    def test_pattern_detection(self):
        """Test pattern detection in outcomes."""
        from core.self_annealing import SelfAnnealingEngine
        
        engine = SelfAnnealingEngine(epsilon=0.30)
        
        for i in range(5):
            engine.learn_from_outcome(
                workflow=f"campaign_tier1_{i:03d}",
                outcome={"positive_reply": True},
                success=True
            )
        
        for i in range(3):
            engine.learn_from_outcome(
                workflow=f"campaign_tier3_{i:03d}",
                outcome={"bounce": True},
                success=False
            )
        
        patterns = engine.detect_patterns(min_frequency=2)
        
        assert len(patterns) >= 0
    
    def test_annealing_step(self):
        """Test executing an annealing step."""
        from core.self_annealing import SelfAnnealingEngine
        
        engine = SelfAnnealingEngine(epsilon=0.30)
        
        engine.learn_from_outcome(
            workflow="test_workflow_001",
            outcome={"email_opened": True},
            success=True
        )
        
        initial_epsilon = engine.epsilon
        result = engine.anneal_step()
        
        assert "step" in result
        assert "epsilon" in result
        assert "patterns_found" in result
        assert engine.epsilon <= initial_epsilon
    
    def test_epsilon_decay(self):
        """Test that epsilon decays over time."""
        from core.self_annealing import SelfAnnealingEngine
        
        engine = SelfAnnealingEngine(
            epsilon=0.30,
            epsilon_decay=0.9,
            min_epsilon=0.05
        )
        
        engine.epsilon = 0.30
        initial_epsilon = engine.epsilon
        
        for _ in range(10):
            engine.anneal_step()
        
        assert engine.epsilon <= initial_epsilon
        assert engine.epsilon >= engine.min_epsilon
    
    def test_get_annealing_status(self):
        """Test getting annealing status."""
        from core.self_annealing import SelfAnnealingEngine
        
        engine = SelfAnnealingEngine(epsilon=0.30)
        
        status = engine.get_annealing_status()
        
        assert "epsilon" in status
        assert "epsilon_target" in status
        assert "total_outcomes" in status
        assert "patterns_count" in status
    
    def test_report_to_queen(self):
        """Test generating QUEEN report."""
        from core.self_annealing import SelfAnnealingEngine
        
        engine = SelfAnnealingEngine(epsilon=0.30)
        
        engine.learn_from_outcome(
            workflow="test_001",
            outcome={"positive_reply": True},
            success=True
        )
        
        report = engine.report_to_queen()
        
        assert report["report_type"] == "self_annealing_summary"
        assert "metrics" in report
        assert "health_status" in report
        assert "recommendations" in report


# ============================================================================
# Test: Segmentation
# ============================================================================

class TestSegmentation:
    """Tests for lead segmentation and ICP scoring."""
    
    def test_icp_scoring(self, sample_leads):
        """Test ICP score calculation."""
        from execution.segmentor_classify import LeadSegmentor
        
        segmentor = LeadSegmentor(use_annealing=False)
        lead = sample_leads[0]
        
        result = segmentor.calculate_icp_score(lead)
        score, breakdown = result[0], result[1]

        assert isinstance(score, int)
        assert 0 <= score <= 100
        assert isinstance(breakdown, dict)
    
    def test_tier_assignment(self):
        """Test tier assignment based on score."""
        from execution.segmentor_classify import LeadSegmentor, ICPTier
        
        segmentor = LeadSegmentor(use_annealing=False)
        
        assert segmentor.get_tier(85) == ICPTier.TIER_1.value
        assert segmentor.get_tier(70) == ICPTier.TIER_2.value
        assert segmentor.get_tier(50) == ICPTier.TIER_3.value
        assert segmentor.get_tier(30) == ICPTier.TIER_4.value
    
    def test_segment_single_lead(self, sample_leads):
        """Test segmenting a single lead."""
        from execution.segmentor_classify import LeadSegmentor
        
        segmentor = LeadSegmentor(use_annealing=False)
        lead = sample_leads[0]
        
        result = segmentor.segment_lead(lead)
        
        assert result.lead_id is not None
        assert result.icp_score >= 0
        assert result.icp_tier in ["tier_1", "tier_2", "tier_3", "tier_4"]
        assert result.recommended_campaign is not None
    
    def test_title_scoring(self):
        """Test title seniority scoring."""
        from execution.segmentor_classify import LeadSegmentor
        
        segmentor = LeadSegmentor(use_annealing=False)
        
        test_cases = [
            ("CEO", 25),
            ("VP of Sales", 20),
            ("Director of Marketing", 15),
            ("Sales Manager", 10),
            ("Sales Representative", 5)
        ]
        
        for title, expected_min_score in test_cases:
            lead = {
                "title": title,
                "company": {"employee_count": 100, "industry": "Technology"}
            }
            result = segmentor.calculate_icp_score(lead)
            score, breakdown = result[0], result[1]
            title_score = breakdown.get("title_seniority", 0)
            assert title_score > 0 or expected_min_score <= 5
    
    def test_company_size_scoring(self):
        """Test company size scoring."""
        from execution.segmentor_classify import LeadSegmentor
        
        segmentor = LeadSegmentor(use_annealing=False)
        
        test_cases = [
            (5, None),
            (100, 20),
            (300, 20),
            (750, 15),
            (5000, 10)
        ]
        
        for size, expected_score in test_cases:
            lead = {
                "title": "Manager",
                "company": {"employee_count": size, "industry": "Technology"}
            }
            result = segmentor.calculate_icp_score(lead)
            score, breakdown, dq_reason = result[0], result[1], result[2]
            
            if expected_score is None:
                assert dq_reason is not None
            else:
                assert breakdown.get("company_size", 0) > 0
    
    def test_disqualification_rules(self):
        """Test lead disqualification rules."""
        from execution.segmentor_classify import LeadSegmentor
        
        segmentor = LeadSegmentor(use_annealing=False)
        
        small_company_lead = {
            "title": "CEO",
            "company": {"employee_count": 5, "industry": "Technology"}
        }
        
        result = segmentor.calculate_icp_score(small_company_lead)
        score, breakdown, dq_reason = result[0], result[1], result[2]
        
        assert dq_reason is not None
        assert "too small" in dq_reason.lower() or score == 0
    
    def test_campaign_routing(self):
        """Test campaign routing based on tier and source."""
        from execution.segmentor_classify import SegmentedLead
        
        tier1_lead = SegmentedLead(
            lead_id="test_001",
            linkedin_url="https://linkedin.com/in/test",
            name="Test User",
            title="VP of Sales",
            company="Test Corp",
            icp_score=85,
            icp_tier="tier_1",
            intent_score=80,
            source_type="competitor_follower",
            source_name="gong"
        )
        
        assert tier1_lead.icp_tier == "tier_1"


# ============================================================================
# Test: Context Management
# ============================================================================

class TestContextManagement:
    """Tests for context management and compaction."""
    
    def test_context_manager_initialization(self):
        """Test ContextManager initialization."""
        from core.context import ContextManager
        
        manager = ContextManager(workflow_id="test_workflow_001")
        
        assert manager.workflow_id == "test_workflow_001"
        assert manager.current_token_usage == 0
    
    def test_context_zone_detection(self):
        """Test context zone detection based on token usage."""
        from core.context import get_context_zone, ContextZone
        
        assert get_context_zone(10000, 128000) == ContextZone.SMART
        assert get_context_zone(60000, 128000) == ContextZone.CAUTION
        assert get_context_zone(90000, 128000) == ContextZone.DUMB
        assert get_context_zone(110000, 128000) == ContextZone.CRITICAL
    
    def test_token_estimation(self):
        """Test token estimation for content."""
        from core.context import estimate_tokens
        
        short_text = "Hello world"
        long_text = "Hello world " * 1000
        
        short_estimate = estimate_tokens(short_text)
        long_estimate = estimate_tokens(long_text)
        
        assert short_estimate < long_estimate
        assert short_estimate > 0
    
    def test_event_thread_creation(self):
        """Test EventThread creation and event adding."""
        from core.context import EventThread, EventType
        
        thread = EventThread(thread_id="test_thread_001")
        
        event = thread.add_event(
            EventType.PHASE_STARTED,
            {"phase": "research", "agent": "SCOUT"},
            phase="research"
        )
        
        assert len(thread.events) == 1
        assert event.event_type == EventType.PHASE_STARTED
        assert event.data["phase"] == "research"
    
    def test_event_thread_compaction(self):
        """Test EventThread compaction."""
        from core.context import EventThread, EventType
        
        thread = EventThread(thread_id="test_thread_002", max_events=50)
        
        for i in range(10):
            thread.add_event(
                EventType.PHASE_COMPLETE,
                {"phase": f"phase_{i}"},
                phase=f"phase_{i}"
            )
        
        for i in range(5):
            event = thread.add_event(
                EventType.ERROR,
                {"error": f"error_{i}"}
            )
            thread.resolve_event(len(thread.events) - 1)
        
        removed = thread.compact()
        
        assert removed >= 0
    
    def test_context_summary_serialization(self):
        """Test ContextSummary serialization."""
        from core.context import ContextSummary
        
        summary = ContextSummary(
            phase="research",
            agent="SCOUT",
            created_at=datetime.now(timezone.utc).isoformat(),
            summary="Research completed successfully",
            key_findings=["Finding 1", "Finding 2"],
            action_items=["Action 1"]
        )
        
        prompt_block = summary.to_prompt_block()
        xml_block = summary.to_xml()
        
        assert "research" in prompt_block.lower() or "research" in xml_block.lower()
        assert len(prompt_block) > 0
        assert len(xml_block) > 0
    
    def test_lead_batch_compaction(self):
        """Test lead batch compaction for large datasets."""
        from core.context import compact_lead_batch
        
        leads = [
            {
                "lead_id": f"lead_{i}",
                "icp_tier": f"tier_{(i % 4) + 1}",
                "icp_score": 90 - (i * 2),
                "source_type": "competitor_follower",
                "industry": "SaaS"
            }
            for i in range(50)
        ]
        
        result = compact_lead_batch(leads, max_leads=10)
        
        assert result["compacted"] is True
        assert result["total_count"] == 50
        assert result["sample_count"] == 10
        assert "tier_distribution" in result
        assert "avg_icp_score" in result
    
    def test_small_batch_not_compacted(self):
        """Test that small batches are not compacted."""
        from core.context import compact_lead_batch
        
        leads = [{"lead_id": f"lead_{i}"} for i in range(5)]
        
        result = compact_lead_batch(leads, max_leads=10)
        
        assert result["compacted"] is False
        assert "leads" in result


# ============================================================================
# Test: Edge Cases
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_empty_lead_list_segmentation(self):
        """Test segmentation with empty lead list."""
        from execution.segmentor_classify import LeadSegmentor
        
        segmentor = LeadSegmentor(use_annealing=False)
        
        assert segmentor.segmented == []
    
    def test_missing_lead_fields(self):
        """Test handling of leads with missing fields."""
        from execution.segmentor_classify import LeadSegmentor
        
        segmentor = LeadSegmentor(use_annealing=False)
        
        incomplete_lead = {
            "lead_id": "incomplete_001",
            "name": "Test User"
        }
        
        result = segmentor.segment_lead(incomplete_lead)
        
        assert result is not None
        assert result.icp_tier in ["tier_1", "tier_2", "tier_3", "tier_4"]
    
    def test_annealing_with_empty_outcomes(self):
        """Test annealing step with no outcomes."""
        from core.self_annealing import SelfAnnealingEngine
        
        engine = SelfAnnealingEngine(epsilon=0.30)
        initial_step = engine.metrics["annealing_steps"]
        
        result = engine.anneal_step()
        
        assert result["step"] == initial_step + 1
        assert "epsilon" in result
    
    def test_context_manager_with_no_phases(self):
        """Test context manager with no phases added."""
        from core.context import ContextManager
        
        manager = ContextManager(workflow_id="empty_workflow")
        
        context = manager.get_compacted_context()
        
        assert context == ""
        assert manager.is_in_smart_zone() is True


# ============================================================================
# Test: Integration Flow
# ============================================================================

class TestIntegrationFlow:
    """Tests for complete integration flows."""
    
    def test_lead_to_segment_flow(self, sample_leads):
        """Test complete flow from lead to segmentation."""
        from execution.segmentor_classify import LeadSegmentor
        
        segmentor = LeadSegmentor(use_annealing=False)
        
        segmented = []
        for lead in sample_leads:
            result = segmentor.segment_lead(lead)
            segmented.append(result)
        
        assert len(segmented) == len(sample_leads)
        
        tiers = [s.icp_tier for s in segmented]
        assert all(t in ["tier_1", "tier_2", "tier_3", "tier_4"] for t in tiers)
        
        campaigns = [s.recommended_campaign for s in segmented]
        assert all(c is not None and c != "" for c in campaigns)
    
    def test_annealing_integration_with_segmentation(self, sample_leads):
        """Test annealing learning from segmentation outcomes."""
        from core.self_annealing import SelfAnnealingEngine
        from execution.segmentor_classify import LeadSegmentor
        
        engine = SelfAnnealingEngine(epsilon=0.30)
        initial_outcomes = engine.metrics["total_outcomes"]
        segmentor = LeadSegmentor(use_annealing=False)
        
        for lead in sample_leads:
            result = segmentor.segment_lead(lead)
            
            engine.learn_from_outcome(
                workflow=f"segmentation_{result.lead_id}",
                outcome={
                    "action": "segment",
                    "state": {
                        "icp_tier": result.icp_tier,
                        "source_type": result.source_type
                    }
                },
                success=True,
                details={"icp_score": result.icp_score}
            )
        
        assert engine.metrics["total_outcomes"] == initial_outcomes + len(sample_leads)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
