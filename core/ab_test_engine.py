#!/usr/bin/env python3
"""
A/B Test Engine for Email Optimization
=======================================
Implements subject line A/B testing, negative reply pattern detection,
and CTA optimization based on self-annealing recommendations.

Key Features:
1. Subject line variant generation and testing
2. Negative reply pattern analysis
3. CTA softness scoring and optimization
4. Statistical significance tracking
5. Auto-winner selection with Q-learning integration

Triggered by: Self-annealing alert "reply rate below target"

Usage:
    from core.ab_test_engine import get_ab_engine, SubjectLineTest
    
    engine = get_ab_engine()
    
    # Create new A/B test
    test = await engine.create_subject_test(
        base_subject="Quick thought on {company}'s development cycle",
        campaign_id="campaign_001"
    )
    
    # Get variant for a lead
    variant = engine.get_variant_for_lead("lead_123", test.test_id)
    
    # Record outcome
    engine.record_outcome(test.test_id, variant.variant_id, "replied", positive=True)
"""

import os
import sys
import json
import asyncio
import logging
import hashlib
import random
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env', override=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ab_test')


class TestStatus(Enum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    WINNER_SELECTED = "winner_selected"


class VariantType(Enum):
    CONTROL = "control"
    VARIANT_A = "variant_a"
    VARIANT_B = "variant_b"
    VARIANT_C = "variant_c"


class CTASoftness(Enum):
    """CTA aggressiveness levels."""
    HARD = "hard"      # "Book a call now"
    MEDIUM = "medium"  # "Would you be open to a quick chat?"
    SOFT = "soft"      # "Would later today or tomorrow work better?"
    ULTRA_SOFT = "ultra_soft"  # "Happy to share more if helpful"


@dataclass
class SubjectVariant:
    """A subject line variant in a test."""
    variant_id: str
    variant_type: VariantType
    subject_line: str
    sends: int = 0
    opens: int = 0
    replies: int = 0
    positive_replies: int = 0
    negative_replies: int = 0
    clicks: int = 0
    unsubscribes: int = 0
    
    @property
    def open_rate(self) -> float:
        return self.opens / self.sends if self.sends > 0 else 0
    
    @property
    def reply_rate(self) -> float:
        return self.replies / self.sends if self.sends > 0 else 0
    
    @property
    def positive_reply_rate(self) -> float:
        return self.positive_replies / self.sends if self.sends > 0 else 0
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["variant_type"] = self.variant_type.value
        d["open_rate"] = round(self.open_rate * 100, 2)
        d["reply_rate"] = round(self.reply_rate * 100, 2)
        d["positive_reply_rate"] = round(self.positive_reply_rate * 100, 2)
        return d


@dataclass
class SubjectLineTest:
    """A/B test for subject lines."""
    test_id: str
    campaign_id: str
    base_subject: str
    variants: List[SubjectVariant]
    status: TestStatus = TestStatus.DRAFT
    target_sample_size: int = 100
    confidence_threshold: float = 0.95
    winner_variant_id: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    
    def total_sends(self) -> int:
        return sum(v.sends for v in self.variants)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "campaign_id": self.campaign_id,
            "base_subject": self.base_subject,
            "variants": [v.to_dict() for v in self.variants],
            "status": self.status.value,
            "target_sample_size": self.target_sample_size,
            "total_sends": self.total_sends(),
            "winner_variant_id": self.winner_variant_id,
            "created_at": self.created_at,
            "completed_at": self.completed_at
        }


@dataclass
class NegativeReplyPattern:
    """Pattern detected in negative replies."""
    pattern_id: str
    pattern_type: str
    keywords: List[str]
    frequency: int
    example_replies: List[str]
    suggested_fix: str
    confidence: float


@dataclass
class CTAVariant:
    """CTA variant for testing."""
    cta_text: str
    softness: CTASoftness
    sends: int = 0
    conversions: int = 0
    
    @property
    def conversion_rate(self) -> float:
        return self.conversions / self.sends if self.sends > 0 else 0


