#!/usr/bin/env python3
"""
Day 3-4 Framework Integration Tests
====================================
Tests for Context Manager, Grounding Chain, and Feedback Collector integration.
"""

import sys
from pathlib import Path
import json

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_context_manager():
    """Test Context Manager with FIC compaction."""
    print("\n" + "=" * 60)
    print("Testing Context Manager...")
    print("=" * 60)
    
    from core.context_manager import ContextManager, Priority
    
    # Initialize
    ctx = ContextManager(max_tokens=10000)
    
    # Add context items with different priorities
    ctx.add_context(
        content="You are the CRAFTER agent for Chief AI Officer Alpha Swarm.",
        priority=Priority.CRITICAL,
        source="system",
        item_id="system_prompt"
    )
    
    ctx.add_context(
        content=json.dumps({"segment": "B2B SaaS", "revenue": "$20M+"}),
        priority=Priority.HIGH,
        source="icp",
        item_id="icp_data"
    )
    
    ctx.add_context(
        content=json.dumps({"name": "John Doe", "company": "Acme Corp"}),
        priority=Priority.MEDIUM,
        source="lead",
        item_id="lead_data"
    )
    
    # Check budget status using get_stats()
    stats = ctx.get_stats()
    print(f"\n📊 Context Stats: {stats}")
    print(f"   Token count: {ctx.budget.current_tokens}")
    print(f"   Utilization: {ctx.budget.utilization_percent:.1f}%")
    print(f"   Remaining tokens: {ctx.budget.remaining_tokens}")
    
    # Test context retrieval
    context = ctx.get_context()
    print(f"\n📋 Context items retrieved: {len(context)}")
    
    # Check budget status
    budget_result = ctx.check_budget()
    print(f"   Budget check: {budget_result}")
    
    # Test compaction trigger
    print("\n🗜️  Adding bulk data to trigger compaction...")
    for i in range(20):
        ctx.add_context(
            content="x" * 500,  # Large content
            priority=Priority.EPHEMERAL,
            source=f"temp_{i}",
            ttl_seconds=60
        )
    
    print(f"   After bulk add: {ctx.budget.utilization_percent:.1f}%")
    
    # Manual compact
    removed = ctx.compact(target_utilization=0.30)
    print(f"   After compact: {ctx.budget.utilization_percent:.1f}%")
    print(f"   Items removed: {removed}")
    
    # Verify critical items survived
    critical_item = ctx.get_item("system_prompt")
    assert critical_item is not None, "Critical item should survive compaction"
    print("\n✅ Critical items survived compaction")
    
    # Test save/load
    ctx.save_state("test_context_state.json")
    print("✅ Context state saved")
    
    ctx2 = ContextManager()
    loaded = ctx2.restore_state("test_context_state.json")
    print(f"✅ Context state loaded: {loaded}")
    
    print("\n✅ Context Manager tests passed!")
    return True


def test_grounding_chain():
    """Test Grounding Chain for hallucination prevention."""
    print("\n" + "=" * 60)
    print("Testing Grounding Chain...")
    print("=" * 60)
    
    from core.grounding_chain import (
        GroundingChain, GroundingSource, VerificationStatus, Claim
    )
    from datetime import datetime
    import uuid
    
    # Initialize grounding chain
    chain = GroundingChain()
    
    # Test claim creation and grounding
    print("\n📋 Testing claim grounding...")
    
    # Create and ground a claim
    claim = chain.ground_claim(
        content="Acme Corp has 200 employees",
        source=GroundingSource.CLAY,
        source_id="clay_enrich_001",
        evidence={"employee_count": 200, "verified": True}
    )
    
    print(f"   Claim: {claim.content}")
    print(f"   Source: {claim.source.value}")
    print(f"   Confidence: {claim.confidence:.2f}")
    print(f"   Verified: {claim.verified}")
    
    # Create a grounded output
    claims = [claim]
    output = chain.create_grounded_output(
        agent_name="CRAFTER",
        output_type="email_campaign",
        claims=claims
    )
    
    print(f"\n   Output ID: {output.id}")
    print(f"   Overall confidence: {output.overall_confidence:.2f}")
    print(f"   Status: {output.verification_status.value}")
    
    # Test flagging a hallucination
    hallucination_claim = chain.ground_claim(
        content="Acme Corp was founded in 1920",
        source=GroundingSource.INFERRED,
        source_id=None
    )
    hallucination_claim.confidence = 0.3  # Low confidence
    
    chain.flag_hallucination(
        claim=hallucination_claim,
        reason="Low confidence - needs verification"
    )
    
    print(f"\n   Hallucination flagged: {hallucination_claim.content}")
    print(f"   Confidence: {hallucination_claim.confidence:.2f}")
    print(f"   Flagged: {hallucination_claim.flagged}")
    print(f"   Flag reason: {hallucination_claim.flag_reason}")
    
    # Get flagged claims
    flagged = chain.get_flagged_claims()
    print(f"\n📊 Flagged claims: {len(flagged)}")
    
    # Get audit trail for the output
    audit = chain.get_audit_trail(output.id)
    print(f"   Audit entries: {len(audit)}")
    
    print("\n✅ Grounding Chain tests passed!")
    return True


