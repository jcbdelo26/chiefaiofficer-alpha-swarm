#!/usr/bin/env python3
"""
Call Coach - Sales Call Analysis & Coaching
============================================

Tracks and analyzes sales calls to:
- Score call quality
- Identify coaching opportunities
- Track rep performance over time
- Generate improvement recommendations
"""

import os
import json
import logging
from enum import Enum
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("call-coach")


class CallOutcome(Enum):
    BOOKED = "booked"
    COMPLETED = "completed"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"
    QUALIFIED = "qualified"
    DISQUALIFIED = "disqualified"


class CallType(Enum):
    DISCOVERY = "discovery"
    DEMO = "demo"
    FOLLOW_UP = "follow_up"
    CLOSING = "closing"
    ONBOARDING = "onboarding"


# =============================================================================
# SCORING FRAMEWORK
# =============================================================================

CALL_SCORING_CRITERIA = {
    "discovery_depth": {
        "weight": 25,
        "description": "How well did rep uncover pain points and needs?",
        "signals": {
            "excellent": ["multiple pain points identified", "quantified impact", "root cause explored"],
            "good": ["clear pain point", "some context gathered"],
            "poor": ["surface level", "no pain points", "assumptions made"]
        }
    },
    "objection_handling": {
        "weight": 20,
        "description": "How effectively were objections addressed?",
        "signals": {
            "excellent": ["acknowledged concern", "provided evidence", "resolved objection"],
            "good": ["addressed objection", "partial resolution"],
            "poor": ["dismissed objection", "no response", "defensive"]
        }
    },
    "next_steps": {
        "weight": 20,
        "description": "Were clear next steps established?",
        "signals": {
            "excellent": ["specific date/time", "mutual commitment", "follow-up scheduled"],
            "good": ["general agreement", "some commitment"],
            "poor": ["vague ending", "no next steps", "lead went cold"]
        }
    },
    "talk_listen_ratio": {
        "weight": 15,
        "description": "Did rep listen more than talk?",
        "signals": {
            "excellent": ["60%+ listening", "open questions", "active listening cues"],
            "good": ["balanced conversation", "some questions"],
            "poor": ["dominated conversation", "monologue", "interrupted"]
        }
    },
    "value_proposition": {
        "weight": 10,
        "description": "Was value clearly articulated?",
        "signals": {
            "excellent": ["personalized value", "connected to pain", "clear ROI"],
            "good": ["general value stated", "some relevance"],
            "poor": ["generic pitch", "feature dumping", "no value connection"]
        }
    },
    "rapport_building": {
        "weight": 10,
        "description": "Was rapport established?",
        "signals": {
            "excellent": ["personal connection", "mirroring", "genuine interest"],
            "good": ["professional tone", "pleasant interaction"],
            "poor": ["awkward", "rushed", "transactional only"]
        }
    },
}


@dataclass
class CallScore:
    call_id: str
    overall_score: float  # 0-100
    category_scores: Dict[str, float]
    strengths: List[str]
    improvements: List[str]
    coaching_points: List[str]
    
    def to_dict(self) -> Dict:
        return {
            "call_id": self.call_id,
            "overall_score": self.overall_score,
            "category_scores": self.category_scores,
            "strengths": self.strengths,
            "improvements": self.improvements,
            "coaching_points": self.coaching_points,
        }


@dataclass
class CallRecord:
    id: str
    lead_id: str
    rep_id: str
    call_type: CallType
    outcome: CallOutcome
    scheduled_at: str
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    duration_minutes: Optional[int] = None
    notes: str = ""
    key_points: List[str] = field(default_factory=list)
    objections_raised: List[str] = field(default_factory=list)
    next_steps: str = ""
    score: Optional[CallScore] = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "lead_id": self.lead_id,
            "rep_id": self.rep_id,
            "call_type": self.call_type.value,
            "outcome": self.outcome.value,
            "scheduled_at": self.scheduled_at,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_minutes": self.duration_minutes,
            "notes": self.notes,
            "key_points": self.key_points,
            "objections_raised": self.objections_raised,
            "next_steps": self.next_steps,
            "score": self.score.to_dict() if self.score else None,
        }


# =============================================================================
# CALL TRACKER
# =============================================================================

