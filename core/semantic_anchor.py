"""
Semantic Anchor Module
======================

Implements semantic anchors for preventing semantic diffusion in the Alpha Swarm.
Based on Dex Horthy's Context Engineering principles.

Semantic anchors are structured metadata that preserve the WHY + WHAT + HOW
context as information flows between agents, preventing meaning loss.

Usage:
    from core.semantic_anchor import SemanticAnchor, LeadWithAnchors, attach_anchor
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum
import json
import hashlib


class AnchorType(Enum):
    """Types of semantic anchors in the system."""
    RESEARCH = "research"           # Why this lead matters (from RPI Research)
    SEGMENTATION = "segmentation"   # Why this tier/score (from SEGMENTOR)
    ENRICHMENT = "enrichment"       # What we learned (from ENRICHER)
    PLANNING = "planning"           # Strategic intent (from RPI Plan)
    CAMPAIGN = "campaign"           # Template rationale (from CRAFTER)
    REVIEW = "review"               # Human decision context (from GATEKEEPER)


@dataclass
class SemanticAnchor:
    """
    A semantic anchor that preserves context between agent handoffs.
    
    Attributes:
        anchor_type: The phase/agent that created this anchor
        why: The rationale/reason behind the decision
        what: The decision or classification made
        how: The method or criteria used
        confidence: Confidence score (0.0 - 1.0)
        created_by: Agent that created this anchor
        created_at: Timestamp of creation
        metadata: Additional structured data
    """
    anchor_type: AnchorType
    why: str
    what: str
    how: str
    confidence: float = 0.8
    created_by: str = "unknown"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "anchor_type": self.anchor_type.value,
            "why": self.why,
            "what": self.what,
            "how": self.how,
            "confidence": self.confidence,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SemanticAnchor":
        """Create from dictionary."""
        return cls(
            anchor_type=AnchorType(data["anchor_type"]),
            why=data["why"],
            what=data["what"],
            how=data["how"],
            confidence=data.get("confidence", 0.8),
            created_by=data.get("created_by", "unknown"),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            metadata=data.get("metadata", {})
        )
    
    def to_narrative(self) -> str:
        """Generate human-readable narrative for AE review."""
        return f"[{self.anchor_type.value.upper()}] {self.what} because {self.why} (via {self.how})"
    
    def fingerprint(self) -> str:
        """Generate unique fingerprint for deduplication."""
        content = f"{self.anchor_type.value}:{self.what}:{self.why}"
        return hashlib.md5(content.encode()).hexdigest()[:8]


@dataclass
class LeadWithAnchors:
    """
    A lead enriched with semantic anchors from all processing phases.
    
    This preserves the full context chain as the lead flows through:
    HUNTER → ENRICHER → SEGMENTOR → CRAFTER → GATEKEEPER
    """
    lead_id: str
    lead_data: Dict[str, Any]
    anchors: List[SemanticAnchor] = field(default_factory=list)
    
    def add_anchor(self, anchor: SemanticAnchor) -> None:
        """Add a semantic anchor to this lead."""
        self.anchors.append(anchor)
    
    def get_anchors_by_type(self, anchor_type: AnchorType) -> List[SemanticAnchor]:
        """Get all anchors of a specific type."""
        return [a for a in self.anchors if a.anchor_type == anchor_type]
    
    def get_latest_anchor(self, anchor_type: AnchorType) -> Optional[SemanticAnchor]:
        """Get the most recent anchor of a specific type."""
        type_anchors = self.get_anchors_by_type(anchor_type)
        if type_anchors:
            return max(type_anchors, key=lambda a: a.created_at)
        return None
    
    def generate_narrative(self) -> str:
        """
        Generate full contextual narrative for human review.
        
        This is what GATEKEEPER shows to AEs for informed decision-making.
        """
        lines = [f"=== Lead Context: {self.lead_id} ===\n"]
        
        # Group by anchor type in logical order
        order = [
            AnchorType.RESEARCH,
            AnchorType.ENRICHMENT,
            AnchorType.SEGMENTATION,
            AnchorType.PLANNING,
            AnchorType.CAMPAIGN
        ]
        
        for anchor_type in order:
            type_anchors = self.get_anchors_by_type(anchor_type)
            if type_anchors:
                lines.append(f"\n📌 {anchor_type.value.upper()}:")
                for anchor in type_anchors:
                    lines.append(f"  • {anchor.to_narrative()}")
                    if anchor.confidence < 0.7:
                        lines.append(f"    ⚠️ Low confidence: {anchor.confidence:.0%}")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "lead_id": self.lead_id,
            "lead_data": self.lead_data,
            "anchors": [a.to_dict() for a in self.anchors]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LeadWithAnchors":
        """Create from dictionary."""
        return cls(
            lead_id=data["lead_id"],
            lead_data=data["lead_data"],
            anchors=[SemanticAnchor.from_dict(a) for a in data.get("anchors", [])]
        )


# ============================================================================
# Helper Functions for Agent Integration
# ============================================================================

def attach_anchor(
    lead: Dict[str, Any],
    anchor_type: AnchorType,
    why: str,
    what: str,
    how: str,
    created_by: str,
    confidence: float = 0.8,
    metadata: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Attach a semantic anchor to a lead dictionary.
    
    This is the primary interface for agents to add context.
    
    Args:
        lead: The lead dictionary to enrich
        anchor_type: Type of anchor (which phase)
        why: Rationale for the decision
        what: The decision made
        how: Method/criteria used
        created_by: Agent name
        confidence: Confidence score
        metadata: Additional data
        
    Returns:
        The lead dictionary with the anchor attached
    """
    anchor = SemanticAnchor(
        anchor_type=anchor_type,
        why=why,
        what=what,
        how=how,
        confidence=confidence,
        created_by=created_by,
        metadata=metadata or {}
    )
    
    # Initialize anchors list if not present
    if "semantic_anchors" not in lead:
        lead["semantic_anchors"] = []
    
    lead["semantic_anchors"].append(anchor.to_dict())
    return lead