def test_feedback_collector():
    """Test Feedback Collector for campaign learning."""
    print("\n" + "=" * 60)
    print("Testing Feedback Collector...")
    print("=" * 60)
    
    from core.feedback_collector import FeedbackCollector, FeedbackType, REWARD_MAP
    
    # Initialize collector
    collector = FeedbackCollector()
    
    # Record various feedback events
    print("\n📋 Recording feedback events...")
    
    events_to_record = [
        (FeedbackType.OPEN, "lead_001", "campaign_001"),
        (FeedbackType.CLICK, "lead_001", "campaign_001"),
        (FeedbackType.REPLY_POSITIVE, "lead_001", "campaign_001"),
        (FeedbackType.MEETING_BOOKED, "lead_001", "campaign_001"),
        (FeedbackType.OPEN, "lead_002", "campaign_001"),
        (FeedbackType.UNSUBSCRIBE, "lead_003", "campaign_001"),
    ]
    
    recorded_events = []
    for event_type, lead_id, campaign_id in events_to_record:
        event = collector.record_feedback(event_type, lead_id, campaign_id)
        recorded_events.append(event)
        print(f"   Recorded: {event_type.value} for {lead_id}")
    
    # Get campaign feedback
    campaign_events = collector.get_feedback_by_campaign("campaign_001")
    print(f"\n📊 Campaign 001 events: {len(campaign_events)}")
    
    # Get summary
    summary = collector.get_summary()
    print(f"   Summary: {summary}")
    
    # Check reward mapping
    print(f"\n📊 Reward Mapping (sample):")
    for event_type in [FeedbackType.MEETING_BOOKED, FeedbackType.REPLY_POSITIVE, FeedbackType.UNSUBSCRIBE]:
        reward = REWARD_MAP.get(event_type, 0)
        print(f"   {event_type.value}: {reward:+.2f}")
    
    # Export for RL training
    training_signals = collector.export_for_training()
    print(f"\n🤖 Training Signals exported: {len(training_signals)} signals")
    
    # Calculate total reward
    if training_signals:
        # Training signals may be dicts or objects
        if isinstance(training_signals[0], dict):
            total_reward = sum(s.get('reward', 0) for s in training_signals)
        else:
            total_reward = sum(s.reward for s in training_signals)
        print(f"   Total reward signal: {total_reward:.2f}")
    
    # Calculate campaign rewards (method takes no args, calculates for all)
    campaign_rewards = collector.calculate_campaign_rewards()
    print(f"   Total campaign rewards: {campaign_rewards}")
    
    print("\n✅ Feedback Collector tests passed!")
    return True