class CallTracker:
    """Track and store call records."""
    
    def __init__(self, storage_path: str = ".hive-mind/calls"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._calls: Dict[str, CallRecord] = {}
        self._load()
    
    def _load(self):
        index_file = self.storage_path / "index.json"
        if index_file.exists():
            with open(index_file) as f:
                data = json.load(f)
                for call_id, call_data in data.items():
                    self._calls[call_id] = self._dict_to_record(call_data)
    
    def _save(self):
        index_file = self.storage_path / "index.json"
        with open(index_file, 'w') as f:
            data = {call_id: call.to_dict() for call_id, call in self._calls.items()}
            json.dump(data, f, indent=2)
    
    def _dict_to_record(self, data: Dict) -> CallRecord:
        score = None
        if data.get("score"):
            score = CallScore(**data["score"])
        
        return CallRecord(
            id=data["id"],
            lead_id=data["lead_id"],
            rep_id=data["rep_id"],
            call_type=CallType(data["call_type"]),
            outcome=CallOutcome(data["outcome"]),
            scheduled_at=data["scheduled_at"],
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
            duration_minutes=data.get("duration_minutes"),
            notes=data.get("notes", ""),
            key_points=data.get("key_points", []),
            objections_raised=data.get("objections_raised", []),
            next_steps=data.get("next_steps", ""),
            score=score,
        )
    
    def record_call(self, call: CallRecord) -> str:
        self._calls[call.id] = call
        self._save()
        return call.id
    
    def update_call(self, call_id: str, updates: Dict) -> bool:
        if call_id not in self._calls:
            return False
        
        call = self._calls[call_id]
        for key, value in updates.items():
            if hasattr(call, key):
                setattr(call, key, value)
        
        self._save()
        return True
    
    def get_call(self, call_id: str) -> Optional[CallRecord]:
        return self._calls.get(call_id)
    
    def get_calls_by_rep(self, rep_id: str, days: int = 30) -> List[CallRecord]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return [
            call for call in self._calls.values()
            if call.rep_id == rep_id and call.scheduled_at > cutoff
        ]
    
    def get_calls_by_lead(self, lead_id: str) -> List[CallRecord]:
        return [call for call in self._calls.values() if call.lead_id == lead_id]


# =============================================================================
# CALL SCORER
# =============================================================================

class CallScorer:
    """Score calls based on quality criteria."""
    
    def score_call(
        self,
        call: CallRecord,
        category_ratings: Dict[str, str] = None  # category -> "excellent", "good", "poor"
    ) -> CallScore:
        """Score a call based on provided ratings or auto-analysis."""
        
        category_scores = {}
        total_score = 0
        total_weight = 0
        strengths = []
        improvements = []
        coaching_points = []
        
        # If ratings provided, use them
        if category_ratings:
            for category, criteria in CALL_SCORING_CRITERIA.items():
                rating = category_ratings.get(category, "good")
                
                # Convert rating to score
                if rating == "excellent":
                    score = 100
                    strengths.append(f"{category}: {criteria['description']}")
                elif rating == "good":
                    score = 70
                elif rating == "poor":
                    score = 30
                    improvements.append(f"Improve {category}: {criteria['description']}")
                    coaching_points.append(self._get_coaching_point(category, rating))
                else:
                    score = 50
                
                category_scores[category] = score
                total_score += score * criteria["weight"]
                total_weight += criteria["weight"]
        else:
            # Auto-analyze from notes
            category_scores, strengths, improvements, coaching_points = self._auto_analyze(call)
            total_score = sum(
                score * CALL_SCORING_CRITERIA[cat]["weight"] 
                for cat, score in category_scores.items()
            )
            total_weight = sum(c["weight"] for c in CALL_SCORING_CRITERIA.values())
        
        overall_score = total_score / total_weight if total_weight > 0 else 0
        
        # Add outcome-based adjustments
        outcome_adjustments = {
            CallOutcome.COMPLETED: 0,
            CallOutcome.QUALIFIED: 10,
            CallOutcome.BOOKED: 5,
            CallOutcome.NO_SHOW: -10,
            CallOutcome.DISQUALIFIED: -5,
        }
        overall_score += outcome_adjustments.get(call.outcome, 0)
        overall_score = max(0, min(100, overall_score))
        
        return CallScore(
            call_id=call.id,
            overall_score=round(overall_score, 1),
            category_scores=category_scores,
            strengths=strengths,
            improvements=improvements,
            coaching_points=coaching_points,
        )
    
    def _auto_analyze(self, call: CallRecord) -> Tuple[Dict, List, List, List]:
        """Auto-analyze call from notes."""
        notes_lower = call.notes.lower()
        category_scores = {}
        strengths = []
        improvements = []
        coaching_points = []
        
        # Simple keyword-based analysis
        for category, criteria in CALL_SCORING_CRITERIA.items():
            score = 50  # Default
            
            # Check for positive signals
            excellent_signals = criteria["signals"]["excellent"]
            good_signals = criteria["signals"]["good"]
            poor_signals = criteria["signals"]["poor"]
            
            has_excellent = any(s.lower() in notes_lower for s in excellent_signals)
            has_poor = any(s.lower() in notes_lower for s in poor_signals)
            
            if has_excellent:
                score = 90
                strengths.append(f"Strong {category.replace('_', ' ')}")
            elif has_poor:
                score = 30
                improvements.append(f"Work on {category.replace('_', ' ')}")
                coaching_points.append(self._get_coaching_point(category, "poor"))
            else:
                score = 60
            
            category_scores[category] = score
        
        # Check objections
        if call.objections_raised:
            if "resolved" in notes_lower or "addressed" in notes_lower:
                category_scores["objection_handling"] = max(category_scores.get("objection_handling", 0), 80)
            else:
                category_scores["objection_handling"] = min(category_scores.get("objection_handling", 100), 40)
                coaching_points.append("Practice objection handling frameworks")
        
        # Check next steps
        if call.next_steps and len(call.next_steps) > 20:
            category_scores["next_steps"] = max(category_scores.get("next_steps", 0), 80)
        elif not call.next_steps:
            category_scores["next_steps"] = 30
            coaching_points.append("Always establish clear next steps before ending call")
        
        return category_scores, strengths, improvements, coaching_points
    
    def _get_coaching_point(self, category: str, rating: str) -> str:
        """Get specific coaching point for a category."""
        coaching_tips = {
            "discovery_depth": {
                "poor": "Use the 5 Whys technique to dig deeper into pain points",
                "good": "Try to quantify the impact of problems (time, money, resources)"
            },
            "objection_handling": {
                "poor": "Use the Feel-Felt-Found framework for objections",
                "good": "Prepare case studies for common objections"
            },
            "next_steps": {
                "poor": "Always schedule the next meeting before ending the current one",
                "good": "Be specific: date, time, and agenda for next touchpoint"
            },
            "talk_listen_ratio": {
                "poor": "Practice asking open-ended questions, then pause",
                "good": "Aim for 60% listening, 40% talking"
            },
            "value_proposition": {
                "poor": "Connect features to the specific pain points discussed",
                "good": "Use the prospect's own words when describing value"
            },
            "rapport_building": {
                "poor": "Research the prospect before the call, find common ground",
                "good": "Use their name and reference earlier conversation points"
            },
        }
        return coaching_tips.get(category, {}).get(rating, f"Focus on improving {category}")


# =============================================================================
# PERFORMANCE ANALYTICS
# =============================================================================

class PerformanceAnalytics:
    """Analyze rep performance over time."""
    
    def __init__(self, tracker: CallTracker):
        self.tracker = tracker
    
    def get_rep_stats(self, rep_id: str, days: int = 30) -> Dict:
        """Get performance stats for a rep."""
        calls = self.tracker.get_calls_by_rep(rep_id, days)
        
        if not calls:
            return {"error": "No calls found"}
        
        # Calculate metrics
        total_calls = len(calls)
        completed_calls = [c for c in calls if c.outcome == CallOutcome.COMPLETED]
        no_shows = [c for c in calls if c.outcome == CallOutcome.NO_SHOW]
        qualified = [c for c in calls if c.outcome == CallOutcome.QUALIFIED]
        
        # Score stats
        scored_calls = [c for c in calls if c.score]
        avg_score = sum(c.score.overall_score for c in scored_calls) / len(scored_calls) if scored_calls else 0
        
        # Category averages
        category_avgs = {}
        for category in CALL_SCORING_CRITERIA.keys():
            scores = [c.score.category_scores.get(category, 0) for c in scored_calls if c.score]
            category_avgs[category] = sum(scores) / len(scores) if scores else 0
        
        # Find weakest areas
        weakest = sorted(category_avgs.items(), key=lambda x: x[1])[:2]
        
        return {
            "rep_id": rep_id,
            "period_days": days,
            "total_calls": total_calls,
            "completed": len(completed_calls),
            "no_show_rate": len(no_shows) / total_calls if total_calls else 0,
            "qualification_rate": len(qualified) / len(completed_calls) if completed_calls else 0,
            "average_score": round(avg_score, 1),
            "category_averages": {k: round(v, 1) for k, v in category_avgs.items()},
            "areas_to_improve": [w[0] for w in weakest],
            "coaching_focus": self._get_coaching_focus(weakest),
        }
    
    def _get_coaching_focus(self, weakest_areas: List[Tuple[str, float]]) -> List[str]:
        """Generate coaching focus based on weakest areas."""
        focus = []
        for area, score in weakest_areas:
            if score < 50:
                focus.append(f"Priority coaching needed on {area.replace('_', ' ')}")
            elif score < 70:
                focus.append(f"Continue developing {area.replace('_', ' ')}")
        return focus
    
    def compare_reps(self, rep_ids: List[str], days: int = 30) -> Dict:
        """Compare performance across reps."""
        comparison = {}
        for rep_id in rep_ids:
            comparison[rep_id] = self.get_rep_stats(rep_id, days)
        
        # Rank by average score
        ranked = sorted(
            [(rep_id, stats.get("average_score", 0)) for rep_id, stats in comparison.items()],
            key=lambda x: x[1],
            reverse=True
        )
        
        return {
            "period_days": days,
            "rankings": [{"rep_id": r[0], "avg_score": r[1]} for r in ranked],
            "individual_stats": comparison,
        }


# =============================================================================
# CALL COACH (Main Class)
# =============================================================================

class CallCoach:
    """Main call coaching system."""
    
    def __init__(self):
        self.tracker = CallTracker()
        self.scorer = CallScorer()
        self.analytics = PerformanceAnalytics(self.tracker)
    
    def log_call(
        self,
        lead_id: str,
        rep_id: str,
        call_type: CallType,
        outcome: CallOutcome,
        duration_minutes: int = None,
        notes: str = "",
        key_points: List[str] = None,
        objections: List[str] = None,
        next_steps: str = "",
    ) -> str:
        """Log a completed call."""
        import hashlib
        call_id = hashlib.md5(
            f"{lead_id}:{rep_id}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:12]
        
        call = CallRecord(
            id=call_id,
            lead_id=lead_id,
            rep_id=rep_id,
            call_type=call_type,
            outcome=outcome,
            scheduled_at=datetime.now(timezone.utc).isoformat(),
            ended_at=datetime.now(timezone.utc).isoformat(),
            duration_minutes=duration_minutes,
            notes=notes,
            key_points=key_points or [],
            objections_raised=objections or [],
            next_steps=next_steps,
        )
        
        # Auto-score the call
        call.score = self.scorer.score_call(call)
        
        self.tracker.record_call(call)
        
        logger.info(f"Call {call_id} logged: {outcome.value}, score: {call.score.overall_score}")
        
        return call_id
    
    def get_coaching_feedback(self, call_id: str) -> Dict:
        """Get coaching feedback for a specific call."""
        call = self.tracker.get_call(call_id)
        if not call:
            return {"error": "Call not found"}
        
        if not call.score:
            call.score = self.scorer.score_call(call)
            self.tracker.update_call(call_id, {"score": call.score})
        
        return {
            "call_id": call_id,
            "overall_score": call.score.overall_score,
            "grade": self._score_to_grade(call.score.overall_score),
            "strengths": call.score.strengths,
            "areas_to_improve": call.score.improvements,
            "coaching_points": call.score.coaching_points,
            "category_breakdown": call.score.category_scores,
        }
    
    def _score_to_grade(self, score: float) -> str:
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"
    
    def get_rep_performance(self, rep_id: str, days: int = 30) -> Dict:
        """Get performance summary for a rep."""
        return self.analytics.get_rep_stats(rep_id, days)
    
    def get_team_leaderboard(self, rep_ids: List[str], days: int = 30) -> Dict:
        """Get team performance comparison."""
        return self.analytics.compare_reps(rep_ids, days)


# =============================================================================
# DEMO
# =============================================================================

def demo():
    print("=" * 60)
    print("Call Coach Demo")
    print("=" * 60)
    
    coach = CallCoach()
    
    # Log some sample calls
    print("\n[1] Logging sample calls...")
    
    call_id = coach.log_call(
        lead_id="lead_001",
        rep_id="chris",
        call_type=CallType.DISCOVERY,
        outcome=CallOutcome.QUALIFIED,
        duration_minutes=30,
        notes="Great discovery call. Uncovered multiple pain points around manual data entry. Prospect mentioned spending 20 hours/week on admin. Next steps: demo scheduled for next week.",
        key_points=["Manual data entry pain", "20 hours/week wasted", "Growing team"],
        objections=["timing concerns"],
        next_steps="Demo scheduled for Tuesday 2pm"
    )
    
    print(f"    Logged call: {call_id}")
    
    # Get coaching feedback
    print("\n[2] Getting coaching feedback...")
    feedback = coach.get_coaching_feedback(call_id)
    print(f"    Score: {feedback['overall_score']} ({feedback['grade']})")
    print(f"    Strengths: {feedback['strengths'][:2]}")
    print(f"    Improve: {feedback['areas_to_improve'][:2]}")
    
    # Get rep performance
    print("\n[3] Rep Performance...")
    perf = coach.get_rep_performance("chris", days=30)
    if "error" not in perf:
        print(f"    Total Calls: {perf['total_calls']}")
        print(f"    Avg Score: {perf['average_score']}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    demo()
