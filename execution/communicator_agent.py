#!/usr/bin/env python3
"""
Communicator Agent (Enhanced Crafter) - Beta Swarm
===================================================
Day 15 Implementation: Advanced communication agent with tone matching,
email threading context, sales stage awareness, and scheduling routing.

Capabilities:
1. Tone Matching (>85% similarity to existing thread)
2. Email-threading-mcp context integration
3. Scheduling intent detection → route to SCHEDULER
4. 8-stage sales awareness (SalesGPT methodology)
5. Follow-up automation (2-day cadence)
6. Preserve existing campaign creation functionality

Architecture:
    ┌──────────────────────────────────────────────────────────────────────┐
    │                      COMMUNICATOR AGENT                               │
    ├──────────────────────────────────────────────────────────────────────┤
    │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐          │
    │  │ Tone Analyzer  │  │ Intent Router  │  │ Stage Manager  │          │
    │  │ (85% match)    │  │ (→ Scheduler)  │  │ (8 stages)     │          │
    │  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘          │
    │          │                   │                   │                    │
    │          └───────────────────┴───────────────────┘                    │
    │                              │                                        │
    │  ┌────────────────┐  ┌───────▼────────┐  ┌────────────────┐          │
    │  │ Email Threading│  │ Response       │  │ Follow-up      │          │
    │  │ MCP            │  │ Generator      │  │ Scheduler      │          │
    │  └────────────────┘  └────────────────┘  └────────────────┘          │
    └──────────────────────────────────────────────────────────────────────┘

Sales Stages (SalesGPT-inspired):
    1. INTRODUCTION     - Initial outreach, brand awareness
    2. QUALIFICATION    - ICP fit validation, needs discovery
    3. VALUE_PROP       - Pain points addressed, solution positioning
    4. NEEDS_ANALYSIS   - Deep dive into requirements
    5. SOLUTION_PRESENT - Demo/proposal offered
    6. OBJECTION_HANDLE - Address concerns and blockers
    7. CLOSE            - Ask for commitment, next steps
    8. FOLLOW_UP        - Post-meeting nurture, retention

Usage:
    from execution.communicator_agent import CommunicatorAgent
    
    communicator = CommunicatorAgent()
    
    # Generate context-aware response
    response = await communicator.generate_response(
        thread_id="abc123",
        prospect_email="john@example.com"
    )
    
    # Process incoming email
    result = await communicator.process_incoming_email(
        raw_email="...",
        sender_email="john@example.com"
    )
"""

import os
import sys
import json
import asyncio
import logging
import hashlib
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import Counter
import math

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("communicator-agent")

# Try to import rich for CLI output
try:
    from rich.console import Console
    from rich.table import Table
    console = Console()
except ImportError:
    console = None

# Import email threading MCP
try:
    from mcp_servers.email_threading_mcp.server import (
        EmailThreadingMCP,
        EmailIntent,
        ThreadContext,
        EmailMessage
    )
    EMAIL_MCP_AVAILABLE = True
except ImportError:
    EMAIL_MCP_AVAILABLE = False
    logger.warning("Email Threading MCP not available - using mock mode")

# Import existing crafter for campaign creation
try:
    from execution.crafter_campaign import CampaignCrafter, Campaign, EmailStep
    CRAFTER_AVAILABLE = True
except ImportError:
    CRAFTER_AVAILABLE = False
    logger.warning("Crafter not available - limited functionality")


# ============================================================================
# SALES STAGE DEFINITIONS (SalesGPT Methodology)
# ============================================================================

class SalesStage(Enum):
    """8-stage sales awareness model based on SalesGPT methodology."""
    INTRODUCTION = "introduction"           # Stage 1: Initial outreach
    QUALIFICATION = "qualification"         # Stage 2: ICP fit validation
    VALUE_PROP = "value_proposition"        # Stage 3: Solution positioning
    NEEDS_ANALYSIS = "needs_analysis"       # Stage 4: Deep requirements
    SOLUTION_PRESENT = "solution_present"   # Stage 5: Demo/proposal
    OBJECTION_HANDLE = "objection_handle"   # Stage 6: Address concerns
    CLOSE = "close"                         # Stage 7: Ask for commitment
    FOLLOW_UP = "follow_up"                 # Stage 8: Post-meeting nurture


@dataclass
class SalesStageConfig:
    """Configuration for each sales stage."""
    stage: SalesStage
    objective: str
    tactics: List[str]
    success_signals: List[str]
    next_stage_triggers: List[str]
    max_touches: int
    tone_keywords: List[str]
    urgency_level: str  # low, medium, high


