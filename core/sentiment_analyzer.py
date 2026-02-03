#!/usr/bin/env python3
"""
Sentiment Analyzer - Revenue Swarm Intelligence
================================================

Analyzes email replies, conversations, and engagement patterns to:
- Classify sentiment (positive, neutral, negative, objection)
- Detect buying signals
- Identify objection types
- Recommend responses
- Adjust lead scores based on sentiment
"""

import re
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentiment")


class Sentiment(Enum):
    VERY_POSITIVE = "very_positive"
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    VERY_NEGATIVE = "very_negative"
    OBJECTION = "objection"


class ObjectionType(Enum):
    PRICE = "price"
    TIMING = "timing"
    AUTHORITY = "authority"
    NEED = "need"
    TRUST = "trust"
    COMPETITOR = "competitor"
    NONE = "none"


class BuyingSignal(Enum):
    HIGH_INTENT = "high_intent"
    MEDIUM_INTENT = "medium_intent"
    LOW_INTENT = "low_intent"
    NO_INTENT = "no_intent"


# =============================================================================
# SENTIMENT KEYWORDS
# =============================================================================

POSITIVE_SIGNALS = {
    "very_positive": [
        "love this", "perfect", "exactly what we need", "sign me up",
        "let's do it", "ready to start", "when can we begin",
        "this is great", "impressed", "excited", "let's move forward",
        "send me the contract", "how do we get started", "i'm in"
    ],
    "positive": [
        "interested", "sounds good", "tell me more", "like to learn",
        "makes sense", "good timing", "worth exploring", "curious",
        "open to", "let's chat", "schedule a call", "send info",
        "would love to", "appreciate", "helpful", "thanks for reaching out"
    ],
}

NEGATIVE_SIGNALS = {
    "very_negative": [
        "not interested", "stop emailing", "remove me", "unsubscribe",
        "spam", "don't contact", "never contact", "leave me alone",
        "harassment", "reported", "blocking"
    ],
    "negative": [
        "no thanks", "not right now", "not a fit", "doesn't apply",
        "wrong person", "not the decision maker", "already have",
        "not looking", "bad timing", "no budget", "pass",
        "not for us", "decline", "busy"
    ],
}

OBJECTION_PATTERNS = {
    ObjectionType.PRICE: [
        "too expensive", "cost", "budget", "afford", "price",
        "cheaper", "discount", "investment", "roi", "pricing",
        "what's the cost", "how much", "fees", "rates"
    ],
    ObjectionType.TIMING: [
        "bad timing", "not now", "next quarter", "next year",
        "too busy", "swamped", "in the middle of", "revisit later",
        "reach out in", "check back", "maybe later", "down the road"
    ],
    ObjectionType.AUTHORITY: [
        "not my decision", "need to check with", "boss decides",
        "committee", "board approval", "multiple stakeholders",
        "run it by", "get buy-in", "talk to my team"
    ],
    ObjectionType.NEED: [
        "don't need", "already have", "solved", "not a problem",
        "working fine", "no pain", "not a priority", "not relevant",
        "doesn't apply", "happy with current"
    ],
    ObjectionType.TRUST: [
        "never heard of", "not sure about", "sounds too good",
        "skeptical", "prove it", "case studies", "references",
        "who else uses", "how long in business"
    ],
    ObjectionType.COMPETITOR: [
        "using competitor", "already have vendor", "locked in",
        "contract with", "working with another", "happy with provider",
        "just switched", "already implemented"
    ],
}

BUYING_SIGNAL_PATTERNS = {
    BuyingSignal.HIGH_INTENT: [
        "how do we start", "what's the process", "implementation",
        "timeline", "onboarding", "contract", "agreement", "pricing",
        "next steps", "when can you", "let's schedule", "demo",
        "pilot", "trial", "proof of concept"
    ],
    BuyingSignal.MEDIUM_INTENT: [
        "tell me more", "how does it work", "what's included",
        "features", "capabilities", "integrations", "support",
        "interested in learning", "could you explain", "sounds interesting"
    ],
    BuyingSignal.LOW_INTENT: [
        "just curious", "exploring options", "research", "comparing",
        "send information", "brochure", "website", "maybe later"
    ],
}

URGENCY_SIGNALS = [
    "asap", "urgent", "immediately", "this week", "right away",
    "soon as possible", "quickly", "fast", "now", "today"
]