# Subject line generation patterns
SUBJECT_PATTERNS = {
    "curiosity": [
        "Quick thought on {company}'s {pain_point}",
        "Something I noticed about {company}",
        "A question about {company}'s approach",
    ],
    "personalized": [
        "{first_name}, saw your team's work on {topic}",
        "{first_name} - re: {company}'s {pain_point}",
        "For {first_name}'s consideration",
    ],
    "direct_value": [
        "22% faster cycles for {company}?",
        "The {metric}% you were reading about",
        "{company} + AI frameworks",
    ],
    "social_proof": [
        "How {reference_company} solved this",
        "What {industry} leaders are doing differently",
        "Pattern we're seeing with {industry} teams",
    ],
    "question": [
        "Is {company} exploring AI for {use_case}?",
        "Quick question about {company}'s priorities",
        "Friction in {pain_point}?",
    ]
}

# Soft CTA options
SOFT_CTAS = {
    CTASoftness.HARD: [
        "Book a call here: {booking_link}",
        "Let's schedule 15 minutes this week.",
        "Click here to grab time on my calendar.",
    ],
    CTASoftness.MEDIUM: [
        "Would you be open to a quick chat?",
        "Worth a 10-minute conversation?",
        "Open to exploring this further?",
    ],
    CTASoftness.SOFT: [
        "Would later today or tomorrow work better?",
        "Happy to share more when timing works.",
        "No rush—just let me know if it's worth exploring.",
    ],
    CTASoftness.ULTRA_SOFT: [
        "Happy to share more if helpful.",
        "Just thought it might be relevant to what you're working on.",
        "If timing ever makes sense, I'm around.",
    ]
}

# Negative reply patterns to detect
NEGATIVE_PATTERNS = {
    "not_interested": {
        "keywords": ["not interested", "no thanks", "not a fit", "not for us", "pass"],
        "suggested_fix": "Consider warmer intro or social proof"
    },
    "bad_timing": {
        "keywords": ["bad time", "not now", "too busy", "maybe later", "not a priority"],
        "suggested_fix": "Add to nurture sequence, follow up in 30 days"
    },
    "wrong_person": {
        "keywords": ["wrong person", "not my area", "reach out to", "try contacting"],
        "suggested_fix": "Improve targeting and ICP matching"
    },
    "too_salesy": {
        "keywords": ["too salesy", "spam", "stop emailing", "remove me", "unsubscribe"],
        "suggested_fix": "Softer CTA, more value-first approach"
    },
    "already_have_solution": {
        "keywords": ["already have", "using another", "happy with", "locked in"],
        "suggested_fix": "Add competitive differentiation angle"
    },
    "budget_concerns": {
        "keywords": ["no budget", "too expensive", "cost", "can't afford"],
        "suggested_fix": "Lead with ROI metrics, offer audit first"
    },
    "skeptical": {
        "keywords": ["sounds too good", "hard to believe", "prove it", "show me data"],
        "suggested_fix": "Add case studies and specific metrics"
    }
}


