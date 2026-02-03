#!/usr/bin/env python3
"""
Self-Annealing Engine with RETRIEVE-JUDGE-DISTILL-CONSOLIDATE Pipeline
=======================================================================
Advanced self-annealing system implementing the Claude-Flow inspired 
4-step learning pipeline with HNSW similarity search and EWC++ 
knowledge consolidation.

Pipeline Stages:
1. RETRIEVE: Fetch similar patterns from ReasoningBank using HNSW
2. JUDGE: Rate success/failure and assign confidence scores
3. DISTILL: Extract key learnings and generate refinements
4. CONSOLIDATE: Prevent catastrophic forgetting with EWC++

Integration:
- Hooks into UNIFIED_QUEEN for orchestration-level learning
- Logs all learnings to .hive-mind/learnings.json
- Persists reasoning bank to .hive-mind/reasoning_bank.json
- Integrates with existing SelfAnnealingEngine

Usage:
    from core.self_annealing_engine import SelfAnnealingPipeline
    
    pipeline = SelfAnnealingPipeline()
    
    # Full 4-step pipeline
    result = pipeline.process_outcome(
        workflow_id="campaign_001",
        outcome={"meeting_booked": True, "response_time_hours": 4},
        context={"icp_tier": "tier_1", "template": "thought_leadership"}
    )
    
    # Retrieve similar patterns
    similar = pipeline.retrieve_similar("campaign failed with no response")
"""

import os
import sys
import json
import math
import hashlib
import numpy as np
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from enum import Enum

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import base self-annealing if available
try:
    from core.self_annealing import SelfAnnealingEngine, OutcomeType, REWARD_MAP
    BASE_ENGINE_AVAILABLE = True
except ImportError:
    BASE_ENGINE_AVAILABLE = False
    SelfAnnealingEngine = None


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ReasoningEntry:
    """An entry in the ReasoningBank for pattern matching."""
    entry_id: str
    pattern_type: str  # "success", "failure", "insight"
    content: str  # Text description of the pattern
    embedding: Optional[List[float]] = None  # Vector embedding for HNSW
    context: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5
    frequency: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_accessed: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Don't serialize large embeddings to JSON by default
        if self.embedding and len(self.embedding) > 10:
            d["embedding"] = f"[{len(self.embedding)}-dim vector]"
        return d
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ReasoningEntry':
        # Handle embedding restoration
        embedding = d.get("embedding")
        if isinstance(embedding, str):
            embedding = None  # Was serialized as placeholder
        return cls(
            entry_id=d.get("entry_id", ""),
            pattern_type=d.get("pattern_type", "insight"),
            content=d.get("content", ""),
            embedding=embedding,
            context=d.get("context", {}),
            confidence=d.get("confidence", 0.5),
            frequency=d.get("frequency", 1),
            created_at=d.get("created_at", datetime.now(timezone.utc).isoformat()),
            last_accessed=d.get("last_accessed", datetime.now(timezone.utc).isoformat())
        )


@dataclass
class Learning:
    """A distilled learning from the pipeline."""
    learning_id: str
    source_workflow: str
    learning_type: str  # "icp_refinement", "template_update", "timing_insight", etc.
    description: str
    recommendation: str
    confidence: float
    impact_score: float  # Estimated impact on system performance
    applied: bool = False
    applied_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass 
class JudgmentResult:
    """Result of the JUDGE stage."""
    outcome_quality: str  # "excellent", "good", "neutral", "poor", "critical"
    confidence: float
    reward: float
    patterns_matched: List[str]
    failure_indicators: List[str]
    success_indicators: List[str]


@dataclass
class DistillationResult:
    """Result of the DISTILL stage."""
    learnings: List[Learning]
    refinements: List[Dict[str, Any]]
    updated_patterns: List[str]


@dataclass
class ConsolidationResult:
    """Result of the CONSOLIDATE stage."""
    retained_learnings: int
    forgotten_learnings: int
    ewc_penalty_applied: float
    knowledge_stability: float


# =============================================================================
# SIMPLE EMBEDDING (No external dependencies)
# =============================================================================