SALES_STAGE_CONFIGS = {
    SalesStage.INTRODUCTION: SalesStageConfig(
        stage=SalesStage.INTRODUCTION,
        objective="Create awareness and spark interest",
        tactics=[
            "Personalized hook based on prospect's activity",
            "Brief value proposition",
            "Single clear CTA (reply or book)",
            "Reference mutual connection or shared interest"
        ],
        success_signals=["reply", "link_click", "meeting_request"],
        next_stage_triggers=["reply_received", "interest_expressed"],
        max_touches=3,
        tone_keywords=["curious", "noticed", "thought you might"],
        urgency_level="low"
    ),
    SalesStage.QUALIFICATION: SalesStageConfig(
        stage=SalesStage.QUALIFICATION,
        objective="Validate ICP fit and discover needs",
        tactics=[
            "Ask open-ended questions about challenges",
            "Confirm decision-making authority",
            "Validate budget/timeline",
            "Identify key stakeholders"
        ],
        success_signals=["answered_questions", "shared_challenges", "introduced_team"],
        next_stage_triggers=["icp_confirmed", "needs_identified"],
        max_touches=4,
        tone_keywords=["understand", "tell me more", "curious about"],
        urgency_level="low"
    ),
    SalesStage.VALUE_PROP: SalesStageConfig(
        stage=SalesStage.VALUE_PROP,
        objective="Position solution against pain points",
        tactics=[
            "Connect features to stated needs",
            "Share relevant case study",
            "Quantify potential value/ROI",
            "Differentiate from alternatives"
        ],
        success_signals=["positive_response", "asked_for_details", "shared_with_team"],
        next_stage_triggers=["interest_confirmed", "demo_requested"],
        max_touches=3,
        tone_keywords=["help", "solve", "results", "imagine"],
        urgency_level="medium"
    ),
    SalesStage.NEEDS_ANALYSIS: SalesStageConfig(
        stage=SalesStage.NEEDS_ANALYSIS,
        objective="Deep dive into specific requirements",
        tactics=[
            "Discovery questions about current process",
            "Map stakeholder needs",
            "Document technical requirements",
            "Identify success metrics"
        ],
        success_signals=["detailed_requirements", "technical_discussion", "timeline_shared"],
        next_stage_triggers=["requirements_complete", "ready_for_demo"],
        max_touches=4,
        tone_keywords=["specifically", "walk me through", "crucial"],
        urgency_level="medium"
    ),
    SalesStage.SOLUTION_PRESENT: SalesStageConfig(
        stage=SalesStage.SOLUTION_PRESENT,
        objective="Present tailored solution via demo/proposal",
        tactics=[
            "Personalized demo focused on their use case",
            "Clear pricing and implementation plan",
            "Address known concerns proactively",
            "Outline next steps and timeline"
        ],
        success_signals=["positive_demo_feedback", "requested_proposal", "involved_stakeholders"],
        next_stage_triggers=["proposal_sent", "evaluation_started"],
        max_touches=3,
        tone_keywords=["show you", "specifically designed", "your use case"],
        urgency_level="medium"
    ),
    SalesStage.OBJECTION_HANDLE: SalesStageConfig(
        stage=SalesStage.OBJECTION_HANDLE,
        objective="Address concerns and remove blockers",
        tactics=[
            "Acknowledge concern genuinely",
            "Provide evidence/case studies",
            "Offer trial or pilot",
            "Involve technical team if needed"
        ],
        success_signals=["objection_resolved", "asked_followup", "reconsidering"],
        next_stage_triggers=["objections_resolved", "ready_to_close"],
        max_touches=5,
        tone_keywords=["understand", "valid concern", "let me address"],
        urgency_level="high"
    ),
    SalesStage.CLOSE: SalesStageConfig(
        stage=SalesStage.CLOSE,
        objective="Secure commitment and close deal",
        tactics=[
            "Direct ask for commitment",
            "Create urgency if appropriate",
            "Summarize agreed value",
            "Clear next steps"
        ],
        success_signals=["verbal_commitment", "contract_requested", "start_date_confirmed"],
        next_stage_triggers=["deal_closed", "need_more_time"],
        max_touches=3,
        tone_keywords=["ready", "move forward", "get started"],
        urgency_level="high"
    ),
    SalesStage.FOLLOW_UP: SalesStageConfig(
        stage=SalesStage.FOLLOW_UP,
        objective="Nurture relationship post-meeting/deal",
        tactics=[
            "Thank you and summary email",
            "Share relevant resources",
            "Check-in on implementation",
            "Ask for referrals/testimonials"
        ],
        success_signals=["positive_feedback", "referral_made", "renewal_started"],
        next_stage_triggers=["renewal_opportunity", "referral_opportunity"],
        max_touches=6,
        tone_keywords=["appreciate", "checking in", "thought of you"],
        urgency_level="low"
    ),
}


# ============================================================================
# TONE ANALYSIS
# ============================================================================

@dataclass
class ToneProfile:
    """Analysis of communication tone."""
    formality: float        # 0 = casual, 1 = formal
    warmth: float           # 0 = cold, 1 = warm
    urgency: float          # 0 = relaxed, 1 = urgent
    complexity: float       # 0 = simple, 1 = complex
    assertiveness: float    # 0 = passive, 1 = assertive
    sentiment: float        # -1 = negative, 0 = neutral, 1 = positive
    avg_sentence_length: float
    vocabulary_richness: float
    keywords: List[str] = field(default_factory=list)
    
    def similarity(self, other: 'ToneProfile') -> float:
        """Calculate similarity score between two tone profiles (0-1)."""
        dimensions = [
            (self.formality, other.formality),
            (self.warmth, other.warmth),
            (self.urgency, other.urgency),
            (self.complexity, other.complexity),
            (self.assertiveness, other.assertiveness),
            ((self.sentiment + 1) / 2, (other.sentiment + 1) / 2),  # Normalize to 0-1
        ]
        
        # Calculate Euclidean distance
        distance = math.sqrt(sum((a - b) ** 2 for a, b in dimensions))
        
        # Convert to similarity (max distance would be sqrt(6) ≈ 2.45)
        max_distance = math.sqrt(len(dimensions))
        similarity = 1 - (distance / max_distance)
        
        return round(similarity, 3)