def create_segmentation_anchor(
    tier: str,
    icp_score: int,
    score_breakdown: Dict[str, int],
    disqualification_reason: Optional[str] = None
) -> SemanticAnchor:
    """
    Create a semantic anchor for SEGMENTOR decisions.
    
    Args:
        tier: The assigned tier (tier1, tier2, tier3, dq)
        icp_score: The calculated ICP score
        score_breakdown: Component scores
        disqualification_reason: Why lead was DQ'd (if applicable)
        
    Returns:
        SemanticAnchor with segmentation context
    """
    # Generate human-readable breakdown
    breakdown_str = ", ".join(f"{k}: +{v}" for k, v in score_breakdown.items())
    
    if disqualification_reason:
        why = disqualification_reason
        what = f"DISQUALIFIED (would be {tier} with score {icp_score})"
        confidence = 0.95  # High confidence in DQ
    else:
        why = f"Score breakdown: {breakdown_str}"
        what = f"Assigned to {tier.upper()} with ICP score {icp_score}"
        confidence = min(0.5 + (icp_score / 200), 0.95)  # Higher score = higher confidence
    
    how = "ICP scoring algorithm with company size, industry, title, revenue, and intent factors"
    
    return SemanticAnchor(
        anchor_type=AnchorType.SEGMENTATION,
        why=why,
        what=what,
        how=how,
        confidence=confidence,
        created_by="SEGMENTOR",
        metadata={
            "tier": tier,
            "icp_score": icp_score,
            "score_breakdown": score_breakdown,
            "disqualification_reason": disqualification_reason
        }
    )


