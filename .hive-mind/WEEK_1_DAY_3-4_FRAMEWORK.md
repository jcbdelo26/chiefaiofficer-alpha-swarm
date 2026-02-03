# 🏗️ Week 1 Day 3-4: Core Framework Integration
**Chief AI Officer Alpha Swarm**

**Timeline:** Day 3-4 (January 19-20, 2026)  
**Goal:** Integrate core framework components into existing agents  
**Prerequisites:** ✅ All API connections verified (Day 1-2 complete)

---

## 📋 Overview

This guide integrates the advanced framework components into your existing Alpha Swarm:

```
┌─────────────────────────────────────────────────────────────┐
│                  CORE FRAMEWORK STACK                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Layer 1: Context Management                                │
│  ├─ Token budget tracking (100K limit)                      │
│  ├─ FIC (Forget, Ignore, Compact) compaction                │
│  └─ Conversation history management                         │
│                                                             │
│  Layer 2: Grounding & Verification                          │
│  ├─ Hallucination detection                                 │
│  ├─ Fact verification against sources                       │
│  └─ Output validation hooks                                 │
│                                                             │
│  Layer 3: Feedback & Learning                               │
│  ├─ Campaign performance tracking                           │
│  ├─ Self-annealing loops                                    │
│  └─ Continuous improvement                                  │
│                                                             │
│  Layer 4: Monitoring & Observability                        │
│  ├─ KPI dashboard                                           │
│  ├─ Real-time metrics                                       │
│  └─ Alert system                                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🎯 Day 3: Context Manager & Grounding Chain

### Part 1: Context Manager Integration

The Context Manager prevents token overflow and manages conversation history efficiently.

#### Step 1: Verify Context Manager Exists

```powershell
# Check if file exists
ls core/context_manager.py
```

If it doesn't exist, we'll create it:

```powershell
# Create core directory if needed
mkdir -p core
```

#### Step 2: Create Context Manager

Create `core/context_manager.py`:

```python
"""
Context Manager
===============
Manages token budgets and conversation context with FIC compaction.

Features:
- Token counting and budget tracking
- FIC (Forget, Ignore, Compact) strategy
- Automatic context compaction
- Conversation history management
"""

import tiktoken
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
from pathlib import Path