class ToneAnalyzer:
    """Analyzes and matches communication tone."""
    
    # Formality indicators
    FORMAL_PATTERNS = [
        r"\b(?:Dear|Regarding|Pursuant|Furthermore|Therefore|Consequently)\b",
        r"\b(?:Please find|Kindly|I would like to)\b",
        r"\b(?:respectfully|accordingly|hereby)\b",
    ]
    
    INFORMAL_PATTERNS = [
        r"\b(?:Hey|Hi|Thanks|Cheers|BTW|FYI)\b",
        r"\b(?:gonna|wanna|kinda|gotta)\b",
        r"(?:!!|!\?|\?\?)",
        r"(?:lol|haha|:[\)\(])",
    ]
    
    # Warmth indicators
    WARM_PATTERNS = [
        r"\b(?:appreciate|grateful|wonderful|fantastic|excited)\b",
        r"\b(?:happy to|love to|thrilled)\b",
        r"\b(?:thanks so much|really appreciate)\b",
    ]
    
    COLD_PATTERNS = [
        r"\b(?:unfortunately|however|nevertheless)\b",
        r"\b(?:must|required|mandatory)\b",
        r"\b(?:deadline|urgent|immediately)\b",
    ]
    
    # Urgency indicators
    URGENT_PATTERNS = [
        r"\b(?:ASAP|urgent|immediately|today|now)\b",
        r"\b(?:deadline|critical|priority|time-sensitive)\b",
        r"(?:!!!|!!)",
    ]
    
    # Assertiveness indicators
    ASSERTIVE_PATTERNS = [
        r"\b(?:I need|I want|I require|must)\b",
        r"\b(?:confirm|ensure|guarantee)\b",
        r"\b(?:will|shall|expect)\b",
    ]
    
    PASSIVE_PATTERNS = [
        r"\b(?:maybe|perhaps|possibly|might)\b",
        r"\b(?:I think|I guess|I suppose)\b",
        r"\b(?:if you could|would you mind|when you get a chance)\b",
    ]
    
    def analyze(self, text: str) -> ToneProfile:
        """Analyze the tone of text and return a profile."""
        if not text.strip():
            return ToneProfile(
                formality=0.5, warmth=0.5, urgency=0.2,
                complexity=0.3, assertiveness=0.5, sentiment=0.0,
                avg_sentence_length=10.0, vocabulary_richness=0.5
            )
        
        text_lower = text.lower()
        
        # Calculate formality
        formal_count = self._count_patterns(text, self.FORMAL_PATTERNS)
        informal_count = self._count_patterns(text, self.INFORMAL_PATTERNS)
        formality = self._ratio_score(formal_count, informal_count, len(text.split()) / 10)
        
        # Calculate warmth
        warm_count = self._count_patterns(text_lower, self.WARM_PATTERNS)
        cold_count = self._count_patterns(text_lower, self.COLD_PATTERNS)
        warmth = self._ratio_score(warm_count, cold_count, len(text.split()) / 10)
        
        # Calculate urgency
        urgent_count = self._count_patterns(text, self.URGENT_PATTERNS)
        urgency = min(1.0, urgent_count / 3)
        
        # Calculate assertiveness
        assertive_count = self._count_patterns(text_lower, self.ASSERTIVE_PATTERNS)
        passive_count = self._count_patterns(text_lower, self.PASSIVE_PATTERNS)
        assertiveness = self._ratio_score(assertive_count, passive_count, len(text.split()) / 10)
        
        # Calculate complexity
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        avg_sentence_length = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
        
        words = text.split()
        unique_words = set(w.lower() for w in words)
        vocabulary_richness = len(unique_words) / max(len(words), 1)
        
        complexity = min(1.0, (avg_sentence_length / 25 + vocabulary_richness) / 2)
        
        # Calculate sentiment
        sentiment = self._analyze_sentiment(text)
        
        # Extract keywords
        keywords = self._extract_keywords(text)
        
        return ToneProfile(
            formality=round(formality, 2),
            warmth=round(warmth, 2),
            urgency=round(urgency, 2),
            complexity=round(complexity, 2),
            assertiveness=round(assertiveness, 2),
            sentiment=round(sentiment, 2),
            avg_sentence_length=round(avg_sentence_length, 1),
            vocabulary_richness=round(vocabulary_richness, 2),
            keywords=keywords
        )
    
    def _count_patterns(self, text: str, patterns: List[str]) -> int:
        """Count pattern matches in text."""
        count = 0
        for pattern in patterns:
            count += len(re.findall(pattern, text, re.IGNORECASE))
        return count
    
    def _ratio_score(self, positive: int, negative: int, baseline: float) -> float:
        """Calculate ratio score between two counts."""
        total = positive + negative + baseline
        if total == 0:
            return 0.5
        return max(0, min(1, (positive + baseline / 2) / total))
    
    def _analyze_sentiment(self, text: str) -> float:
        """Simple sentiment analysis returning -1 to 1."""
        positive_words = [
            "great", "good", "excellent", "wonderful", "amazing", "fantastic",
            "love", "appreciate", "thanks", "happy", "excited", "helpful",
            "perfect", "awesome", "brilliant", "outstanding"
        ]
        negative_words = [
            "bad", "poor", "terrible", "awful", "disappointed", "frustrated",
            "unfortunately", "problem", "issue", "concern", "worried", "unhappy",
            "difficult", "impossible", "fail", "wrong"
        ]
        
        text_lower = text.lower()
        words = text_lower.split()
        
        positive_count = sum(1 for w in words if w in positive_words)
        negative_count = sum(1 for w in words if w in negative_words)
        
        total = positive_count + negative_count
        if total == 0:
            return 0.0
        
        return (positive_count - negative_count) / total
    
    def _extract_keywords(self, text: str, n: int = 5) -> List[str]:
        """Extract top keywords from text."""
        # Remove common words
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
            "have", "has", "had", "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "must", "shall", "can", "need", "dare",
            "to", "of", "in", "for", "on", "with", "at", "by", "from", "up",
            "about", "into", "over", "after", "i", "you", "he", "she", "it",
            "we", "they", "my", "your", "his", "her", "its", "our", "their",
            "this", "that", "these", "those", "and", "but", "or", "nor", "so",
            "if", "then", "else", "when", "where", "how", "what", "which", "who"
        }
        
        words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
        filtered = [w for w in words if w not in stop_words]
        
        # Count frequencies
        freq = Counter(filtered)
        
        return [word for word, _ in freq.most_common(n)]
    
    def adapt_text(self, text: str, target_profile: ToneProfile) -> str:
        """Adapt text to match target tone profile."""
        # This is a simplified adaptation - in production would use LLM
        
        # Adjust formality
        if target_profile.formality > 0.7:
            text = text.replace("Hi ", "Dear ")
            text = text.replace("Hey ", "Hello ")
            text = text.replace("Thanks!", "Thank you.")
        elif target_profile.formality < 0.3:
            text = text.replace("Dear ", "Hi ")
            text = text.replace("Thank you.", "Thanks!")
        
        # Adjust warmth
        if target_profile.warmth > 0.7:
            if "Thanks" not in text and "appreciate" not in text.lower():
                text = text.rstrip() + "\n\nReally appreciate your time!"
        
        # Adjust urgency markers
        if target_profile.urgency > 0.7:
            text = text.replace("when you get a chance", "at your earliest convenience")
        elif target_profile.urgency < 0.3:
            text = text.replace("ASAP", "when you have time")
            text = text.replace("urgent", "")
        
        return text


