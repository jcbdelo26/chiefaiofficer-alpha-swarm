#!/usr/bin/env python3
"""
Confidence-Based Replanning - System Two Logic
===============================================
Implements Vercel's Lead Agent pattern of confidence scoring and 
automatic replanning when confidence falls below threshold.

Key Concepts:
- Every agent decision includes a confidence score (0.0-1.0)
- If confidence < threshold (default 0.85), trigger replan loop
- Replan loop gathers additional context before retrying
- Prevents low-confidence actions from executing

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                CONFIDENCE-BASED REPLANNING                   │
    │                                                              │
    │  Agent Decision                                              │
    │       │                                                      │
    │       ▼                                                      │
    │  ┌─────────────┐                                            │
    │  │ Confidence  │                                            │
    │  │   Check     │                                            │
    │  └──────┬──────┘                                            │
    │         │                                                    │
    │    ┌────┴────┐                                              │
    │    │         │                                              │
    │   ≥0.85    <0.85                                            │
    │    │         │                                              │
    │    ▼         ▼                                              │
    │ EXECUTE   REPLAN                                            │
    │            │                                                │
    │            ▼                                                │
    │   ┌────────────────┐                                        │
    │   │ Gather Context │ (Research, Enrichment, Oracle)         │
    │   └───────┬────────┘                                        │
    │           │                                                 │
    │           ▼                                                 │
    │   ┌────────────────┐                                        │
    │   │ Retry Decision │                                        │
    │   └───────┬────────┘                                        │
    │           │                                                 │
    │       (loop max 3x)                                         │
    └─────────────────────────────────────────────────────────────┘

Based on Vercel Lead Agent's System Two reasoning pattern.
"""

import json
import logging
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable, TypeVar, Generic, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from abc import ABC, abstractmethod

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("confidence_replanning")

T = TypeVar('T')


class ConfidenceLevel(Enum):
    """Confidence level categories."""
    HIGH = "high"       # >= 0.85 - Execute immediately
    MEDIUM = "medium"   # 0.70-0.85 - Execute with caution
    LOW = "low"         # 0.50-0.70 - Consider replanning
    VERY_LOW = "very_low"  # < 0.50 - Must replan


@dataclass
class ConfidenceResult(Generic[T]):
    """
    Result wrapper that includes confidence scoring.
    
    This is the structured output format for all agent decisions,
    inspired by Vercel's generateObject pattern.
    """
    value: T
    confidence: float  # 0.0 - 1.0
    reason: str        # Explanation for the decision
    factors: Dict[str, float] = field(default_factory=dict)  # Contributing factors
    needs_replan: bool = False
    replan_suggestions: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    @property
    def confidence_level(self) -> ConfidenceLevel:
        """Get categorical confidence level."""
        if self.confidence >= 0.85:
            return ConfidenceLevel.HIGH
        elif self.confidence >= 0.70:
            return ConfidenceLevel.MEDIUM
        elif self.confidence >= 0.50:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value if isinstance(self.value, dict) else {"result": self.value},
            "confidence": self.confidence,
            "confidence_level": self.confidence_level.value,
            "reason": self.reason,
            "factors": self.factors,
            "needs_replan": self.needs_replan,
            "replan_suggestions": self.replan_suggestions,
            "timestamp": self.timestamp
        }


@dataclass
class QualificationResult:
    """
    Structured output for SEGMENTOR qualification decisions.
    
    This replaces the simple tier assignment with a full qualification
    result including confidence and reasoning (like Vercel's generateObject).
    """
    category: str  # "HOT_LEAD", "WARM_LEAD", "NURTURE", "UNQUALIFIED", etc.
    tier: str      # "tier_1", "tier_2", "tier_3", "tier_4"
    icp_score: int
    confidence: float
    reason: str
    next_action: str  # Recommended next step
    urgency: int = 3  # 1=highest, 5=lowest
    score_breakdown: Dict[str, int] = field(default_factory=dict)
    enrichment_gaps: List[str] = field(default_factory=list)
    personalization_hooks: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @property
    def needs_replan(self) -> bool:
        """Check if confidence is too low for execution."""
        return self.confidence < 0.85
    
    @property
    def is_actionable(self) -> bool:
        """Check if lead is ready for outreach."""
        return self.category in ("HOT_LEAD", "WARM_LEAD") and self.confidence >= 0.70


class ReplanContext(ABC):
    """Abstract base for replan context gatherers."""
    
    @abstractmethod
    async def gather_additional_context(
        self, 
        lead: Dict[str, Any],
        current_result: ConfidenceResult
    ) -> Dict[str, Any]:
        """Gather additional context to improve confidence."""
        pass


