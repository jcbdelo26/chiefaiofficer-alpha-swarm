"""
Precision Scorecard - Revenue Operations Constraint Detection
=============================================================

Inspired by Precision.co's philosophy:
"The only company scorecard that tells you what to fix."

Key Principles:
1. 12 metrics max - only what moves the revenue needle
2. Every metric has an owner (person or agent)
3. ONE constraint highlighted at a time with action recommendation
4. Auto-synced from existing data sources, zero manual entry
5. Theory of Constraints: find the bottleneck killing growth

Usage:
    from core.precision_scorecard import PrecisionScorecard, get_scorecard
    
    scorecard = get_scorecard()
    scorecard.refresh()
    
    # Get the ONE thing to fix
    constraint = scorecard.get_constraint()
    print(f"Fix: {constraint.metric_name} - {constraint.root_cause}")
    print(f"Action: {constraint.recommended_action}")
    
    # Get full scorecard
    summary = scorecard.get_summary()
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Literal, Any, Tuple
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
HIVE_MIND = PROJECT_ROOT / ".hive-mind"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("precision-scorecard")


# =============================================================================
# ENUMS & TYPES
# =============================================================================

class MetricStatus(Enum):
    """Simple 3-state status inspired by Precision's color coding."""
    ON_TRACK = "on_track"      # 🟢 Meeting or exceeding target
    AT_RISK = "at_risk"        # 🟡 Below target but within warning threshold
    OFF_TRACK = "off_track"    # 🔴 Below warning threshold, needs attention


class MetricTrend(Enum):
    """Week-over-week trend direction."""
    UP = "up"        # ↑ Improving
    DOWN = "down"    # ↓ Declining
    STABLE = "stable"  # → No significant change


class MetricCategory(Enum):
    """The 4 categories that matter for RevOps."""
    PIPELINE = "pipeline"      # Lead generation & qualification
    OUTREACH = "outreach"      # Email/messaging performance
    CONVERSION = "conversion"  # Turning leads into revenue
    HEALTH = "health"          # Swarm operational health


# =============================================================================
# CORE DATA CLASSES
# =============================================================================

@dataclass
class Metric:
    """
    Single metric with ownership and status.
    
    Precision's key insight: Every number has a name attached.
    """
    id: str                    # Unique identifier (e.g., "lead_velocity_rate")
    name: str                  # Human-readable name
    value: float               # Current value
    target: float              # Goal to hit
    warning_threshold: float   # Below this = at_risk
    unit: str = "%"            # Display unit
    owner: str = "QUEEN"       # Agent or person responsible
    category: MetricCategory = MetricCategory.PIPELINE
    trend: MetricTrend = MetricTrend.STABLE
    trend_value: float = 0.0   # % change week-over-week
    last_updated: str = ""
    description: str = ""
    
    def __post_init__(self):
        if not self.last_updated:
            self.last_updated = datetime.now(timezone.utc).isoformat()
    
    @property
    def status(self) -> MetricStatus:
        """Calculate status based on value vs thresholds."""
        if self.value >= self.target:
            return MetricStatus.ON_TRACK
        elif self.value >= self.warning_threshold:
            return MetricStatus.AT_RISK
        else:
            return MetricStatus.OFF_TRACK
    
    @property
    def status_emoji(self) -> str:
        """Simple visual indicator."""
        return {
            MetricStatus.ON_TRACK: "🟢",
            MetricStatus.AT_RISK: "🟡",
            MetricStatus.OFF_TRACK: "🔴"
        }[self.status]
    
    @property
    def trend_arrow(self) -> str:
        """Direction indicator."""
        return {
            MetricTrend.UP: "↑",
            MetricTrend.DOWN: "↓",
            MetricTrend.STABLE: "→"
        }[self.trend]
    
    @property
    def gap_to_target(self) -> float:
        """How far from target (negative = below)."""
        return self.value - self.target
    
    @property
    def gap_percentage(self) -> float:
        """Gap as percentage of target."""
        if self.target == 0:
            return 0
        return ((self.value - self.target) / self.target) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "value": self.value,
            "target": self.target,
            "warning_threshold": self.warning_threshold,
            "unit": self.unit,
            "owner": self.owner,
            "category": self.category.value,
            "status": self.status.value,
            "status_emoji": self.status_emoji,
            "trend": self.trend.value,
            "trend_arrow": self.trend_arrow,
            "trend_value": self.trend_value,
            "gap_to_target": self.gap_to_target,
            "gap_percentage": round(self.gap_percentage, 1),
            "last_updated": self.last_updated,
            "description": self.description
        }