def create_enrichment_anchor(
    sources_used: List[str],
    fields_enriched: List[str],
    data_quality_score: float
) -> SemanticAnchor:
    """
    Create a semantic anchor for ENRICHER results.
    
    Args:
        sources_used: List of enrichment sources (e.g., ["clay", "clearbit"])
        fields_enriched: List of fields that were enriched
        data_quality_score: Overall data quality (0.0 - 1.0)
        
    Returns:
        SemanticAnchor with enrichment context
    """
    return SemanticAnchor(
        anchor_type=AnchorType.ENRICHMENT,
        why=f"Used {len(sources_used)} sources to enhance lead profile",
        what=f"Enriched {len(fields_enriched)} fields: {', '.join(fields_enriched[:5])}{'...' if len(fields_enriched) > 5 else ''}",
        how=f"Waterfall enrichment via {', '.join(sources_used)}",
        confidence=data_quality_score,
        created_by="ENRICHER",
        metadata={
            "sources_used": sources_used,
            "fields_enriched": fields_enriched,
            "data_quality_score": data_quality_score
        }
    )


def create_campaign_anchor(
    template_name: str,
    template_rationale: str,
    personalization_hooks: List[str],
    ab_test_variant: Optional[str] = None
) -> SemanticAnchor:
    """
    Create a semantic anchor for CRAFTER decisions.
    
    Args:
        template_name: Selected template identifier
        template_rationale: Why this template was chosen
        personalization_hooks: Personalization elements used
        ab_test_variant: A/B test group (if applicable)
        
    Returns:
        SemanticAnchor with campaign context
    """
    return SemanticAnchor(
        anchor_type=AnchorType.CAMPAIGN,
        why=template_rationale,
        what=f"Selected template: {template_name}" + (f" (A/B: {ab_test_variant})" if ab_test_variant else ""),
        how=f"Personalized with: {', '.join(personalization_hooks[:3])}{'...' if len(personalization_hooks) > 3 else ''}",
        confidence=0.85,
        created_by="CRAFTER",
        metadata={
            "template_name": template_name,
            "personalization_hooks": personalization_hooks,
            "ab_test_variant": ab_test_variant
        }
    )


def create_planning_anchor(
    strategy: str,
    predicted_response_rate: float,
    key_insights: List[str]
) -> SemanticAnchor:
    """
    Create a semantic anchor for RPI Plan phase.
    
    Args:
        strategy: High-level strategic approach
        predicted_response_rate: Expected response rate
        key_insights: Key research insights driving the plan
        
    Returns:
        SemanticAnchor with planning context
    """
    return SemanticAnchor(
        anchor_type=AnchorType.PLANNING,
        why=f"Based on insights: {'; '.join(key_insights[:2])}",
        what=f"Strategy: {strategy}",
        how=f"Expected response rate: {predicted_response_rate:.1%}",
        confidence=0.75,  # Planning is inherently less certain
        created_by="RPI_PLANNER",
        metadata={
            "strategy": strategy,
            "predicted_response_rate": predicted_response_rate,
            "key_insights": key_insights
        }
    )


def generate_review_summary(leads_with_anchors: List[LeadWithAnchors]) -> str:
    """
    Generate a summary for GATEKEEPER AE review.
    
    This provides the high-level context for human decision-making.
    
    Args:
        leads_with_anchors: List of leads with their anchors
        
    Returns:
        Formatted summary string for AE review
    """
    lines = [
        "=" * 60,
        "CAMPAIGN REVIEW SUMMARY",
        "=" * 60,
        f"\nTotal Leads: {len(leads_with_anchors)}",
        ""
    ]
    
    # Aggregate tier distribution
    tiers = {}
    low_confidence_count = 0
    
    for lwa in leads_with_anchors:
        seg_anchor = lwa.get_latest_anchor(AnchorType.SEGMENTATION)
        if seg_anchor:
            tier = seg_anchor.metadata.get("tier", "unknown")
            tiers[tier] = tiers.get(tier, 0) + 1
            if seg_anchor.confidence < 0.7:
                low_confidence_count += 1
    
    lines.append("📊 TIER DISTRIBUTION:")
    for tier, count in sorted(tiers.items()):
        lines.append(f"  • {tier.upper()}: {count} leads")
    
    if low_confidence_count > 0:
        lines.append(f"\n⚠️ {low_confidence_count} leads have low-confidence classifications")
    
    # Show sample narratives
    lines.append("\n📝 SAMPLE LEAD CONTEXTS (first 3):")
    for lwa in leads_with_anchors[:3]:
        lines.append(lwa.generate_narrative())
    
    lines.append("\n" + "=" * 60)
    
    return "\n".join(lines)


