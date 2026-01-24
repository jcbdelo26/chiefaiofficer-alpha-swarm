#!/usr/bin/env python3
"""
Self-Learning ICP Engine

Captures deal outcomes (won/lost) from GoHighLevel webhooks and uses them
to continuously improve ICP scoring accuracy. Stores lead embeddings in
Supabase pgvector for pattern analysis.

The system learns from:
1. Won deals → Positive signals (what works)
2. Lost deals → Negative signals (what to avoid)
3. Ghost/No-show → Weak ICP indicators

Architecture:
- GHL Webhook → Capture outcome signals
- Supabase pgvector → Store embeddings
- Pattern Analyzer → Extract winning traits
- Scoring Updater → Adjust ICP weights
"""

import os
import json
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# DATA MODELS
# =============================================================================

class DealOutcome(Enum):
    """Possible deal outcomes."""
    WON = "won"
    LOST = "lost"
    GHOST = "ghost"
    DISQUALIFIED = "disqualified"
    PENDING = "pending"


@dataclass
class LeadFeatures:
    """Features extracted from a lead for ICP scoring."""
    company_size: Optional[str] = None
    industry: Optional[str] = None
    revenue_range: Optional[str] = None
    job_title: Optional[str] = None
    tech_stack: Optional[List[str]] = None
    location: Optional[str] = None
    source: Optional[str] = None
    engagement_score: float = 0.0
    response_time_hours: Optional[float] = None
    email_opens: int = 0
    email_replies: int = 0
    meetings_booked: int = 0
    
    def to_vector_input(self) -> str:
        """Convert features to text for embedding."""
        parts = []
        if self.company_size:
            parts.append(f"Company size: {self.company_size}")
        if self.industry:
            parts.append(f"Industry: {self.industry}")
        if self.revenue_range:
            parts.append(f"Revenue: {self.revenue_range}")
        if self.job_title:
            parts.append(f"Title: {self.job_title}")
        if self.tech_stack:
            parts.append(f"Tech: {', '.join(self.tech_stack)}")
        if self.location:
            parts.append(f"Location: {self.location}")
        if self.source:
            parts.append(f"Source: {self.source}")
        return ". ".join(parts)


@dataclass
class DealRecord:
    """A deal with its outcome for learning."""
    deal_id: str
    contact_id: str
    company_name: str
    features: LeadFeatures
    outcome: DealOutcome
    outcome_reason: Optional[str] = None
    deal_value: float = 0.0
    days_to_close: Optional[int] = None
    created_at: str = ""
    closed_at: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class ICPWeight:
    """Weight for an ICP trait."""
    trait_name: str
    trait_value: str
    weight: float  # Positive = good, Negative = bad
    confidence: float  # 0-1, based on sample size
    sample_size: int
    last_updated: str = ""


# =============================================================================
# ICP MEMORY (Supabase pgvector)
# =============================================================================