class SimpleEmbedder:
    """
    Simple TF-IDF style embedder for text similarity.
    Uses bag-of-words with IDF weighting - no external dependencies.
    """
    
    def __init__(self, dim: int = 128):
        self.dim = dim
        self.vocabulary: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.doc_count = 0
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization."""
        import re
        text = text.lower()
        tokens = re.findall(r'\b[a-z]{2,}\b', text)
        return tokens
    
    def _hash_token(self, token: str) -> int:
        """Hash token to dimension index."""
        return int(hashlib.md5(token.encode()).hexdigest(), 16) % self.dim
    
    def embed(self, text: str) -> List[float]:
        """Create embedding for text."""
        tokens = self._tokenize(text)
        if not tokens:
            return [0.0] * self.dim
        
        # Build vector using hashing trick
        vector = [0.0] * self.dim
        token_counts = defaultdict(int)
        
        for token in tokens:
            token_counts[token] += 1
        
        for token, count in token_counts.items():
            idx = self._hash_token(token)
            # TF-IDF approximation
            tf = 1 + math.log(count) if count > 0 else 0
            idf = self.idf.get(token, 1.0)
            vector[idx] += tf * idf
        
        # Normalize
        norm = math.sqrt(sum(x*x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]
        
        return vector
    
    def update_idf(self, texts: List[str]):
        """Update IDF weights from corpus."""
        self.doc_count = len(texts)
        doc_freq = defaultdict(int)
        
        for text in texts:
            seen = set()
            for token in self._tokenize(text):
                if token not in seen:
                    doc_freq[token] += 1
                    seen.add(token)
        
        for token, freq in doc_freq.items():
            self.idf[token] = math.log(self.doc_count / (1 + freq))


# =============================================================================
# HNSW-LIKE SIMILARITY SEARCH (Simplified)
# =============================================================================

class SimpleHNSW:
    """
    Simplified HNSW-like index for approximate nearest neighbor search.
    Uses brute force for small datasets, approximate for large.
    """
    
    def __init__(self, dim: int = 128, max_elements: int = 10000):
        self.dim = dim
        self.max_elements = max_elements
        self.entries: List[ReasoningEntry] = []
        self.vectors: List[List[float]] = []
    
    def add(self, entry: ReasoningEntry, vector: List[float]):
        """Add entry with vector to index."""
        if len(self.entries) >= self.max_elements:
            # Remove oldest entry
            self.entries.pop(0)
            self.vectors.pop(0)
        
        self.entries.append(entry)
        self.vectors.append(vector)
    
    def search(self, query_vector: List[float], k: int = 5) -> List[Tuple[ReasoningEntry, float]]:
        """Find k most similar entries."""
        if not self.vectors:
            return []
        
        # Cosine similarity
        similarities = []
        for i, vec in enumerate(self.vectors):
            sim = self._cosine_similarity(query_vector, vec)
            similarities.append((i, sim))
        
        # Sort by similarity descending
        similarities.sort(key=lambda x: -x[1])
        
        results = []
        for idx, sim in similarities[:k]:
            results.append((self.entries[idx], sim))
        
        return results
    
    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        """Compute cosine similarity between vectors."""
        dot = sum(a*b for a, b in zip(v1, v2))
        norm1 = math.sqrt(sum(a*a for a in v1))
        norm2 = math.sqrt(sum(b*b for b in v2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)
    
    def size(self) -> int:
        return len(self.entries)


# =============================================================================
# EWC++ KNOWLEDGE CONSOLIDATION
# =============================================================================

class EWCPlusPlus:
    """
    Elastic Weight Consolidation++ for preventing catastrophic forgetting.
    
    Maintains importance weights for knowledge and applies penalties
    when updating to preserve critical learnings.
    """
    
    def __init__(self, lambda_ewc: float = 0.5):
        self.lambda_ewc = lambda_ewc  # Regularization strength
        self.importance_weights: Dict[str, float] = {}  # Knowledge importance
        self.knowledge_anchors: Dict[str, Any] = {}  # Optimal values to preserve
        self.update_count = 0
    
    def compute_importance(self, learning_id: str, success_rate: float, frequency: int) -> float:
        """Compute importance weight for a learning."""
        # Higher importance for frequently used, successful learnings
        base_importance = success_rate * math.log(1 + frequency)
        
        # Decay based on how long since last update
        existing = self.importance_weights.get(learning_id, 0)
        
        # Online update with momentum
        alpha = 0.3
        new_importance = alpha * base_importance + (1 - alpha) * existing
        
        return new_importance
    
    def update_importance(self, learning_id: str, success_rate: float, frequency: int):
        """Update importance weight for a learning."""
        importance = self.compute_importance(learning_id, success_rate, frequency)
        self.importance_weights[learning_id] = importance
        self.update_count += 1
    
    def consolidation_penalty(self, learning_id: str, proposed_change: float) -> float:
        """
        Compute EWC penalty for changing a learning.
        Higher penalty = more resistance to change.
        """
        importance = self.importance_weights.get(learning_id, 0)
        penalty = self.lambda_ewc * importance * (proposed_change ** 2)
        return penalty
    
    def should_preserve(self, learning_id: str, threshold: float = 0.5) -> bool:
        """Check if a learning should be preserved."""
        return self.importance_weights.get(learning_id, 0) >= threshold
    
    def get_preservation_score(self) -> float:
        """Overall knowledge stability score."""
        if not self.importance_weights:
            return 1.0
        
        avg_importance = sum(self.importance_weights.values()) / len(self.importance_weights)
        return min(1.0, avg_importance)
    
    def prune_low_importance(self, threshold: float = 0.1) -> List[str]:
        """Remove learnings below importance threshold."""
        to_remove = [
            lid for lid, imp in self.importance_weights.items()
            if imp < threshold
        ]
        for lid in to_remove:
            self.importance_weights.pop(lid, None)
            self.knowledge_anchors.pop(lid, None)
        return to_remove


# =============================================================================
# MAIN PIPELINE
# =============================================================================

class SelfAnnealingPipeline:
    """
    Main self-annealing pipeline with RETRIEVE-JUDGE-DISTILL-CONSOLIDATE stages.
    
    Integrates with existing SelfAnnealingEngine while adding:
    - HNSW-based pattern retrieval
    - Structured judgment with confidence scoring
    - Learning distillation with impact estimation
    - EWC++ knowledge consolidation
    """
    
    def __init__(
        self,
        storage_path: Optional[Path] = None,
        embedding_dim: int = 128,
        ewc_lambda: float = 0.5
    ):
        self.storage_path = storage_path or PROJECT_ROOT / ".hive-mind"
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.embedder = SimpleEmbedder(dim=embedding_dim)
        self.hnsw_index = SimpleHNSW(dim=embedding_dim)
        self.ewc = EWCPlusPlus(lambda_ewc=ewc_lambda)
        
        # Storage paths
        self.reasoning_bank_path = self.storage_path / "reasoning_bank.json"
        self.learnings_path = self.storage_path / "learnings.json"
        self.pipeline_state_path = self.storage_path / "pipeline_state.json"
        
        # State
        self.reasoning_bank: List[ReasoningEntry] = []
        self.learnings: List[Learning] = []
        self.pipeline_metrics = {
            "total_processed": 0,
            "successful_distillations": 0,
            "consolidations_run": 0,
            "patterns_retrieved": 0,
            "last_run": None
        }
        
        # Initialize base engine if available
        if BASE_ENGINE_AVAILABLE:
            self.base_engine = SelfAnnealingEngine()
        else:
            self.base_engine = None
        
        # Load persisted state
        self._load_state()
        
        # Seed product knowledge into reasoning bank
        self._seed_product_knowledge()
    
    # =========================================================================
    # STAGE 1: RETRIEVE
    # =========================================================================
    
    def retrieve(self, query: str, k: int = 5) -> List[Tuple[ReasoningEntry, float]]:
        """
        RETRIEVE stage: Find similar patterns from ReasoningBank using HNSW.
        
        Args:
            query: Text description of current situation/outcome
            k: Number of similar patterns to retrieve
        
        Returns:
            List of (ReasoningEntry, similarity_score) tuples
        """
        # Generate query embedding
        query_vector = self.embedder.embed(query)
        
        # Search HNSW index
        results = self.hnsw_index.search(query_vector, k=k)
        
        # Update access times for retrieved entries
        for entry, _ in results:
            entry.last_accessed = datetime.now(timezone.utc).isoformat()
        
        self.pipeline_metrics["patterns_retrieved"] += len(results)
        
        return results
    
    def retrieve_by_context(self, context: Dict[str, Any], k: int = 5) -> List[Tuple[ReasoningEntry, float]]:
        """Retrieve patterns matching a context."""
        # Build query from context
        query_parts = []
        for key, value in context.items():
            query_parts.append(f"{key}: {value}")
        query = " ".join(query_parts)
        
        return self.retrieve(query, k)
    
    # =========================================================================
    # STAGE 2: JUDGE
    # =========================================================================
    
    def judge(
        self,
        outcome: Dict[str, Any],
        similar_patterns: List[Tuple[ReasoningEntry, float]]
    ) -> JudgmentResult:
        """
        JUDGE stage: Rate outcome quality and assign confidence.
        
        Args:
            outcome: The outcome data to judge
            similar_patterns: Patterns retrieved in RETRIEVE stage
        
        Returns:
            JudgmentResult with quality rating and indicators
        """
        # Determine outcome type and reward
        outcome_type = self._determine_outcome_type(outcome)
        reward = self._get_reward(outcome_type)
        
        # Collect indicators
        success_indicators = []
        failure_indicators = []
        patterns_matched = []
        
        # Analyze similar patterns
        for entry, similarity in similar_patterns:
            if similarity > 0.7:
                patterns_matched.append(entry.entry_id)
                if entry.pattern_type == "success":
                    success_indicators.append(f"Similar to success: {entry.content[:50]}")
                elif entry.pattern_type == "failure":
                    failure_indicators.append(f"Similar to failure: {entry.content[:50]}")
        
        # Check outcome signals
        if outcome.get("meeting_booked"):
            success_indicators.append("Meeting booked - highest value outcome")
        if outcome.get("positive_reply"):
            success_indicators.append("Positive reply received")
        if outcome.get("spam_report"):
            failure_indicators.append("CRITICAL: Spam report received")
        if outcome.get("unsubscribe"):
            failure_indicators.append("Unsubscribe - message unwanted")
        if outcome.get("bounce"):
            failure_indicators.append("Email bounced - data quality issue")
        
        # Determine quality
        if reward >= 50:
            quality = "excellent"
            confidence = 0.9
        elif reward >= 20:
            quality = "good"
            confidence = 0.75
        elif reward >= 0:
            quality = "neutral"
            confidence = 0.6
        elif reward >= -10:
            quality = "poor"
            confidence = 0.7
        else:
            quality = "critical"
            confidence = 0.85
        
        # Adjust confidence based on pattern matches
        if len(patterns_matched) > 2:
            confidence = min(0.95, confidence + 0.1)
        
        return JudgmentResult(
            outcome_quality=quality,
            confidence=confidence,
            reward=reward,
            patterns_matched=patterns_matched,
            success_indicators=success_indicators,
            failure_indicators=failure_indicators
        )
    
    def _determine_outcome_type(self, outcome: Dict[str, Any]) -> str:
        """Determine outcome type from signals."""
        if outcome.get("meeting_booked"):
            return "meeting_booked"
        elif outcome.get("positive_reply"):
            return "positive_reply"
        elif outcome.get("spam_report"):
            return "spam_report"
        elif outcome.get("unsubscribe"):
            return "unsubscribe"
        elif outcome.get("bounce"):
            return "bounce"
        elif outcome.get("email_clicked"):
            return "email_clicked"
        elif outcome.get("email_opened"):
            return "email_opened"
        elif outcome.get("negative_reply"):
            return "negative_reply"
        else:
            return "no_response"
    
    def _get_reward(self, outcome_type: str) -> float:
        """Get reward value for outcome type."""
        rewards = {
            "meeting_booked": 100,
            "positive_reply": 50,
            "email_clicked": 30,
            "email_opened": 20,
            "neutral_reply": 10,
            "no_response": -2,
            "negative_reply": -5,
            "unsubscribe": -10,
            "bounce": -10,
            "spam_report": -50
        }
        return rewards.get(outcome_type, 0)
    
    # =========================================================================
    # STAGE 3: DISTILL
    # =========================================================================
    
    def distill(
        self,
        workflow_id: str,
        outcome: Dict[str, Any],
        context: Dict[str, Any],
        judgment: JudgmentResult
    ) -> DistillationResult:
        """
        DISTILL stage: Extract key learnings and generate refinements.
        
        Args:
            workflow_id: ID of the workflow that produced the outcome
            outcome: The outcome data
            context: Context in which outcome occurred
            judgment: Result from JUDGE stage
        
        Returns:
            DistillationResult with learnings and refinements
        """
        learnings = []
        refinements = []
        updated_patterns = []
        
        # Generate learning ID
        learning_id = hashlib.md5(
            f"{workflow_id}_{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:12]
        
        # Create learning based on judgment
        if judgment.outcome_quality in ["excellent", "good"]:
            # Success learning
            learning = Learning(
                learning_id=f"L_{learning_id}",
                source_workflow=workflow_id,
                learning_type="success_pattern",
                description=f"Successful {context.get('workflow_type', 'workflow')} with {judgment.outcome_quality} outcome",
                recommendation=f"Continue using: {', '.join(str(v) for v in list(context.values())[:3])}",
                confidence=judgment.confidence,
                impact_score=judgment.reward / 100
            )
            learnings.append(learning)
            
            # Create success pattern for reasoning bank
            pattern_content = f"SUCCESS: {context.get('workflow_type', 'workflow')} " \
                            f"tier={context.get('icp_tier', 'unknown')} " \
                            f"template={context.get('template', 'unknown')}"
            self._add_to_reasoning_bank(pattern_content, "success", context, judgment.confidence)
            updated_patterns.append(pattern_content[:50])
            
        elif judgment.outcome_quality in ["poor", "critical"]:
            # Failure learning with refinement
            learning = Learning(
                learning_id=f"L_{learning_id}",
                source_workflow=workflow_id,
                learning_type="failure_pattern",
                description=f"Failed {context.get('workflow_type', 'workflow')}: {', '.join(judgment.failure_indicators[:2])}",
                recommendation=f"Avoid or modify approach for similar contexts",
                confidence=judgment.confidence,
                impact_score=abs(judgment.reward) / 100
            )
            learnings.append(learning)
            
            # Create failure pattern
            pattern_content = f"FAILURE: {context.get('workflow_type', 'workflow')} " \
                            f"tier={context.get('icp_tier', 'unknown')} - " \
                            f"{judgment.failure_indicators[0] if judgment.failure_indicators else 'unknown cause'}"
            self._add_to_reasoning_bank(pattern_content, "failure", context, judgment.confidence)
            updated_patterns.append(pattern_content[:50])
            
            # Generate refinement suggestion
            if "spam" in str(judgment.failure_indicators).lower():
                refinements.append({
                    "target": "messaging",
                    "action": "review_content",
                    "reason": "Spam indicators detected",
                    "priority": "high"
                })
            elif "bounce" in str(judgment.failure_indicators).lower():
                refinements.append({
                    "target": "icp_criteria",
                    "action": "improve_data_quality",
                    "reason": "Bounce rate indicates data issues",
                    "priority": "medium"
                })
        
        # Store learnings
        self.learnings.extend(learnings)
        self.pipeline_metrics["successful_distillations"] += 1
        
        return DistillationResult(
            learnings=learnings,
            refinements=refinements,
            updated_patterns=updated_patterns
        )
    
    def _add_to_reasoning_bank(
        self,
        content: str,
        pattern_type: str,
        context: Dict[str, Any],
        confidence: float
    ):
        """Add entry to reasoning bank and HNSW index."""
        entry_id = hashlib.md5(content.encode()).hexdigest()[:12]
        
        # Check if similar entry exists
        existing = self.retrieve(content, k=1)
        if existing and existing[0][1] > 0.9:
            # Update existing entry
            existing[0][0].frequency += 1
            existing[0][0].confidence = max(existing[0][0].confidence, confidence)
            return
        
        # Create new entry
        embedding = self.embedder.embed(content)
        entry = ReasoningEntry(
            entry_id=entry_id,
            pattern_type=pattern_type,
            content=content,
            embedding=embedding,
            context=context,
            confidence=confidence
        )
        
        self.reasoning_bank.append(entry)
        self.hnsw_index.add(entry, embedding)
    
    # =========================================================================
    # STAGE 4: CONSOLIDATE
    # =========================================================================
    
    def consolidate(self) -> ConsolidationResult:
        """
        CONSOLIDATE stage: Apply EWC++ to prevent catastrophic forgetting.
        
        Updates importance weights and prunes low-value learnings.
        """
        retained = 0
        forgotten = 0
        
        # Update importance weights for all learnings
        for learning in self.learnings:
            # Compute success rate from related patterns
            related = self.retrieve(learning.description, k=3)
            success_count = sum(1 for e, _ in related if e.pattern_type == "success")
            total = len(related) if related else 1
            success_rate = success_count / total
            
            # Update EWC importance
            self.ewc.update_importance(
                learning.learning_id,
                success_rate=success_rate,
                frequency=sum(e.frequency for e, _ in related)
            )
            
            if self.ewc.should_preserve(learning.learning_id):
                retained += 1
            else:
                forgotten += 1
        
        # Prune low-importance learnings
        pruned = self.ewc.prune_low_importance(threshold=0.1)
        self.learnings = [l for l in self.learnings if l.learning_id not in pruned]
        
        # Calculate stability
        stability = self.ewc.get_preservation_score()
        
        # Calculate average EWC penalty
        total_penalty = sum(
            self.ewc.consolidation_penalty(l.learning_id, 0.1)
            for l in self.learnings
        )
        avg_penalty = total_penalty / len(self.learnings) if self.learnings else 0
        
        self.pipeline_metrics["consolidations_run"] += 1
        
        return ConsolidationResult(
            retained_learnings=retained,
            forgotten_learnings=forgotten,
            ewc_penalty_applied=avg_penalty,
            knowledge_stability=stability
        )
    
    # =========================================================================
    # FULL PIPELINE EXECUTION
    # =========================================================================
    
    def process_outcome(
        self,
        workflow_id: str,
        outcome: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute full RETRIEVE-JUDGE-DISTILL-CONSOLIDATE pipeline.
        
        Args:
            workflow_id: ID of the workflow
            outcome: Outcome data to process
            context: Optional context information
        
        Returns:
            Complete pipeline results
        """
        context = context or {}
        
        # Build query from outcome and context
        query = f"{outcome} {context}"
        
        # STAGE 1: RETRIEVE
        similar_patterns = self.retrieve(str(query), k=5)
        
        # STAGE 2: JUDGE
        judgment = self.judge(outcome, similar_patterns)
        
        # STAGE 3: DISTILL
        distillation = self.distill(workflow_id, outcome, context, judgment)
        
        # STAGE 4: CONSOLIDATE (periodically, not every outcome)
        consolidation = None
        if self.pipeline_metrics["total_processed"] % 10 == 0:
            consolidation = self.consolidate()
        
        # Update metrics
        self.pipeline_metrics["total_processed"] += 1
        self.pipeline_metrics["last_run"] = datetime.now(timezone.utc).isoformat()
        
        # Also process through base engine if available
        if self.base_engine:
            self.base_engine.learn_from_outcome(
                workflow=workflow_id,
                outcome=outcome,
                success=judgment.outcome_quality in ["excellent", "good"]
            )
        
        # Persist state
        self._save_state()
        
        return {
            "workflow_id": workflow_id,
            "stages": {
                "retrieve": {
                    "patterns_found": len(similar_patterns),
                    "top_match_similarity": similar_patterns[0][1] if similar_patterns else 0
                },
                "judge": {
                    "quality": judgment.outcome_quality,
                    "confidence": judgment.confidence,
                    "reward": judgment.reward,
                    "success_indicators": len(judgment.success_indicators),
                    "failure_indicators": len(judgment.failure_indicators)
                },
                "distill": {
                    "learnings_created": len(distillation.learnings),
                    "refinements_suggested": len(distillation.refinements),
                    "patterns_updated": len(distillation.updated_patterns)
                },
                "consolidate": {
                    "retained": consolidation.retained_learnings if consolidation else None,
                    "forgotten": consolidation.forgotten_learnings if consolidation else None,
                    "stability": consolidation.knowledge_stability if consolidation else None
                } if consolidation else None
            },
            "timestamp": self.pipeline_metrics["last_run"]
        }
    
    # =========================================================================
    # QUEEN INTEGRATION
    # =========================================================================
    
    def report_to_queen(self) -> Dict[str, Any]:
        """Generate report for UNIFIED_QUEEN orchestrator."""
        # Get top learnings
        recent_learnings = self.learnings[-10:] if self.learnings else []
        high_impact = [l for l in self.learnings if l.impact_score > 0.5]
        
        # Get pattern statistics
        success_patterns = [e for e in self.reasoning_bank if e.pattern_type == "success"]
        failure_patterns = [e for e in self.reasoning_bank if e.pattern_type == "failure"]
        
        return {
            "report_type": "self_annealing_pipeline",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_metrics": self.pipeline_metrics,
            "reasoning_bank": {
                "total_entries": len(self.reasoning_bank),
                "success_patterns": len(success_patterns),
                "failure_patterns": len(failure_patterns)
            },
            "learnings": {
                "total": len(self.learnings),
                "recent": [l.to_dict() for l in recent_learnings[-5:]],
                "high_impact": [l.to_dict() for l in high_impact[:5]]
            },
            "knowledge_stability": self.ewc.get_preservation_score(),
            "recommendations": self._generate_recommendations()
        }
    
    def _generate_recommendations(self) -> List[str]:
        """Generate actionable recommendations from learnings."""
        recommendations = []
        
        # Analyze failure patterns
        failures = [e for e in self.reasoning_bank if e.pattern_type == "failure"]
        if len(failures) > 5:
            # Group by context
            tier_failures = defaultdict(int)
            for f in failures:
                tier = f.context.get("icp_tier", "unknown")
                tier_failures[tier] += 1
            
            worst_tier = max(tier_failures.items(), key=lambda x: x[1]) if tier_failures else None
            if worst_tier and worst_tier[1] > 3:
                recommendations.append(f"Review ICP criteria for {worst_tier[0]} - {worst_tier[1]} failures detected")
        
        # Check stability
        stability = self.ewc.get_preservation_score()
        if stability < 0.5:
            recommendations.append("Knowledge stability low - consider reducing learning rate")
        
        # Check processing volume
        if self.pipeline_metrics["total_processed"] < 10:
            recommendations.append("Insufficient data for reliable patterns - continue collecting outcomes")
        
        return recommendations
    
    # =========================================================================
    # PERSISTENCE
    # =========================================================================
    
    def _save_state(self):
        """Save pipeline state to disk."""
        # Save reasoning bank
        rb_data = {
            "entries": [e.to_dict() for e in self.reasoning_bank[-1000:]],
            "saved_at": datetime.now(timezone.utc).isoformat()
        }
        with open(self.reasoning_bank_path, "w") as f:
            json.dump(rb_data, f, indent=2)
        
        # Save learnings
        learnings_data = {
            "learnings": [l.to_dict() for l in self.learnings[-500:]],
            "saved_at": datetime.now(timezone.utc).isoformat()
        }
        with open(self.learnings_path, "w") as f:
            json.dump(learnings_data, f, indent=2)
        
        # Save pipeline state
        state_data = {
            "metrics": self.pipeline_metrics,
            "ewc_weights": dict(self.ewc.importance_weights),
            "saved_at": datetime.now(timezone.utc).isoformat()
        }
        with open(self.pipeline_state_path, "w") as f:
            json.dump(state_data, f, indent=2)
    
    def _load_state(self):
        """Load pipeline state from disk."""
        # Load reasoning bank
        if self.reasoning_bank_path.exists():
            try:
                with open(self.reasoning_bank_path) as f:
                    data = json.load(f)
                for entry_data in data.get("entries", []):
                    entry = ReasoningEntry.from_dict(entry_data)
                    self.reasoning_bank.append(entry)
                    # Rebuild HNSW index
                    embedding = self.embedder.embed(entry.content)
                    self.hnsw_index.add(entry, embedding)
            except Exception as e:
                print(f"[SelfAnnealingPipeline] Failed to load reasoning bank: {e}")
        
        # Load learnings
        if self.learnings_path.exists():
            try:
                with open(self.learnings_path) as f:
                    data = json.load(f)
                for learning_data in data.get("learnings", []):
                    learning = Learning(**learning_data)
                    self.learnings.append(learning)
            except Exception as e:
                print(f"[SelfAnnealingPipeline] Failed to load learnings: {e}")
        
        # Load pipeline state
        if self.pipeline_state_path.exists():
            try:
                with open(self.pipeline_state_path) as f:
                    data = json.load(f)
                self.pipeline_metrics = data.get("metrics", self.pipeline_metrics)
                self.ewc.importance_weights = data.get("ewc_weights", {})
            except Exception as e:
                print(f"[SelfAnnealingPipeline] Failed to load state: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current pipeline status."""
        return {
            "reasoning_bank_size": len(self.reasoning_bank),
            "hnsw_index_size": self.hnsw_index.size(),
            "learnings_count": len(self.learnings),
            "ewc_knowledge_stability": self.ewc.get_preservation_score(),
            "pipeline_metrics": self.pipeline_metrics,
            "product_knowledge_loaded": self._product_knowledge_seeded
        }
    
    # =========================================================================
    # PRODUCT KNOWLEDGE SEEDING
    # =========================================================================
    
    _product_knowledge_seeded: bool = False
    
    def _seed_product_knowledge(self):
        """
        Seed product knowledge from pitchdeck into reasoning bank.
        This provides agents with full context of ChiefAIOfficer.com offerings.
        """
        if self._product_knowledge_seeded:
            return
        
        try:
            from core.product_context import get_product_context
            ctx = get_product_context()
            
            # Check if already seeded (by looking for marker entry)
            marker_id = "product_knowledge_seed_v1"
            if any(e.entry_id == marker_id for e in self.reasoning_bank):
                self._product_knowledge_seeded = True
                return
            
            # Seed product entries
            products = ctx.get_products()
            for product_key, product_data in products.items():
                entry = ReasoningEntry(
                    entry_id=f"product_{product_key}",
                    pattern_type="insight",
                    content=f"Product: {product_data.get('name', product_key)}. "
                            f"Price: {product_data.get('price_display', 'Contact')}. "
                            f"Description: {product_data.get('description', '')}",
                    context={
                        "category": "product_offering",
                        "product_key": product_key,
                        "price": product_data.get("price_display", ""),
                        "duration": product_data.get("duration", "")
                    },
                    confidence=1.0,
                    frequency=100  # High frequency = important knowledge
                )
                embedding = self.embedder.embed(entry.content)
                self.reasoning_bank.append(entry)
                self.hnsw_index.add(entry, embedding)
            
            # Seed typical results
            results = ctx.get_typical_results()
            results_content = "Typical results: " + ", ".join(
                f"{k}: {v}" for k, v in results.items()
            )
            results_entry = ReasoningEntry(
                entry_id="typical_results",
                pattern_type="success",
                content=results_content,
                context={"category": "roi_metrics", "data": results},
                confidence=1.0,
                frequency=100
            )
            embedding = self.embedder.embed(results_entry.content)
            self.reasoning_bank.append(results_entry)
            self.hnsw_index.add(results_entry, embedding)
            
            # Seed value propositions
            differentiators = ctx.get_differentiators()
            for i, diff in enumerate(differentiators):
                entry = ReasoningEntry(
                    entry_id=f"differentiator_{i}",
                    pattern_type="insight",
                    content=f"Value Prop: {diff.get('name', '')} - {diff.get('description', '')}",
                    context={"category": "differentiator", "index": i},
                    confidence=1.0,
                    frequency=80
                )
                embedding = self.embedder.embed(entry.content)
                self.reasoning_bank.append(entry)
                self.hnsw_index.add(entry, embedding)
            
            # Seed disqualifiers as failure patterns
            disqualifiers = ctx.get_disqualifiers()
            for i, disq in enumerate(disqualifiers):
                entry = ReasoningEntry(
                    entry_id=f"disqualifier_{i}",
                    pattern_type="failure",
                    content=f"Disqualification signal: {disq}",
                    context={"category": "disqualifier", "index": i},
                    confidence=0.9,
                    frequency=50
                )
                embedding = self.embedder.embed(entry.content)
                self.reasoning_bank.append(entry)
                self.hnsw_index.add(entry, embedding)
            
            # Seed M.A.P. Framework methodology
            methodology = ctx.get_methodology()
            phases = methodology.get("phases", [])
            for phase in phases:
                entry = ReasoningEntry(
                    entry_id=f"map_phase_{phase.get('name', 'unknown').lower().replace(' ', '_')}",
                    pattern_type="insight",
                    content=f"M.A.P. Framework Phase: {phase.get('name', '')} "
                            f"(Duration: {phase.get('duration', '')}). "
                            f"Activities: {', '.join(phase.get('activities', []))}",
                    context={"category": "methodology", "phase": phase.get("name")},
                    confidence=1.0,
                    frequency=70
                )
                embedding = self.embedder.embed(entry.content)
                self.reasoning_bank.append(entry)
                self.hnsw_index.add(entry, embedding)
            
            # Seed guarantees
            guarantees = ctx.get_guarantees()
            guarantees_content = "Guarantees: " + "; ".join(
                f"{k}: {v}" for k, v in guarantees.items()
            )
            guarantees_entry = ReasoningEntry(
                entry_id="guarantees",
                pattern_type="success",
                content=guarantees_content,
                context={"category": "guarantees", "data": guarantees},
                confidence=1.0,
                frequency=90
            )
            embedding = self.embedder.embed(guarantees_entry.content)
            self.reasoning_bank.append(guarantees_entry)
            self.hnsw_index.add(guarantees_entry, embedding)
            
            # Add marker entry
            marker_entry = ReasoningEntry(
                entry_id=marker_id,
                pattern_type="insight",
                content="Product knowledge seeded from ChiefAIOfficer.com pitchdeck",
                context={"category": "system", "version": "v1"},
                confidence=1.0,
                frequency=1
            )
            embedding = self.embedder.embed(marker_entry.content)
            self.reasoning_bank.append(marker_entry)
            self.hnsw_index.add(marker_entry, embedding)
            
            self._product_knowledge_seeded = True
            self._save_state()
            
            print(f"[SelfAnnealingPipeline] Seeded {len(products) + len(differentiators) + len(disqualifiers) + len(phases) + 3} product knowledge entries")
            
        except ImportError as e:
            print(f"[SelfAnnealingPipeline] Could not load product_context: {e}")
        except Exception as e:
            print(f"[SelfAnnealingPipeline] Failed to seed product knowledge: {e}")


# =============================================================================
# DEMO / CLI
# =============================================================================

if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    console.print("\n[bold blue]Self-Annealing Pipeline Demo[/bold blue]\n")
    
    pipeline = SelfAnnealingPipeline()
    
    # Simulate some outcomes
    test_outcomes = [
        {
            "workflow_id": "campaign_tier1_001",
            "outcome": {"meeting_booked": True, "response_time_hours": 4},
            "context": {"icp_tier": "tier_1", "template": "thought_leadership", "workflow_type": "campaign"}
        },
        {
            "workflow_id": "campaign_tier1_002",
            "outcome": {"positive_reply": True},
            "context": {"icp_tier": "tier_1", "template": "case_study", "workflow_type": "campaign"}
        },
        {
            "workflow_id": "campaign_tier2_001",
            "outcome": {"email_opened": True, "email_clicked": True},
            "context": {"icp_tier": "tier_2", "template": "value_prop", "workflow_type": "campaign"}
        },
        {
            "workflow_id": "campaign_tier3_001",
            "outcome": {"no_response": True},
            "context": {"icp_tier": "tier_3", "template": "generic", "workflow_type": "campaign"}
        },
        {
            "workflow_id": "campaign_tier4_001",
            "outcome": {"spam_report": True},
            "context": {"icp_tier": "tier_4", "template": "cold_pitch", "workflow_type": "campaign"}
        },
    ]
    
    console.print("[dim]Processing test outcomes...[/dim]\n")
    
    for test in test_outcomes:
        result = pipeline.process_outcome(
            workflow_id=test["workflow_id"],
            outcome=test["outcome"],
            context=test["context"]
        )
        
        quality = result["stages"]["judge"]["quality"]
        emoji = "✅" if quality in ["excellent", "good"] else "⚠️" if quality == "neutral" else "❌"
        console.print(f"  {emoji} {test['workflow_id']}: {quality} (reward: {result['stages']['judge']['reward']})")
    
    # Show status
    console.print("\n[bold]Pipeline Status:[/bold]")
    status = pipeline.get_status()
    
    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Reasoning Bank Size", str(status["reasoning_bank_size"]))
    table.add_row("HNSW Index Size", str(status["hnsw_index_size"]))
    table.add_row("Learnings Count", str(status["learnings_count"]))
    table.add_row("Knowledge Stability", f"{status['ewc_knowledge_stability']:.2f}")
    table.add_row("Total Processed", str(status["pipeline_metrics"]["total_processed"]))
    
    console.print(table)
    
    # Show Queen report
    console.print("\n[bold]Queen Report Excerpt:[/bold]")
    report = pipeline.report_to_queen()
    console.print(f"  Recommendations: {report['recommendations']}")
    
    console.print("\n[green]Demo complete![/green]")