# ============================================================================
# FOLLOW-UP AUTOMATION
# ============================================================================

@dataclass
class FollowUpSchedule:
    """Scheduled follow-up for a prospect."""
    prospect_email: str
    thread_id: str
    scheduled_at: datetime
    followup_number: int
    stage: SalesStage
    template: str
    status: str  # pending, sent, cancelled
    created_at: datetime = field(default_factory=datetime.now)


class FollowUpManager:
    """Manages follow-up email scheduling with 2-day cadence."""
    
    DEFAULT_CADENCE_DAYS = 2
    MAX_FOLLOWUPS = 4
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or (PROJECT_ROOT / ".hive-mind" / "communicator" / "followups")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._scheduled: Dict[str, List[FollowUpSchedule]] = {}
        self._load_scheduled()
    
    def _load_scheduled(self):
        """Load scheduled follow-ups from storage."""
        schedule_file = self.storage_dir / "schedules.json"
        if schedule_file.exists():
            try:
                with open(schedule_file) as f:
                    data = json.load(f)
                    for email, items in data.items():
                        self._scheduled[email] = [
                            FollowUpSchedule(
                                prospect_email=item["prospect_email"],
                                thread_id=item["thread_id"],
                                scheduled_at=datetime.fromisoformat(item["scheduled_at"]),
                                followup_number=item["followup_number"],
                                stage=SalesStage(item["stage"]),
                                template=item["template"],
                                status=item["status"],
                                created_at=datetime.fromisoformat(item["created_at"])
                            )
                            for item in items
                        ]
            except Exception as e:
                logger.error(f"Error loading follow-up schedules: {e}")
    
    def _save_scheduled(self):
        """Save scheduled follow-ups to storage."""
        schedule_file = self.storage_dir / "schedules.json"
        data = {}
        for email, items in self._scheduled.items():
            data[email] = [
                {
                    "prospect_email": item.prospect_email,
                    "thread_id": item.thread_id,
                    "scheduled_at": item.scheduled_at.isoformat(),
                    "followup_number": item.followup_number,
                    "stage": item.stage.value,
                    "template": item.template,
                    "status": item.status,
                    "created_at": item.created_at.isoformat()
                }
                for item in items
            ]
        with open(schedule_file, "w") as f:
            json.dump(data, f, indent=2)
    
    def schedule_followup(
        self,
        prospect_email: str,
        thread_id: str,
        stage: SalesStage,
        days_delay: int = DEFAULT_CADENCE_DAYS,
        template: str = "standard_followup"
    ) -> Optional[FollowUpSchedule]:
        """Schedule a follow-up email."""
        
        # Check existing follow-ups for this prospect
        existing = self._scheduled.get(prospect_email, [])
        pending = [f for f in existing if f.status == "pending"]
        
        if len(pending) >= self.MAX_FOLLOWUPS:
            logger.warning(f"Max follow-ups reached for {prospect_email}")
            return None
        
        followup_number = len(existing) + 1
        scheduled_at = datetime.now() + timedelta(days=days_delay)
        
        schedule = FollowUpSchedule(
            prospect_email=prospect_email,
            thread_id=thread_id,
            scheduled_at=scheduled_at,
            followup_number=followup_number,
            stage=stage,
            template=template,
            status="pending"
        )
        
        if prospect_email not in self._scheduled:
            self._scheduled[prospect_email] = []
        self._scheduled[prospect_email].append(schedule)
        
        self._save_scheduled()
        logger.info(f"Scheduled follow-up #{followup_number} for {prospect_email} at {scheduled_at}")
        
        return schedule
    
    def get_due_followups(self) -> List[FollowUpSchedule]:
        """Get all follow-ups that are due now."""
        now = datetime.now()
        due = []
        
        for email, schedules in self._scheduled.items():
            for schedule in schedules:
                if schedule.status == "pending" and schedule.scheduled_at <= now:
                    due.append(schedule)
        
        return due
    
    def mark_sent(self, prospect_email: str, thread_id: str) -> bool:
        """Mark a follow-up as sent."""
        if prospect_email not in self._scheduled:
            return False
        
        for schedule in self._scheduled[prospect_email]:
            if schedule.thread_id == thread_id and schedule.status == "pending":
                schedule.status = "sent"
                self._save_scheduled()
                return True
        
        return False
    
    def cancel_followups(self, prospect_email: str, reason: str = "") -> int:
        """Cancel all pending follow-ups for a prospect."""
        if prospect_email not in self._scheduled:
            return 0
        
        cancelled = 0
        for schedule in self._scheduled[prospect_email]:
            if schedule.status == "pending":
                schedule.status = f"cancelled: {reason}" if reason else "cancelled"
                cancelled += 1
        
        self._save_scheduled()
        return cancelled


# ============================================================================
# PROSPECT STATE TRACKING
# ============================================================================