class ICPMemory:
    """
    Stores lead embeddings and deal outcomes in Supabase for pattern analysis.
    Uses pgvector extension for similarity search.
    """
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or Path(".hive-mind/icp_memory")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Supabase client
        self.supabase = None
        self._init_supabase()
        
        # Local cache of weights
        self.weights_file = self.storage_dir / "icp_weights.json"
        self.weights: Dict[str, ICPWeight] = self._load_weights()
        
        # Deal history
        self.deals_file = self.storage_dir / "deal_history.json"
        self.deals: List[DealRecord] = self._load_deals()
    
    def _init_supabase(self):
        """Initialize Supabase client."""
        try:
            from supabase import create_client
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_KEY")
            if url and key:
                self.supabase = create_client(url, key)
                print("✓ ICP Memory connected to Supabase")
        except Exception as e:
            print(f"Warning: Supabase not available for ICP Memory - {e}")
    
    def _load_weights(self) -> Dict[str, ICPWeight]:
        """Load ICP weights from file."""
        if self.weights_file.exists():
            try:
                with open(self.weights_file) as f:
                    data = json.load(f)
                    return {k: ICPWeight(**v) for k, v in data.items()}
            except Exception as e:
                print(f"Error loading weights: {e}")
        return self._default_weights()
    
    def _default_weights(self) -> Dict[str, ICPWeight]:
        """Default ICP weights based on initial criteria."""
        now = datetime.now(timezone.utc).isoformat()
        return {
            # Company size weights
            "size_51-200": ICPWeight("company_size", "51-200", 0.8, 0.5, 0, now),
            "size_201-500": ICPWeight("company_size", "201-500", 1.0, 0.5, 0, now),
            "size_501-1000": ICPWeight("company_size", "501-1000", 0.7, 0.5, 0, now),
            "size_<50": ICPWeight("company_size", "<50", -0.5, 0.5, 0, now),
            
            # Industry weights
            "industry_b2b_saas": ICPWeight("industry", "B2B SaaS", 1.0, 0.5, 0, now),
            "industry_technology": ICPWeight("industry", "Technology", 0.9, 0.5, 0, now),
            "industry_professional_services": ICPWeight("industry", "Professional Services", 0.7, 0.5, 0, now),
            "industry_retail": ICPWeight("industry", "Retail", -0.3, 0.5, 0, now),
            
            # Title weights
            "title_vp_sales": ICPWeight("job_title", "VP Sales", 1.0, 0.5, 0, now),
            "title_cro": ICPWeight("job_title", "CRO", 1.0, 0.5, 0, now),
            "title_revops": ICPWeight("job_title", "RevOps Director", 0.9, 0.5, 0, now),
            "title_sales_manager": ICPWeight("job_title", "Sales Manager", 0.5, 0.5, 0, now),
        }
    
    def _save_weights(self):
        """Save ICP weights to file."""
        with open(self.weights_file, 'w') as f:
            json.dump({k: asdict(v) for k, v in self.weights.items()}, f, indent=2)
    
    def _load_deals(self) -> List[DealRecord]:
        """Load deal history from file."""
        if self.deals_file.exists():
            try:
                with open(self.deals_file) as f:
                    data = json.load(f)
                    return [
                        DealRecord(
                            features=LeadFeatures(**d.pop("features")),
                            outcome=DealOutcome(d.pop("outcome")),
                            **d
                        ) for d in data
                    ]
            except Exception as e:
                print(f"Error loading deals: {e}")
        return []
    
    def _save_deals(self):
        """Save deal history to file."""
        with open(self.deals_file, 'w') as f:
            data = []
            for deal in self.deals:
                d = asdict(deal)
                d["outcome"] = deal.outcome.value
                data.append(d)
            json.dump(data, f, indent=2)
    
    async def record_deal_outcome(self, deal: DealRecord) -> bool:
        """
        Record a deal outcome for learning.
        
        Args:
            deal: The deal record with outcome
            
        Returns:
            True if recorded successfully
        """
        # Add to local history
        self.deals.append(deal)
        self._save_deals()
        
        # Store in Supabase if available
        if self.supabase:
            try:
                # Generate embedding for the lead features
                embedding = await self._generate_embedding(deal.features.to_vector_input())
                
                # Store in icp_learning table
                record = {
                    "deal_id": deal.deal_id,
                    "contact_id": deal.contact_id,
                    "company_name": deal.company_name,
                    "features": asdict(deal.features),
                    "outcome": deal.outcome.value,
                    "outcome_reason": deal.outcome_reason,
                    "deal_value": deal.deal_value,
                    "days_to_close": deal.days_to_close,
                    "embedding": embedding,
                    "created_at": deal.created_at,
                    "closed_at": deal.closed_at
                }
                
                self.supabase.table("icp_learning").insert(record).execute()
                print(f"✓ Recorded {deal.outcome.value} deal: {deal.company_name}")
                return True
                
            except Exception as e:
                print(f"Error storing deal in Supabase: {e}")
        
        return True  # Still recorded locally
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using OpenAI."""
        try:
            import httpx
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return [0.0] * 1536  # Return zero vector if no API key
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": "text-embedding-3-small",
                        "input": text
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return data["data"][0]["embedding"]
                    
        except Exception as e:
            print(f"Error generating embedding: {e}")
        
        return [0.0] * 1536  # Fallback
    
    def update_weight(self, trait_name: str, trait_value: str, outcome: DealOutcome) -> ICPWeight:
        """
        Update a trait weight based on deal outcome.
        
        Won deals increase weight, lost deals decrease it.
        """
        key = f"{trait_name}_{trait_value}".lower().replace(" ", "_")
        
        if key not in self.weights:
            # Create new weight
            self.weights[key] = ICPWeight(
                trait_name=trait_name,
                trait_value=trait_value,
                weight=0.0,
                confidence=0.1,
                sample_size=0,
                last_updated=datetime.now(timezone.utc).isoformat()
            )
        
        weight = self.weights[key]
        
        # Update based on outcome
        if outcome == DealOutcome.WON:
            # Increase weight
            adjustment = 0.1 * (1 - weight.confidence)  # Smaller adjustments as confidence grows
            weight.weight = min(1.0, weight.weight + adjustment)
        elif outcome == DealOutcome.LOST:
            # Decrease weight
            adjustment = 0.1 * (1 - weight.confidence)
            weight.weight = max(-1.0, weight.weight - adjustment)
        elif outcome == DealOutcome.GHOST:
            # Slight decrease
            adjustment = 0.05 * (1 - weight.confidence)
            weight.weight = max(-1.0, weight.weight - adjustment)
        
        # Update metadata
        weight.sample_size += 1
        weight.confidence = min(0.95, 0.1 + (weight.sample_size * 0.05))  # Confidence grows with samples
        weight.last_updated = datetime.now(timezone.utc).isoformat()
        
        self._save_weights()
        return weight
    
    def calculate_icp_score(self, features: LeadFeatures) -> Tuple[float, Dict[str, float]]:
        """
        Calculate ICP score for a lead based on learned weights.
        
        Returns:
            Tuple of (overall_score 0-100, breakdown by trait)
        """
        breakdown = {}
        total_weight = 0.0
        max_possible = 0.0
        
        # Check each feature against weights
        if features.company_size:
            key = f"size_{features.company_size}".lower().replace(" ", "_")
            if key in self.weights:
                w = self.weights[key]
                breakdown["company_size"] = w.weight * w.confidence
                total_weight += w.weight * w.confidence
                max_possible += 1.0
        
        if features.industry:
            key = f"industry_{features.industry}".lower().replace(" ", "_")
            if key in self.weights:
                w = self.weights[key]
                breakdown["industry"] = w.weight * w.confidence
                total_weight += w.weight * w.confidence
                max_possible += 1.0
        
        if features.job_title:
            key = f"title_{features.job_title}".lower().replace(" ", "_")
            if key in self.weights:
                w = self.weights[key]
                breakdown["job_title"] = w.weight * w.confidence
                total_weight += w.weight * w.confidence
                max_possible += 1.0
        
        # Normalize to 0-100 scale
        if max_possible > 0:
            score = ((total_weight / max_possible) + 1) * 50  # Convert -1..1 to 0..100
        else:
            score = 50  # Default to neutral if no data
        
        return score, breakdown
    
    def get_winning_patterns(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the top winning patterns from deal history."""
        won_deals = [d for d in self.deals if d.outcome == DealOutcome.WON]
        
        # Count trait occurrences
        trait_counts: Dict[str, int] = {}
        for deal in won_deals:
            if deal.features.industry:
                key = f"industry:{deal.features.industry}"
                trait_counts[key] = trait_counts.get(key, 0) + 1
            if deal.features.company_size:
                key = f"size:{deal.features.company_size}"
                trait_counts[key] = trait_counts.get(key, 0) + 1
            if deal.features.job_title:
                key = f"title:{deal.features.job_title}"
                trait_counts[key] = trait_counts.get(key, 0) + 1
        
        # Sort by count
        sorted_traits = sorted(trait_counts.items(), key=lambda x: x[1], reverse=True)
        
        return [
            {"trait": k, "count": v, "percentage": v / len(won_deals) * 100 if won_deals else 0}
            for k, v in sorted_traits[:limit]
        ]
    
    def get_losing_patterns(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the top losing patterns from deal history."""
        lost_deals = [d for d in self.deals if d.outcome == DealOutcome.LOST]
        
        # Count trait occurrences
        trait_counts: Dict[str, int] = {}
        for deal in lost_deals:
            if deal.features.industry:
                key = f"industry:{deal.features.industry}"
                trait_counts[key] = trait_counts.get(key, 0) + 1
            if deal.features.company_size:
                key = f"size:{deal.features.company_size}"
                trait_counts[key] = trait_counts.get(key, 0) + 1
            if deal.features.job_title:
                key = f"title:{deal.features.job_title}"
                trait_counts[key] = trait_counts.get(key, 0) + 1
            if deal.outcome_reason:
                key = f"reason:{deal.outcome_reason}"
                trait_counts[key] = trait_counts.get(key, 0) + 1
        
        # Sort by count
        sorted_traits = sorted(trait_counts.items(), key=lambda x: x[1], reverse=True)
        
        return [
            {"trait": k, "count": v, "percentage": v / len(lost_deals) * 100 if lost_deals else 0}
            for k, v in sorted_traits[:limit]
        ]
    
    def generate_insights_report(self) -> Dict[str, Any]:
        """Generate an insights report from learned patterns."""
        total_deals = len(self.deals)
        won_deals = len([d for d in self.deals if d.outcome == DealOutcome.WON])
        lost_deals = len([d for d in self.deals if d.outcome == DealOutcome.LOST])
        ghost_deals = len([d for d in self.deals if d.outcome == DealOutcome.GHOST])
        
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_deals_analyzed": total_deals,
            "win_rate": won_deals / total_deals * 100 if total_deals else 0,
            "outcomes": {
                "won": won_deals,
                "lost": lost_deals,
                "ghost": ghost_deals
            },
            "top_winning_patterns": self.get_winning_patterns(5),
            "top_losing_patterns": self.get_losing_patterns(5),
            "weight_adjustments": {
                k: {"weight": v.weight, "confidence": v.confidence, "samples": v.sample_size}
                for k, v in self.weights.items()
                if v.sample_size > 0
            }
        }


# =============================================================================
# GHL WEBHOOK HANDLER
# =============================================================================

class GHLOutcomeWebhook:
    """
    Handles GoHighLevel webhooks for deal stage changes.
    Captures won/lost signals for ICP learning.
    """
    
    def __init__(self, icp_memory: ICPMemory):
        self.memory = icp_memory
        
        # Stage mapping to outcomes
        self.stage_mapping = {
            # Won stages
            "won": DealOutcome.WON,
            "closed won": DealOutcome.WON,
            "customer": DealOutcome.WON,
            "deal won": DealOutcome.WON,
            
            # Lost stages
            "lost": DealOutcome.LOST,
            "closed lost": DealOutcome.LOST,
            "disqualified": DealOutcome.DISQUALIFIED,
            
            # Ghost stages
            "ghost": DealOutcome.GHOST,
            "no show": DealOutcome.GHOST,
            "unresponsive": DealOutcome.GHOST,
        }
    
    async def handle_opportunity_update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle opportunity/deal update webhook from GHL.
        Supports both custom JSON structure and standard GHL flat payload.
        """
        # Strategy 1: Check for Custom JSON structure (type/data wrapper)
        event_type = payload.get("type", "")
        if event_type and ("stageChanged" in event_type or "opportunity" in event_type):
            data = payload.get("data", {})
            return await self._process_deal_data(data, event_type)
            
        # Strategy 2: Check for Standard GHL Flat Payload
        # Standard GHL webhooks send flattened contact/opp data
        if "contact_id" in payload or "contact.id" in payload:
            print("✓ Detected Standard GHL Payload")
            return await self._process_deal_data(payload, "standard_ghl")
            
        return {"status": "ignored", "reason": "Unknown payload format"}

    async def _process_deal_data(self, data: Dict[str, Any], source_type: str) -> Dict[str, Any]:
        """Process extracted deal data regardless of source format."""
        
        # Normalize fields (handle flat vs nested)
        stage = (data.get("stage") or data.get("opportunity_status") or data.get("status") or "").lower().strip()
        outcome = self.stage_mapping.get(stage)
        
        if not outcome:
            # Try to infer from status field common in GHL
            if stage in ["won", "closed won"]: outcome = DealOutcome.WON
            elif stage in ["lost", "closed lost"]: outcome = DealOutcome.LOST
            elif stage in ["abandoned"]: outcome = DealOutcome.OTHER
            else: return {"status": "ignored", "reason": f"Stage/Status '{stage}' not mapped"}
        
        # Extract features
        features = self._extract_features(data)
        
        # Create deal record
        deal = DealRecord(
            deal_id=data.get("id") or data.get("opportunity_id") or "unknown",
            contact_id=data.get("contact_id") or data.get("contact", {}).get("id") or "",
            company_name=data.get("contact", {}).get("company") or data.get("company_name") or data.get("contact.company_name") or "Unknown",
            features=features,
            outcome=outcome,
            outcome_reason=data.get("lost_reason") or data.get("custom_fields", {}).get("lost_reason"),
            deal_value=float(data.get("value") or data.get("monetary_value") or 0),
            closed_at=datetime.now(timezone.utc).isoformat()
        )
        
        # Record the outcome
        await self.memory.record_deal_outcome(deal)
        
        # Update weights
        self._update_weights_for_deal(deal)
        
        return {
            "status": "recorded",
            "deal_id": deal.deal_id,
            "outcome": outcome.value,
            "company": deal.company_name
        }
    
    def _extract_features(self, data: Dict[str, Any]) -> LeadFeatures:
        """Extract lead features from GHL opportunity data."""
        contact = data.get("contact", {})
        custom = data.get("custom_fields", {})
        
        return LeadFeatures(
            company_size=custom.get("company_size") or custom.get("employee_count"),
            industry=custom.get("industry"),
            revenue_range=custom.get("revenue") or custom.get("annual_revenue"),
            job_title=contact.get("title") or custom.get("job_title"),
            tech_stack=custom.get("tech_stack", "").split(",") if custom.get("tech_stack") else None,
            location=contact.get("city") or custom.get("location"),
            source=data.get("source") or custom.get("lead_source"),
            engagement_score=float(custom.get("engagement_score", 0)),
            email_opens=int(custom.get("email_opens", 0)),
            email_replies=int(custom.get("email_replies", 0)),
            meetings_booked=int(custom.get("meetings_booked", 0))
        )
    
    def _update_weights_for_deal(self, deal: DealRecord):
        """Update ICP weights based on deal outcome."""
        features = deal.features
        
        if features.company_size:
            self.memory.update_weight("size", features.company_size, deal.outcome)
        
        if features.industry:
            self.memory.update_weight("industry", features.industry, deal.outcome)
        
        if features.job_title:
            self.memory.update_weight("title", features.job_title, deal.outcome)
        
        if features.source:
            self.memory.update_weight("source", features.source, deal.outcome)


# =============================================================================
# PATTERN ANALYZER
# =============================================================================

class PatternAnalyzer:
    """
    Analyzes deal patterns to extract actionable insights.
    Runs weekly to identify trends and update strategies.
    """
    
    def __init__(self, icp_memory: ICPMemory):
        self.memory = icp_memory
        self.reports_dir = Path(".hive-mind/icp_memory/reports")
        self.reports_dir.mkdir(parents=True, exist_ok=True)
    
    async def run_weekly_analysis(self) -> Dict[str, Any]:
        """
        Run weekly pattern analysis.
        
        Called by the Inngest scheduler every Monday.
        """
        report = self.memory.generate_insights_report()
        
        # Add trend analysis
        report["trends"] = await self._analyze_trends()
        
        # Add recommendations
        report["recommendations"] = self._generate_recommendations(report)
        
        # Save report
        report_file = self.reports_dir / f"weekly_{datetime.now().strftime('%Y%m%d')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"✓ Weekly ICP analysis complete. Win rate: {report['win_rate']:.1f}%")
        
        return report
    
    async def _analyze_trends(self) -> Dict[str, Any]:
        """Analyze trends over time."""
        now = datetime.now(timezone.utc)
        last_week = now - timedelta(days=7)
        last_month = now - timedelta(days=30)
        
        recent_deals = [
            d for d in self.memory.deals 
            if datetime.fromisoformat(d.created_at.replace('Z', '+00:00')) > last_week
        ]
        
        older_deals = [
            d for d in self.memory.deals 
            if last_month < datetime.fromisoformat(d.created_at.replace('Z', '+00:00')) <= last_week
        ]
        
        recent_win_rate = (
            len([d for d in recent_deals if d.outcome == DealOutcome.WON]) / len(recent_deals) * 100
            if recent_deals else 0
        )
        
        older_win_rate = (
            len([d for d in older_deals if d.outcome == DealOutcome.WON]) / len(older_deals) * 100
            if older_deals else 0
        )
        
        return {
            "recent_deals": len(recent_deals),
            "recent_win_rate": recent_win_rate,
            "previous_win_rate": older_win_rate,
            "trend": "improving" if recent_win_rate > older_win_rate else "declining" if recent_win_rate < older_win_rate else "stable"
        }
    
    def _generate_recommendations(self, report: Dict[str, Any]) -> List[str]:
        """Generate actionable recommendations from analysis."""
        recommendations = []
        
        # Check win rate
        win_rate = report.get("win_rate", 0)
        if win_rate < 20:
            recommendations.append("Win rate is low. Consider tightening ICP criteria to focus on higher-quality leads.")
        elif win_rate > 50:
            recommendations.append("Strong win rate! Consider expanding outreach volume while maintaining ICP criteria.")
        
        # Check winning patterns
        winning = report.get("top_winning_patterns", [])
        if winning:
            top_trait = winning[0].get("trait", "")
            if top_trait:
                recommendations.append(f"Top winning trait: {top_trait}. Prioritize leads matching this pattern.")
        
        # Check losing patterns
        losing = report.get("top_losing_patterns", [])
        if losing:
            top_loss = losing[0].get("trait", "")
            if top_loss and "reason:" in top_loss:
                reason = top_loss.replace("reason:", "")
                recommendations.append(f"Common loss reason: '{reason}'. Train CRAFTER to address this objection.")
        
        return recommendations


# =============================================================================
# FASTAPI ENDPOINTS
# =============================================================================

# Initialize global instances
icp_memory = ICPMemory()
ghl_webhook = GHLOutcomeWebhook(icp_memory)
pattern_analyzer = PatternAnalyzer(icp_memory)


def get_icp_router():
    """Get FastAPI router for ICP learning endpoints."""
    from fastapi import APIRouter, Request, HTTPException
    
    router = APIRouter(prefix="/api/icp", tags=["ICP Learning"])
    
    @router.post("/ghl/outcome")
    async def ghl_outcome_webhook(request: Request):
        """
        Receive deal outcome webhooks from GoHighLevel.
        
        Configure in GHL: Workflows → Trigger → Webhook
        URL: https://YOUR-RAILWAY-URL/api/icp/ghl/outcome
        """
        try:
            payload = await request.json()
            result = await ghl_webhook.handle_opportunity_update(payload)
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get("/score")
    async def calculate_score(
        company_size: str = None,
        industry: str = None,
        job_title: str = None
    ):
        """Calculate ICP score for given features."""
        features = LeadFeatures(
            company_size=company_size,
            industry=industry,
            job_title=job_title
        )
        score, breakdown = icp_memory.calculate_icp_score(features)
        return {
            "score": round(score, 1),
            "breakdown": breakdown,
            "features": {
                "company_size": company_size,
                "industry": industry,
                "job_title": job_title
            }
        }
    
    @router.get("/insights")
    async def get_insights():
        """Get current ICP insights and patterns."""
        return icp_memory.generate_insights_report()
    
    @router.get("/weights")
    async def get_weights():
        """Get current ICP weights."""
        return {
            k: {
                "trait": v.trait_name,
                "value": v.trait_value,
                "weight": round(v.weight, 3),
                "confidence": round(v.confidence, 3),
                "samples": v.sample_size
            }
            for k, v in icp_memory.weights.items()
        }
    
    @router.post("/analyze")
    async def run_analysis():
        """Trigger manual pattern analysis."""
        report = await pattern_analyzer.run_weekly_analysis()
        return report
    
    return router


if __name__ == "__main__":
    print("=" * 60)
    print("Self-Learning ICP Engine")
    print("=" * 60)
    print()
    print("Components:")
    print("  - ICPMemory: Stores weights and deal history")
    print("  - GHLOutcomeWebhook: Captures won/lost signals")
    print("  - PatternAnalyzer: Extracts insights weekly")
    print()
    print("Endpoints (when integrated with webhook server):")
    print("  POST /api/icp/ghl/outcome  - GHL deal outcome webhook")
    print("  GET  /api/icp/score        - Calculate ICP score")
    print("  GET  /api/icp/insights     - View patterns")
    print("  GET  /api/icp/weights      - View learned weights")
    print("  POST /api/icp/analyze      - Trigger analysis")
    print()
    
    # Show current insights
    report = icp_memory.generate_insights_report()
    print(f"Current Stats:")
    print(f"  Total deals: {report['total_deals_analyzed']}")
    print(f"  Win rate: {report['win_rate']:.1f}%")
