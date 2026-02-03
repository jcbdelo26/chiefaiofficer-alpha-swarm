"""
Hallucination Prevention Framework with Source Attribution and Confidence Scoring.

Every agent output must be grounded in verifiable data with full audit trail.
"""

import json
import uuid
import asyncio
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path


class GroundingSource(Enum):
    """Sources for grounding agent claims."""
    SUPABASE = "supabase"
    GHL = "gohighlevel"
    LINKEDIN = "linkedin"
    CLAY = "clay"
    MANUAL = "manual"
    INFERRED = "inferred"


class VerificationStatus(Enum):
    """Status of claim verification."""
    PENDING = "pending"
    VERIFIED = "verified"
    PARTIAL = "partial"
    FAILED = "failed"
    FLAGGED = "flagged"


class ConfidenceLevel(Enum):
    """Confidence thresholds for claims."""
    HIGH = "high"        # >= 0.8 - verified against source
    MEDIUM = "medium"    # >= 0.5 - partial verification
    LOW = "low"          # < 0.5 - needs human review


@dataclass
class Claim:
    """A single grounded claim with source attribution."""
    id: str
    content: str
    source: GroundingSource
    source_id: Optional[str]
    confidence: float
    verified: bool
    timestamp: datetime
    evidence: Optional[Dict[str, Any]] = None
    verification_notes: Optional[str] = None
    flagged: bool = False
    flag_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "source": self.source.value,
            "source_id": self.source_id,
            "confidence": self.confidence,
            "verified": self.verified,
            "timestamp": self.timestamp.isoformat(),
            "evidence": self.evidence,
            "verification_notes": self.verification_notes,
            "flagged": self.flagged,
            "flag_reason": self.flag_reason
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Claim":
        return cls(
            id=data["id"],
            content=data["content"],
            source=GroundingSource(data["source"]),
            source_id=data.get("source_id"),
            confidence=data["confidence"],
            verified=data["verified"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            evidence=data.get("evidence"),
            verification_notes=data.get("verification_notes"),
            flagged=data.get("flagged", False),
            flag_reason=data.get("flag_reason")
        )


@dataclass
class GroundedOutput:
    """Wrapped agent output with all claims grounded."""
    id: str
    agent_name: str
    output_type: str
    claims: List[Claim]
    overall_confidence: float
    verification_status: VerificationStatus
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "agent_name": self.agent_name,
            "output_type": self.output_type,
            "claims": [c.to_dict() for c in self.claims],
            "overall_confidence": self.overall_confidence,
            "verification_status": self.verification_status.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }
    
    def get_confidence_level(self) -> ConfidenceLevel:
        if self.overall_confidence >= 0.8:
            return ConfidenceLevel.HIGH
        elif self.overall_confidence >= 0.5:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW
    
    def needs_human_review(self) -> bool:
        return self.get_confidence_level() == ConfidenceLevel.LOW or any(c.flagged for c in self.claims)


@dataclass
class AuditEntry:
    """Single entry in the audit trail."""
    id: str
    output_id: str
    action: str
    claim_id: Optional[str]
    timestamp: datetime
    details: Dict[str, Any]
    actor: str  # agent or system
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "output_id": self.output_id,
            "action": self.action,
            "claim_id": self.claim_id,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
            "actor": self.actor
        }


