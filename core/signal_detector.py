"""
Signal Detector Module
======================
Analyzes lead data (from RB2B, Clay, etc.) to detect specific intent signals.
These signals drive the selection of highly relevant email angles.

Signals Detected:
- HIRING: Active job postings for relevant roles (AI, Data, Transformation)
- TECH_STACK: Usage of specific tools (Salesforce, HubSpot, etc.)
- INTENT: High-intent website behavior (Pricing page, Case studies)
- FUNDING: Recent funding rounds (if available)
"""

from typing import Dict, Any, List, Set
from enum import Enum
from dataclasses import dataclass

class SignalType(Enum):
    HIRING = "hiring"
    TECH_STACK = "tech_stack"
    HIGH_INTENT = "high_intent"
    FUNDING = "funding"
    GENERAL = "general"

@dataclass
class DetectedSignal:
    type: SignalType
    value: str
    confidence: float
    source: str

class SignalDetector:
    """Detects business signals from lead data."""
    
    def __init__(self):
        # Hiring keywords from HoS Requirements - AI/Data/Transformation roles
        self.hiring_keywords = [
            "ai engineer", "data scientist", "machine learning", 
            "head of ai", "director of data", "digital transformation",
            "revops", "revenue operations", "chief ai officer",
            "ai lead", "ai strategist", "data analyst", "ml engineer",
            "vp of ai", "head of data", "ai architect", "data engineer",
            "ai/ml", "artificial intelligence", "automation engineer"
        ]
        
        # Tech stack keywords - Tools that indicate good fit
        self.tech_stack_keywords = [
            "salesforce", "hubspot", "marketo", "pardot", "outreach", 
            "salesloft", "gong", "chilipiper", "zapier", "make",
            "airtable", "notion", "slack", "monday", "asana",
            "zendesk", "intercom", "freshdesk", "servicenow"
        ]
        
        # Industry keywords for Tier 1 Angle B
        self.industry_keywords = [
            "construction", "manufacturing", "real estate", "legal",
            "law firm", "cpa", "accounting", "consulting", "agency",
            "staffing", "recruitment", "brokerage", "property management"
        ]
        
        self.intent_pages = [
            "pricing", "case-studies", "book-a-demo", "contact",
            "solutions/enterprise", "case-study", "demo", "schedule"
        ]


    def detect_signals(self, lead_data: Dict[str, Any]) -> List[DetectedSignal]:
        """
        Analyze lead data and return a list of detected signals.
        
        Args:
            lead_data: Dictionary containing lead info (normalized)
            
        Returns:
            List of DetectedSignal objects
        """
        signals = []
        
        # 1. Detect Hiring Signals
        # Check 'open_jobs' or description fields if available
        # RB2B/Clay might provide this in various fields
        job_data = str(lead_data.get("hiring", "")).lower() + " " + \
                   str(lead_data.get("open_roles", "")).lower()
        
        for keyword in self.hiring_keywords:
            if keyword in job_data:
                signals.append(DetectedSignal(
                    type=SignalType.HIRING,
                    value=keyword,
                    confidence=0.9,
                    source="hiring_data"
                ))
                break # Found one strong hiring signal
                
        # 2. Tech Stack Signals
        # Check 'technologies', 'tools', or 'tech_stack'
        tech_data = lead_data.get("technologies", [])
        if isinstance(tech_data, str):
            tech_data = [t.strip().lower() for t in tech_data.split(",")]
        elif isinstance(tech_data, list):
            tech_data = [str(t).lower() for t in tech_data]
            
        for tool in self.tech_stack_keywords:
            for detected_tech in tech_data:
                if tool in detected_tech:
                    signals.append(DetectedSignal(
                        type=SignalType.TECH_STACK,
                        value=tool,
                        confidence=1.0,
                        source="tech_stack_data"
                    ))
        
        # 3. Intent Signals (Website Behavior)
        pages_viewed = lead_data.get("pages_viewed", [])
        if isinstance(pages_viewed, str):
            pages_viewed = [pages_viewed]
            
        for page in pages_viewed:
            page_lower = str(page).lower()
            for intent_keyword in self.intent_pages:
                if intent_keyword in page_lower:
                    signals.append(DetectedSignal(
                        type=SignalType.HIGH_INTENT,
                        value=intent_keyword,
                        confidence=0.8,
                        source="website_behavior"
                    ))
                    
        return signals

    def get_primary_signal(self, signals: List[DetectedSignal]) -> DetectedSignal:
        """
        Determine the most important signal to act upon.
        Priority: HIRING > TECH_STACK > HIGH_INTENT > GENERAL
        """
        if not signals:
            return DetectedSignal(SignalType.GENERAL, "generic", 0.0, "default")
            
        # Priority map
        priority = {
            SignalType.HIRING: 1,
            SignalType.TECH_STACK: 2,
            SignalType.HIGH_INTENT: 3,
            SignalType.FUNDING: 4,
            SignalType.GENERAL: 5
        }
        
        # Sort by priority
        sorted_signals = sorted(signals, key=lambda s: priority.get(s.type, 99))
        return sorted_signals[0]
