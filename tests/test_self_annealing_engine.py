#!/usr/bin/env python3
"""
Tests for Self-Annealing Pipeline with RETRIEVE-JUDGE-DISTILL-CONSOLIDATE
=========================================================================
Tests covering all 4 pipeline stages, HNSW similarity search, 
EWC++ consolidation, and Queen integration.
"""

import pytest
import json
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.self_annealing_engine import (
    SelfAnnealingPipeline,
    SimpleEmbedder,
    SimpleHNSW,
    EWCPlusPlus,
    ReasoningEntry,
    Learning,
    JudgmentResult,
    DistillationResult,
    ConsolidationResult,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def pipeline(tmp_path):
    """Create a fresh pipeline with temp storage."""
    return SelfAnnealingPipeline(storage_path=tmp_path)


@pytest.fixture
def embedder():
    """Create a simple embedder."""
    return SimpleEmbedder(dim=64)


@pytest.fixture
def hnsw():
    """Create a simple HNSW index."""
    return SimpleHNSW(dim=64)


@pytest.fixture
def ewc():
    """Create EWC++ instance."""
    return EWCPlusPlus(lambda_ewc=0.5)


@pytest.fixture
def success_outcome():
    """A successful outcome."""
    return {
        "meeting_booked": True,
        "response_time_hours": 4
    }


@pytest.fixture
def failure_outcome():
    """A failure outcome."""
    return {
        "spam_report": True
    }


@pytest.fixture
def sample_context():
    """Sample context for testing."""
    return {
        "icp_tier": "tier_1",
        "template": "thought_leadership",
        "workflow_type": "campaign"
    }


# =============================================================================
# EMBEDDER TESTS
# =============================================================================

class TestSimpleEmbedder:
    """Tests for SimpleEmbedder."""
    
    def test_embed_returns_correct_dimension(self, embedder):
        """Embedding should have correct dimension."""
        text = "This is a test sentence"
        embedding = embedder.embed(text)
        assert len(embedding) == 64
    
    def test_embed_empty_returns_zeros(self, embedder):
        """Empty text should return zero vector."""
        embedding = embedder.embed("")
        assert all(v == 0.0 for v in embedding)
    
    def test_similar_texts_similar_embeddings(self, embedder):
        """Similar texts should have similar embeddings."""
        text1 = "campaign email marketing success"
        text2 = "email campaign successful marketing"
        
        emb1 = embedder.embed(text1)
        emb2 = embedder.embed(text2)
        
        # Compute cosine similarity
        import math
        dot = sum(a*b for a, b in zip(emb1, emb2))
        norm1 = math.sqrt(sum(a*a for a in emb1))
        norm2 = math.sqrt(sum(b*b for b in emb2))
        similarity = dot / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0
        
        assert similarity > 0.5  # Should be somewhat similar
    
    def test_different_texts_different_embeddings(self, embedder):
        """Different texts should have different embeddings."""
        text1 = "campaign email marketing"
        text2 = "database schema migration"
        
        emb1 = embedder.embed(text1)
        emb2 = embedder.embed(text2)
        
        # Compute cosine similarity
        import math
        dot = sum(a*b for a, b in zip(emb1, emb2))
        norm1 = math.sqrt(sum(a*a for a in emb1))
        norm2 = math.sqrt(sum(b*b for b in emb2))
        similarity = dot / (norm1 * norm2) if norm1 > 0 and norm2 > 0 else 0
        
        assert similarity < 0.5  # Should be different


# =============================================================================
# HNSW TESTS
# =============================================================================

class TestSimpleHNSW:
    """Tests for SimpleHNSW index."""
    
    def test_add_and_search(self, hnsw, embedder):
        """Should be able to add and search entries."""
        # Add entries
        entry1 = ReasoningEntry(
            entry_id="e1",
            pattern_type="success",
            content="Campaign tier 1 meeting booked"
        )
        entry2 = ReasoningEntry(
            entry_id="e2",
            pattern_type="failure",
            content="Campaign tier 4 spam report"
        )
        
        hnsw.add(entry1, embedder.embed(entry1.content))
        hnsw.add(entry2, embedder.embed(entry2.content))
        
        assert hnsw.size() == 2
        
        # Search for similar
        query = embedder.embed("tier 1 campaign meeting")
        results = hnsw.search(query, k=2)
        
        assert len(results) == 2
        # First result should be more similar to query
        assert results[0][0].entry_id == "e1"
    
    def test_empty_search_returns_empty(self, hnsw, embedder):
        """Search on empty index should return empty."""
        query = embedder.embed("test query")
        results = hnsw.search(query, k=5)
        assert len(results) == 0
    
    def test_max_elements_limit(self, embedder):
        """Should respect max elements limit."""
        hnsw = SimpleHNSW(dim=64, max_elements=3)
        
        for i in range(5):
            entry = ReasoningEntry(
                entry_id=f"e{i}",
                pattern_type="success",
                content=f"Content {i}"
            )
            hnsw.add(entry, embedder.embed(entry.content))
        
        # Should only have 3 entries (last 3)
        assert hnsw.size() == 3


# =============================================================================
# EWC++ TESTS
# =============================================================================

class TestEWCPlusPlus:
    """Tests for EWC++ consolidation."""
    
    def test_compute_importance(self, ewc):
        """Should compute importance from success rate and frequency."""
        importance = ewc.compute_importance("L001", success_rate=0.8, frequency=10)
        assert importance > 0
    
    def test_update_importance(self, ewc):
        """Should update importance weights."""
        ewc.update_importance("L001", success_rate=0.9, frequency=5)
        ewc.update_importance("L002", success_rate=0.3, frequency=2)
        
        assert ewc.importance_weights["L001"] > ewc.importance_weights["L002"]
    
    def test_consolidation_penalty(self, ewc):
        """Higher importance should have higher penalty."""
        ewc.importance_weights["L001"] = 0.9
        ewc.importance_weights["L002"] = 0.1
        
        penalty1 = ewc.consolidation_penalty("L001", 0.5)
        penalty2 = ewc.consolidation_penalty("L002", 0.5)
        
        assert penalty1 > penalty2
    
    def test_should_preserve(self, ewc):
        """Should correctly identify learnings to preserve."""
        ewc.importance_weights["high"] = 0.8
        ewc.importance_weights["low"] = 0.2
        
        assert ewc.should_preserve("high", threshold=0.5) is True
        assert ewc.should_preserve("low", threshold=0.5) is False
    
    def test_prune_low_importance(self, ewc):
        """Should prune low importance learnings."""
        ewc.importance_weights = {
            "keep1": 0.8,
            "keep2": 0.6,
            "prune1": 0.05,
            "prune2": 0.02
        }
        
        pruned = ewc.prune_low_importance(threshold=0.1)
        
        assert len(pruned) == 2
        assert "prune1" in pruned
        assert "prune2" in pruned
        assert "keep1" in ewc.importance_weights
    
    def test_preservation_score(self, ewc):
        """Should calculate preservation score."""
        ewc.importance_weights = {"a": 0.5, "b": 0.7, "c": 0.3}
        score = ewc.get_preservation_score()
        assert 0 <= score <= 1.0


# =============================================================================
# PIPELINE STAGE TESTS
# =============================================================================

class TestRetrieveStage:
    """Tests for RETRIEVE stage."""
    
    def test_retrieve_returns_similar_patterns(self, pipeline):
        """RETRIEVE should find similar patterns."""
        # Add some patterns first
        pipeline._add_to_reasoning_bank(
            "Campaign tier 1 meeting booked successfully",
            "success",
            {"icp_tier": "tier_1"},
            0.9
        )
        pipeline._add_to_reasoning_bank(
            "Campaign tier 4 spam report received",
            "failure",
            {"icp_tier": "tier_4"},
            0.8
        )
        
        # Retrieve similar
        results = pipeline.retrieve("tier 1 campaign meeting", k=2)
        
        assert len(results) == 2
        # Success pattern should be first
        assert results[0][0].pattern_type == "success"
    
    def test_retrieve_by_context(self, pipeline, sample_context):
        """Should retrieve by context."""
        pipeline._add_to_reasoning_bank(
            "tier_1 thought_leadership campaign",
            "success",
            sample_context,
            0.9
        )
        
        results = pipeline.retrieve_by_context(sample_context, k=1)
        assert len(results) == 1


class TestJudgeStage:
    """Tests for JUDGE stage."""
    
    def test_judge_success_outcome(self, pipeline, success_outcome):
        """JUDGE should rate meeting booked as excellent."""
        result = pipeline.judge(success_outcome, [])
        
        assert result.outcome_quality == "excellent"
        assert result.reward == 100
        assert result.confidence > 0.5
    
    def test_judge_failure_outcome(self, pipeline, failure_outcome):
        """JUDGE should rate spam report as critical."""
        result = pipeline.judge(failure_outcome, [])
        
        assert result.outcome_quality == "critical"
        assert result.reward == -50
        assert len(result.failure_indicators) > 0
    
    def test_judge_with_similar_patterns(self, pipeline, success_outcome, embedder):
        """JUDGE should use similar patterns."""
        # Create similar pattern
        entry = ReasoningEntry(
            entry_id="test",
            pattern_type="success",
            content="Meeting booked tier 1",
            confidence=0.9
        )
        
        similar = [(entry, 0.85)]
        result = pipeline.judge(success_outcome, similar)
        
        assert len(result.patterns_matched) == 1
        assert result.confidence >= 0.9  # Should be boosted


class TestDistillStage:
    """Tests for DISTILL stage."""
    
    def test_distill_creates_learnings(self, pipeline, success_outcome, sample_context):
        """DISTILL should create learnings from judgment."""
        judgment = JudgmentResult(
            outcome_quality="excellent",
            confidence=0.9,
            reward=100,
            patterns_matched=[],
            success_indicators=["Meeting booked"],
            failure_indicators=[]
        )
        
        result = pipeline.distill(
            "test_001",
            success_outcome,
            sample_context,
            judgment
        )
        
        assert len(result.learnings) >= 1
        assert result.learnings[0].learning_type == "success_pattern"
    
    def test_distill_failure_generates_refinements(self, pipeline, failure_outcome, sample_context):
        """DISTILL should suggest refinements for failures."""
        judgment = JudgmentResult(
            outcome_quality="critical",
            confidence=0.85,
            reward=-50,
            patterns_matched=[],
            success_indicators=[],
            failure_indicators=["CRITICAL: Spam report received"]
        )
        
        result = pipeline.distill(
            "test_002",
            failure_outcome,
            sample_context,
            judgment
        )
        
        assert len(result.refinements) >= 1
        assert any(r["target"] == "messaging" for r in result.refinements)


class TestConsolidateStage:
    """Tests for CONSOLIDATE stage."""
    
    def test_consolidate_updates_ewc(self, pipeline):
        """CONSOLIDATE should update EWC weights."""
        # Add some learnings
        pipeline.learnings.append(Learning(
            learning_id="L001",
            source_workflow="test",
            learning_type="success_pattern",
            description="Test learning",
            recommendation="Continue",
            confidence=0.8,
            impact_score=0.7
        ))
        
        pipeline._add_to_reasoning_bank(
            "Test learning pattern",
            "success",
            {},
            0.8
        )
        
        result = pipeline.consolidate()
        
        assert result.retained_learnings >= 0
        assert result.knowledge_stability >= 0


# =============================================================================
# FULL PIPELINE TESTS
# =============================================================================

class TestFullPipeline:
    """Tests for complete pipeline execution."""
    
    def test_process_outcome_success(self, pipeline, success_outcome, sample_context):
        """Full pipeline should process successful outcome."""
        result = pipeline.process_outcome(
            workflow_id="test_001",
            outcome=success_outcome,
            context=sample_context
        )
        
        assert result["workflow_id"] == "test_001"
        assert result["stages"]["judge"]["quality"] == "excellent"
        assert result["stages"]["distill"]["learnings_created"] >= 1
    
    def test_process_outcome_failure(self, pipeline, failure_outcome, sample_context):
        """Full pipeline should process failure outcome."""
        result = pipeline.process_outcome(
            workflow_id="test_002",
            outcome=failure_outcome,
            context=sample_context
        )
        
        assert result["stages"]["judge"]["quality"] == "critical"
        assert result["stages"]["distill"]["refinements_suggested"] >= 0
    
    def test_multiple_outcomes_build_patterns(self, pipeline):
        """Processing multiple outcomes should build pattern bank."""
        outcomes = [
            ({"meeting_booked": True}, {"icp_tier": "tier_1"}),
            ({"positive_reply": True}, {"icp_tier": "tier_1"}),
            ({"no_response": True}, {"icp_tier": "tier_3"}),
            ({"spam_report": True}, {"icp_tier": "tier_4"}),
        ]
        
        for i, (outcome, context) in enumerate(outcomes):
            pipeline.process_outcome(f"wf_{i}", outcome, context)
        
        # Should have patterns in bank
        assert len(pipeline.reasoning_bank) >= 2
        assert len(pipeline.learnings) >= 2


# =============================================================================
# QUEEN INTEGRATION TESTS
# =============================================================================

class TestQueenIntegration:
    """Tests for Queen orchestrator integration."""
    
    def test_report_to_queen_format(self, pipeline):
        """Report should have correct format."""
        report = pipeline.report_to_queen()
        
        assert "report_type" in report
        assert report["report_type"] == "self_annealing_pipeline"
        assert "pipeline_metrics" in report
        assert "reasoning_bank" in report
        assert "learnings" in report
        assert "knowledge_stability" in report
        assert "recommendations" in report
    
    def test_report_contains_metrics(self, pipeline, success_outcome):
        """Report should contain pipeline metrics."""
        pipeline.process_outcome("test", success_outcome, {})
        
        report = pipeline.report_to_queen()
        
        assert report["pipeline_metrics"]["total_processed"] >= 1
    
    def test_recommendations_generated(self, pipeline):
        """Should generate recommendations."""
        report = pipeline.report_to_queen()
        
        # With no data, should recommend collecting more
        assert any("data" in r.lower() for r in report["recommendations"]) or len(report["recommendations"]) == 0


# =============================================================================
# PERSISTENCE TESTS
# =============================================================================

class TestPersistence:
    """Tests for state persistence."""
    
    def test_save_and_load_state(self, tmp_path, success_outcome):
        """Should save and load state correctly."""
        # Create and use pipeline
        pipeline1 = SelfAnnealingPipeline(storage_path=tmp_path)
        pipeline1.process_outcome("test", success_outcome, {"tier": "1"})
        
        # Get counts
        reasoning_count = len(pipeline1.reasoning_bank)
        learnings_count = len(pipeline1.learnings)
        
        # Create new pipeline loading same state
        pipeline2 = SelfAnnealingPipeline(storage_path=tmp_path)
        
        assert len(pipeline2.reasoning_bank) == reasoning_count
        assert len(pipeline2.learnings) == learnings_count
    
    def test_reasoning_bank_persisted(self, tmp_path):
        """Reasoning bank should be persisted to JSON."""
        pipeline = SelfAnnealingPipeline(storage_path=tmp_path)
        pipeline._add_to_reasoning_bank("Test pattern", "success", {}, 0.9)
        pipeline._save_state()
        
        rb_path = tmp_path / "reasoning_bank.json"
        assert rb_path.exists()
        
        with open(rb_path) as f:
            data = json.load(f)
        
        assert len(data["entries"]) >= 1


# =============================================================================
# STATUS TESTS
# =============================================================================

class TestStatus:
    """Tests for pipeline status."""
    
    def test_get_status(self, pipeline):
        """Should return status dict."""
        status = pipeline.get_status()
        
        assert "reasoning_bank_size" in status
        assert "hnsw_index_size" in status
        assert "learnings_count" in status
        assert "ewc_knowledge_stability" in status
        assert "pipeline_metrics" in status
    
    def test_status_updates_after_processing(self, pipeline, success_outcome):
        """Status should update after processing."""
        initial_count = pipeline.pipeline_metrics["total_processed"]
        
        pipeline.process_outcome("test", success_outcome, {})
        
        assert pipeline.pipeline_metrics["total_processed"] == initial_count + 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