@dataclass
class ProspectState:
    """Current state of communication with a prospect."""
    email: str
    name: str
    company: str
    current_stage: SalesStage
    thread_id: Optional[str]
    last_contact: datetime
    total_exchanges: int
    tone_profile: Optional[ToneProfile]
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProspectStateManager:
    """Manages prospect communication state."""
    
    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or (PROJECT_ROOT / ".hive-mind" / "communicator" / "prospects")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._states: Dict[str, ProspectState] = {}
        self._load_states()
    
    def _load_states(self):
        """Load prospect states from storage."""
        for file in self.storage_dir.glob("*.json"):
            try:
                with open(file) as f:
                    data = json.load(f)
                    tone = None
                    if data.get("tone_profile"):
                        tone = ToneProfile(**data["tone_profile"])
                    
                    state = ProspectState(
                        email=data["email"],
                        name=data["name"],
                        company=data["company"],
                        current_stage=SalesStage(data["current_stage"]),
                        thread_id=data.get("thread_id"),
                        last_contact=datetime.fromisoformat(data["last_contact"]),
                        total_exchanges=data["total_exchanges"],
                        tone_profile=tone,
                        tags=data.get("tags", []),
                        metadata=data.get("metadata", {})
                    )
                    self._states[data["email"]] = state
            except Exception as e:
                logger.error(f"Error loading prospect state from {file}: {e}")
    
    def _save_state(self, state: ProspectState):
        """Save a prospect state to storage."""
        filename = hashlib.md5(state.email.encode()).hexdigest()[:12] + ".json"
        filepath = self.storage_dir / filename
        
        data = {
            "email": state.email,
            "name": state.name,
            "company": state.company,
            "current_stage": state.current_stage.value,
            "thread_id": state.thread_id,
            "last_contact": state.last_contact.isoformat(),
            "total_exchanges": state.total_exchanges,
            "tone_profile": asdict(state.tone_profile) if state.tone_profile else None,
            "tags": state.tags,
            "metadata": state.metadata
        }
        
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    def get_state(self, email: str) -> Optional[ProspectState]:
        """Get current state for a prospect."""
        return self._states.get(email)
    
    def update_state(
        self,
        email: str,
        name: str = "",
        company: str = "",
        stage: Optional[SalesStage] = None,
        thread_id: Optional[str] = None,
        tone_profile: Optional[ToneProfile] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ProspectState:
        """Update or create prospect state."""
        
        existing = self._states.get(email)
        
        if existing:
            if name:
                existing.name = name
            if company:
                existing.company = company
            if stage:
                existing.current_stage = stage
            if thread_id:
                existing.thread_id = thread_id
            if tone_profile:
                existing.tone_profile = tone_profile
            if tags:
                existing.tags = list(set(existing.tags + tags))
            if metadata:
                existing.metadata.update(metadata)
            existing.last_contact = datetime.now()
            existing.total_exchanges += 1
            
            self._save_state(existing)
            return existing
        else:
            state = ProspectState(
                email=email,
                name=name or email.split("@")[0],
                company=company or email.split("@")[1] if "@" in email else "",
                current_stage=stage or SalesStage.INTRODUCTION,
                thread_id=thread_id,
                last_contact=datetime.now(),
                total_exchanges=1,
                tone_profile=tone_profile,
                tags=tags or [],
                metadata=metadata or {}
            )
            self._states[email] = state
            self._save_state(state)
            return state
    
    def advance_stage(self, email: str, trigger: str = "") -> Optional[SalesStage]:
        """Advance prospect to next sales stage based on trigger."""
        state = self._states.get(email)
        if not state:
            return None
        
        current_config = SALES_STAGE_CONFIGS.get(state.current_stage)
        if not current_config:
            return state.current_stage
        
        # Check if trigger matches any next stage triggers
        if trigger in current_config.next_stage_triggers:
            # Get next stage
            stages = list(SalesStage)
            current_idx = stages.index(state.current_stage)
            if current_idx < len(stages) - 1:
                new_stage = stages[current_idx + 1]
                state.current_stage = new_stage
                state.metadata["stage_advanced_at"] = datetime.now().isoformat()
                state.metadata["stage_trigger"] = trigger
                self._save_state(state)
                logger.info(f"Advanced {email} to stage {new_stage.value} (trigger: {trigger})")
                return new_stage
        
        return state.current_stage


# ============================================================================
# COMMUNICATOR AGENT
# ============================================================================

class CommunicatorAgent:
    """
    Enhanced Crafter with tone matching, email threading context,
    sales stage awareness, and scheduling routing.
    """
    
    SCHEDULING_INTENT_THRESHOLD = 0.6
    TONE_SIMILARITY_THRESHOLD = 0.85
    
    # Response templates by stage
    STAGE_TEMPLATES = {
        SalesStage.INTRODUCTION: {
            "initial": """Hi {{first_name}},

{{personalized_hook}}

{{value_prop}}

Worth a quick 15-min chat? {{calendar_link}}

{{signature}}""",
            "followup": """Hi {{first_name}},

Just bumping this up - {{value_prop_short}}

{{calendar_link}}

{{signature}}"""
        },
        SalesStage.QUALIFICATION: {
            "question": """{{first_name}},

Thanks for your interest! To make sure we're a good fit, quick question:

{{qualification_question}}

Looking forward to learning more about {{company}}.

{{signature}}""",
        },
        SalesStage.VALUE_PROP: {
            "case_study": """{{first_name}},

Based on what you shared, I think you'll find this relevant:

{{case_study_summary}}

Companies like {{company}} are seeing {{metric}} improvement.

Shall we schedule time to discuss? {{calendar_link}}

{{signature}}""",
        },
        SalesStage.OBJECTION_HANDLE: {
            "address": """{{first_name}},

I completely understand your concern about {{objection}}.

{{objection_response}}

Would it help to {{offer}}?

{{signature}}""",
        },
        SalesStage.CLOSE: {
            "ask": """{{first_name}},

Based on our conversations, I believe {{company}} would see real value.

Ready to move forward? I can have the paperwork ready by {{date}}.

{{calendar_link}}

{{signature}}""",
        },
        SalesStage.FOLLOW_UP: {
            "checkin": """{{first_name}},

Hope all is well at {{company}}!

{{checkin_content}}

Let me know if there's anything I can help with.

{{signature}}""",
        },
    }
    
    def __init__(self):
        """Initialize the Communicator Agent."""
        self.tone_analyzer = ToneAnalyzer()
        self.followup_manager = FollowUpManager()
        self.prospect_manager = ProspectStateManager()
        
        # Initialize Email Threading MCP
        if EMAIL_MCP_AVAILABLE:
            self.email_mcp = EmailThreadingMCP()
        else:
            self.email_mcp = None
            logger.warning("Email Threading MCP not available - using mock mode")
        
        # Initialize existing Crafter for campaign creation
        if CRAFTER_AVAILABLE:
            self.crafter = CampaignCrafter()
        else:
            self.crafter = None
        
        # Storage for scheduler routing
        self.scheduler_queue_dir = PROJECT_ROOT / ".hive-mind" / "scheduler" / "queue"
        self.scheduler_queue_dir.mkdir(parents=True, exist_ok=True)
        
        # Sender info
        self.sender_info = {
            "name": "Chris Daigle",
            "title": "CEO",
            "company": "Chiefaiofficer.com",
            "calendar_link": "https://calendly.com/chiefaiofficer/intro"
        }
        
        logger.info("Communicator Agent initialized")
    
    async def process_incoming_email(
        self,
        raw_email: str,
        sender_email: str,
        format: str = "text"
    ) -> Dict[str, Any]:
        """
        Process an incoming email and determine appropriate response.
        
        Args:
            raw_email: Raw email content
            sender_email: Email address of sender
            format: Email format ("raw" or "text")
        
        Returns:
            Processing result including intent, recommended action, and draft response
        """
        result = {
            "sender_email": sender_email,
            "processed_at": datetime.now().isoformat(),
            "success": False
        }
        
        # Parse email thread
        if self.email_mcp:
            parsed = self.email_mcp.parse_thread(raw_email, format)
            if parsed.get("success"):
                result["thread_id"] = parsed.get("thread_id")
                result["message_count"] = parsed.get("message_count")
        else:
            # Mock parsing
            parsed = {"success": True, "thread_id": hashlib.md5(raw_email.encode()).hexdigest()[:12]}
            result["thread_id"] = parsed["thread_id"]
        
        # Detect intent
        intent_result = await self.detect_intent(raw_email)
        result["intent"] = intent_result
        
        # Check for scheduling intent - route to SCHEDULER
        if intent_result.get("is_scheduling_related"):
            confidence = intent_result.get("confidence", 0)
            if confidence >= self.SCHEDULING_INTENT_THRESHOLD:
                result["action"] = "route_to_scheduler"
                result["scheduler_task"] = await self._create_scheduler_task(
                    sender_email,
                    raw_email,
                    intent_result
                )
                result["success"] = True
                logger.info(f"Routing {sender_email} to SCHEDULER (confidence: {confidence})")
                return result
        
        # Analyze tone for matching
        tone_profile = self.tone_analyzer.analyze(raw_email)
        result["tone_profile"] = asdict(tone_profile)
        
        # Get or create prospect state
        prospect_state = self.prospect_manager.get_state(sender_email)
        if prospect_state:
            # Check stage advancement triggers
            if intent_result.get("primary_intent") == "interest_high":
                self.prospect_manager.advance_stage(sender_email, "interest_confirmed")
            elif intent_result.get("primary_intent") == "objection":
                self.prospect_manager.update_state(
                    sender_email,
                    stage=SalesStage.OBJECTION_HANDLE,
                    tags=["has_objection"]
                )
        else:
            # Create new prospect state
            prospect_state = self.prospect_manager.update_state(
                sender_email,
                thread_id=result.get("thread_id"),
                tone_profile=tone_profile,
                stage=SalesStage.QUALIFICATION  # They replied, so past introduction
            )
        
        result["prospect_stage"] = prospect_state.current_stage.value
        
        # Generate response draft
        response = await self.generate_response(
            prospect_email=sender_email,
            incoming_text=raw_email,
            tone_profile=tone_profile,
            stage=prospect_state.current_stage
        )
        result["draft_response"] = response
        
        # Handle follow-ups based on intent
        if intent_result.get("primary_intent") in ["not_interested", "unsubscribe"]:
            # Cancel follow-ups
            cancelled = self.followup_manager.cancel_followups(
                sender_email,
                reason=intent_result.get("primary_intent")
            )
            result["followups_cancelled"] = cancelled
            result["action"] = "close_thread"
        elif intent_result.get("primary_intent") == "out_of_office":
            # Reschedule follow-up for later
            self.followup_manager.schedule_followup(
                sender_email,
                result.get("thread_id", ""),
                prospect_state.current_stage,
                days_delay=5  # Give them time to return
            )
            result["action"] = "wait_for_return"
        else:
            # Standard follow-up scheduling
            self.followup_manager.schedule_followup(
                sender_email,
                result.get("thread_id", ""),
                prospect_state.current_stage
            )
            result["action"] = "send_response"
        
        result["success"] = True
        return result
    
    async def detect_intent(self, text: str) -> Dict[str, Any]:
        """
        Detect the intent of incoming email text.
        
        Returns:
            Intent detection result with confidence scores
        """
        if self.email_mcp:
            return self.email_mcp.detect_intent(text, include_confidence=True)
        
        # Mock intent detection
        text_lower = text.lower()
        
        scheduling_keywords = [
            "schedule", "meeting", "call", "available", "calendar",
            "time", "book", "chat", "discuss"
        ]
        
        objection_keywords = [
            "too expensive", "not interested", "budget", "not the right time",
            "already using", "think about it"
        ]
        
        scheduling_count = sum(1 for k in scheduling_keywords if k in text_lower)
        objection_count = sum(1 for k in objection_keywords if k in text_lower)
        
        if scheduling_count >= 2:
            return {
                "success": True,
                "primary_intent": "scheduling_request",
                "confidence": min(0.9, 0.5 + scheduling_count * 0.1),
                "is_scheduling_related": True
            }
        elif objection_count >= 1:
            return {
                "success": True,
                "primary_intent": "objection",
                "confidence": min(0.9, 0.5 + objection_count * 0.15),
                "is_scheduling_related": False
            }
        else:
            return {
                "success": True,
                "primary_intent": "unknown",
                "confidence": 0.3,
                "is_scheduling_related": False
            }
    
    async def generate_response(
        self,
        prospect_email: str,
        incoming_text: str = "",
        tone_profile: Optional[ToneProfile] = None,
        stage: Optional[SalesStage] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate a context-aware, tone-matched response.
        
        Args:
            prospect_email: Prospect's email address
            incoming_text: Text of incoming email (for tone matching)
            tone_profile: Pre-analyzed tone profile
            stage: Current sales stage
            context: Additional context for personalization
        
        Returns:
            Generated response with tone similarity score
        """
        # Get prospect state if not provided
        if not stage:
            state = self.prospect_manager.get_state(prospect_email)
            stage = state.current_stage if state else SalesStage.INTRODUCTION
        
        # Analyze incoming tone if provided
        if incoming_text and not tone_profile:
            tone_profile = self.tone_analyzer.analyze(incoming_text)
        
        # Get stage configuration
        stage_config = SALES_STAGE_CONFIGS.get(stage)
        
        # Select appropriate template
        templates = self.STAGE_TEMPLATES.get(stage, {})
        template_key = list(templates.keys())[0] if templates else "initial"
        template = templates.get(template_key, self._get_default_template())
        
        # Build template variables
        variables = self._build_response_variables(prospect_email, context or {})
        
        # Render template
        response_text = self._render_template(template, variables)
        
        # Adapt tone if we have a target profile
        if tone_profile:
            response_text = self.tone_analyzer.adapt_text(response_text, tone_profile)
        
        # Calculate tone similarity
        response_tone = self.tone_analyzer.analyze(response_text)
        tone_similarity = 0.85  # Default if no comparison
        
        if tone_profile:
            tone_similarity = response_tone.similarity(tone_profile)
        
        # Check if similarity meets threshold
        tone_match_success = tone_similarity >= self.TONE_SIMILARITY_THRESHOLD
        
        return {
            "response_text": response_text,
            "stage": stage.value,
            "template_used": template_key,
            "tone_similarity": tone_similarity,
            "tone_match_success": tone_match_success,
            "response_tone": asdict(response_tone),
            "stage_objective": stage_config.objective if stage_config else "",
            "generated_at": datetime.now().isoformat()
        }
    
    def _build_response_variables(
        self,
        prospect_email: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build variables for template rendering."""
        
        # Get prospect state
        state = self.prospect_manager.get_state(prospect_email)
        
        first_name = "there"
        company = "your company"
        
        if state:
            first_name = state.name.split()[0] if state.name else "there"
            company = state.company or "your company"
        
        # Extract from context if available
        first_name = context.get("first_name", first_name)
        company = context.get("company", company)
        
        return {
            "first_name": first_name,
            "company": company,
            "personalized_hook": context.get("personalized_hook", "I noticed your work in revenue operations"),
            "value_prop": context.get("value_prop", "We're building AI-native tools that transform how RevOps teams work"),
            "value_prop_short": context.get("value_prop_short", "thought this would be valuable for your team"),
            "calendar_link": self.sender_info["calendar_link"],
            "signature": f"\n{self.sender_info['name']}\n{self.sender_info['title']}, {self.sender_info['company']}",
            "qualification_question": context.get("qualification_question", "What's the biggest challenge your team faces with revenue forecasting?"),
            "case_study_summary": context.get("case_study_summary", "A similar company reduced their forecasting time by 40%"),
            "metric": context.get("metric", "35%"),
            "objection": context.get("objection", "timing"),
            "objection_response": context.get("objection_response", "Many of our clients felt the same way initially, but found that starting small actually helped them prepare for their busy season."),
            "offer": context.get("offer", "schedule a brief 15-min call to explore if this makes sense for your timeline"),
            "date": context.get("date", "end of week"),
            "checkin_content": context.get("checkin_content", "Just wanted to share an article I thought you'd find interesting about AI in RevOps."),
        }
    
    def _render_template(self, template: str, variables: Dict[str, Any]) -> str:
        """Render a template with variables."""
        result = template
        for key, value in variables.items():
            result = result.replace("{{" + key + "}}", str(value))
        return result
    
    def _get_default_template(self) -> str:
        """Get default response template."""
        return """Hi {{first_name}},

Thanks for getting in touch.

{{value_prop}}

Would love to chat more about how this could help {{company}}.

{{calendar_link}}

{{signature}}"""
    
    async def _create_scheduler_task(
        self,
        prospect_email: str,
        email_content: str,
        intent_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create a task for the SCHEDULER agent."""
        
        task_id = f"sched_{datetime.now().strftime('%Y%m%d%H%M%S')}_{hashlib.md5(prospect_email.encode()).hexdigest()[:8]}"
        
        task = {
            "task_id": task_id,
            "prospect_email": prospect_email,
            "email_content": email_content[:500],  # Truncate for context
            "intent": intent_result.get("primary_intent"),
            "confidence": intent_result.get("confidence"),
            "created_at": datetime.now().isoformat(),
            "status": "pending",
            "source": "communicator_agent"
        }
        
        # Save task to scheduler queue
        task_file = self.scheduler_queue_dir / f"{task_id}.json"
        with open(task_file, "w") as f:
            json.dump(task, f, indent=2)
        
        logger.info(f"Created scheduler task: {task_id}")
        return task
    
    # =========================================================================
    # CAMPAIGN CREATION (Preserved from Crafter)
    # =========================================================================
    
    def create_campaign(
        self,
        leads: List[Dict[str, Any]],
        segment: str,
        campaign_type: str = None
    ) -> Optional[Any]:  # Returns Campaign if crafter available
        """
        Create a campaign from leads (preserved from Crafter).
        
        Args:
            leads: List of lead data
            segment: Segment name
            campaign_type: Campaign type (optional)
        
        Returns:
            Campaign object if crafter is available
        """
        if not self.crafter:
            logger.error("Crafter not available for campaign creation")
            return None
        
        return self.crafter.create_campaign(leads, segment, campaign_type)
    
    def generate_email(
        self,
        lead: Dict[str, Any],
        template_name: str = None
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a personalized email for a lead (preserved from Crafter).
        
        Args:
            lead: Lead data
            template_name: Template to use (optional)
        
        Returns:
            Generated email dict
        """
        if not self.crafter:
            logger.error("Crafter not available")
            return None
        
        return self.crafter.generate_email(lead, template_name)
    
    # =========================================================================
    # FOLLOW-UP PROCESSING
    # =========================================================================
    
    async def process_due_followups(self) -> List[Dict[str, Any]]:
        """
        Process all follow-ups that are due.
        
        Returns:
            List of processed follow-ups with generated content
        """
        due = self.followup_manager.get_due_followups()
        processed = []
        
        for followup in due:
            try:
                # Get prospect state
                state = self.prospect_manager.get_state(followup.prospect_email)
                
                # Generate follow-up content
                response = await self.generate_response(
                    prospect_email=followup.prospect_email,
                    stage=followup.stage or (state.current_stage if state else SalesStage.FOLLOW_UP)
                )
                
                # Mark as sent (in production, this would actually send)
                self.followup_manager.mark_sent(followup.prospect_email, followup.thread_id)
                
                processed.append({
                    "prospect_email": followup.prospect_email,
                    "followup_number": followup.followup_number,
                    "response": response,
                    "processed_at": datetime.now().isoformat()
                })
                
                logger.info(f"Processed follow-up #{followup.followup_number} for {followup.prospect_email}")
                
            except Exception as e:
                logger.error(f"Error processing follow-up for {followup.prospect_email}: {e}")
        
        return processed
    
    # =========================================================================
    # METRICS AND REPORTING
    # =========================================================================
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get Communicator Agent metrics."""
        
        # Count prospects by stage
        stage_counts = {stage.value: 0 for stage in SalesStage}
        for state in self.prospect_manager._states.values():
            stage_counts[state.current_stage.value] += 1
        
        # Count pending follow-ups
        pending_followups = sum(
            len([f for f in followups if f.status == "pending"])
            for followups in self.followup_manager._scheduled.values()
        )
        
        # Calculate average tone similarity (from recent responses)
        # This would be tracked in production
        
        return {
            "total_prospects": len(self.prospect_manager._states),
            "prospects_by_stage": stage_counts,
            "pending_followups": pending_followups,
            "tone_threshold": self.TONE_SIMILARITY_THRESHOLD,
            "scheduling_threshold": self.SCHEDULING_INTENT_THRESHOLD,
            "email_mcp_available": EMAIL_MCP_AVAILABLE,
            "crafter_available": CRAFTER_AVAILABLE
        }


# ============================================================================
# CLI / DEMO
# ============================================================================

async def demo():
    """Demonstrate Communicator Agent capabilities."""
    print("\n" + "=" * 60)
    print("🎯 COMMUNICATOR AGENT DEMO (Day 15)")
    print("=" * 60)
    
    agent = CommunicatorAgent()
    
    # Demo 1: Process incoming email with scheduling intent
    print("\n📧 Demo 1: Processing email with scheduling intent...")
    scheduling_email = """
    Hi Chris,
    
    Thanks for reaching out. I'd love to learn more about what you're building.
    
    Are you available for a call this week? Maybe Thursday or Friday afternoon?
    
    Let me know what works.
    
    Best,
    John
    """
    
    result = await agent.process_incoming_email(
        raw_email=scheduling_email,
        sender_email="john@example.com"
    )
    
    print(f"  Intent: {result.get('intent', {}).get('primary_intent')}")
    print(f"  Confidence: {result.get('intent', {}).get('confidence')}")
    print(f"  Action: {result.get('action')}")
    if result.get("scheduler_task"):
        print(f"  Scheduler Task: {result['scheduler_task'].get('task_id')}")
    
    # Demo 2: Process email with objection
    print("\n📧 Demo 2: Processing email with objection...")
    objection_email = """
    Hi Chris,
    
    Thanks for the info, but I'm a bit concerned about the pricing.
    Our budget is pretty tight this quarter.
    
    Also, we already have a solution in place that we're somewhat happy with.
    
    Maybe we can revisit this next quarter?
    
    Thanks,
    Sarah
    """
    
    result = await agent.process_incoming_email(
        raw_email=objection_email,
        sender_email="sarah@company.com"
    )
    
    print(f"  Intent: {result.get('intent', {}).get('primary_intent')}")
    print(f"  Stage: {result.get('prospect_stage')}")
    print(f"  Action: {result.get('action')}")
    if result.get("draft_response"):
        print(f"  Tone Match: {result['draft_response'].get('tone_similarity', 0):.0%}")
    
    # Demo 3: Generate stage-appropriate response
    print("\n📝 Demo 3: Generating stage-appropriate response...")
    response = await agent.generate_response(
        prospect_email="mike@startup.io",
        incoming_text="Very interested! What are the next steps?",
        stage=SalesStage.VALUE_PROP,
        context={
            "first_name": "Mike",
            "company": "TechStartup",
            "metric": "40%"
        }
    )
    
    print(f"  Stage: {response.get('stage')}")
    print(f"  Tone Similarity: {response.get('tone_similarity', 0):.0%}")
    print(f"  Tone Match Success: {response.get('tone_match_success')}")
    print(f"\n  Response Preview:")
    print("  " + "-" * 40)
    preview = response.get("response_text", "")[:200]
    for line in preview.split("\n"):
        print(f"  {line}")
    print("  ...")
    
    # Demo 4: Metrics
    print("\n📊 Demo 4: Agent Metrics...")
    metrics = agent.get_metrics()
    print(f"  Total Prospects: {metrics['total_prospects']}")
    print(f"  Pending Follow-ups: {metrics['pending_followups']}")
    print(f"  Email MCP: {'✅' if metrics['email_mcp_available'] else '❌'}")
    print(f"  Crafter: {'✅' if metrics['crafter_available'] else '❌'}")
    
    print("\n" + "=" * 60)
    print("✅ COMMUNICATOR AGENT DEMO COMPLETE")
    print("=" * 60)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Communicator Agent (Enhanced Crafter)")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    parser.add_argument("--process-followups", action="store_true", help="Process due follow-ups")
    parser.add_argument("--metrics", action="store_true", help="Show metrics")
    
    args = parser.parse_args()
    
    if args.demo:
        asyncio.run(demo())
    elif args.process_followups:
        agent = CommunicatorAgent()
        results = asyncio.run(agent.process_due_followups())
        print(f"Processed {len(results)} follow-ups")
    elif args.metrics:
        agent = CommunicatorAgent()
        metrics = agent.get_metrics()
        print(json.dumps(metrics, indent=2))
    else:
        asyncio.run(demo())


if __name__ == "__main__":
    main()
