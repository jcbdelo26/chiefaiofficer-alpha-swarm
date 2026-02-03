"""
Context Handoff Protocol - Standardized Agent Communication
============================================================

Ensures proper context transfer between agents to avoid:
1. Information loss during handoffs
2. Context window overflow
3. Missing critical facts
4. Broken decision chains
"""

import os
import json
import logging
import hashlib
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('context_handoff')


class HandoffType(Enum):
    """Types of context handoffs between agents"""
    SEQUENTIAL = "sequential"       # Agent A -> Agent B
    PARALLEL_MERGE = "parallel_merge"  # Agents A,B,C -> Agent D
    ESCALATION = "escalation"       # Agent -> Human
    RETRY = "retry"                 # Same agent, new attempt
    BROADCAST = "broadcast"         # One agent -> Many agents


class HandoffStatus(Enum):
    """Status of a handoff"""
    PENDING = "pending"
    RECEIVED = "received"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class CriticalFact:
    """A fact that MUST be preserved across handoffs"""
    key: str
    value: Any
    source: str
    importance: str  # critical, high, medium
    expires_at: Optional[str] = None


@dataclass
class Decision:
    """A decision made by an agent"""
    agent: str
    decision_type: str
    choice: str
    reasoning: str
    timestamp: str
    reversible: bool = True


@dataclass
class PendingAction:
    """An action that needs to happen"""
    action_type: str
    target: str
    parameters: Dict[str, Any]
    priority: int  # 1-10
    deadline: Optional[str] = None
    assigned_to: Optional[str] = None


@dataclass
class ContextPacket:
    """
    Standardized context package for agent handoffs.
    
    This is the "envelope" that carries all context between agents.
    """
    # Identity
    id: str
    source_agent: str
    target_agent: str
    handoff_type: HandoffType
    timestamp: str
    
    # Status tracking
    status: HandoffStatus = HandoffStatus.PENDING
    received_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    # Core payload
    payload: Dict[str, Any] = field(default_factory=dict)
    
    # Compacted summary for LLM context windows
    summary: str = ""
    
    # Must-preserve information
    critical_facts: List[CriticalFact] = field(default_factory=list)
    
    # Decision trail
    decisions_made: List[Decision] = field(default_factory=list)
    
    # What needs to happen next
    pending_actions: List[PendingAction] = field(default_factory=list)
    
    # Data provenance
    grounding_evidence: Dict[str, Any] = field(default_factory=dict)
    
    # Error history
    errors_encountered: List[str] = field(default_factory=list)
    
    # Context budget tracking (0-1, how much context this uses)
    context_budget_used: float = 0.0
    
    # Chain tracking
    parent_handoff_id: Optional[str] = None
    child_handoff_ids: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            'id': self.id,
            'source_agent': self.source_agent,
            'target_agent': self.target_agent,
            'handoff_type': self.handoff_type.value,
            'timestamp': self.timestamp,
            'status': self.status.value,
            'received_at': self.received_at,
            'completed_at': self.completed_at,
            'payload': self.payload,
            'summary': self.summary,
            'critical_facts': [asdict(f) for f in self.critical_facts],
            'decisions_made': [asdict(d) for d in self.decisions_made],
            'pending_actions': [asdict(a) for a in self.pending_actions],
            'grounding_evidence': self.grounding_evidence,
            'errors_encountered': self.errors_encountered,
            'context_budget_used': self.context_budget_used,
            'parent_handoff_id': self.parent_handoff_id,
            'child_handoff_ids': self.child_handoff_ids
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ContextPacket':
        """Deserialize from dictionary"""
        return cls(
            id=data['id'],
            source_agent=data['source_agent'],
            target_agent=data['target_agent'],
            handoff_type=HandoffType(data['handoff_type']),
            timestamp=data['timestamp'],
            status=HandoffStatus(data.get('status', 'pending')),
            received_at=data.get('received_at'),
            completed_at=data.get('completed_at'),
            payload=data.get('payload', {}),
            summary=data.get('summary', ''),
            critical_facts=[CriticalFact(**f) for f in data.get('critical_facts', [])],
            decisions_made=[Decision(**d) for d in data.get('decisions_made', [])],
            pending_actions=[PendingAction(**a) for a in data.get('pending_actions', [])],
            grounding_evidence=data.get('grounding_evidence', {}),
            errors_encountered=data.get('errors_encountered', []),
            context_budget_used=data.get('context_budget_used', 0.0),
            parent_handoff_id=data.get('parent_handoff_id'),
            child_handoff_ids=data.get('child_handoff_ids', [])
        )