class DefaultReplanContext(ReplanContext):
    """Default context gatherer that suggests enrichment."""
    
    async def gather_additional_context(
        self, 
        lead: Dict[str, Any],
        current_result: ConfidenceResult
    ) -> Dict[str, Any]:
        """Identify missing data that would improve confidence."""
        gaps = []
        suggestions = []
        
        # Check for missing enrichment data
        if not lead.get("email"):
            gaps.append("email")
            suggestions.append("Run email enrichment via Clay")
        
        if not lead.get("company", {}).get("employee_count"):
            gaps.append("company_size")
            suggestions.append("Enrich company data for size verification")
        
        if not lead.get("company", {}).get("industry"):
            gaps.append("industry")
            suggestions.append("Identify industry for ICP matching")
        
        if not lead.get("intent", {}):
            gaps.append("intent_signals")
            suggestions.append("Check for website visits or content engagement")
        
        # Check confidence factors for low scores
        for factor, score in current_result.factors.items():
            if score < 0.5:
                gaps.append(f"low_{factor}")
                suggestions.append(f"Improve {factor} data quality")
        
        return {
            "gaps": gaps,
            "suggestions": suggestions,
            "lead_id": lead.get("lead_id", lead.get("linkedin_url", "unknown")),
            "current_confidence": current_result.confidence
        }