@dataclass
class Constraint:
    """
    The ONE thing killing growth right now.
    
    Precision's core value prop: "Find the constraint killing your growth"
    with "Recommended actions based on YOUR data"
    """
    metric_id: str
    metric_name: str
    current_value: float
    target_value: float
    gap_percentage: float
    root_cause: str           # WHY it's broken
    recommended_action: str   # WHAT to do next
    impact_if_fixed: str      # WHY fixing this matters
    owner: str                # WHO needs to act
    detected_at: str = ""
    severity: Literal["critical", "high", "medium"] = "high"
    
    def __post_init__(self):
        if not self.detected_at:
            self.detected_at = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_slack_block(self) -> Dict[str, Any]:
        """Format for Slack Block Kit notification."""
        severity_emoji = {
            "critical": "🚨",
            "high": "⚠️",
            "medium": "📊"
        }[self.severity]
        
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{severity_emoji} *Constraint Detected: {self.metric_name}*\n\n"
                    f"*Current:* {self.current_value} (Target: {self.target_value})\n"
                    f"*Gap:* {self.gap_percentage:+.1f}%\n\n"
                    f"*Why:* {self.root_cause}\n\n"
                    f"*Fix:* {self.recommended_action}\n\n"
                    f"*Owner:* @{self.owner}"
                )
            }
        }


# =============================================================================
# THE 12 METRICS THAT MATTER
# =============================================================================