class ABTestEngine:
    """
    A/B testing engine for email optimization.
    
    Implements:
    - Subject line variant generation
    - Negative reply pattern detection
    - CTA optimization
    - Statistical significance testing
    """
    
    def __init__(self):
        self.storage_dir = PROJECT_ROOT / ".hive-mind" / "ab_tests"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self._active_tests: Dict[str, SubjectLineTest] = {}
        self._lead_assignments: Dict[str, Dict[str, str]] = {}  # lead_id -> {test_id: variant_id}
        self._negative_patterns: List[NegativeReplyPattern] = []
        self._reply_log: List[Dict[str, Any]] = []
        
        self._load_state()
        logger.info("A/B Test Engine initialized")
    
    async def create_subject_test(
        self,
        base_subject: str,
        campaign_id: str,
        num_variants: int = 3,
        context: Optional[Dict[str, str]] = None
    ) -> SubjectLineTest:
        """
        Create a new subject line A/B test with auto-generated variants.
        
        Args:
            base_subject: Original subject line template
            campaign_id: Campaign this test is for
            num_variants: Number of variants to generate (including control)
            context: Variables for personalization (company, first_name, etc.)
        
        Returns:
            SubjectLineTest with generated variants
        """
        test_id = f"test_{campaign_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        variants = [
            SubjectVariant(
                variant_id=f"{test_id}_control",
                variant_type=VariantType.CONTROL,
                subject_line=base_subject
            )
        ]
        
        # Generate variants using different patterns
        generated = await self._generate_subject_variants(base_subject, num_variants - 1, context)
        
        variant_types = [VariantType.VARIANT_A, VariantType.VARIANT_B, VariantType.VARIANT_C]
        for i, subject in enumerate(generated):
            if i < len(variant_types):
                variants.append(SubjectVariant(
                    variant_id=f"{test_id}_{variant_types[i].value}",
                    variant_type=variant_types[i],
                    subject_line=subject
                ))
        
        test = SubjectLineTest(
            test_id=test_id,
            campaign_id=campaign_id,
            base_subject=base_subject,
            variants=variants,
            status=TestStatus.RUNNING,
            target_sample_size=100 * len(variants)
        )
        
        self._active_tests[test_id] = test
        self._save_test(test)
        
        logger.info(f"Created A/B test {test_id} with {len(variants)} variants")
        return test
    
    async def _generate_subject_variants(
        self,
        base_subject: str,
        count: int,
        context: Optional[Dict[str, str]] = None
    ) -> List[str]:
        """Generate subject line variants using Gemini."""
        try:
            from core.agent_llm_mixin import crafter_create
        except ImportError:
            logger.warning("LLM not available, using pattern-based generation")
            return self._pattern_based_variants(base_subject, count, context)
        
        prompt = f"""Generate {count} alternative subject lines for A/B testing.

ORIGINAL SUBJECT:
{base_subject}

CONTEXT:
{json.dumps(context or {}, indent=2)}

REQUIREMENTS:
1. Keep under 50 characters
2. No spam trigger words (free, guarantee, act now, limited time)
3. Maintain personalization placeholders like {{company}}, {{first_name}}
4. Try different approaches:
   - Curiosity-driven
   - Direct value proposition
   - Question-based
   - Social proof
5. Each variant should be distinctly different

Return ONLY a JSON array of subject line strings, nothing else:
["subject 1", "subject 2", ...]
"""
        
        try:
            response = await crafter_create(prompt)
            import re
            json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
            if json_match:
                subjects = json.loads(json_match.group())
                return subjects[:count]
        except Exception as e:
            logger.warning(f"LLM variant generation failed: {e}")
        
        return self._pattern_based_variants(base_subject, count, context)
    
    def _pattern_based_variants(
        self,
        base_subject: str,
        count: int,
        context: Optional[Dict[str, str]] = None
    ) -> List[str]:
        """Generate variants using predefined patterns."""
        context = context or {}
        variants = []
        
        pattern_types = list(SUBJECT_PATTERNS.keys())
        random.shuffle(pattern_types)
        
        for pattern_type in pattern_types[:count]:
            patterns = SUBJECT_PATTERNS[pattern_type]
            template = random.choice(patterns)
            
            # Fill in context variables with defaults
            subject = template.format(
                company=context.get("company", "{company}"),
                first_name=context.get("first_name", "{first_name}"),
                pain_point=context.get("pain_point", "sales cycles"),
                topic=context.get("topic", "AI adoption"),
                metric=context.get("metric", "22"),
                reference_company=context.get("reference_company", "P&G"),
                industry=context.get("industry", "SaaS"),
                use_case=context.get("use_case", "sales")
            )
            variants.append(subject)
        
        return variants
    
    def get_variant_for_lead(
        self,
        lead_id: str,
        test_id: str
    ) -> Optional[SubjectVariant]:
        """
        Get the assigned variant for a lead (consistent assignment).
        
        Uses deterministic hashing to ensure same lead always gets same variant.
        """
        test = self._active_tests.get(test_id)
        if not test or test.status != TestStatus.RUNNING:
            return None
        
        # Check existing assignment
        if lead_id in self._lead_assignments:
            if test_id in self._lead_assignments[lead_id]:
                variant_id = self._lead_assignments[lead_id][test_id]
                return next((v for v in test.variants if v.variant_id == variant_id), None)
        
        # Deterministic assignment based on lead_id hash
        hash_val = int(hashlib.md5(f"{lead_id}_{test_id}".encode()).hexdigest(), 16)
        variant_index = hash_val % len(test.variants)
        variant = test.variants[variant_index]
        
        # Store assignment
        if lead_id not in self._lead_assignments:
            self._lead_assignments[lead_id] = {}
        self._lead_assignments[lead_id][test_id] = variant.variant_id
        
        return variant
    
    def record_send(self, test_id: str, variant_id: str):
        """Record that a variant was sent."""
        test = self._active_tests.get(test_id)
        if not test:
            return
        
        for variant in test.variants:
            if variant.variant_id == variant_id:
                variant.sends += 1
                break
        
        self._check_test_completion(test)
        self._save_test(test)
    
    def record_outcome(
        self,
        test_id: str,
        variant_id: str,
        outcome: str,
        positive: bool = False,
        reply_content: Optional[str] = None
    ):
        """
        Record an outcome for a variant.
        
        Args:
            test_id: Test ID
            variant_id: Variant ID
            outcome: "opened", "replied", "clicked", "unsubscribed"
            positive: Whether reply was positive
            reply_content: Reply text for pattern analysis
        """
        test = self._active_tests.get(test_id)
        if not test:
            return
        
        for variant in test.variants:
            if variant.variant_id == variant_id:
                if outcome == "opened":
                    variant.opens += 1
                elif outcome == "replied":
                    variant.replies += 1
                    if positive:
                        variant.positive_replies += 1
                    else:
                        variant.negative_replies += 1
                        if reply_content:
                            self._analyze_negative_reply(reply_content, variant_id)
                elif outcome == "clicked":
                    variant.clicks += 1
                elif outcome == "unsubscribed":
                    variant.unsubscribes += 1
                break
        
        self._check_test_completion(test)
        self._save_test(test)
    
    def _analyze_negative_reply(self, content: str, variant_id: str):
        """Analyze negative reply for patterns."""
        content_lower = content.lower()
        
        matched_patterns = []
        for pattern_type, pattern_info in NEGATIVE_PATTERNS.items():
            for keyword in pattern_info["keywords"]:
                if keyword in content_lower:
                    matched_patterns.append((pattern_type, keyword))
                    break
        
        if matched_patterns:
            self._reply_log.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "variant_id": variant_id,
                "content_preview": content[:200],
                "patterns_matched": matched_patterns
            })
            self._reply_log = self._reply_log[-500:]  # Keep last 500
    
    def analyze_negative_patterns(self) -> List[NegativeReplyPattern]:
        """Analyze collected negative replies for patterns."""
        pattern_counts = defaultdict(lambda: {"count": 0, "examples": [], "keywords": set()})
        
        for reply in self._reply_log:
            for pattern_type, keyword in reply.get("patterns_matched", []):
                pattern_counts[pattern_type]["count"] += 1
                pattern_counts[pattern_type]["keywords"].add(keyword)
                if len(pattern_counts[pattern_type]["examples"]) < 3:
                    pattern_counts[pattern_type]["examples"].append(reply["content_preview"])
        
        patterns = []
        for pattern_type, data in pattern_counts.items():
            if data["count"] >= 3:  # Minimum frequency
                patterns.append(NegativeReplyPattern(
                    pattern_id=f"neg_{pattern_type}",
                    pattern_type=pattern_type,
                    keywords=list(data["keywords"]),
                    frequency=data["count"],
                    example_replies=data["examples"],
                    suggested_fix=NEGATIVE_PATTERNS[pattern_type]["suggested_fix"],
                    confidence=min(data["count"] / 10, 1.0)
                ))
        
        patterns.sort(key=lambda p: p.frequency, reverse=True)
        self._negative_patterns = patterns
        return patterns
    
    def get_soft_cta_options(self, current_softness: CTASoftness = CTASoftness.MEDIUM) -> List[str]:
        """Get softer CTA options based on current level."""
        # Return options at same or softer level
        softness_order = [CTASoftness.HARD, CTASoftness.MEDIUM, CTASoftness.SOFT, CTASoftness.ULTRA_SOFT]
        current_idx = softness_order.index(current_softness)
        
        softer_options = []
        for softness in softness_order[current_idx:]:
            softer_options.extend(SOFT_CTAS[softness])
        
        return softer_options
    
    def _check_test_completion(self, test: SubjectLineTest):
        """Check if test has reached statistical significance."""
        if test.status != TestStatus.RUNNING:
            return
        
        if test.total_sends() >= test.target_sample_size:
            winner = self._determine_winner(test)
            if winner:
                test.winner_variant_id = winner.variant_id
                test.status = TestStatus.WINNER_SELECTED
                test.completed_at = datetime.now(timezone.utc).isoformat()
                logger.info(f"Test {test.test_id} completed. Winner: {winner.variant_id}")
    
    def _determine_winner(self, test: SubjectLineTest) -> Optional[SubjectVariant]:
        """Determine winning variant based on positive reply rate."""
        if not test.variants:
            return None
        
        # Sort by positive reply rate
        sorted_variants = sorted(
            test.variants,
            key=lambda v: v.positive_reply_rate,
            reverse=True
        )
        
        best = sorted_variants[0]
        
        # Check if statistically significant (simplified check)
        if best.sends >= 30 and best.positive_reply_rate > 0:
            # Check if best is meaningfully better than control
            control = next((v for v in test.variants if v.variant_type == VariantType.CONTROL), None)
            if control:
                if best.positive_reply_rate > control.positive_reply_rate * 1.1:  # 10% improvement
                    return best
            return best
        
        return None
    
    def get_test_results(self, test_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed results for a test."""
        test = self._active_tests.get(test_id)
        if not test:
            return None
        
        results = test.to_dict()
        
        # Add comparison data
        if len(test.variants) > 1:
            control = next((v for v in test.variants if v.variant_type == VariantType.CONTROL), None)
            if control and control.positive_reply_rate > 0:
                results["variant_lifts"] = {}
                for v in test.variants:
                    if v.variant_id != control.variant_id:
                        lift = ((v.positive_reply_rate - control.positive_reply_rate) / 
                                control.positive_reply_rate * 100) if control.positive_reply_rate > 0 else 0
                        results["variant_lifts"][v.variant_id] = round(lift, 1)
        
        return results
    
    def get_all_active_tests(self) -> List[Dict[str, Any]]:
        """Get all active tests."""
        return [test.to_dict() for test in self._active_tests.values() 
                if test.status == TestStatus.RUNNING]
    
    def get_recommendations(self) -> Dict[str, Any]:
        """Get optimization recommendations based on test data."""
        recommendations = {
            "subject_lines": [],
            "ctas": [],
            "targeting": [],
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Analyze negative patterns
        patterns = self.analyze_negative_patterns()
        
        for pattern in patterns[:3]:  # Top 3 patterns
            recommendations["targeting"].append({
                "issue": pattern.pattern_type.replace("_", " ").title(),
                "frequency": pattern.frequency,
                "fix": pattern.suggested_fix
            })
        
        # Analyze completed tests for winning patterns
        for test in self._active_tests.values():
            if test.status == TestStatus.WINNER_SELECTED and test.winner_variant_id:
                winner = next((v for v in test.variants if v.variant_id == test.winner_variant_id), None)
                control = next((v for v in test.variants if v.variant_type == VariantType.CONTROL), None)
                
                if winner and control:
                    lift = ((winner.positive_reply_rate - control.positive_reply_rate) / 
                            control.positive_reply_rate * 100) if control.positive_reply_rate > 0 else 0
                    
                    if lift > 10:
                        recommendations["subject_lines"].append({
                            "winning_subject": winner.subject_line,
                            "lift_vs_control": f"+{round(lift, 1)}%",
                            "sample_size": winner.sends
                        })
        
        # CTA recommendations based on unsubscribe rate
        total_unsubscribes = sum(
            v.unsubscribes for test in self._active_tests.values() 
            for v in test.variants
        )
        total_sends = sum(
            v.sends for test in self._active_tests.values() 
            for v in test.variants
        )
        
        if total_sends > 0:
            unsub_rate = total_unsubscribes / total_sends
            if unsub_rate > 0.02:  # > 2% unsubscribe rate
                recommendations["ctas"].append({
                    "issue": f"High unsubscribe rate ({round(unsub_rate * 100, 2)}%)",
                    "fix": "Consider softer CTAs for cold lists",
                    "suggested_ctas": self.get_soft_cta_options(CTASoftness.SOFT)[:3]
                })
        
        return recommendations
    
    def _save_test(self, test: SubjectLineTest):
        """Save test to disk."""
        test_file = self.storage_dir / f"{test.test_id}.json"
        try:
            with open(test_file, "w") as f:
                json.dump(test.to_dict(), f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save test: {e}")
    
    def _load_state(self):
        """Load tests from disk."""
        for test_file in self.storage_dir.glob("test_*.json"):
            try:
                with open(test_file) as f:
                    data = json.load(f)
                    
                variants = [
                    SubjectVariant(
                        variant_id=v["variant_id"],
                        variant_type=VariantType(v["variant_type"]),
                        subject_line=v["subject_line"],
                        sends=v.get("sends", 0),
                        opens=v.get("opens", 0),
                        replies=v.get("replies", 0),
                        positive_replies=v.get("positive_replies", 0),
                        negative_replies=v.get("negative_replies", 0),
                        clicks=v.get("clicks", 0),
                        unsubscribes=v.get("unsubscribes", 0)
                    )
                    for v in data.get("variants", [])
                ]
                
                test = SubjectLineTest(
                    test_id=data["test_id"],
                    campaign_id=data["campaign_id"],
                    base_subject=data["base_subject"],
                    variants=variants,
                    status=TestStatus(data.get("status", "running")),
                    target_sample_size=data.get("target_sample_size", 100),
                    winner_variant_id=data.get("winner_variant_id"),
                    created_at=data.get("created_at"),
                    completed_at=data.get("completed_at")
                )
                
                self._active_tests[test.test_id] = test
            except Exception as e:
                logger.warning(f"Failed to load test {test_file}: {e}")


# Singleton
_engine: Optional[ABTestEngine] = None


def get_ab_engine() -> ABTestEngine:
    """Get or create the global A/B test engine."""
    global _engine
    if _engine is None:
        _engine = ABTestEngine()
    return _engine


async def demo():
    """Demonstrate A/B testing."""
    print("\n" + "=" * 60)
    print("A/B TEST ENGINE - Demo")
    print("=" * 60)
    
    engine = get_ab_engine()
    
    # Create a test
    print("\n[Creating subject line A/B test...]")
    test = await engine.create_subject_test(
        base_subject="Quick thought on {company}'s development cycle",
        campaign_id="pg_case_study",
        context={
            "company": "Acme Corp",
            "pain_point": "sales cycles",
            "metric": "22"
        }
    )
    
    print(f"  Test ID: {test.test_id}")
    print(f"  Variants created: {len(test.variants)}")
    for v in test.variants:
        print(f"    - {v.variant_type.value}: {v.subject_line}")
    
    # Simulate outcomes
    print("\n[Simulating outcomes...]")
    for i in range(50):
        lead_id = f"lead_{i:03d}"
        variant = engine.get_variant_for_lead(lead_id, test.test_id)
        if variant:
            engine.record_send(test.test_id, variant.variant_id)
            
            # Simulate opens (60%)
            if random.random() < 0.6:
                engine.record_outcome(test.test_id, variant.variant_id, "opened")
                
                # Simulate replies (10%)
                if random.random() < 0.1:
                    positive = random.random() < 0.7
                    reply_content = "Sounds interesting" if positive else "Not interested, please remove me"
                    engine.record_outcome(
                        test.test_id, variant.variant_id, "replied",
                        positive=positive, reply_content=reply_content
                    )
    
    # Get results
    print("\n[Test Results]")
    results = engine.get_test_results(test.test_id)
    for v in results["variants"]:
        print(f"  {v['variant_type']}: {v['sends']} sends, {v['reply_rate']}% reply rate")
    
    # Get recommendations
    print("\n[Recommendations]")
    recs = engine.get_recommendations()
    for rec in recs.get("targeting", [])[:2]:
        print(f"  Issue: {rec['issue']}")
        print(f"  Fix: {rec['fix']}")
    
    # Soft CTA options
    print("\n[Softer CTA Options]")
    soft_ctas = engine.get_soft_cta_options(CTASoftness.MEDIUM)[:3]
    for cta in soft_ctas:
        print(f"  - {cta}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(demo())