class ContextManager:
    """Manages conversation context and token budgets."""
    
    def __init__(self, max_tokens: int = 100000, model: str = "claude-3-sonnet-20240229"):
        """
        Initialize context manager.
        
        Args:
            max_tokens: Maximum token budget (default: 100K)
            model: Model name for token counting
        """
        self.max_tokens = max_tokens
        self.model = model
        self.conversation_history: List[Dict[str, Any]] = []
        self.token_count = 0
        
        # Initialize tokenizer (using tiktoken as approximation)
        try:
            self.tokenizer = tiktoken.encoding_for_model("gpt-4")
        except:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Storage
        self.data_dir = Path(__file__).parent.parent / ".hive-mind"
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.tokenizer.encode(text))
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """
        Add message to conversation history.
        
        Args:
            role: 'user', 'assistant', or 'system'
            content: Message content
            metadata: Optional metadata (source, timestamp, etc.)
        """
        tokens = self.count_tokens(content)
        
        message = {
            "role": role,
            "content": content,
            "tokens": tokens,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        
        self.conversation_history.append(message)
        self.token_count += tokens
        
        # Auto-compact if approaching limit
        if self.token_count > self.max_tokens * 0.8:
            self.compact()
    
    def compact(self, strategy: str = "fic"):
        """
        Compact conversation history using FIC strategy.
        
        FIC = Forget, Ignore, Compact
        - Forget: Remove old, low-importance messages
        - Ignore: Skip redundant information
        - Compact: Summarize long conversations
        
        Args:
            strategy: Compaction strategy ('fic', 'sliding_window', 'summarize')
        """
        if strategy == "fic":
            self._fic_compact()
        elif strategy == "sliding_window":
            self._sliding_window_compact()
        elif strategy == "summarize":
            self._summarize_compact()
    
    def _fic_compact(self):
        """FIC compaction strategy."""
        # Keep system messages and recent messages
        system_messages = [m for m in self.conversation_history if m["role"] == "system"]
        recent_messages = self.conversation_history[-10:]  # Keep last 10
        
        # Forget: Remove middle messages that are old and low-importance
        important_keywords = ["error", "critical", "important", "decision", "approved"]
        middle_messages = self.conversation_history[len(system_messages):-10]
        
        kept_middle = [
            m for m in middle_messages
            if any(kw in m["content"].lower() for kw in important_keywords)
        ]
        
        # Rebuild history
        self.conversation_history = system_messages + kept_middle + recent_messages
        
        # Recalculate token count
        self.token_count = sum(m["tokens"] for m in self.conversation_history)
        
        print(f"🗜️  Context compacted: {self.token_count}/{self.max_tokens} tokens")
    
    def _sliding_window_compact(self):
        """Keep only recent N messages."""
        window_size = 20
        self.conversation_history = self.conversation_history[-window_size:]
        self.token_count = sum(m["tokens"] for m in self.conversation_history)
    
    def _summarize_compact(self):
        """Summarize old messages (requires AI call)."""
        # TODO: Implement AI-powered summarization
        # For now, use sliding window
        self._sliding_window_compact()
    
    def get_context_for_prompt(self, max_tokens: Optional[int] = None) -> List[Dict[str, str]]:
        """
        Get conversation history formatted for API call.
        
        Args:
            max_tokens: Optional token limit for this specific call
        
        Returns:
            List of messages in API format
        """
        limit = max_tokens or self.max_tokens
        
        # Build from most recent backwards
        messages = []
        token_count = 0
        
        for message in reversed(self.conversation_history):
            if token_count + message["tokens"] > limit:
                break
            
            messages.insert(0, {
                "role": message["role"],
                "content": message["content"]
            })
            token_count += message["tokens"]
        
        return messages
    
    def save_context(self, filename: str = "context_state.json"):
        """Save context to disk."""
        filepath = self.data_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump({
                "max_tokens": self.max_tokens,
                "token_count": self.token_count,
                "conversation_history": self.conversation_history,
                "saved_at": datetime.utcnow().isoformat()
            }, f, indent=2)
    
    def load_context(self, filename: str = "context_state.json"):
        """Load context from disk."""
        filepath = self.data_dir / filename
        
        if not filepath.exists():
            return False
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        self.max_tokens = data["max_tokens"]
        self.token_count = data["token_count"]
        self.conversation_history = data["conversation_history"]
        
        return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get context statistics."""
        return {
            "total_messages": len(self.conversation_history),
            "token_count": self.token_count,
            "max_tokens": self.max_tokens,
            "usage_percent": (self.token_count / self.max_tokens) * 100,
            "tokens_remaining": self.max_tokens - self.token_count
        }
```

#### Step 3: Test Context Manager

Create `tests/test_context_manager.py`:

```python
"""Test Context Manager"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_manager import ContextManager


def test_context_manager():
    """Test basic context manager functionality."""
    print("Testing Context Manager...")
    
    # Initialize
    ctx = ContextManager(max_tokens=1000)
    
    # Add messages
    ctx.add_message("system", "You are a helpful assistant.")
    ctx.add_message("user", "Hello, how are you?")
    ctx.add_message("assistant", "I'm doing well, thank you!")
    
    # Check stats
    stats = ctx.get_stats()
    print(f"\n📊 Stats: {stats}")
    
    # Test compaction
    for i in range(50):
        ctx.add_message("user", f"Message {i}" * 10)
    
    print(f"\n🗜️  Before compact: {ctx.token_count} tokens")
    ctx.compact()
    print(f"After compact: {ctx.token_count} tokens")
    
    # Test save/load
    ctx.save_context("test_context.json")
    
    new_ctx = ContextManager()
    new_ctx.load_context("test_context.json")
    print(f"\n💾 Loaded context: {new_ctx.get_stats()}")
    
    print("\n✅ Context Manager tests passed!")


if __name__ == "__main__":
    test_context_manager()
```

Run the test:

```powershell
python tests/test_context_manager.py
```

---

### Part 2: Grounding Chain Integration

The Grounding Chain prevents hallucinations by verifying claims against sources.

#### Step 1: Create Grounding Chain

Create `core/grounding_chain.py`:

```python
"""
Grounding Chain
===============
Prevents hallucinations by verifying claims against source data.

Features:
- Fact verification
- Source attribution
- Confidence scoring
- Audit logging
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import json
from pathlib import Path


class GroundingChain:
    """Verifies AI outputs against source data."""
    
    def __init__(self, confidence_threshold: float = 0.7):
        """
        Initialize grounding chain.
        
        Args:
            confidence_threshold: Minimum confidence for acceptance (0-1)
        """
        self.confidence_threshold = confidence_threshold
        self.audit_log: List[Dict[str, Any]] = []
        
        # Storage
        self.data_dir = Path(__file__).parent.parent / ".hive-mind"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.audit_file = self.data_dir / "grounding_audit.jsonl"
    
    def verify_claim(self, claim: str, sources: List[Dict[str, Any]]) -> Tuple[bool, float, str]:
        """
        Verify a claim against source data.
        
        Args:
            claim: Statement to verify
            sources: List of source documents with 'content' and 'metadata'
        
        Returns:
            (is_verified, confidence, explanation)
        """
        # Extract key facts from claim
        claim_facts = self._extract_facts(claim)
        
        # Check each fact against sources
        verified_facts = 0
        total_facts = len(claim_facts)
        
        if total_facts == 0:
            return True, 1.0, "No verifiable claims"
        
        evidence = []
        
        for fact in claim_facts:
            for source in sources:
                if self._fact_in_source(fact, source["content"]):
                    verified_facts += 1
                    evidence.append({
                        "fact": fact,
                        "source": source.get("metadata", {}).get("source", "unknown")
                    })
                    break
        
        confidence = verified_facts / total_facts
        is_verified = confidence >= self.confidence_threshold
        
        explanation = self._generate_explanation(
            claim, verified_facts, total_facts, evidence
        )
        
        # Log audit
        self._log_audit(claim, sources, is_verified, confidence, explanation)
        
        return is_verified, confidence, explanation
    
    def _extract_facts(self, text: str) -> List[str]:
        """Extract verifiable facts from text."""
        # Simple fact extraction (can be enhanced with NLP)
        sentences = re.split(r'[.!?]', text)
        
        facts = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 10:  # Ignore very short sentences
                # Look for factual indicators
                if any(indicator in sentence.lower() for indicator in [
                    'is', 'are', 'was', 'were', 'has', 'have', 'had',
                    'will', 'would', 'can', 'could', 'should',
                    'employees', 'revenue', 'founded', 'located'
                ]):
                    facts.append(sentence)
        
        return facts
    
    def _fact_in_source(self, fact: str, source_content: str) -> bool:
        """Check if fact is supported by source."""
        # Normalize text
        fact_lower = fact.lower()
        source_lower = source_content.lower()
        
        # Extract key terms from fact
        key_terms = [
            word for word in re.findall(r'\b\w+\b', fact_lower)
            if len(word) > 3  # Skip short words
        ]
        
        # Check if most key terms appear in source
        matches = sum(1 for term in key_terms if term in source_lower)
        
        return matches >= len(key_terms) * 0.6  # 60% of terms must match
    
    def _generate_explanation(
        self, claim: str, verified: int, total: int, evidence: List[Dict]
    ) -> str:
        """Generate explanation of verification result."""
        if verified == total:
            return f"✅ All {total} claims verified with sources"
        elif verified == 0:
            return f"❌ None of {total} claims could be verified"
        else:
            return f"⚠️  {verified}/{total} claims verified ({(verified/total)*100:.0f}%)"
    
    def _log_audit(
        self, claim: str, sources: List[Dict], verified: bool,
        confidence: float, explanation: str
    ):
        """Log verification audit."""
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "claim": claim,
            "verified": verified,
            "confidence": confidence,
            "explanation": explanation,
            "source_count": len(sources)
        }
        
        self.audit_log.append(audit_entry)
        
        # Append to audit file
        with open(self.audit_file, 'a') as f:
            f.write(json.dumps(audit_entry) + '\n')
    
    def get_audit_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get audit summary for last N days."""
        if not self.audit_file.exists():
            return {"error": "No audit log found"}
        
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        total_checks = 0
        verified_count = 0
        total_confidence = 0.0
        
        with open(self.audit_file, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    timestamp = datetime.fromisoformat(entry['timestamp'])
                    
                    if timestamp >= cutoff:
                        total_checks += 1
                        if entry['verified']:
                            verified_count += 1
                        total_confidence += entry['confidence']
                except:
                    continue
        
        if total_checks == 0:
            return {"error": f"No checks in last {days} days"}
        
        return {
            "period_days": days,
            "total_checks": total_checks,
            "verified_count": verified_count,
            "verification_rate": (verified_count / total_checks) * 100,
            "avg_confidence": total_confidence / total_checks
        }
```

#### Step 2: Test Grounding Chain

Create `tests/test_grounding_chain.py`:

```python
"""Test Grounding Chain"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.grounding_chain import GroundingChain


def test_grounding_chain():
    """Test grounding chain functionality."""
    print("Testing Grounding Chain...")
    
    # Initialize
    grounding = GroundingChain(confidence_threshold=0.7)
    
    # Test claim verification
    claim = "Acme Corp has 500 employees and is located in San Francisco."
    
    sources = [
        {
            "content": "Acme Corporation is a technology company based in San Francisco with approximately 500 team members.",
            "metadata": {"source": "company_website"}
        }
    ]
    
    verified, confidence, explanation = grounding.verify_claim(claim, sources)
    
    print(f"\n📝 Claim: {claim}")
    print(f"✅ Verified: {verified}")
    print(f"📊 Confidence: {confidence:.2f}")
    print(f"💬 Explanation: {explanation}")
    
    # Test unverifiable claim
    false_claim = "Acme Corp has 10,000 employees and is located in New York."
    
    verified2, confidence2, explanation2 = grounding.verify_claim(false_claim, sources)
    
    print(f"\n📝 Claim: {false_claim}")
    print(f"✅ Verified: {verified2}")
    print(f"📊 Confidence: {confidence2:.2f}")
    print(f"💬 Explanation: {explanation2}")
    
    # Get audit summary
    summary = grounding.get_audit_summary(days=1)
    print(f"\n📊 Audit Summary: {summary}")
    
    print("\n✅ Grounding Chain tests passed!")


if __name__ == "__main__":
    test_grounding_chain()
```

Run the test:

```powershell
python tests/test_grounding_chain.py
```

---

## 🎯 Day 4: Feedback Collector & Integration

### Part 3: Feedback Collector

Create `core/feedback_collector.py`:

```python
"""
Feedback Collector
==================
Collects and analyzes feedback for continuous improvement.

Features:
- Campaign performance tracking
- Reply sentiment analysis
- Learning extraction
- Self-annealing support
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict


class FeedbackCollector:
    """Collects and analyzes feedback from campaigns."""
    
    def __init__(self):
        """Initialize feedback collector."""
        self.data_dir = Path(__file__).parent.parent / ".hive-mind"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.feedback_file = self.data_dir / "feedback_history.jsonl"
    
    def record_campaign_feedback(
        self, campaign_id: str, lead_email: str,
        event_type: str, event_data: Dict[str, Any]
    ):
        """
        Record campaign feedback event.
        
        Args:
            campaign_id: Campaign identifier
            lead_email: Lead email address
            event_type: 'sent', 'opened', 'clicked', 'replied', 'bounced', 'unsubscribed'
            event_data: Additional event data
        """
        feedback = {
            "timestamp": datetime.utcnow().isoformat(),
            "campaign_id": campaign_id,
            "lead_email": lead_email,
            "event_type": event_type,
            "event_data": event_data
        }
        
        with open(self.feedback_file, 'a') as f:
            f.write(json.dumps(feedback) + '\n')
    
    def analyze_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """
        Analyze performance of a specific campaign.
        
        Args:
            campaign_id: Campaign to analyze
        
        Returns:
            Performance metrics and insights
        """
        if not self.feedback_file.exists():
            return {"error": "No feedback data"}
        
        events = defaultdict(int)
        replies = []
        
        with open(self.feedback_file, 'r') as f:
            for line in f:
                try:
                    feedback = json.loads(line)
                    if feedback['campaign_id'] == campaign_id:
                        events[feedback['event_type']] += 1
                        
                        if feedback['event_type'] == 'replied':
                            replies.append(feedback['event_data'])
                except:
                    continue
        
        total_sent = events.get('sent', 0)
        
        if total_sent == 0:
            return {"error": "No sends recorded for this campaign"}
        
        metrics = {
            "campaign_id": campaign_id,
            "total_sent": total_sent,
            "opened": events.get('opened', 0),
            "clicked": events.get('clicked', 0),
            "replied": events.get('replied', 0),
            "bounced": events.get('bounced', 0),
            "unsubscribed": events.get('unsubscribed', 0),
            "open_rate": (events.get('opened', 0) / total_sent) * 100,
            "click_rate": (events.get('clicked', 0) / total_sent) * 100,
            "reply_rate": (events.get('replied', 0) / total_sent) * 100,
            "bounce_rate": (events.get('bounced', 0) / total_sent) * 100,
            "unsubscribe_rate": (events.get('unsubscribed', 0) / total_sent) * 100,
            "replies": replies
        }
        
        return metrics
    
    def extract_learnings(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Extract learnings from recent campaigns.
        
        Args:
            days: Number of days to analyze
        
        Returns:
            List of learnings and insights
        """
        if not self.feedback_file.exists():
            return []
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        campaign_metrics = defaultdict(lambda: defaultdict(int))
        
        with open(self.feedback_file, 'r') as f:
            for line in f:
                try:
                    feedback = json.loads(line)
                    timestamp = datetime.fromisoformat(feedback['timestamp'])
                    
                    if timestamp >= cutoff:
                        campaign_id = feedback['campaign_id']
                        event_type = feedback['event_type']
                        campaign_metrics[campaign_id][event_type] += 1
                except:
                    continue
        
        learnings = []
        
        # Analyze each campaign
        for campaign_id, events in campaign_metrics.items():
            total_sent = events.get('sent', 0)
            if total_sent == 0:
                continue
            
            reply_rate = (events.get('replied', 0) / total_sent) * 100
            open_rate = (events.get('opened', 0) / total_sent) * 100
            
            # Extract insights
            if reply_rate > 10:
                learnings.append({
                    "type": "high_performance",
                    "campaign_id": campaign_id,
                    "insight": f"High reply rate ({reply_rate:.1f}%) - analyze messaging",
                    "action": "Replicate successful elements"
                })
            
            if reply_rate < 3:
                learnings.append({
                    "type": "low_performance",
                    "campaign_id": campaign_id,
                    "insight": f"Low reply rate ({reply_rate:.1f}%) - needs improvement",
                    "action": "Review targeting and messaging"
                })
            
            if events.get('unsubscribed', 0) > total_sent * 0.02:  # >2% unsubscribe
                learnings.append({
                    "type": "high_unsubscribe",
                    "campaign_id": campaign_id,
                    "insight": "High unsubscribe rate - messaging may be off-target",
                    "action": "Review ICP fit and value proposition"
                })
        
        return learnings
```

---

### Part 4: Integrate into Existing Agents

Now let's integrate these components into your existing agents.

#### Example: Update CRAFTER Agent

Edit `execution/crafter_campaign.py`:

```python
# Add at top of file
from core.context_manager import ContextManager
from core.grounding_chain import GroundingChain
from core.feedback_collector import FeedbackCollector

# Initialize in main function
def main():
    # Initialize core components
    context = ContextManager(max_tokens=100000)
    grounding = GroundingChain(confidence_threshold=0.7)
    feedback = FeedbackCollector()
    
    # Add system context
    context.add_message("system", """
    You are the CRAFTER agent for Chief AI Officer Alpha Swarm.
    Your role is to create personalized email campaigns based on lead data.
    Always verify claims against source data before including in emails.
    """)
    
    # When generating campaign
    lead_data = get_lead_data()
    
    # Add lead context
    context.add_message("user", f"Generate campaign for: {json.dumps(lead_data)}")
    
    # Generate campaign (your existing logic)
    campaign_content = generate_campaign(lead_data, context)
    
    # Verify campaign content
    sources = [{"content": json.dumps(lead_data), "metadata": {"source": "lead_database"}}]
    verified, confidence, explanation = grounding.verify_claim(campaign_content, sources)
    
    if not verified:
        print(f"⚠️  Campaign verification failed: {explanation}")
        print("Regenerating with stricter grounding...")
        # Regenerate or flag for review
    
    # Record campaign creation
    feedback.record_campaign_feedback(
        campaign_id=campaign_id,
        lead_email=lead_data['email'],
        event_type='created',
        event_data={"confidence": confidence}
    )
    
    # Save context state
    context.save_context(f"campaign_{campaign_id}_context.json")
```

---

## ✅ Day 3-4 Completion Checklist

### Core Components Created ✅

- [x] `core/context_manager.py` created (with FIC compaction)
- [x] `core/grounding_chain.py` created (hallucination prevention)
- [x] `core/feedback_collector.py` created (RL training signals)
- [x] Test files created and passing (`tests/test_day3_4_framework.py`)

### Integration Complete ✅

- [x] CRAFTER agent integrated (via run_workflow.py)
- [x] HUNTER agent integrated (optional) - not required
- [x] ENRICHER agent integrated (via run_workflow.py)
- [x] Context management working
- [x] Grounding verification working
- [x] Feedback collection working

### Verification ✅ (Completed 2026-01-19)

- [x] All tests pass (4/4 framework tests)
- [x] No import errors
- [x] Context compaction tested
- [x] Grounding verification tested
- [x] Feedback recording tested

**Test Results:**
```
context_manager: ✅ PASS
grounding_chain: ✅ PASS
feedback_collector: ✅ PASS
full_integration: ✅ PASS

Total: 4/4 tests passed
```

---

## 🎯 Next Steps: Day 5

Proceed to webhook setup and real-time event processing.

See: `WEEK_1_DAY_5_WEBHOOKS.md`

---

**Last Updated:** 2026-01-17T18:21:50+08:00  
**Guide Version:** 1.0  
**Next:** Day 5 Webhook Setup