# Metric definitions with defaults - the Precision "pre-built library" concept
METRIC_DEFINITIONS = {
    # PIPELINE (Lead Gen) - 3 metrics
    "lead_velocity_rate": {
        "name": "Lead Velocity Rate",
        "target": 10,  # 10% week-over-week growth
        "warning": 0,
        "unit": "%",
        "owner": "HUNTER",
        "category": MetricCategory.PIPELINE,
        "description": "Week-over-week growth in qualified leads"
    },
    "icp_match_rate": {
        "name": "ICP Match Rate",
        "target": 75,
        "warning": 60,
        "unit": "%",
        "owner": "SEGMENTOR",
        "category": MetricCategory.PIPELINE,
        "description": "Percentage of leads matching Ideal Customer Profile"
    },
    "enrichment_rate": {
        "name": "Enrichment Rate",
        "target": 90,
        "warning": 75,
        "unit": "%",
        "owner": "ENRICHER",
        "category": MetricCategory.PIPELINE,
        "description": "Leads successfully enriched with additional data"
    },
    
    # OUTREACH - 3 metrics
    "email_open_rate": {
        "name": "Email Open Rate",
        "target": 50,
        "warning": 35,
        "unit": "%",
        "owner": "CRAFTER",
        "category": MetricCategory.OUTREACH,
        "description": "Percentage of emails opened by recipients"
    },
    "reply_rate": {
        "name": "Reply Rate",
        "target": 8,
        "warning": 4,
        "unit": "%",
        "owner": "CRAFTER",
        "category": MetricCategory.OUTREACH,
        "description": "Percentage of outreach getting any reply"
    },
    "positive_reply_rate": {
        "name": "Positive Reply Rate",
        "target": 50,
        "warning": 30,
        "unit": "%",
        "owner": "COACH",
        "category": MetricCategory.OUTREACH,
        "description": "Replies with positive sentiment (interested)"
    },
    
    # CONVERSION - 3 metrics
    "meeting_book_rate": {
        "name": "Meeting Book Rate",
        "target": 2,
        "warning": 1,
        "unit": "%",
        "owner": "SCHEDULER",
        "category": MetricCategory.CONVERSION,
        "description": "Leads converted to scheduled meetings"
    },
    "ae_approval_rate": {
        "name": "AE Approval Rate",
        "target": 70,
        "warning": 50,
        "unit": "%",
        "owner": "GATEKEEPER",
        "category": MetricCategory.CONVERSION,
        "description": "GATEKEEPER approvals for outreach"
    },
    "pipeline_close_rate": {
        "name": "Pipeline → Close",
        "target": 20,
        "warning": 10,
        "unit": "%",
        "owner": "PIPER",
        "category": MetricCategory.CONVERSION,
        "description": "Meetings converted to closed deals"
    },
    
    # HEALTH - 3 metrics
    "agent_success_rate": {
        "name": "Agent Success Rate",
        "target": 95,
        "warning": 85,
        "unit": "%",
        "owner": "UNIFIED_QUEEN",
        "category": MetricCategory.HEALTH,
        "description": "Percentage of agent tasks completing successfully"
    },
    "swarm_uptime": {
        "name": "Swarm Uptime",
        "target": 99,
        "warning": 95,
        "unit": "%",
        "owner": "UNIFIED_QUEEN",
        "category": MetricCategory.HEALTH,
        "description": "System availability over last 24 hours"
    },
    "queue_health": {
        "name": "Queue Health",
        "target": 90,
        "warning": 70,
        "unit": "%",
        "owner": "UNIFIED_QUEEN",
        "category": MetricCategory.HEALTH,
        "description": "Queue processing efficiency (low depth = healthy)"
    }
}


# =============================================================================
# ROOT CAUSE ANALYZER
# =============================================================================