def test_full_integration():
    """Test full integration of all three components."""
    print("\n" + "=" * 60)
    print("Testing Full Integration...")
    print("=" * 60)
    
    from core.context_manager import ContextManager, Priority
    from core.grounding_chain import GroundingChain, GroundingSource
    from core.feedback_collector import FeedbackCollector, FeedbackType
    
    # Initialize all components
    context = ContextManager(max_tokens=50000)
    grounding = GroundingChain()
    feedback = FeedbackCollector()
    
    print("\n📋 Simulating CRAFTER workflow...")
    
    # 1. Add system context
    context.add_context(
        content="CRAFTER agent generating personalized email campaign",
        priority=Priority.CRITICAL,
        source="system"
    )
    
    # 2. Add lead data (from enricher)
    lead_data = {
        "first_name": "Jennifer",
        "company": "ScaleForce Solutions",
        "title": "VP of Sales",
        "industry": "B2B SaaS",
        "employee_count": 200
    }
    
    context.add_context(
        content=json.dumps(lead_data),
        priority=Priority.HIGH,
        source="enricher"
    )
    
    # 3. Generate email content (simulated)
    email_content = f"""
    Hi {lead_data['first_name']},
    
    I noticed {lead_data['company']} is growing rapidly in the {lead_data['industry']} space.
    
    With {lead_data['employee_count']} employees, you're likely facing scaling challenges
    in your sales operations.
    
    Would a quick chat about automating your RevOps be useful?
    
    Best,
    Chris
    """
    
    print(f"   Generated email for {lead_data['first_name']}")
    
    # 4. Create grounded claims
    claim1 = grounding.ground_claim(
        content=f"{lead_data['company']} has {lead_data['employee_count']} employees",
        source=GroundingSource.CLAY,
        source_id="enrichment_001",
        evidence=lead_data
    )
    
    claim2 = grounding.ground_claim(
        content=f"{lead_data['first_name']} is {lead_data['title']}",
        source=GroundingSource.CLAY,
        source_id="enrichment_001",
        evidence=lead_data
    )
    
    output = grounding.create_grounded_output(
        agent_name="CRAFTER",
        output_type="email_campaign",
        claims=[claim1, claim2]
    )
    
    print(f"   Created grounded output: {output.id[:8]}...")
    print(f"   Overall confidence: {output.overall_confidence:.2f}")
    
    # 5. Record campaign creation
    campaign_id = "campaign_test_001"
    feedback.record_feedback(
        FeedbackType.AE_APPROVED,
        lead_id="lead_001",
        campaign_id=campaign_id,
        metadata={"email_length": len(email_content)}
    )
    
    print(f"   Campaign {campaign_id} recorded for feedback")
    
    # 6. Simulate engagement
    feedback.record_feedback(FeedbackType.OPEN, "lead_001", campaign_id)
    feedback.record_feedback(FeedbackType.REPLY_POSITIVE, "lead_001", campaign_id)
    
    print("   Engagement signals recorded")
    
    # 7. Get final stats
    print(f"\n📊 Final Stats:")
    print(f"   Context utilization: {context.budget.utilization_percent:.1f}%")
    print(f"   Grounded outputs: {len(grounding.outputs)}")
    
    summary = feedback.get_summary()
    print(f"   Feedback summary: {summary}")
    
    print("\n✅ Full Integration test passed!")
    return True


def run_all_tests():
    """Run all Day 3-4 framework tests."""
    print("\n" + "=" * 70)
    print("🧪 DAY 3-4 FRAMEWORK INTEGRATION TESTS")
    print("=" * 70)
    
    results = {
        "context_manager": False,
        "grounding_chain": False,
        "feedback_collector": False,
        "full_integration": False
    }
    
    try:
        results["context_manager"] = test_context_manager()
    except Exception as e:
        print(f"\n❌ Context Manager test failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        results["grounding_chain"] = test_grounding_chain()
    except Exception as e:
        print(f"\n❌ Grounding Chain test failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        results["feedback_collector"] = test_feedback_collector()
    except Exception as e:
        print(f"\n❌ Feedback Collector test failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        results["full_integration"] = test_full_integration()
    except Exception as e:
        print(f"\n❌ Full Integration test failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Print summary
    print("\n" + "=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, passed_test in results.items():
        status = "✅ PASS" if passed_test else "❌ FAIL"
        print(f"   {test_name}: {status}")
    
    print(f"\n   Total: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL DAY 3-4 FRAMEWORK TESTS PASSED!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