class ConfidenceReplanEngine:
    """
    Engine for confidence-based replanning.
    
    When an agent decision has low confidence, this engine:
    1. Identifies what additional context is needed
    2. Gathers that context (via enrichment, research, etc.)
    3. Retries the decision with improved context
    4. Repeats up to max_replan_attempts
    """
    
    DEFAULT_THRESHOLD = 0.85
    MAX_REPLAN_ATTEMPTS = 3
    
    def __init__(
        self,
        confidence_threshold: float = DEFAULT_THRESHOLD,
        max_attempts: int = MAX_REPLAN_ATTEMPTS,
        context_gatherer: Optional[ReplanContext] = None
    ):
        self.confidence_threshold = confidence_threshold
        self.max_attempts = max_attempts
        self.context_gatherer = context_gatherer or DefaultReplanContext()
        self._replan_history: List[Dict[str, Any]] = []
    
    async def execute_with_confidence(
        self,
        decision_fn: Callable[..., ConfidenceResult],
        input_data: Dict[str, Any],
        context_enhancer: Optional[Callable] = None,
        force_execute: bool = False
    ) -> Tuple[ConfidenceResult, List[Dict[str, Any]]]:
        """
        Execute a decision function with confidence-based replanning.
        
        Args:
            decision_fn: Function that returns a ConfidenceResult
            input_data: Data to pass to the decision function
            context_enhancer: Optional function to enhance context between attempts
            force_execute: If True, execute even with low confidence
            
        Returns:
            Tuple of (final_result, replan_history)
        """
        attempts = []
        current_data = input_data.copy()
        
        for attempt in range(self.max_attempts):
            # Execute decision
            if asyncio.iscoroutinefunction(decision_fn):
                result = await decision_fn(current_data)
            else:
                result = decision_fn(current_data)
            
            # Record attempt
            attempt_record = {
                "attempt": attempt + 1,
                "confidence": result.confidence,
                "confidence_level": result.confidence_level.value,
                "reason": result.reason,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            attempts.append(attempt_record)
            
            # Check if confidence is acceptable
            if result.confidence >= self.confidence_threshold:
                logger.info(
                    f"Decision accepted with confidence {result.confidence:.2f} "
                    f"(threshold: {self.confidence_threshold})"
                )
                return result, attempts
            
            # Force execute on last attempt or if requested
            if attempt == self.max_attempts - 1 or force_execute:
                logger.warning(
                    f"Executing with low confidence {result.confidence:.2f} "
                    f"after {attempt + 1} attempts"
                )
                result.needs_replan = True
                return result, attempts
            
            # Gather additional context for replan
            logger.info(
                f"Confidence {result.confidence:.2f} below threshold "
                f"{self.confidence_threshold}, gathering additional context..."
            )
            
            additional_context = await self.context_gatherer.gather_additional_context(
                current_data, result
            )
            
            # Enhance context if enhancer provided
            if context_enhancer:
                if asyncio.iscoroutinefunction(context_enhancer):
                    enhanced = await context_enhancer(current_data, additional_context)
                else:
                    enhanced = context_enhancer(current_data, additional_context)
                current_data.update(enhanced)
            else:
                current_data["_replan_context"] = additional_context
                current_data["_replan_attempt"] = attempt + 1
            
            attempt_record["replan_context"] = additional_context
        
        # Should not reach here, but return last result
        return result, attempts
    
    def calculate_qualification_confidence(
        self,
        lead: Dict[str, Any],
        icp_score: int,
        score_breakdown: Dict[str, int]
    ) -> Tuple[float, Dict[str, float], str]:
        """
        Calculate confidence score for a lead qualification decision.
        
        This is specifically for SEGMENTOR to determine how confident
        we are in the ICP score and tier assignment.
        
        Returns:
            Tuple of (confidence, factors, reason)
        """
        factors = {}
        confidence = 0.0
        reasons = []
        
        # Factor 1: Data completeness (30%)
        required_fields = ["title", "company", "email"]
        optional_fields = ["company.employee_count", "company.industry", "intent"]
        
        required_present = sum(1 for f in required_fields if self._has_field(lead, f))
        optional_present = sum(1 for f in optional_fields if self._has_field(lead, f))
        
        data_completeness = (required_present / len(required_fields) * 0.7 + 
                            optional_present / len(optional_fields) * 0.3)
        factors["data_completeness"] = data_completeness
        confidence += data_completeness * 0.30
        
        if data_completeness < 0.5:
            reasons.append("Missing critical lead data")
        
        # Factor 2: Score distribution (25%)
        # High confidence if score components are well-distributed
        if score_breakdown:
            non_zero_components = sum(1 for v in score_breakdown.values() if isinstance(v, int) and v > 0)
            total_components = 5  # company_size, title, industry, tech, intent
            distribution_score = min(1.0, non_zero_components / total_components)
        else:
            distribution_score = 0.3
        
        factors["score_distribution"] = distribution_score
        confidence += distribution_score * 0.25
        
        if distribution_score < 0.5:
            reasons.append("ICP score relies on few data points")
        
        # Factor 3: Tier clarity (20%)
        # High confidence if score is clearly in a tier (not on boundary)
        tier_boundaries = [40, 60, 80]
        min_distance = min(abs(icp_score - b) for b in tier_boundaries)
        tier_clarity = min(1.0, min_distance / 10)  # Max confidence at 10+ points from boundary
        
        factors["tier_clarity"] = tier_clarity
        confidence += tier_clarity * 0.20
        
        if tier_clarity < 0.5:
            reasons.append(f"Score {icp_score} is near tier boundary")
        
        # Factor 4: Intent signal strength (15%)
        intent = lead.get("intent", {})
        intent_strength = 0.0
        if intent.get("demo_requested"):
            intent_strength = 1.0
        elif intent.get("pricing_page_visits", 0) > 0:
            intent_strength = 0.8
        elif intent.get("content_downloads", 0) > 0:
            intent_strength = 0.6
        elif intent.get("website_visits", 0) > 0:
            intent_strength = 0.4
        else:
            intent_strength = 0.2
        
        factors["intent_strength"] = intent_strength
        confidence += intent_strength * 0.15
        
        if intent_strength < 0.3:
            reasons.append("No intent signals detected")
        
        # Factor 5: Source reliability (10%)
        source_type = lead.get("source_type", "unknown")
        source_reliability = {
            "demo_requester": 1.0,
            "content_downloader": 0.8,
            "website_visitor": 0.7,
            "event_attendee": 0.6,
            "competitor_follower": 0.5,
            "post_commenter": 0.5,
            "group_member": 0.4,
            "unknown": 0.3
        }.get(source_type, 0.3)
        
        factors["source_reliability"] = source_reliability
        confidence += source_reliability * 0.10
        
        # Generate reason
        if not reasons:
            reason = f"High-quality lead data with clear tier assignment (ICP: {icp_score})"
        else:
            reason = "; ".join(reasons)
        
        return round(confidence, 3), factors, reason
    
    def _has_field(self, data: Dict[str, Any], field_path: str) -> bool:
        """Check if a field exists and has a value."""
        parts = field_path.split(".")
        current = data
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return False
        
        # Check if the value is meaningful
        if current is None:
            return False
        if isinstance(current, str) and not current.strip():
            return False
        if isinstance(current, (list, dict)) and not current:
            return False
        
        return True
    
    def create_qualification_result(
        self,
        lead: Dict[str, Any],
        icp_score: int,
        tier: str,
        score_breakdown: Dict[str, int],
        disqualification_reason: Optional[str] = None
    ) -> QualificationResult:
        """
        Create a full qualification result with confidence scoring.
        
        This is the main method for SEGMENTOR to use when classifying leads.
        """
        # Calculate confidence
        confidence, factors, reason = self.calculate_qualification_confidence(
            lead, icp_score, score_breakdown
        )
        
        # Determine category
        if disqualification_reason:
            category = "UNQUALIFIED"
            next_action = "Archive or mark as disqualified"
            urgency = 5
        elif tier == "tier_1":
            category = "HOT_LEAD"
            next_action = "Immediate personalized outreach"
            urgency = 1
        elif tier == "tier_2":
            category = "WARM_LEAD"
            next_action = "Prioritized campaign inclusion"
            urgency = 2
        elif tier == "tier_3":
            category = "NURTURE"
            next_action = "Add to nurture sequence"
            urgency = 3
        else:
            category = "MONITOR"
            next_action = "Monitor for intent signals"
            urgency = 4
        
        # Identify enrichment gaps
        enrichment_gaps = []
        if factors.get("data_completeness", 0) < 0.7:
            if not lead.get("email"):
                enrichment_gaps.append("email")
            if not lead.get("company", {}).get("employee_count"):
                enrichment_gaps.append("company_size")
            if not lead.get("company", {}).get("industry"):
                enrichment_gaps.append("industry")
        
        if factors.get("intent_strength", 0) < 0.3:
            enrichment_gaps.append("intent_signals")
        
        # Identify personalization hooks
        personalization_hooks = []
        source_type = lead.get("source_type", "")
        if source_type == "competitor_follower":
            personalization_hooks.append("competitor_displacement")
        if source_type == "event_attendee":
            personalization_hooks.append("event_reference")
        if lead.get("company", {}).get("technologies"):
            personalization_hooks.append("tech_stack_mention")
        if icp_score >= 80:
            personalization_hooks.append("high_priority_treatment")
        
        return QualificationResult(
            category=category,
            tier=tier,
            icp_score=icp_score,
            confidence=confidence,
            reason=reason,
            next_action=next_action,
            urgency=urgency,
            score_breakdown=score_breakdown,
            enrichment_gaps=enrichment_gaps,
            personalization_hooks=personalization_hooks
        )


# =============================================================================
# ENHANCED SEGMENTOR INTEGRATION
# =============================================================================

class ConfidenceAwareSegmentor:
    """
    Enhanced segmentor with confidence-based replanning.
    
    Wraps the existing LeadSegmentor to add System Two logic:
    - Confidence scoring on every qualification
    - Automatic replan when confidence < threshold
    - Structured output with reasoning
    """
    
    def __init__(
        self,
        confidence_threshold: float = 0.85,
        max_replan_attempts: int = 3
    ):
        self.replan_engine = ConfidenceReplanEngine(
            confidence_threshold=confidence_threshold,
            max_attempts=max_replan_attempts
        )
    
    def qualify_lead(
        self,
        lead: Dict[str, Any],
        icp_score: int,
        tier: str,
        score_breakdown: Dict[str, int],
        disqualification_reason: Optional[str] = None
    ) -> QualificationResult:
        """
        Qualify a lead with confidence scoring.
        
        Returns a full QualificationResult with:
        - Category (HOT_LEAD, WARM_LEAD, NURTURE, UNQUALIFIED)
        - Confidence score
        - Reason for the decision
        - Recommended next action
        - Enrichment gaps to address
        """
        return self.replan_engine.create_qualification_result(
            lead=lead,
            icp_score=icp_score,
            tier=tier,
            score_breakdown=score_breakdown,
            disqualification_reason=disqualification_reason
        )
    
    async def qualify_with_replan(
        self,
        lead: Dict[str, Any],
        scoring_fn: Callable[[Dict[str, Any]], Tuple[int, Dict[str, int], Optional[str]]],
        tier_fn: Callable[[int], str],
        context_enhancer: Optional[Callable] = None
    ) -> Tuple[QualificationResult, List[Dict[str, Any]]]:
        """
        Qualify a lead with automatic replanning if confidence is low.
        
        Args:
            lead: Lead data
            scoring_fn: Function to calculate ICP score (returns score, breakdown, dq_reason)
            tier_fn: Function to get tier from score
            context_enhancer: Optional function to improve lead data between attempts
            
        Returns:
            Tuple of (QualificationResult, replan_history)
        """
        async def decision_fn(data: Dict[str, Any]) -> ConfidenceResult:
            icp_score, breakdown, dq_reason = scoring_fn(data)
            tier = tier_fn(icp_score)
            
            qual_result = self.qualify_lead(
                lead=data,
                icp_score=icp_score,
                tier=tier,
                score_breakdown=breakdown,
                disqualification_reason=dq_reason
            )
            
            return ConfidenceResult(
                value=qual_result,
                confidence=qual_result.confidence,
                reason=qual_result.reason,
                factors={
                    "icp_score": icp_score / 100,
                    "tier": {"tier_1": 1.0, "tier_2": 0.7, "tier_3": 0.4, "tier_4": 0.2}.get(tier, 0.2)
                }
            )
        
        result, history = await self.replan_engine.execute_with_confidence(
            decision_fn=decision_fn,
            input_data=lead,
            context_enhancer=context_enhancer
        )
        
        return result.value, history


# =============================================================================
# SINGLETON ACCESS
# =============================================================================

_replan_engine_instance: Optional[ConfidenceReplanEngine] = None


def get_replan_engine() -> ConfidenceReplanEngine:
    """Get singleton instance of ConfidenceReplanEngine."""
    global _replan_engine_instance
    if _replan_engine_instance is None:
        _replan_engine_instance = ConfidenceReplanEngine()
    return _replan_engine_instance


# =============================================================================
# DEMO
# =============================================================================

async def demo():
    """Demonstrate confidence-based replanning."""
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    console.print("\n[bold blue]Confidence-Based Replanning Demo[/bold blue]\n")
    
    segmentor = ConfidenceAwareSegmentor(confidence_threshold=0.85)
    
    # Test leads with varying data quality
    test_leads = [
        {
            "lead_id": "lead_001",
            "name": "John Smith",
            "title": "VP of Sales",
            "email": "john.smith@acme.com",
            "company": {
                "name": "Acme Corp",
                "employee_count": 250,
                "industry": "B2B SaaS",
                "technologies": ["Salesforce", "Gong", "HubSpot"]
            },
            "source_type": "competitor_follower",
            "intent": {
                "website_visits": 5,
                "pricing_page_visits": 2,
                "content_downloads": 3
            }
        },
        {
            "lead_id": "lead_002",
            "name": "Jane Doe",
            "title": "Manager",
            "company": {"name": "Unknown Corp"},
            "source_type": "post_liker"
        },
        {
            "lead_id": "lead_003",
            "name": "Bob Wilson",
            "title": "CRO",
            "email": "bob@startup.io",
            "company": {
                "name": "Startup.io",
                "employee_count": 75,
                "industry": "Technology"
            },
            "source_type": "event_attendee"
        }
    ]
    
    for lead in test_leads:
        console.print(f"\n[yellow]Lead: {lead.get('name')}[/yellow]")
        
        # Simulate scoring
        icp_score = 85 if lead.get("company", {}).get("employee_count", 0) > 50 else 45
        if "vp" in lead.get("title", "").lower() or "cro" in lead.get("title", "").lower():
            icp_score += 20
        
        tier = "tier_1" if icp_score >= 80 else "tier_2" if icp_score >= 60 else "tier_3"
        
        breakdown = {
            "company_size": 15 if lead.get("company", {}).get("employee_count", 0) > 50 else 5,
            "title_seniority": 22 if "vp" in lead.get("title", "").lower() else 8,
            "industry_fit": 15 if lead.get("company", {}).get("industry") else 0,
            "tech_stack": 10 if lead.get("company", {}).get("technologies") else 0,
            "intent_signals": 15 if lead.get("intent") else 0
        }
        
        result = segmentor.qualify_lead(
            lead=lead,
            icp_score=icp_score,
            tier=tier,
            score_breakdown=breakdown
        )
        
        table = Table(show_header=True, header_style="bold")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Category", result.category)
        table.add_row("Tier", result.tier)
        table.add_row("ICP Score", str(result.icp_score))
        table.add_row("Confidence", f"{result.confidence:.2f}")
        table.add_row("Needs Replan", "Yes ⚠️" if result.needs_replan else "No ✓")
        table.add_row("Reason", result.reason[:50] + "..." if len(result.reason) > 50 else result.reason)
        table.add_row("Next Action", result.next_action)
        
        if result.enrichment_gaps:
            table.add_row("Enrichment Gaps", ", ".join(result.enrichment_gaps))
        
        console.print(table)
    
    console.print("\n[green]Demo complete![/green]")


if __name__ == "__main__":
    asyncio.run(demo())