class ConstraintAnalyzer:
    """
    AI-powered root cause analysis.
    
    Precision's insight: "It tells you WHY revenue dropped,
    WHERE the funnel broke, and WHAT to do next."
    """
    
    # Mapping of metrics to potential causes and actions
    CAUSE_MAP = {
        "lead_velocity_rate": {
            "causes": [
                ("HUNTER scraping sources returning fewer results", "Review and rotate scraping sources"),
                ("LinkedIn rate limits affecting extraction", "Reduce scraping frequency or add proxies"),
                ("ICP criteria too narrow", "Widen targeting parameters"),
                ("Seasonal drop in target market activity", "Expand to adjacent verticals")
            ]
        },
        "icp_match_rate": {
            "causes": [
                ("Scraping sources targeting wrong audience", "Switch to industry-specific sources"),
                ("ICP criteria outdated", "Review and update ICP based on recent wins"),
                ("SEGMENTOR scoring weights miscalibrated", "Retrain on recent closed-won data")
            ]
        },
        "enrichment_rate": {
            "causes": [
                ("Clay/enrichment API errors", "Check Clay API status and credentials"),
                ("Invalid email addresses in pipeline", "Add email validation pre-enrichment"),
                ("Rate limits on enrichment provider", "Implement request throttling")
            ]
        },
        "email_open_rate": {
            "causes": [
                ("Subject lines not compelling", "A/B test new subject line patterns"),
                ("Poor sender reputation", "Check domain reputation, warm up new IPs"),
                ("Wrong send times", "Shift to target timezone business hours"),
                ("Spam folder delivery", "Review and remove spam trigger words")
            ]
        },
        "reply_rate": {
            "causes": [
                ("Message copy not resonating", "Review CRAFTER templates, update value props"),
                ("Too generic personalization", "Increase personalization depth"),
                ("Wrong personas targeted", "Review ICP title targeting"),
                ("Follow-up cadence too aggressive", "Extend time between touches")
            ]
        },
        "positive_reply_rate": {
            "causes": [
                ("Value proposition unclear", "Sharpen the pain → solution narrative"),
                ("Targeting companies not in buying mode", "Add intent signals to ICP"),
                ("Competitive messaging not differentiated", "Update competitive displacement plays")
            ]
        },
        "meeting_book_rate": {
            "causes": [
                ("Calendar availability too limited", "Expand SCHEDULER available slots"),
                ("Too many steps to book", "Simplify booking flow"),
                ("Follow-up on positive replies delayed", "Reduce COACH response time")
            ]
        },
        "ae_approval_rate": {
            "causes": [
                ("Low quality leads reaching GATEKEEPER", "Tighten SEGMENTOR thresholds"),
                ("Approval queue backlog", "Review pending approvals, set SLAs"),
                ("Unclear approval criteria", "Document GATEKEEPER decision matrix")
            ]
        },
        "pipeline_close_rate": {
            "causes": [
                ("Unqualified meetings booked", "Add qualification questions pre-meeting"),
                ("Sales team capacity constrained", "Review meeting distribution"),
                ("Pricing objections", "Arm AEs with ROI calculators")
            ]
        },
        "agent_success_rate": {
            "causes": [
                ("API failures from integrations", "Check GHL/Calendar API health"),
                ("Circuit breakers tripped", "Review and reset circuit breakers"),
                ("Invalid input data causing errors", "Add input validation")
            ]
        },
        "swarm_uptime": {
            "causes": [
                ("Service crashes or restarts", "Review error logs, add health checks"),
                ("Memory/CPU constraints", "Scale infrastructure"),
                ("Dependency service outages", "Add fallback for external services")
            ]
        },
        "queue_health": {
            "causes": [
                ("Tasks accumulating faster than processing", "Scale worker count"),
                ("Stuck tasks blocking queue", "Add timeout and dead letter handling"),
                ("Uneven task distribution", "Balance load across agents")
            ]
        }
    }
    
    def analyze(self, metrics: List[Metric]) -> Optional[Constraint]:
        """
        Find the ONE constraint killing growth.
        
        Theory of Constraints: The chain is only as strong as its weakest link.
        Fix one constraint at a time for maximum leverage.
        """
        if not metrics:
            return None
        
        # Sort by gap percentage (most negative = worst performing)
        off_track = [m for m in metrics if m.status == MetricStatus.OFF_TRACK]
        
        if not off_track:
            # No off-track metrics, check at-risk
            at_risk = [m for m in metrics if m.status == MetricStatus.AT_RISK]
            if not at_risk:
                return None  # Everything is on track!
            candidates = at_risk
            severity = "medium"
        else:
            candidates = off_track
            severity = "high" if len(off_track) == 1 else "critical"
        
        # Find the worst one
        worst = min(candidates, key=lambda m: m.gap_percentage)
        
        # Get root cause and action
        root_cause, action = self._get_cause_and_action(worst)
        
        return Constraint(
            metric_id=worst.id,
            metric_name=worst.name,
            current_value=worst.value,
            target_value=worst.target,
            gap_percentage=worst.gap_percentage,
            root_cause=root_cause,
            recommended_action=action,
            impact_if_fixed=self._estimate_impact(worst),
            owner=worst.owner,
            severity=severity
        )
    
    def _get_cause_and_action(self, metric: Metric) -> Tuple[str, str]:
        """Get the most likely cause and recommended action."""
        causes = self.CAUSE_MAP.get(metric.id, {}).get("causes", [])
        
        if not causes:
            return (
                f"{metric.name} is below target",
                f"Review {metric.owner} agent configuration"
            )
        
        # For now, return the first cause. 
        # Future: Use AI to match based on additional signals
        return causes[0]
    
    def _estimate_impact(self, metric: Metric) -> str:
        """Estimate the business impact of fixing this constraint."""
        gap = abs(metric.gap_percentage)
        
        if metric.category == MetricCategory.PIPELINE:
            return f"Fixing could increase qualified leads by ~{gap:.0f}%"
        elif metric.category == MetricCategory.OUTREACH:
            return f"Improving could generate {gap:.0f}% more conversations"
        elif metric.category == MetricCategory.CONVERSION:
            return f"Could add {gap:.0f}% more revenue from existing pipeline"
        else:
            return f"Would improve system reliability by {gap:.0f}%"


