"""
Tests for Precision Scorecard - Revenue Operations Constraint Detection
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.precision_scorecard import (
    Metric,
    MetricStatus,
    MetricTrend,
    MetricCategory,
    Constraint,
    ConstraintAnalyzer,
    PrecisionScorecard,
    METRIC_DEFINITIONS,
    get_scorecard,
    reset_scorecard,
)


# =============================================================================
# METRIC TESTS
# =============================================================================

class TestMetric:
    """Tests for the Metric dataclass."""
    
    def test_metric_on_track_status(self):
        """Metric meeting target should be ON_TRACK."""
        metric = Metric(
            id="test_metric",
            name="Test Metric",
            value=85,
            target=80,
            warning_threshold=70,
            unit="%",
            owner="TESTER"
        )
        
        assert metric.status == MetricStatus.ON_TRACK
        assert metric.status_emoji == "🟢"
    
    def test_metric_at_risk_status(self):
        """Metric below target but above warning should be AT_RISK."""
        metric = Metric(
            id="test_metric",
            name="Test Metric",
            value=75,
            target=80,
            warning_threshold=70,
            unit="%",
            owner="TESTER"
        )
        
        assert metric.status == MetricStatus.AT_RISK
        assert metric.status_emoji == "🟡"
    
    def test_metric_off_track_status(self):
        """Metric below warning threshold should be OFF_TRACK."""
        metric = Metric(
            id="test_metric",
            name="Test Metric",
            value=60,
            target=80,
            warning_threshold=70,
            unit="%",
            owner="TESTER"
        )
        
        assert metric.status == MetricStatus.OFF_TRACK
        assert metric.status_emoji == "🔴"
    
    def test_gap_to_target_calculation(self):
        """Gap to target should be value - target."""
        metric = Metric(
            id="test_metric",
            name="Test Metric",
            value=60,
            target=80,
            warning_threshold=70
        )
        
        assert metric.gap_to_target == -20
    
    def test_gap_percentage_calculation(self):
        """Gap percentage should be calculated correctly."""
        metric = Metric(
            id="test_metric",
            name="Test Metric",
            value=60,
            target=80,
            warning_threshold=70
        )
        
        assert metric.gap_percentage == -25.0  # (60-80)/80 * 100
    
    def test_trend_arrows(self):
        """Trend should show correct arrows."""
        up = Metric(id="up", name="Up", value=50, target=50, warning_threshold=40, trend=MetricTrend.UP)
        down = Metric(id="down", name="Down", value=50, target=50, warning_threshold=40, trend=MetricTrend.DOWN)
        stable = Metric(id="stable", name="Stable", value=50, target=50, warning_threshold=40, trend=MetricTrend.STABLE)
        
        assert up.trend_arrow == "↑"
        assert down.trend_arrow == "↓"
        assert stable.trend_arrow == "→"
    
    def test_metric_to_dict(self):
        """Metric should serialize to dictionary."""
        metric = Metric(
            id="test_metric",
            name="Test Metric",
            value=85,
            target=80,
            warning_threshold=70,
            unit="%",
            owner="TESTER",
            category=MetricCategory.PIPELINE
        )
        
        d = metric.to_dict()
        
        assert d["id"] == "test_metric"
        assert d["name"] == "Test Metric"
        assert d["value"] == 85
        assert d["status"] == "on_track"
        assert d["category"] == "pipeline"
        assert d["gap_to_target"] == 5


# =============================================================================
# CONSTRAINT TESTS
# =============================================================================

class TestConstraint:
    """Tests for the Constraint dataclass."""
    
    def test_constraint_creation(self):
        """Constraint should initialize correctly."""
        constraint = Constraint(
            metric_id="lead_velocity_rate",
            metric_name="Lead Velocity Rate",
            current_value=5,
            target_value=10,
            gap_percentage=-50,
            root_cause="HUNTER scraping sources returning fewer results",
            recommended_action="Review and rotate scraping sources",
            impact_if_fixed="Fixing could increase qualified leads by ~50%",
            owner="HUNTER",
            severity="high"
        )
        
        assert constraint.metric_name == "Lead Velocity Rate"
        assert constraint.gap_percentage == -50
        assert constraint.severity == "high"
    
    def test_constraint_to_dict(self):
        """Constraint should serialize to dictionary."""
        constraint = Constraint(
            metric_id="test",
            metric_name="Test",
            current_value=50,
            target_value=80,
            gap_percentage=-37.5,
            root_cause="Test cause",
            recommended_action="Test action",
            impact_if_fixed="Test impact",
            owner="TESTER"
        )
        
        d = constraint.to_dict()
        
        assert d["metric_id"] == "test"
        assert d["root_cause"] == "Test cause"
        assert "detected_at" in d
    
    def test_constraint_slack_block(self):
        """Constraint should generate Slack Block Kit format."""
        constraint = Constraint(
            metric_id="test",
            metric_name="Test Metric",
            current_value=50,
            target_value=80,
            gap_percentage=-37.5,
            root_cause="Something broke",
            recommended_action="Fix it",
            impact_if_fixed="Things will work",
            owner="TESTER",
            severity="critical"
        )
        
        block = constraint.to_slack_block()
        
        assert block["type"] == "section"
        assert "🚨" in block["text"]["text"]  # Critical emoji
        assert "Test Metric" in block["text"]["text"]


# =============================================================================
# CONSTRAINT ANALYZER TESTS
# =============================================================================

class TestConstraintAnalyzer:
    """Tests for the AI-powered constraint analyzer."""
    
    def test_finds_worst_metric_as_constraint(self):
        """Analyzer should identify the worst-performing metric."""
        analyzer = ConstraintAnalyzer()
        
        metrics = [
            Metric(id="good", name="Good", value=90, target=80, warning_threshold=70),
            Metric(id="bad", name="Bad", value=50, target=80, warning_threshold=70),
            Metric(id="ok", name="OK", value=75, target=80, warning_threshold=70),
        ]
        
        constraint = analyzer.analyze(metrics)
        
        assert constraint is not None
        assert constraint.metric_id == "bad"
        assert constraint.severity in ["high", "critical"]
    
    def test_no_constraint_when_all_on_track(self):
        """No constraint should be returned if all metrics are on track."""
        analyzer = ConstraintAnalyzer()
        
        metrics = [
            Metric(id="a", name="A", value=90, target=80, warning_threshold=70),
            Metric(id="b", name="B", value=85, target=80, warning_threshold=70),
            Metric(id="c", name="C", value=95, target=80, warning_threshold=70),
        ]
        
        constraint = analyzer.analyze(metrics)
        
        assert constraint is None
    
    def test_at_risk_becomes_constraint_when_no_off_track(self):
        """At-risk metric should be constraint when nothing is off-track."""
        analyzer = ConstraintAnalyzer()
        
        metrics = [
            Metric(id="good", name="Good", value=90, target=80, warning_threshold=70),
            Metric(id="at_risk", name="At Risk", value=72, target=80, warning_threshold=70),
        ]
        
        constraint = analyzer.analyze(metrics)
        
        assert constraint is not None
        assert constraint.metric_id == "at_risk"
        assert constraint.severity == "medium"
    
    def test_provides_cause_and_action_for_known_metrics(self):
        """Analyzer should provide specific causes for known metrics."""
        analyzer = ConstraintAnalyzer()
        
        metrics = [
            Metric(
                id="lead_velocity_rate",
                name="Lead Velocity Rate",
                value=-5,
                target=10,
                warning_threshold=0,
                category=MetricCategory.PIPELINE
            ),
        ]
        
        constraint = analyzer.analyze(metrics)
        
        assert constraint is not None
        assert "HUNTER" in constraint.root_cause or "scraping" in constraint.root_cause.lower()
    
    def test_empty_metrics_returns_none(self):
        """Empty metric list should return no constraint."""
        analyzer = ConstraintAnalyzer()
        
        constraint = analyzer.analyze([])
        
        assert constraint is None


# =============================================================================
# SCORECARD TESTS
# =============================================================================

class TestPrecisionScorecard:
    """Tests for the main Precision Scorecard class."""
    
    @pytest.fixture
    def temp_hive_mind(self, tmp_path):
        """Create temporary .hive-mind directory."""
        hive_mind = tmp_path / ".hive-mind"
        hive_mind.mkdir(parents=True)
        (hive_mind / "scraped").mkdir()
        (hive_mind / "segmented").mkdir()
        (hive_mind / "enriched").mkdir()
        (hive_mind / "campaigns").mkdir()
        return hive_mind
    
    def test_initializes_all_12_metrics(self):
        """Scorecard should have all 12 defined metrics."""
        reset_scorecard()
        scorecard = PrecisionScorecard()
        
        assert len(scorecard.metrics) == 12
        assert "lead_velocity_rate" in scorecard.metrics
        assert "icp_match_rate" in scorecard.metrics
        assert "swarm_uptime" in scorecard.metrics
    
    def test_metrics_have_correct_categories(self):
        """Metrics should be assigned to correct categories."""
        reset_scorecard()
        scorecard = PrecisionScorecard()
        
        pipeline = [m for m in scorecard.metrics.values() if m.category == MetricCategory.PIPELINE]
        outreach = [m for m in scorecard.metrics.values() if m.category == MetricCategory.OUTREACH]
        conversion = [m for m in scorecard.metrics.values() if m.category == MetricCategory.CONVERSION]
        health = [m for m in scorecard.metrics.values() if m.category == MetricCategory.HEALTH]
        
        assert len(pipeline) == 3
        assert len(outreach) == 3
        assert len(conversion) == 3
        assert len(health) == 3
    
    def test_every_metric_has_owner(self):
        """Precision principle: Every number has a name attached."""
        reset_scorecard()
        scorecard = PrecisionScorecard()
        
        for metric in scorecard.metrics.values():
            assert metric.owner is not None
            assert len(metric.owner) > 0
    
    def test_get_summary_structure(self):
        """Summary should have correct structure."""
        reset_scorecard()
        scorecard = PrecisionScorecard()
        
        summary = scorecard.get_summary()
        
        assert "scorecard" in summary
        assert "constraint" in summary
        assert "metrics_by_category" in summary["scorecard"]
        assert "status_summary" in summary["scorecard"]
    
    def test_category_summary(self):
        """Category summary should filter correctly."""
        reset_scorecard()
        scorecard = PrecisionScorecard()
        
        pipeline_summary = scorecard.get_category_summary(MetricCategory.PIPELINE)
        
        assert pipeline_summary["category"] == "pipeline"
        assert len(pipeline_summary["metrics"]) == 3
    
    def test_markdown_report_generation(self):
        """Should generate valid markdown report."""
        reset_scorecard()
        scorecard = PrecisionScorecard()
        
        report = scorecard.to_markdown_report()
        
        assert "# 📊 Precision Scorecard" in report
        assert "PIPELINE" in report
        assert "OUTREACH" in report
        assert "CONVERSION" in report
        assert "HEALTH" in report


class TestScorecardDataFetching:
    """Tests for scorecard data fetching from .hive-mind."""
    
    @pytest.fixture
    def mock_hive_mind(self, tmp_path):
        """Create mock .hive-mind with test data."""
        hive_mind = tmp_path / ".hive-mind"
        hive_mind.mkdir(parents=True)
        
        # Create scraped files
        scraped = hive_mind / "scraped"
        scraped.mkdir()
        for i in range(10):
            (scraped / f"lead_{i}.json").write_text('{"name": "Test Lead"}')
        
        # Create segmented files with ICP data
        segmented = hive_mind / "segmented"
        segmented.mkdir()
        (segmented / "batch_001.json").write_text(json.dumps({
            "leads": [
                {"icp_tier": "tier_1"},
                {"icp_tier": "tier_2"},
                {"icp_tier": "tier_3"},
                {"icp_tier": "tier_4"},
            ]
        }))
        
        # Create enriched files
        enriched = hive_mind / "enriched"
        enriched.mkdir()
        for i in range(8):
            (enriched / f"enriched_{i}.json").write_text('{"enriched": true}')
        
        # Create campaign stats
        campaigns = hive_mind / "campaigns"
        campaigns.mkdir()
        (campaigns / "campaign_001.json").write_text(json.dumps({
            "stats": {
                "sent": 100,
                "opened": 55,
                "replied": 8,
                "positive_replies": 5
            }
        }))
        
        return hive_mind
    
    def test_icp_match_rate_calculation(self, mock_hive_mind, monkeypatch):
        """ICP match rate should count tier_1 and tier_2."""
        monkeypatch.setattr(
            "core.precision_scorecard.HIVE_MIND",
            mock_hive_mind
        )
        
        reset_scorecard()
        scorecard = PrecisionScorecard()
        scorecard.refresh()
        
        # 2 out of 4 leads are tier_1 or tier_2 = 50%
        assert scorecard.metrics["icp_match_rate"].value == 50.0
    
    def test_enrichment_rate_calculation(self, mock_hive_mind, monkeypatch):
        """Enrichment rate should be enriched/scraped ratio."""
        monkeypatch.setattr(
            "core.precision_scorecard.HIVE_MIND",
            mock_hive_mind
        )
        
        reset_scorecard()
        scorecard = PrecisionScorecard()
        scorecard.refresh()
        
        # 8 enriched out of 10 scraped = 80%
        assert scorecard.metrics["enrichment_rate"].value == 80.0
    
    def test_email_metrics_calculation(self, mock_hive_mind, monkeypatch):
        """Email metrics should calculate from campaign stats."""
        monkeypatch.setattr(
            "core.precision_scorecard.HIVE_MIND",
            mock_hive_mind
        )
        
        reset_scorecard()
        scorecard = PrecisionScorecard()
        scorecard.refresh()
        
        assert scorecard.metrics["email_open_rate"].value == 55.0  # 55/100
        assert scorecard.metrics["reply_rate"].value == 8.0  # 8/100
        assert scorecard.metrics["positive_reply_rate"].value == 62.5  # 5/8


# =============================================================================
# SINGLETON TESTS
# =============================================================================

class TestSingleton:
    """Tests for singleton pattern."""
    
    def test_get_scorecard_returns_same_instance(self):
        """get_scorecard() should return same instance."""
        reset_scorecard()
        
        sc1 = get_scorecard()
        sc2 = get_scorecard()
        
        assert sc1 is sc2
    
    def test_reset_scorecard_clears_instance(self):
        """reset_scorecard() should clear the singleton."""
        sc1 = get_scorecard()
        reset_scorecard()
        sc2 = get_scorecard()
        
        assert sc1 is not sc2


# =============================================================================
# METRIC DEFINITIONS TESTS
# =============================================================================

class TestMetricDefinitions:
    """Tests for the pre-built metrics library."""
    
    def test_all_12_metrics_defined(self):
        """Should have exactly 12 metric definitions."""
        assert len(METRIC_DEFINITIONS) == 12
    
    def test_each_metric_has_required_fields(self):
        """Each metric definition should have all required fields."""
        required = ["name", "target", "warning", "unit", "owner", "category"]
        
        for metric_id, definition in METRIC_DEFINITIONS.items():
            for field in required:
                assert field in definition, f"{metric_id} missing {field}"
    
    def test_balanced_categories(self):
        """Should have 3 metrics per category."""
        by_category = {}
        for metric_id, definition in METRIC_DEFINITIONS.items():
            cat = definition["category"].value
            by_category[cat] = by_category.get(cat, 0) + 1
        
        assert by_category["pipeline"] == 3
        assert by_category["outreach"] == 3
        assert by_category["conversion"] == 3
        assert by_category["health"] == 3
    
    def test_targets_are_sensible(self):
        """Targets should be reasonable percentages."""
        for metric_id, definition in METRIC_DEFINITIONS.items():
            target = definition["target"]
            warning = definition["warning"]
            
            # Warning should be below target
            assert warning < target, f"{metric_id}: warning >= target"
            
            # Most metrics should have positive targets
            # (except lead_velocity_rate which can be 0 or negative)
            if metric_id != "lead_velocity_rate":
                assert target > 0, f"{metric_id}: target <= 0"