class HandoffProtocol:
    """
    Manages context handoffs between agents.
    
    Ensures:
    1. No critical information is lost
    2. Context stays within budgets
    3. Full audit trail of handoffs
    4. Proper validation before handoff
    """
    
    # Maximum payload size (10KB)
    MAX_PAYLOAD_SIZE = 10240
    
    # Required fields for validation
    REQUIRED_FOR_HIGH_RISK = ['grounding_evidence', 'summary', 'critical_facts']
    
    def __init__(self):
        self.hive_mind_path = Path(__file__).parent.parent / ".hive-mind"
        self.handoffs_path = self.hive_mind_path / "handoffs"
        self.handoffs_path.mkdir(parents=True, exist_ok=True)
        
        # In-memory pending handoffs by target agent
        self.pending: Dict[str, List[ContextPacket]] = {}
        
        # Load pending handoffs from disk
        self._load_pending()
        
        logger.info(f"Handoff Protocol initialized with {sum(len(v) for v in self.pending.values())} pending")
    
    def _load_pending(self):
        """Load pending handoffs from disk"""
        pending_file = self.handoffs_path / "pending.json"
        if pending_file.exists():
            with open(pending_file) as f:
                data = json.load(f)
            for target, packets in data.items():
                self.pending[target] = [ContextPacket.from_dict(p) for p in packets]
    
    def _save_pending(self):
        """Save pending handoffs to disk"""
        pending_file = self.handoffs_path / "pending.json"
        data = {
            target: [p.to_dict() for p in packets]
            for target, packets in self.pending.items()
        }
        with open(pending_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _generate_id(self, source: str, target: str) -> str:
        """Generate unique handoff ID"""
        content = f"{source}:{target}:{datetime.now().isoformat()}"
        return f"HO-{hashlib.sha256(content.encode()).hexdigest()[:12]}"
    
    def create_handoff(
        self,
        source_agent: str,
        target_agent: str,
        payload: Dict[str, Any],
        handoff_type: HandoffType = HandoffType.SEQUENTIAL,
        summary: str = "",
        critical_facts: List[Dict] = None,
        decisions: List[Dict] = None,
        pending_actions: List[Dict] = None,
        grounding_evidence: Dict = None,
        parent_handoff_id: str = None
    ) -> ContextPacket:
        """
        Create a new handoff packet.
        
        Args:
            source_agent: Agent sending the context
            target_agent: Agent receiving the context
            payload: The actual data to transfer
            handoff_type: Type of handoff
            summary: Compacted summary for LLM context
            critical_facts: Must-preserve information
            decisions: Decisions made so far
            pending_actions: Actions that need to happen
            grounding_evidence: Data sources used
            parent_handoff_id: Previous handoff in chain
            
        Returns:
            ContextPacket ready for validation and sending
        """
        handoff_id = self._generate_id(source_agent, target_agent)
        
        # Convert dicts to dataclasses
        facts = [CriticalFact(**f) for f in (critical_facts or [])]
        decs = [Decision(**d) for d in (decisions or [])]
        actions = [PendingAction(**a) for a in (pending_actions or [])]
        
        # Estimate context budget
        payload_size = len(json.dumps(payload))
        context_budget = min(1.0, payload_size / self.MAX_PAYLOAD_SIZE)
        
        packet = ContextPacket(
            id=handoff_id,
            source_agent=source_agent,
            target_agent=target_agent,
            handoff_type=handoff_type,
            timestamp=datetime.now().isoformat(),
            payload=payload,
            summary=summary or self._auto_summarize(payload),
            critical_facts=facts,
            decisions_made=decs,
            pending_actions=actions,
            grounding_evidence=grounding_evidence or {},
            context_budget_used=context_budget,
            parent_handoff_id=parent_handoff_id
        )
        
        logger.info(f"Created handoff {handoff_id}: {source_agent} -> {target_agent}")
        
        return packet
    
    def _auto_summarize(self, payload: Dict) -> str:
        """Generate automatic summary from payload"""
        parts = []
        
        # Extract key identifiers
        if 'lead_id' in payload:
            parts.append(f"Lead: {payload['lead_id']}")
        if 'email' in payload:
            parts.append(f"Email: {payload['email']}")
        if 'company' in payload:
            parts.append(f"Company: {payload['company']}")
        if 'icp_score' in payload:
            parts.append(f"ICP: {payload['icp_score']}")
        if 'action' in payload:
            parts.append(f"Action: {payload['action']}")
        
        return " | ".join(parts) if parts else "Context handoff"
    
    def validate_handoff(self, packet: ContextPacket) -> Tuple[bool, List[str]]:
        """
        Validate a handoff packet before sending.
        
        Returns:
            (valid, list of issues)
        """
        issues = []
        
        # Must have summary
        if not packet.summary:
            issues.append("Missing summary - required for context handoffs")
        
        # Must have at least 1 critical fact for non-trivial handoffs
        if not packet.critical_facts and packet.payload:
            issues.append("No critical facts specified - at least 1 required")
        
        # Payload size check
        payload_size = len(json.dumps(packet.payload))
        if payload_size > self.MAX_PAYLOAD_SIZE:
            issues.append(f"Payload too large ({payload_size} > {self.MAX_PAYLOAD_SIZE} bytes)")
        
        # Must specify target agent
        if not packet.target_agent:
            issues.append("No target agent specified")
        
        # High-risk handoffs need grounding
        high_risk_targets = ['GHL_MASTER', 'CRAFTER']
        if packet.target_agent in high_risk_targets:
            if not packet.grounding_evidence:
                issues.append(f"Handoff to {packet.target_agent} requires grounding evidence")
        
        # Check for unresolved actions
        if packet.pending_actions:
            unassigned = [a for a in packet.pending_actions if not a.assigned_to]
            if unassigned:
                issues.append(f"{len(unassigned)} pending actions without assigned agent")
        
        valid = len(issues) == 0
        
        if not valid:
            logger.warning(f"Handoff {packet.id} validation failed: {issues}")
        
        return valid, issues
    
    def compact_for_target(
        self,
        packet: ContextPacket,
        target_context_budget: float = 0.3
    ) -> ContextPacket:
        """
        Compact a handoff packet to fit target's context budget.
        
        Args:
            packet: Original packet
            target_context_budget: How much context the target has available (0-1)
            
        Returns:
            Compacted ContextPacket
        """
        if packet.context_budget_used <= target_context_budget:
            return packet  # Already fits
        
        logger.info(f"Compacting handoff {packet.id}: {packet.context_budget_used:.1%} -> {target_context_budget:.1%}")
        
        # Create compacted version
        compacted = ContextPacket(
            id=packet.id,
            source_agent=packet.source_agent,
            target_agent=packet.target_agent,
            handoff_type=packet.handoff_type,
            timestamp=packet.timestamp,
            status=packet.status,
            parent_handoff_id=packet.parent_handoff_id
        )
        
        # Keep critical facts (highest priority)
        compacted.critical_facts = [f for f in packet.critical_facts if f.importance == 'critical']
        
        # Keep most recent decisions only
        compacted.decisions_made = packet.decisions_made[-3:]
        
        # Keep high-priority pending actions only
        compacted.pending_actions = [a for a in packet.pending_actions if a.priority >= 7]
        
        # Summarize payload instead of including full data
        compacted.summary = packet.summary
        compacted.payload = {
            '_compacted': True,
            '_original_size': len(json.dumps(packet.payload)),
            'key_fields': {k: v for k, v in packet.payload.items() 
                          if k in ['lead_id', 'email', 'company', 'icp_score', 'segment']}
        }
        
        # Keep grounding reference but not full evidence
        compacted.grounding_evidence = {
            'source': packet.grounding_evidence.get('source'),
            'data_id': packet.grounding_evidence.get('data_id')
        }
        
        # Keep recent errors only
        compacted.errors_encountered = packet.errors_encountered[-3:]
        
        # Recalculate budget
        new_size = len(json.dumps(compacted.to_dict()))
        compacted.context_budget_used = min(1.0, new_size / self.MAX_PAYLOAD_SIZE)
        
        logger.info(f"Compacted to {compacted.context_budget_used:.1%}")
        
        return compacted
    
    def merge_handoffs(self, packets: List[ContextPacket], target_agent: str) -> ContextPacket:
        """
        Merge multiple handoffs into one (for parallel -> single agent flows).
        
        Args:
            packets: List of packets to merge
            target_agent: The receiving agent
            
        Returns:
            Single merged ContextPacket
        """
        if not packets:
            raise ValueError("No packets to merge")
        
        merged_id = self._generate_id("MERGE", target_agent)
        
        # Combine payloads
        merged_payload = {}
        for i, p in enumerate(packets):
            merged_payload[f"from_{p.source_agent}"] = p.payload
        
        # Combine critical facts (dedupe by key)
        all_facts = {}
        for p in packets:
            for fact in p.critical_facts:
                if fact.key not in all_facts or fact.importance == 'critical':
                    all_facts[fact.key] = fact
        
        # Combine decisions
        all_decisions = []
        for p in packets:
            all_decisions.extend(p.decisions_made)
        all_decisions.sort(key=lambda d: d.timestamp)
        
        # Combine pending actions
        all_actions = []
        for p in packets:
            all_actions.extend(p.pending_actions)
        all_actions.sort(key=lambda a: a.priority, reverse=True)
        
        # Combine grounding evidence
        merged_grounding = {}
        for p in packets:
            if p.grounding_evidence:
                merged_grounding[p.source_agent] = p.grounding_evidence
        
        # Combine errors
        all_errors = []
        for p in packets:
            all_errors.extend(p.errors_encountered)
        
        # Create merged summary
        summaries = [f"{p.source_agent}: {p.summary}" for p in packets]
        merged_summary = " | ".join(summaries)
        
        merged = ContextPacket(
            id=merged_id,
            source_agent="MERGE",
            target_agent=target_agent,
            handoff_type=HandoffType.PARALLEL_MERGE,
            timestamp=datetime.now().isoformat(),
            payload=merged_payload,
            summary=merged_summary,
            critical_facts=list(all_facts.values()),
            decisions_made=all_decisions,
            pending_actions=all_actions,
            grounding_evidence=merged_grounding,
            errors_encountered=all_errors,
            child_handoff_ids=[p.id for p in packets]
        )
        
        # Calculate combined budget
        merged.context_budget_used = min(1.0, sum(p.context_budget_used for p in packets))
        
        logger.info(f"Merged {len(packets)} handoffs into {merged_id}")
        
        return merged
    
    def send_handoff(self, packet: ContextPacket) -> bool:
        """
        Send a handoff to target agent.
        
        Args:
            packet: Validated ContextPacket
            
        Returns:
            True if sent successfully
        """
        # Validate first
        valid, issues = self.validate_handoff(packet)
        if not valid:
            logger.error(f"Cannot send invalid handoff: {issues}")
            return False
        
        # Add to pending queue
        if packet.target_agent not in self.pending:
            self.pending[packet.target_agent] = []
        
        self.pending[packet.target_agent].append(packet)
        
        # Persist
        self._save_pending()
        
        # Save to handoff history
        self._save_handoff(packet)
        
        logger.info(f"Sent handoff {packet.id} to {packet.target_agent}")
        
        return True
    
    def receive_handoff(self, agent_name: str) -> Optional[ContextPacket]:
        """
        Receive the next pending handoff for an agent.
        
        Args:
            agent_name: Name of the receiving agent
            
        Returns:
            ContextPacket or None if no pending
        """
        if agent_name not in self.pending or not self.pending[agent_name]:
            return None
        
        # Get oldest pending
        packet = self.pending[agent_name].pop(0)
        packet.status = HandoffStatus.RECEIVED
        packet.received_at = datetime.now().isoformat()
        
        # Update history
        self._save_handoff(packet)
        self._save_pending()
        
        logger.info(f"Agent {agent_name} received handoff {packet.id}")
        
        return packet
    
    def complete_handoff(
        self,
        handoff_id: str,
        result: Dict[str, Any] = None,
        success: bool = True,
        errors: List[str] = None
    ):
        """
        Mark a handoff as completed.
        
        Args:
            handoff_id: ID of the handoff
            result: Result data from processing
            success: Whether processing succeeded
            errors: Any errors encountered
        """
        # Load handoff
        packet = self._load_handoff(handoff_id)
        if not packet:
            logger.warning(f"Handoff {handoff_id} not found")
            return
        
        packet.status = HandoffStatus.COMPLETED if success else HandoffStatus.FAILED
        packet.completed_at = datetime.now().isoformat()
        
        if errors:
            packet.errors_encountered.extend(errors)
        
        if result:
            packet.payload['_result'] = result
        
        # Save updated
        self._save_handoff(packet)
        
        logger.info(f"Handoff {handoff_id} completed (success={success})")
    
    def get_pending_handoffs(self, agent_name: str) -> List[ContextPacket]:
        """Get all pending handoffs for an agent"""
        return self.pending.get(agent_name, [])
    
    def get_handoff_chain(self, handoff_id: str) -> List[ContextPacket]:
        """
        Get full chain of handoffs (parent -> child -> grandchild...).
        
        Args:
            handoff_id: Any handoff in the chain
            
        Returns:
            List of packets in chronological order
        """
        chain = []
        current = self._load_handoff(handoff_id)
        
        if not current:
            return chain
        
        # Walk up to root
        while current and current.parent_handoff_id:
            parent = self._load_handoff(current.parent_handoff_id)
            if parent:
                chain.insert(0, parent)
                current = parent
            else:
                break
        
        # Add current
        current = self._load_handoff(handoff_id)
        if current:
            chain.append(current)
        
        # Walk down through children
        def add_children(packet):
            for child_id in packet.child_handoff_ids:
                child = self._load_handoff(child_id)
                if child:
                    chain.append(child)
                    add_children(child)
        
        add_children(chain[-1] if chain else current)
        
        return chain
    
    def _save_handoff(self, packet: ContextPacket):
        """Save handoff to history file"""
        file_path = self.handoffs_path / f"{packet.id}.json"
        with open(file_path, 'w') as f:
            json.dump(packet.to_dict(), f, indent=2)
    
    def _load_handoff(self, handoff_id: str) -> Optional[ContextPacket]:
        """Load handoff from file"""
        file_path = self.handoffs_path / f"{handoff_id}.json"
        if file_path.exists():
            with open(file_path) as f:
                return ContextPacket.from_dict(json.load(f))
        return None


def main():
    """Demonstrate handoff protocol"""
    print("=" * 70)
    print("CONTEXT HANDOFF PROTOCOL - Agent Communication Demo")
    print("=" * 70)
    
    protocol = HandoffProtocol()
    
    # Simulate HUNTER -> ENRICHER -> SEGMENTOR -> CRAFTER chain
    
    print("\n[Step 1] HUNTER creates handoff to ENRICHER")
    print("-" * 50)
    
    hunter_handoff = protocol.create_handoff(
        source_agent="HUNTER",
        target_agent="ENRICHER",
        payload={
            'lead_id': 'lead_12345',
            'linkedin_url': 'https://linkedin.com/in/johndoe',
            'name': 'John Doe',
            'title': 'VP of Sales',
            'company': 'Acme Corp',
            'scraped_at': datetime.now().isoformat()
        },
        summary="Scraped lead John Doe, VP Sales @ Acme Corp",
        critical_facts=[{
            'key': 'lead_id',
            'value': 'lead_12345',
            'source': 'linkedin',
            'importance': 'critical'
        }],
        grounding_evidence={
            'source': 'linkedin',
            'url': 'https://linkedin.com/in/johndoe',
            'scraped_at': datetime.now().isoformat()
        }
    )
    
    valid, issues = protocol.validate_handoff(hunter_handoff)
    print(f"  Handoff ID: {hunter_handoff.id}")
    print(f"  Valid: {valid}")
    print(f"  Context budget: {hunter_handoff.context_budget_used:.1%}")
    
    protocol.send_handoff(hunter_handoff)
    
    print("\n[Step 2] ENRICHER receives and processes")
    print("-" * 50)
    
    received = protocol.receive_handoff("ENRICHER")
    print(f"  Received: {received.id if received else 'None'}")
    print(f"  Summary: {received.summary if received else 'N/A'}")
    
    # ENRICHER creates handoff to SEGMENTOR
    enricher_handoff = protocol.create_handoff(
        source_agent="ENRICHER",
        target_agent="SEGMENTOR",
        payload={
            'lead_id': 'lead_12345',
            'email': 'john.doe@acmecorp.com',
            'company': 'Acme Corp',
            'employee_count': 250,
            'industry': 'B2B SaaS',
            'technologies': ['Salesforce', 'HubSpot'],
            'enriched_at': datetime.now().isoformat()
        },
        summary="Enriched: john.doe@acmecorp.com, Acme Corp (250 emp, B2B SaaS)",
        critical_facts=[
            {'key': 'lead_id', 'value': 'lead_12345', 'source': 'linkedin', 'importance': 'critical'},
            {'key': 'email', 'value': 'john.doe@acmecorp.com', 'source': 'clay', 'importance': 'critical'},
            {'key': 'employee_count', 'value': 250, 'source': 'clay', 'importance': 'high'}
        ],
        decisions=[{
            'agent': 'ENRICHER',
            'decision_type': 'enrichment_source',
            'choice': 'clay',
            'reasoning': 'Best match confidence',
            'timestamp': datetime.now().isoformat()
        }],
        grounding_evidence={
            'source': 'clay',
            'data_id': 'clay_enrich_789',
            'verified': True
        },
        parent_handoff_id=hunter_handoff.id
    )
    
    protocol.send_handoff(enricher_handoff)
    print(f"  Sent to SEGMENTOR: {enricher_handoff.id}")
    
    print("\n[Step 3] SEGMENTOR receives and processes")
    print("-" * 50)
    
    received = protocol.receive_handoff("SEGMENTOR")
    print(f"  Received: {received.id if received else 'None'}")
    
    # SEGMENTOR creates handoff to CRAFTER
    segmentor_handoff = protocol.create_handoff(
        source_agent="SEGMENTOR",
        target_agent="CRAFTER",
        payload={
            'lead_id': 'lead_12345',
            'email': 'john.doe@acmecorp.com',
            'company': 'Acme Corp',
            'icp_score': 85,
            'segment': 'tier_1',
            'routing': 'gohighlevel_cold',
            'recommended_sequence': 'cold_outbound'
        },
        summary="Tier 1 lead (ICP: 85) - route to GHL cold_outbound",
        critical_facts=[
            {'key': 'lead_id', 'value': 'lead_12345', 'source': 'linkedin', 'importance': 'critical'},
            {'key': 'email', 'value': 'john.doe@acmecorp.com', 'source': 'clay', 'importance': 'critical'},
            {'key': 'icp_score', 'value': 85, 'source': 'segmentor', 'importance': 'critical'},
            {'key': 'segment', 'value': 'tier_1', 'source': 'segmentor', 'importance': 'high'}
        ],
        decisions=[
            {'agent': 'ENRICHER', 'decision_type': 'enrichment_source', 'choice': 'clay', 
             'reasoning': 'Best match', 'timestamp': datetime.now().isoformat()},
            {'agent': 'SEGMENTOR', 'decision_type': 'segment_assignment', 'choice': 'tier_1',
             'reasoning': 'ICP score 85 > 80 threshold', 'timestamp': datetime.now().isoformat()}
        ],
        pending_actions=[{
            'action_type': 'send_campaign',
            'target': 'john.doe@acmecorp.com',
            'parameters': {'sequence': 'cold_outbound', 'template': 'cold_initial'},
            'priority': 8,
            'assigned_to': 'GHL_MASTER'
        }],
        grounding_evidence={
            'source': 'supabase',
            'data_id': 'lead_12345',
            'icp_verified': True
        },
        parent_handoff_id=enricher_handoff.id
    )
    
    protocol.send_handoff(segmentor_handoff)
    print(f"  Sent to CRAFTER: {segmentor_handoff.id}")
    print(f"  Full chain length: {len(protocol.get_handoff_chain(segmentor_handoff.id))}")
    
    print("\n[Step 4] View handoff chain")
    print("-" * 50)
    
    chain = protocol.get_handoff_chain(segmentor_handoff.id)
    for i, packet in enumerate(chain):
        print(f"  {i+1}. {packet.source_agent} -> {packet.target_agent}")
        print(f"     Summary: {packet.summary[:50]}...")
    
    print("\n[Step 5] Test context compaction")
    print("-" * 50)
    
    # Create a large packet
    large_payload = {'data': 'x' * 5000, 'lead_id': 'test'}
    large_packet = protocol.create_handoff(
        source_agent="TEST",
        target_agent="COMPACT_TEST",
        payload=large_payload,
        summary="Large payload test",
        critical_facts=[{'key': 'lead_id', 'value': 'test', 'source': 'test', 'importance': 'critical'}]
    )
    
    print(f"  Original budget: {large_packet.context_budget_used:.1%}")
    
    compacted = protocol.compact_for_target(large_packet, target_context_budget=0.2)
    print(f"  Compacted budget: {compacted.context_budget_used:.1%}")
    print(f"  Compacted payload keys: {list(compacted.payload.keys())}")
    
    print("\n" + "=" * 70)
    print("Context Handoff Protocol demonstration complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