# =============================================================================
# PRECISION SCORECARD
# =============================================================================

class PrecisionScorecard:
    """
    The 12-metric scorecard with constraint detection.
    
    Design principles from Precision.co:
    1. Auto-generated from your data
    2. Only metrics that matter
    3. Every number has an owner
    4. Tells you what to fix, not just what's broken
    """
    
    def __init__(self):
        self.metrics: Dict[str, Metric] = {}
        self.constraint: Optional[Constraint] = None
        self.analyzer = ConstraintAnalyzer()
        self.history: Dict[str, List[Dict]] = {}
        self._history_file = HIVE_MIND / "scorecard_history.json"
        self._last_refresh: Optional[datetime] = None
        
        self._load_history()
        self._initialize_metrics()
    
    def _initialize_metrics(self):
        """Initialize metrics with default values."""
        for metric_id, definition in METRIC_DEFINITIONS.items():
            self.metrics[metric_id] = Metric(
                id=metric_id,
                name=definition["name"],
                value=0,  # Will be populated on refresh
                target=definition["target"],
                warning_threshold=definition["warning"],
                unit=definition["unit"],
                owner=definition["owner"],
                category=definition["category"],
                description=definition["description"]
            )
    
    def _load_history(self):
        """Load metric history for trend calculation."""
        if self._history_file.exists():
            try:
                with open(self._history_file) as f:
                    self.history = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load history: {e}")
                self.history = {}
    
    def _save_history(self):
        """Persist current values to history."""
        self._history_file.parent.mkdir(parents=True, exist_ok=True)
        
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        for metric_id, metric in self.metrics.items():
            if metric_id not in self.history:
                self.history[metric_id] = []
            
            # Add today's value
            self.history[metric_id].append({
                "date": today,
                "value": metric.value,
                "status": metric.status.value
            })
            
            # Keep last 90 days
            self.history[metric_id] = self.history[metric_id][-90:]
        
        try:
            with open(self._history_file, "w") as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save history: {e}")
    
    def _calculate_trend(self, metric_id: str, current_value: float) -> Tuple[MetricTrend, float]:
        """Calculate week-over-week trend."""
        history = self.history.get(metric_id, [])
        
        if len(history) < 7:
            return MetricTrend.STABLE, 0.0
        
        # Compare to 7 days ago
        week_ago_value = history[-7]["value"] if len(history) >= 7 else history[0]["value"]
        
        if week_ago_value == 0:
            return MetricTrend.STABLE, 0.0
        
        change = ((current_value - week_ago_value) / week_ago_value) * 100
        
        if change > 5:
            return MetricTrend.UP, change
        elif change < -5:
            return MetricTrend.DOWN, change
        else:
            return MetricTrend.STABLE, change
    
    def refresh(self):
        """
        Fetch current values for all metrics from data sources.
        
        This is the "auto-sync" that Precision emphasizes - 
        no manual data entry required.
        """
        logger.info("Refreshing scorecard metrics...")
        
        # Fetch from each data source
        self._fetch_pipeline_metrics()
        self._fetch_outreach_metrics()
        self._fetch_conversion_metrics()
        self._fetch_health_metrics()
        
        # Calculate trends
        for metric_id, metric in self.metrics.items():
            trend, trend_value = self._calculate_trend(metric_id, metric.value)
            metric.trend = trend
            metric.trend_value = trend_value
        
        # Find constraint
        self.constraint = self.analyzer.analyze(list(self.metrics.values()))
        
        # Save history
        self._save_history()
        
        self._last_refresh = datetime.now(timezone.utc)
        logger.info(f"Scorecard refreshed. Constraint: {self.constraint.metric_name if self.constraint else 'None'}")
    
    def _fetch_pipeline_metrics(self):
        """Fetch lead gen metrics from .hive-mind directories."""
        # Lead Velocity Rate
        scraped_dir = HIVE_MIND / "scraped"
        if scraped_dir.exists():
            files = list(scraped_dir.glob("*.json"))
            # Simplified: count files from last week vs this week
            now = datetime.now(timezone.utc)
            week_ago = now - timedelta(days=7)
            
            this_week = sum(1 for f in files if datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc) > week_ago)
            last_week = len(files) - this_week
            
            if last_week > 0:
                lvr = ((this_week - last_week) / last_week) * 100
            else:
                lvr = 0 if this_week == 0 else 100
            
            self.metrics["lead_velocity_rate"].value = round(lvr, 1)
        
        # ICP Match Rate
        segmented_dir = HIVE_MIND / "segmented"
        if segmented_dir.exists():
            total_leads = 0
            icp_matches = 0
            for f in segmented_dir.glob("*.json"):
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                        leads = data.get("leads", [data]) if isinstance(data, dict) else data
                        for lead in leads:
                            total_leads += 1
                            if lead.get("icp_tier") in ["tier_1", "tier_2"]:
                                icp_matches += 1
                except Exception:
                    pass
            
            if total_leads > 0:
                self.metrics["icp_match_rate"].value = round((icp_matches / total_leads) * 100, 1)
        
        # Enrichment Rate
        enriched_dir = HIVE_MIND / "enriched"
        if enriched_dir.exists() and scraped_dir.exists():
            scraped_count = len(list(scraped_dir.glob("*.json")))
            enriched_count = len(list(enriched_dir.glob("*.json")))
            
            if scraped_count > 0:
                self.metrics["enrichment_rate"].value = round((enriched_count / scraped_count) * 100, 1)
    
    def _fetch_outreach_metrics(self):
        """Fetch campaign performance metrics."""
        campaigns_dir = HIVE_MIND / "campaigns"
        
        if campaigns_dir.exists():
            total_sent = 0
            total_opened = 0
            total_replied = 0
            total_positive = 0
            
            for f in campaigns_dir.glob("*.json"):
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                        stats = data.get("stats", {})
                        total_sent += stats.get("sent", 0)
                        total_opened += stats.get("opened", 0)
                        total_replied += stats.get("replied", 0)
                        total_positive += stats.get("positive_replies", 0)
                except Exception:
                    pass
            
            if total_sent > 0:
                self.metrics["email_open_rate"].value = round((total_opened / total_sent) * 100, 1)
                self.metrics["reply_rate"].value = round((total_replied / total_sent) * 100, 1)
            
            if total_replied > 0:
                self.metrics["positive_reply_rate"].value = round((total_positive / total_replied) * 100, 1)
    
    def _fetch_conversion_metrics(self):
        """Fetch conversion metrics from GHL and review logs."""
        # Meeting Book Rate
        pipeline_file = HIVE_MIND / "pipeline_stats.json"
        if pipeline_file.exists():
            try:
                with open(pipeline_file) as f:
                    data = json.load(f)
                    self.metrics["meeting_book_rate"].value = data.get("meeting_book_rate", 0)
                    self.metrics["pipeline_close_rate"].value = data.get("close_rate", 0)
            except Exception:
                pass
        
        # AE Approval Rate
        review_log = HIVE_MIND / "review_log.json"
        if review_log.exists():
            try:
                with open(review_log) as f:
                    data = json.load(f)
                    reviews = data.get("reviews", [])
                    if reviews:
                        approved = sum(1 for r in reviews if r.get("action") == "approved")
                        self.metrics["ae_approval_rate"].value = round((approved / len(reviews)) * 100, 1)
            except Exception:
                pass
    
    def _fetch_health_metrics(self):
        """Fetch swarm health metrics from health monitor and audit trail."""
        # Agent Success Rate - from audit trail
        audit_db = HIVE_MIND / "audit.db"
        if audit_db.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(str(audit_db))
                cursor = conn.cursor()
                
                # Count success/failure in last 24 hours
                yesterday = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                cursor.execute("""
                    SELECT status, COUNT(*) FROM audit_log 
                    WHERE timestamp > ? 
                    GROUP BY status
                """, (yesterday,))
                
                results = {row[0]: row[1] for row in cursor.fetchall()}
                total = sum(results.values())
                success = results.get("success", 0)
                
                if total > 0:
                    self.metrics["agent_success_rate"].value = round((success / total) * 100, 1)
                
                conn.close()
            except Exception as e:
                logger.warning(f"Could not read audit trail: {e}")
        
        # Swarm Uptime - from health monitor state
        health_file = HIVE_MIND / "health_status.json"
        if health_file.exists():
            try:
                with open(health_file) as f:
                    data = json.load(f)
                    # Calculate uptime from component health
                    components = data.get("components", {})
                    healthy = sum(1 for c in components.values() if c.get("status") == "healthy")
                    total = len(components) if components else 1
                    self.metrics["swarm_uptime"].value = round((healthy / total) * 100, 1)
            except Exception:
                pass
        else:
            # Default to healthy if no monitoring data
            self.metrics["swarm_uptime"].value = 99.0
        
        # Queue Health - from swarm coordination
        swarm_state = HIVE_MIND / "swarm_state.json"
        if swarm_state.exists():
            try:
                with open(swarm_state) as f:
                    data = json.load(f)
                    queue_depth = data.get("queue_depth", 0)
                    max_queue = data.get("max_queue", 100)
                    # Lower queue = healthier
                    if max_queue > 0:
                        health_pct = 100 - ((queue_depth / max_queue) * 100)
                        self.metrics["queue_health"].value = round(max(0, health_pct), 1)
            except Exception:
                pass
        else:
            self.metrics["queue_health"].value = 95.0
    
    def get_constraint(self) -> Optional[Constraint]:
        """Get the current constraint (refresh first if stale)."""
        if not self._last_refresh or (datetime.now(timezone.utc) - self._last_refresh).seconds > 3600:
            self.refresh()
        return self.constraint
    
    def get_summary(self) -> Dict[str, Any]:
        """Get the full scorecard summary."""
        by_category = defaultdict(list)
        for metric in self.metrics.values():
            by_category[metric.category.value].append(metric.to_dict())
        
        status_counts = {
            "on_track": sum(1 for m in self.metrics.values() if m.status == MetricStatus.ON_TRACK),
            "at_risk": sum(1 for m in self.metrics.values() if m.status == MetricStatus.AT_RISK),
            "off_track": sum(1 for m in self.metrics.values() if m.status == MetricStatus.OFF_TRACK)
        }
        
        return {
            "scorecard": {
                "metrics_by_category": dict(by_category),
                "status_summary": status_counts,
                "total_metrics": len(self.metrics)
            },
            "constraint": self.constraint.to_dict() if self.constraint else None,
            "last_refresh": self._last_refresh.isoformat() if self._last_refresh else None,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
    
    def get_category_summary(self, category: MetricCategory) -> Dict[str, Any]:
        """Get summary for a specific category."""
        metrics = [m for m in self.metrics.values() if m.category == category]
        
        return {
            "category": category.value,
            "metrics": [m.to_dict() for m in metrics],
            "on_track": sum(1 for m in metrics if m.status == MetricStatus.ON_TRACK),
            "at_risk": sum(1 for m in metrics if m.status == MetricStatus.AT_RISK),
            "off_track": sum(1 for m in metrics if m.status == MetricStatus.OFF_TRACK)
        }
    
    def to_markdown_report(self) -> str:
        """Generate a markdown report (for weekly email/Slack)."""
        lines = [
            "# 📊 Precision Scorecard",
            f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
            ""
        ]
        
        # Constraint section
        if self.constraint:
            lines.extend([
                "## ⚠️ Your #1 Constraint",
                "",
                f"**{self.constraint.metric_name}** is {self.constraint.gap_percentage:+.1f}% from target",
                "",
                f"- **Current:** {self.constraint.current_value} (Target: {self.constraint.target_value})",
                f"- **Why:** {self.constraint.root_cause}",
                f"- **Fix:** {self.constraint.recommended_action}",
                f"- **Owner:** @{self.constraint.owner}",
                ""
            ])
        else:
            lines.extend([
                "## ✅ All Systems On Track",
                "",
                "No constraints detected. All metrics meeting targets.",
                ""
            ])
        
        # Category summaries
        for category in MetricCategory:
            cat_metrics = [m for m in self.metrics.values() if m.category == category]
            
            on_track = sum(1 for m in cat_metrics if m.status == MetricStatus.ON_TRACK)
            lines.append(f"### {category.value.upper()} ({on_track}/{len(cat_metrics)} on track)")
            lines.append("")
            lines.append("| Metric | Value | Target | Status |")
            lines.append("|--------|-------|--------|--------|")
            
            for m in cat_metrics:
                lines.append(f"| {m.name} | {m.value}{m.unit} | {m.target}{m.unit} | {m.status_emoji} |")
            
            lines.append("")
        
        return "\n".join(lines)


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_scorecard_instance: Optional[PrecisionScorecard] = None


def get_scorecard() -> PrecisionScorecard:
    """Get the singleton scorecard instance."""
    global _scorecard_instance
    if _scorecard_instance is None:
        _scorecard_instance = PrecisionScorecard()
    return _scorecard_instance


def reset_scorecard():
    """Reset the singleton (for testing)."""
    global _scorecard_instance
    _scorecard_instance = None


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Precision Scorecard - Revenue Operations")
    parser.add_argument("--refresh", action="store_true", help="Refresh all metrics")
    parser.add_argument("--constraint", action="store_true", help="Show current constraint")
    parser.add_argument("--summary", action="store_true", help="Show full summary")
    parser.add_argument("--markdown", action="store_true", help="Generate markdown report")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    scorecard = get_scorecard()
    
    if args.refresh or not scorecard._last_refresh:
        scorecard.refresh()
    
    if args.constraint:
        constraint = scorecard.get_constraint()
        if constraint:
            if args.json:
                print(json.dumps(constraint.to_dict(), indent=2))
            else:
                print(f"\n⚠️  CONSTRAINT: {constraint.metric_name}")
                print(f"   Current: {constraint.current_value} (Target: {constraint.target_value})")
                print(f"   Gap: {constraint.gap_percentage:+.1f}%")
                print(f"\n   Why: {constraint.root_cause}")
                print(f"   Fix: {constraint.recommended_action}")
                print(f"   Owner: {constraint.owner}\n")
        else:
            print("✅ No constraints detected. All metrics on track!")
    
    elif args.summary:
        summary = scorecard.get_summary()
        if args.json:
            print(json.dumps(summary, indent=2))
        else:
            print(scorecard.to_markdown_report())
    
    elif args.markdown:
        print(scorecard.to_markdown_report())
    
    else:
        # Default: show constraint
        constraint = scorecard.get_constraint()
        if constraint:
            print(f"\n⚠️  {constraint.metric_name}: {constraint.root_cause}")
            print(f"   → {constraint.recommended_action}\n")
        else:
            print("✅ All metrics on track!")