# =============================================================================
# SENTIMENT ANALYSIS
# =============================================================================

@dataclass
class SentimentResult:
    sentiment: Sentiment
    confidence: float
    objection_type: ObjectionType
    buying_signal: BuyingSignal
    urgency_detected: bool
    key_phrases: List[str]
    score_adjustment: int  # Points to add/subtract from lead score
    recommended_action: str
    response_template: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "sentiment": self.sentiment.value,
            "confidence": self.confidence,
            "objection_type": self.objection_type.value,
            "buying_signal": self.buying_signal.value,
            "urgency_detected": self.urgency_detected,
            "key_phrases": self.key_phrases,
            "score_adjustment": self.score_adjustment,
            "recommended_action": self.recommended_action,
            "response_template": self.response_template,
        }


class SentimentAnalyzer:
    """Analyze text for sales-relevant sentiment and signals."""
    
    def __init__(self):
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Pre-compile regex patterns for efficiency."""
        self.positive_patterns = {
            level: [re.compile(rf'\b{re.escape(phrase)}\b', re.IGNORECASE) 
                    for phrase in phrases]
            for level, phrases in POSITIVE_SIGNALS.items()
        }
        
        self.negative_patterns = {
            level: [re.compile(rf'\b{re.escape(phrase)}\b', re.IGNORECASE) 
                    for phrase in phrases]
            for level, phrases in NEGATIVE_SIGNALS.items()
        }
        
        self.objection_patterns = {
            obj_type: [re.compile(rf'\b{re.escape(phrase)}\b', re.IGNORECASE) 
                       for phrase in phrases]
            for obj_type, phrases in OBJECTION_PATTERNS.items()
        }
        
        self.buying_patterns = {
            signal: [re.compile(rf'\b{re.escape(phrase)}\b', re.IGNORECASE) 
                     for phrase in phrases]
            for signal, phrases in BUYING_SIGNAL_PATTERNS.items()
        }
        
        self.urgency_patterns = [
            re.compile(rf'\b{re.escape(phrase)}\b', re.IGNORECASE) 
            for phrase in URGENCY_SIGNALS
        ]
    
    def analyze(self, text: str) -> SentimentResult:
        """Analyze text for sentiment and sales signals."""
        text_lower = text.lower()
        key_phrases = []
        
        # Score sentiment
        positive_score = 0
        negative_score = 0
        
        # Check very positive signals
        for pattern in self.positive_patterns.get("very_positive", []):
            if pattern.search(text):
                positive_score += 3
                key_phrases.append(pattern.pattern.replace(r'\b', ''))
        
        # Check positive signals
        for pattern in self.positive_patterns.get("positive", []):
            if pattern.search(text):
                positive_score += 1
                if len(key_phrases) < 5:
                    key_phrases.append(pattern.pattern.replace(r'\b', ''))
        
        # Check very negative signals
        for pattern in self.negative_patterns.get("very_negative", []):
            if pattern.search(text):
                negative_score += 3
                key_phrases.append(pattern.pattern.replace(r'\b', ''))
        
        # Check negative signals
        for pattern in self.negative_patterns.get("negative", []):
            if pattern.search(text):
                negative_score += 1
                if len(key_phrases) < 5:
                    key_phrases.append(pattern.pattern.replace(r'\b', ''))
        
        # Determine sentiment
        net_score = positive_score - negative_score
        if net_score >= 3:
            sentiment = Sentiment.VERY_POSITIVE
            confidence = min(0.9, 0.5 + positive_score * 0.1)
        elif net_score >= 1:
            sentiment = Sentiment.POSITIVE
            confidence = min(0.8, 0.5 + positive_score * 0.1)
        elif net_score <= -3:
            sentiment = Sentiment.VERY_NEGATIVE
            confidence = min(0.9, 0.5 + negative_score * 0.1)
        elif net_score <= -1:
            sentiment = Sentiment.NEGATIVE
            confidence = min(0.8, 0.5 + negative_score * 0.1)
        else:
            sentiment = Sentiment.NEUTRAL
            confidence = 0.5
        
        # Detect objections
        objection_type = ObjectionType.NONE
        for obj_type, patterns in self.objection_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    objection_type = obj_type
                    sentiment = Sentiment.OBJECTION
                    break
            if objection_type != ObjectionType.NONE:
                break
        
        # Detect buying signals
        buying_signal = BuyingSignal.NO_INTENT
        for signal, patterns in self.buying_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    buying_signal = signal
                    break
            if buying_signal != BuyingSignal.NO_INTENT:
                break
        
        # Detect urgency
        urgency_detected = any(p.search(text) for p in self.urgency_patterns)
        
        # Calculate score adjustment
        score_adjustment = self._calculate_score_adjustment(
            sentiment, objection_type, buying_signal, urgency_detected
        )
        
        # Get recommendation
        recommended_action, response_template = self._get_recommendation(
            sentiment, objection_type, buying_signal
        )
        
        return SentimentResult(
            sentiment=sentiment,
            confidence=confidence,
            objection_type=objection_type,
            buying_signal=buying_signal,
            urgency_detected=urgency_detected,
            key_phrases=key_phrases[:5],
            score_adjustment=score_adjustment,
            recommended_action=recommended_action,
            response_template=response_template,
        )
    
    def _calculate_score_adjustment(
        self,
        sentiment: Sentiment,
        objection: ObjectionType,
        buying_signal: BuyingSignal,
        urgency: bool
    ) -> int:
        """Calculate lead score adjustment based on analysis."""
        adjustment = 0
        
        # Sentiment adjustments
        sentiment_scores = {
            Sentiment.VERY_POSITIVE: 30,
            Sentiment.POSITIVE: 15,
            Sentiment.NEUTRAL: 0,
            Sentiment.NEGATIVE: -10,
            Sentiment.VERY_NEGATIVE: -30,
            Sentiment.OBJECTION: 5,  # Objections are engagement
        }
        adjustment += sentiment_scores.get(sentiment, 0)
        
        # Buying signal adjustments
        signal_scores = {
            BuyingSignal.HIGH_INTENT: 25,
            BuyingSignal.MEDIUM_INTENT: 15,
            BuyingSignal.LOW_INTENT: 5,
            BuyingSignal.NO_INTENT: 0,
        }
        adjustment += signal_scores.get(buying_signal, 0)
        
        # Urgency bonus
        if urgency:
            adjustment += 10
        
        return adjustment
    
    def _get_recommendation(
        self,
        sentiment: Sentiment,
        objection: ObjectionType,
        buying_signal: BuyingSignal
    ) -> Tuple[str, Optional[str]]:
        """Get recommended action and response template."""
        
        if sentiment == Sentiment.VERY_POSITIVE or buying_signal == BuyingSignal.HIGH_INTENT:
            return (
                "IMMEDIATE_FOLLOWUP",
                "fast_track_response"
            )
        
        if sentiment == Sentiment.VERY_NEGATIVE:
            return (
                "ADD_TO_SUPPRESSION",
                None
            )
        
        if objection != ObjectionType.NONE:
            templates = {
                ObjectionType.PRICE: "price_objection_handler",
                ObjectionType.TIMING: "timing_objection_handler",
                ObjectionType.AUTHORITY: "authority_objection_handler",
                ObjectionType.NEED: "need_objection_handler",
                ObjectionType.TRUST: "trust_builder_response",
                ObjectionType.COMPETITOR: "competitor_displacement",
            }
            return (
                "HANDLE_OBJECTION",
                templates.get(objection, "general_objection_handler")
            )
        
        if sentiment == Sentiment.POSITIVE:
            return (
                "SCHEDULE_CALL",
                "meeting_request"
            )
        
        if sentiment == Sentiment.NEGATIVE:
            return (
                "NURTURE_SEQUENCE",
                "soft_touch_followup"
            )
        
        return (
            "CONTINUE_SEQUENCE",
            None
        )
    
    def analyze_thread(self, messages: List[Dict]) -> Dict:
        """Analyze a conversation thread for patterns."""
        if not messages:
            return {"error": "No messages to analyze"}
        
        results = []
        for msg in messages:
            text = msg.get("body", "") or msg.get("content", "")
            results.append({
                "timestamp": msg.get("timestamp"),
                "direction": msg.get("direction", "unknown"),
                "analysis": self.analyze(text).to_dict()
            })
        
        # Calculate trend
        sentiments = [r["analysis"]["sentiment"] for r in results]
        sentiment_values = {
            "very_positive": 2, "positive": 1, "neutral": 0,
            "negative": -1, "very_negative": -2, "objection": 0.5
        }
        
        if len(sentiments) >= 2:
            start_avg = sum(sentiment_values.get(s, 0) for s in sentiments[:len(sentiments)//2]) / (len(sentiments)//2)
            end_avg = sum(sentiment_values.get(s, 0) for s in sentiments[len(sentiments)//2:]) / (len(sentiments) - len(sentiments)//2)
            trend = "improving" if end_avg > start_avg else "declining" if end_avg < start_avg else "stable"
        else:
            trend = "insufficient_data"
        
        # Overall sentiment
        final_sentiment = results[-1]["analysis"]["sentiment"] if results else "unknown"
        
        # Total score adjustment
        total_adjustment = sum(r["analysis"]["score_adjustment"] for r in results)
        
        return {
            "message_count": len(messages),
            "trend": trend,
            "final_sentiment": final_sentiment,
            "total_score_adjustment": total_adjustment,
            "messages": results,
            "recommended_action": results[-1]["analysis"]["recommended_action"] if results else "NONE"
        }


# =============================================================================
# RESPONSE TEMPLATES
# =============================================================================

OBJECTION_RESPONSES = {
    "price_objection_handler": """Hi {first_name},