# ============================================================================
# Context Compression for Semantic Anchors
# ============================================================================

def compress_anchors(anchors: List[SemanticAnchor], max_anchors: int = 5) -> List[SemanticAnchor]:
    """
    Compress anchor list to prevent context bloat.
    
    Keeps most important anchors while dropping low-value duplicates.
    
    Args:
        anchors: List of anchors to compress
        max_anchors: Maximum anchors to keep
        
    Returns:
        Compressed list of anchors
    """
    if len(anchors) <= max_anchors:
        return anchors
    
    # Deduplicate by fingerprint (keep latest)
    seen_fingerprints = {}
    for anchor in anchors:
        fp = anchor.fingerprint()
        if fp not in seen_fingerprints or anchor.created_at > seen_fingerprints[fp].created_at:
            seen_fingerprints[fp] = anchor
    
    unique_anchors = list(seen_fingerprints.values())
    
    # Sort by importance: confidence * recency
    def importance(a):
        # More recent = higher importance
        try:
            recency = datetime.fromisoformat(a.created_at).timestamp()
        except:
            recency = 0
        return a.confidence * (recency / 1e10)  # Normalize timestamp
    
    unique_anchors.sort(key=importance, reverse=True)
    
    # Keep one anchor per type if possible
    type_seen = set()
    result = []
    
    for anchor in unique_anchors:
        if len(result) >= max_anchors:
            break
        if anchor.anchor_type not in type_seen or len(result) < len(AnchorType):
            result.append(anchor)
            type_seen.add(anchor.anchor_type)
    
    return result


if __name__ == "__main__":
    # Demo usage
    from rich.console import Console
    from rich.panel import Panel
    
    console = Console()
    
    # Create sample lead
    lead = {
        "lead_id": "demo_001",
        "name": "Jane Smith",
        "title": "VP of Revenue",
        "company": {"name": "TechCorp", "employee_count": 150}
    }
    
    # Attach anchors from different phases
    attach_anchor(
        lead,
        AnchorType.ENRICHMENT,
        why="Lead profile incomplete, needed company data",
        what="Enriched company size, industry, and tech stack",
        how="Clay waterfall with Clearbit fallback",
        created_by="ENRICHER",
        confidence=0.92
    )
    
    attach_anchor(
        lead,
        AnchorType.SEGMENTATION,
        why="Score breakdown: company_size: +20, title: +25, industry: +15",
        what="Assigned to TIER1 with ICP score 92",
        how="ICP scoring algorithm",
        created_by="SEGMENTOR",
        confidence=0.88
    )
    
    attach_anchor(
        lead,
        AnchorType.CAMPAIGN,
        why="VP title + competitor tech stack detected",
        what="Selected template: competitor_displacement",
        how="Personalized with: role, company_size, tech_stack",
        created_by="CRAFTER"
    )
    
    # Create LeadWithAnchors
    lwa = LeadWithAnchors(
        lead_id=lead["lead_id"],
        lead_data=lead,
        anchors=[SemanticAnchor.from_dict(a) for a in lead["semantic_anchors"]]
    )
    
    # Display narrative
    console.print(Panel(
        lwa.generate_narrative(),
        title="🔗 Semantic Anchor Demo",
        border_style="green"
    ))
    
    console.print("\n[green]✓[/green] Semantic anchor module ready!")