class GroundingChain:
    """
    Hallucination Prevention Framework.
    
    Ensures all agent outputs are grounded in verifiable data sources
    with confidence scoring and full audit trail.
    """
    
    HIGH_CONFIDENCE_THRESHOLD = 0.8
    MEDIUM_CONFIDENCE_THRESHOLD = 0.5
    
    def __init__(self, audit_path: Optional[Path] = None):
        self.audit_path = audit_path or Path(".hive-mind/grounding_audit.json")
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.outputs: Dict[str, GroundedOutput] = {}
        self.audit_trail: List[AuditEntry] = []
        self.verification_hooks: Dict[GroundingSource, Callable] = {}
        
        self._load_audit_trail()
    
    def _load_audit_trail(self):
        """Load existing audit trail from disk."""
        if self.audit_path.exists():
            try:
                with open(self.audit_path, 'r') as f:
                    data = json.load(f)
                    self.audit_trail = [
                        AuditEntry(
                            id=e["id"],
                            output_id=e["output_id"],
                            action=e["action"],
                            claim_id=e.get("claim_id"),
                            timestamp=datetime.fromisoformat(e["timestamp"]),
                            details=e["details"],
                            actor=e["actor"]
                        )
                        for e in data.get("entries", [])
                    ]
            except (json.JSONDecodeError, KeyError):
                self.audit_trail = []
    
    def _save_audit_trail(self):
        """Persist audit trail to disk."""
        data = {
            "last_updated": datetime.now().isoformat(),
            "entry_count": len(self.audit_trail),
            "entries": [e.to_dict() for e in self.audit_trail]
        }
        with open(self.audit_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _add_audit_entry(self, output_id: str, action: str, details: Dict[str, Any],
                         claim_id: Optional[str] = None, actor: str = "system"):
        """Add entry to audit trail."""
        entry = AuditEntry(
            id=str(uuid.uuid4()),
            output_id=output_id,
            action=action,
            claim_id=claim_id,
            timestamp=datetime.now(),
            details=details,
            actor=actor
        )
        self.audit_trail.append(entry)
        self._save_audit_trail()
        return entry
    
    def register_verification_hook(self, source: GroundingSource, hook: Callable):
        """Register a verification callback for a data source."""
        self.verification_hooks[source] = hook
        print(f"[GroundingChain] Registered verification hook for {source.value}")
    
    def ground_claim(
        self,
        content: str,
        source: GroundingSource,
        source_id: Optional[str] = None,
        evidence: Optional[Dict[str, Any]] = None,
        initial_confidence: Optional[float] = None
    ) -> Claim:
        """
        Create a grounded claim with source attribution.
        
        Args:
            content: The claim content
            source: Data source for grounding
            source_id: ID/reference in the source system
            evidence: Supporting data from the source
            initial_confidence: Override automatic confidence
        """
        # Calculate initial confidence based on source type and evidence
        if initial_confidence is not None:
            confidence = initial_confidence
        elif source == GroundingSource.MANUAL:
            confidence = 1.0  # Human-provided data is trusted
        elif source == GroundingSource.INFERRED:
            confidence = 0.4  # Inferred claims need verification
        elif evidence:
            confidence = 0.7  # Has evidence but not yet verified
        else:
            confidence = 0.3  # No evidence provided
        
        claim = Claim(
            id=str(uuid.uuid4()),
            content=content,
            source=source,
            source_id=source_id,
            confidence=confidence,
            verified=False,
            timestamp=datetime.now(),
            evidence=evidence
        )
        
        return claim
    
    async def verify_claim(self, claim: Claim, output_id: Optional[str] = None) -> Claim:
        """
        Cross-check claim against live data source.
        
        Returns updated claim with verification status.
        """
        if claim.source not in self.verification_hooks:
            claim.verification_notes = f"No verification hook for {claim.source.value}"
            if output_id:
                self._add_audit_entry(
                    output_id, "verification_skipped",
                    {"reason": "no_hook", "source": claim.source.value},
                    claim_id=claim.id
                )
            return claim
        
        try:
            hook = self.verification_hooks[claim.source]
            result = await hook(claim.source_id, claim.evidence)
            
            if result.get("verified"):
                claim.verified = True
                claim.confidence = min(1.0, claim.confidence + 0.2)
                claim.verification_notes = "Verified against live source"
            elif result.get("partial"):
                claim.confidence = max(0.5, claim.confidence)
                claim.verification_notes = f"Partial match: {result.get('notes', '')}"
            else:
                claim.confidence = max(0.0, claim.confidence - 0.3)
                claim.verification_notes = f"Verification failed: {result.get('error', 'Unknown')}"
            
            if output_id:
                self._add_audit_entry(
                    output_id, "claim_verified",
                    {"result": result, "new_confidence": claim.confidence},
                    claim_id=claim.id
                )
                
        except Exception as e:
            claim.verification_notes = f"Verification error: {str(e)}"
            if output_id:
                self._add_audit_entry(
                    output_id, "verification_error",
                    {"error": str(e)},
                    claim_id=claim.id
                )
        
        return claim
    
    def calculate_confidence(self, claims: List[Claim]) -> float:
        """
        Calculate aggregate confidence score from multiple claims.
        
        Uses weighted average based on verification status.
        """
        if not claims:
            return 0.0
        
        total_weight = 0.0
        weighted_sum = 0.0
        
        for claim in claims:
            # Verified claims have higher weight
            weight = 2.0 if claim.verified else 1.0
            # Flagged claims reduce overall confidence
            if claim.flagged:
                weight *= 0.5
            
            weighted_sum += claim.confidence * weight
            total_weight += weight
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    def create_grounded_output(
        self,
        agent_name: str,
        output_type: str,
        claims: List[Claim],
        metadata: Optional[Dict[str, Any]] = None
    ) -> GroundedOutput:
        """
        Wrap agent output with grounding information.
        
        All agent outputs should go through this to ensure traceability.
        """
        output_id = str(uuid.uuid4())
        overall_confidence = self.calculate_confidence(claims)
        
        # Determine verification status
        if all(c.verified for c in claims):
            status = VerificationStatus.VERIFIED
        elif any(c.flagged for c in claims):
            status = VerificationStatus.FLAGGED
        elif any(c.verified for c in claims):
            status = VerificationStatus.PARTIAL
        elif overall_confidence < self.MEDIUM_CONFIDENCE_THRESHOLD:
            status = VerificationStatus.FAILED
        else:
            status = VerificationStatus.PENDING
        
        output = GroundedOutput(
            id=output_id,
            agent_name=agent_name,
            output_type=output_type,
            claims=claims,
            overall_confidence=overall_confidence,
            verification_status=status,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )
        
        self.outputs[output_id] = output
        
        self._add_audit_entry(
            output_id, "output_created",
            {
                "agent": agent_name,
                "type": output_type,
                "claim_count": len(claims),
                "confidence": overall_confidence,
                "status": status.value
            },
            actor=agent_name
        )
        
        return output
    
    def get_audit_trail(self, output_id: str) -> List[AuditEntry]:
        """Retrieve verification history for an output."""
        return [e for e in self.audit_trail if e.output_id == output_id]
    
    def flag_hallucination(
        self,
        claim: Claim,
        reason: str,
        output_id: Optional[str] = None,
        flagged_by: str = "system"
    ) -> Claim:
        """
        Mark an unverifiable claim as potential hallucination.
        
        Flagged claims trigger human review and reduce overall confidence.
        """
        claim.flagged = True
        claim.flag_reason = reason
        claim.confidence = min(claim.confidence, 0.3)  # Cap confidence
        
        if output_id:
            self._add_audit_entry(
                output_id, "hallucination_flagged",
                {"reason": reason, "claim_content": claim.content},
                claim_id=claim.id,
                actor=flagged_by
            )
            
            # Update output if tracked
            if output_id in self.outputs:
                output = self.outputs[output_id]
                output.overall_confidence = self.calculate_confidence(output.claims)
                output.verification_status = VerificationStatus.FLAGGED
        
        print(f"[GroundingChain] HALLUCINATION FLAGGED: {claim.content[:50]}... - {reason}")
        return claim
    
    def get_unverified_claims(self, output_id: str) -> List[Claim]:
        """Get all claims that still need verification."""
        if output_id not in self.outputs:
            return []
        return [c for c in self.outputs[output_id].claims if not c.verified and not c.flagged]
    
    def get_flagged_claims(self) -> List[tuple[str, Claim]]:
        """Get all flagged claims across all outputs for human review."""
        flagged = []
        for output_id, output in self.outputs.items():
            for claim in output.claims:
                if claim.flagged:
                    flagged.append((output_id, claim))
        return flagged
    
    def generate_grounding_report(self, output_id: str) -> Dict[str, Any]:
        """Generate a detailed grounding report for an output."""
        if output_id not in self.outputs:
            return {"error": "Output not found"}
        
        output = self.outputs[output_id]
        audit = self.get_audit_trail(output_id)
        
        claims_by_source = {}
        for claim in output.claims:
            src = claim.source.value
            if src not in claims_by_source:
                claims_by_source[src] = []
            claims_by_source[src].append(claim.to_dict())
        
        return {
            "output_id": output_id,
            "agent": output.agent_name,
            "output_type": output.output_type,
            "timestamp": output.timestamp.isoformat(),
            "overall_confidence": output.overall_confidence,
            "confidence_level": output.get_confidence_level().value,
            "verification_status": output.verification_status.value,
            "needs_human_review": output.needs_human_review(),
            "claim_summary": {
                "total": len(output.claims),
                "verified": sum(1 for c in output.claims if c.verified),
                "flagged": sum(1 for c in output.claims if c.flagged),
                "pending": sum(1 for c in output.claims if not c.verified and not c.flagged)
            },
            "claims_by_source": claims_by_source,
            "audit_trail": [e.to_dict() for e in audit]
        }


async def main():
    """Demonstration of the Hallucination Prevention Framework."""
    print("=" * 60)
    print("HALLUCINATION PREVENTION FRAMEWORK DEMO")
    print("=" * 60)
    
    # Initialize grounding chain
    chain = GroundingChain()
    
    # Register mock verification hooks
    async def verify_supabase(source_id, evidence):
        # Simulate Supabase verification
        if source_id and source_id.startswith("contact_"):
            return {"verified": True, "data": evidence}
        return {"verified": False, "error": "Record not found"}
    
    async def verify_ghl(source_id, evidence):
        # Simulate GHL verification
        if evidence and evidence.get("pipeline_stage"):
            return {"partial": True, "notes": "Pipeline found, details differ"}
        return {"verified": False, "error": "No matching record"}
    
    chain.register_verification_hook(GroundingSource.SUPABASE, verify_supabase)
    chain.register_verification_hook(GroundingSource.GHL, verify_ghl)
    
    print("\n[1] Creating grounded claims from SDR Agent...")
    
    # Create claims with different grounding sources
    claims = [
        chain.ground_claim(
            content="Contact John Smith is CEO of Acme Corp",
            source=GroundingSource.SUPABASE,
            source_id="contact_12345",
            evidence={"name": "John Smith", "title": "CEO", "company": "Acme Corp"}
        ),
        chain.ground_claim(
            content="John has shown interest in our enterprise plan",
            source=GroundingSource.GHL,
            source_id="opp_789",
            evidence={"pipeline_stage": "Interested", "notes": "Demo requested"}
        ),
        chain.ground_claim(
            content="Based on company size, budget is likely $50k-100k",
            source=GroundingSource.INFERRED,
            evidence={"company_size": "50-200 employees", "industry": "Tech"}
        ),
        chain.ground_claim(
            content="Email verified via LinkedIn profile",
            source=GroundingSource.LINKEDIN,
            source_id="li_profile_abc",
            evidence={"profile_url": "linkedin.com/in/johnsmith"}
        )
    ]
    
    print(f"   Created {len(claims)} claims")
    for claim in claims:
        print(f"   - [{claim.source.value}] {claim.content[:40]}... (confidence: {claim.confidence:.2f})")
    
    print("\n[2] Verifying claims against live sources...")
    
    # Create output first to track verification
    output = chain.create_grounded_output(
        agent_name="SDR_Agent",
        output_type="lead_qualification",
        claims=claims,
        metadata={"lead_id": "lead_001", "campaign": "enterprise_q1"}
    )
    
    # Verify each claim
    for claim in output.claims:
        await chain.verify_claim(claim, output.id)
        status = "[OK]" if claim.verified else "[--]"
        print(f"   {status} {claim.source.value}: {claim.verification_notes}")
    
    print("\n[3] Flagging potential hallucination...")
    
    # Flag the inferred claim as needing review
    inferred_claim = next(c for c in output.claims if c.source == GroundingSource.INFERRED)
    chain.flag_hallucination(
        inferred_claim,
        reason="Budget inference not backed by concrete data",
        output_id=output.id,
        flagged_by="QA_Agent"
    )
    
    print("\n[4] Generating grounding report...")
    
    report = chain.generate_grounding_report(output.id)
    
    print(f"\n   Output ID: {report['output_id']}")
    print(f"   Agent: {report['agent']}")
    print(f"   Overall Confidence: {report['overall_confidence']:.2f} ({report['confidence_level']})")
    print(f"   Verification Status: {report['verification_status']}")
    print(f"   Needs Human Review: {report['needs_human_review']}")
    print(f"\n   Claim Summary:")
    for key, value in report['claim_summary'].items():
        print(f"     - {key}: {value}")
    
    print("\n[5] Audit Trail:")
    for entry in report['audit_trail']:
        print(f"   [{entry['timestamp'][:19]}] {entry['action']} by {entry['actor']}")
    
    print("\n[6] Checking confidence thresholds...")
    
    if output.get_confidence_level() == ConfidenceLevel.HIGH:
        print("   [OK] HIGH CONFIDENCE: Output verified, safe to proceed")
    elif output.get_confidence_level() == ConfidenceLevel.MEDIUM:
        print("   [--] MEDIUM CONFIDENCE: Partial verification, proceed with caution")
    else:
        print("   [!!] LOW CONFIDENCE: Requires human review before proceeding")
    
    print(f"\n   Audit log saved to: {chain.audit_path}")
    
    print("\n" + "=" * 60)
    print("FRAMEWORK DEMO COMPLETE")
    print("=" * 60)
    
    return chain, output


if __name__ == "__main__":
    asyncio.run(main())