Totally understand - investment decisions require careful consideration.

Here's how I think about it: our clients typically see ROI within {timeframe} through:
- {benefit_1}
- {benefit_2}
- {benefit_3}

Would it help to see a case study showing the actual numbers from a similar {industry} company?

{signature}""",

    "timing_objection_handler": """Hi {first_name},

I hear you - timing is everything.

Quick question: is the timing challenge about bandwidth, or is there something specific happening in {company_name} right now?

If it's bandwidth, we can start with a smaller scope. If it's something else, I'd love to understand better so I can either help now or reach out at a more relevant time.

{signature}""",

    "authority_objection_handler": """Hi {first_name},

That makes total sense - these decisions rarely happen in isolation.

Would it be helpful if I put together a one-pager specifically designed for {stakeholder_role}? I can highlight the points that typically matter most to them.

Or if you'd prefer, we could set up a quick call with both of you. Whichever is easier.

{signature}""",

    "need_objection_handler": """Hi {first_name},

Fair point - if things are working, why change them?

The reason I reached out is that I've seen a lot of {industry} companies in a similar position. They thought things were working until they realized they were leaving {value_left_on_table} on the table.

Would you be open to a 15-minute assessment? Worst case, you'll confirm you're already optimized. Best case, we find some quick wins.

{signature}""",
}


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

def analyze_reply(reply_text: str) -> Dict:
    """Quick analysis of a single reply."""
    analyzer = SentimentAnalyzer()
    result = analyzer.analyze(reply_text)
    return result.to_dict()


def should_escalate(sentiment_result: SentimentResult) -> bool:
    """Determine if reply should be escalated to human."""
    escalation_triggers = [
        sentiment_result.sentiment == Sentiment.VERY_POSITIVE,
        sentiment_result.buying_signal == BuyingSignal.HIGH_INTENT,
        sentiment_result.urgency_detected,
        sentiment_result.objection_type == ObjectionType.COMPETITOR,
    ]
    return any(escalation_triggers)


def get_score_adjustment(reply_text: str) -> int:
    """Get lead score adjustment for a reply."""
    analyzer = SentimentAnalyzer()
    result = analyzer.analyze(reply_text)
    return result.score_adjustment


# =============================================================================
# DEMO
# =============================================================================

def demo():
    print("=" * 60)
    print("Sentiment Analyzer Demo")
    print("=" * 60)
    
    analyzer = SentimentAnalyzer()
    
    test_messages = [
        "Thanks for reaching out! I'm definitely interested in learning more about this.",
        "We're already using a competitor and happy with them.",
        "This sounds interesting but the timing isn't great. Can you reach out next quarter?",
        "How much does this cost? What's the pricing look like?",
        "This is exactly what we need! How do we get started?",
        "Please remove me from your list. Not interested.",
        "I need to run this by my boss first. She makes these decisions.",
    ]
    
    for msg in test_messages:
        result = analyzer.analyze(msg)
        print(f"\nMessage: \"{msg[:50]}...\"")
        print(f"  Sentiment: {result.sentiment.value}")
        print(f"  Objection: {result.objection_type.value}")
        print(f"  Buying Signal: {result.buying_signal.value}")
        print(f"  Score Adjustment: {result.score_adjustment:+d}")
        print(f"  Action: {result.recommended_action}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    demo()
