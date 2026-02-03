"""
Test Routing/Escalation System
==============================
Unit tests for core/routing.py escalation triggers and handoff logic.

Usage:
    pytest tests/test_routing.py -v
"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.routing import (
    evaluate_escalation_triggers,
    HandoffTicket,
    HandoffDestination,
    HandoffPriority,
    _matches_c_level,
    _contains_keywords,
    _matches_negative_patterns,
    PRICING_KEYWORDS,
    SECURITY_KEYWORDS,
    BUYING_SIGNAL_KEYWORDS,
)


@pytest.fixture
def standard_lead():
    """Standard lead without special characteristics."""
    return {
        "lead_id": "lead_standard_001",
        "name": "John Smith",
        "email": "john.smith@company.com",
        "company": "Acme Corp",
        "title": "Sales Manager",
        "employee_count": 150,
        "icp_score": 75,
        "campaign_id": "campaign_001"
    }


@pytest.fixture
def enterprise_lead():
    """Enterprise lead with >1000 employees."""
    return {
        "lead_id": "lead_enterprise_001",
        "name": "Sarah Johnson",
        "email": "sarah.johnson@bigcorp.com",
        "company": "BigCorp Industries",
        "title": "Director of Operations",
        "employee_count": 2500,
        "icp_score": 88,
        "campaign_id": "campaign_001"
    }


@pytest.fixture
def clevel_lead():
    """C-level executive lead."""
    return {
        "lead_id": "lead_clevel_001",
        "name": "Michael Chen",
        "email": "mchen@techstartup.io",
        "company": "TechStartup",
        "title": "CEO",
        "employee_count": 80,
        "icp_score": 92,
        "campaign_id": "campaign_001"
    }


@pytest.fixture
def high_icp_lead():
    """Lead with ICP score >= 95."""
    return {
        "lead_id": "lead_highicp_001",
        "name": "Emily Rodriguez",
        "email": "emily@perfectfit.com",
        "company": "Perfect Fit Inc",
        "title": "VP of Sales",
        "employee_count": 200,
        "icp_score": 96,
        "campaign_id": "campaign_001"
    }


@pytest.fixture
def existing_customer_lead():
    """Lead who is an existing customer."""
    return {
        "lead_id": "lead_customer_001",
        "name": "David Kim",
        "email": "dkim@existingcustomer.com",
        "company": "Existing Customer Co",
        "title": "Product Manager",
        "employee_count": 300,
        "is_existing_customer": True,
        "campaign_id": "campaign_001"
    }


@pytest.fixture
def competitor_lead():
    """Lead who works for a competitor."""
    return {
        "lead_id": "lead_competitor_001",
        "name": "Alex Thompson",
        "email": "alex@competitor.com",
        "company": "Competitor Inc",
        "title": "Account Executive",
        "employee_count": 100,
        "is_competitor": True,
        "campaign_id": "campaign_001"
    }


@pytest.fixture
def not_interested_reply():
    """Reply indicating not interested."""
    return {
        "body": "Thanks but we're not interested at this time. Please remove me from your list.",
        "sentiment": "negative"
    }


@pytest.fixture
def pricing_reply():
    """Reply asking about pricing."""
    return {
        "body": "This looks interesting. What's the pricing for a team of 50 users? What's the ROI typically?",
        "sentiment": "positive"
    }


@pytest.fixture
def meeting_request_reply():
    """Reply requesting a meeting."""
    return {
        "body": "Sounds great! Can we schedule a call for next week? I have availability Tuesday afternoon.",
        "sentiment": "positive"
    }


@pytest.fixture
def technical_reply():
    """Reply with technical questions."""
    return {
        "body": "Do you have API documentation? We need to understand the integration with Salesforce and the webhook architecture.",
        "sentiment": "neutral"
    }


@pytest.fixture
def buying_signal_reply():
    """Reply with clear buying signals."""
    return {
        "body": "We're actively evaluating solutions in this space. Can you tell me more about your timeline for implementation?",
        "sentiment": "positive"
    }


class TestImmediateEscalationEnterprise:
    """Tests for immediate escalation of enterprise accounts."""
    
    def test_immediate_escalation_enterprise_triggers(self, enterprise_lead):
        """Enterprise account (>1000 employees) should trigger immediate escalation."""
        tickets = evaluate_escalation_triggers(enterprise_lead)
        
        enterprise_tickets = [t for t in tickets if t.trigger == "enterprise_account"]
        assert len(enterprise_tickets) == 1
        assert enterprise_tickets[0].destination == HandoffDestination.ENTERPRISE_AE.value
        assert enterprise_tickets[0].priority == HandoffPriority.CRITICAL.value
    
    def test_immediate_escalation_enterprise_sla(self, enterprise_lead):
        """Enterprise escalation should have 5-minute SLA."""
        tickets = evaluate_escalation_triggers(enterprise_lead)
        
        enterprise_tickets = [t for t in tickets if t.trigger == "enterprise_account"]
        ticket = enterprise_tickets[0]
        
        created = datetime.fromisoformat(ticket.created_at)
        sla_due = datetime.fromisoformat(ticket.sla_due_at)
        delta = (sla_due - created).total_seconds()
        
        assert delta == 5 * 60
    
    def test_no_enterprise_escalation_for_small_company(self, standard_lead):
        """Small company should not trigger enterprise escalation."""
        tickets = evaluate_escalation_triggers(standard_lead)
        
        enterprise_tickets = [t for t in tickets if t.trigger == "enterprise_account"]
        assert len(enterprise_tickets) == 0


class TestImmediateEscalationCLevel:
    """Tests for immediate escalation of C-level contacts."""
    
    def test_immediate_escalation_clevel(self, clevel_lead):
        """C-level title should trigger immediate escalation."""
        tickets = evaluate_escalation_triggers(clevel_lead)
        
        clevel_tickets = [t for t in tickets if t.trigger == "c_level_engagement"]
        assert len(clevel_tickets) == 1
        assert clevel_tickets[0].destination == HandoffDestination.SENIOR_AE.value
        assert clevel_tickets[0].priority == HandoffPriority.CRITICAL.value
    
    def test_clevel_pattern_ceo(self):
        """CEO title should match C-level pattern."""
        assert _matches_c_level("CEO") is True
        assert _matches_c_level("Chief Executive Officer") is True
    
    def test_clevel_pattern_cfo(self):
        """CFO title should match C-level pattern."""
        assert _matches_c_level("CFO") is True
        assert _matches_c_level("Chief Financial Officer") is True
    
    def test_clevel_pattern_founder(self):
        """Founder title should match C-level pattern."""
        assert _matches_c_level("Founder") is True
        assert _matches_c_level("Co-Founder") is True
        assert _matches_c_level("Co-Founder & CEO") is True
    
    def test_clevel_pattern_president(self):
        """President title should match C-level pattern."""
        assert _matches_c_level("President") is True
        assert _matches_c_level("President & COO") is True
    
    def test_non_clevel_title(self, standard_lead):
        """Non-C-level title should not trigger escalation."""
        tickets = evaluate_escalation_triggers(standard_lead)
        
        clevel_tickets = [t for t in tickets if t.trigger == "c_level_engagement"]
        assert len(clevel_tickets) == 0
    
    def test_manager_not_clevel(self):
        """Manager title should not match C-level."""
        assert _matches_c_level("Sales Manager") is False
        assert _matches_c_level("VP of Sales") is False
        assert _matches_c_level("Director") is False


class TestImmediateEscalationExistingCustomer:
    """Tests for immediate escalation of existing customers."""
    
    def test_immediate_escalation_existing_customer(self, existing_customer_lead):
        """Existing customer should trigger CSM escalation."""
        tickets = evaluate_escalation_triggers(existing_customer_lead)
        
        customer_tickets = [t for t in tickets if t.trigger == "existing_customer"]
        assert len(customer_tickets) == 1
        assert customer_tickets[0].destination == HandoffDestination.CSM.value
        assert customer_tickets[0].priority == HandoffPriority.CRITICAL.value


class TestImmediateEscalationCompetitor:
    """Tests for blocking competitor contacts."""
    
    def test_immediate_escalation_competitor_blocked(self, competitor_lead):
        """Competitor employee should be blocked."""
        tickets = evaluate_escalation_triggers(competitor_lead)
        
        competitor_tickets = [t for t in tickets if t.trigger == "competitor_employee"]
        assert len(competitor_tickets) == 1
        assert competitor_tickets[0].destination == HandoffDestination.SKIP.value
        assert competitor_tickets[0].priority == HandoffPriority.BLOCK.value


class TestStandardEscalationPricing:
    """Tests for standard escalation on pricing questions."""
    
    def test_standard_escalation_pricing(self, standard_lead, pricing_reply):
        """Pricing question should trigger AE escalation."""
        tickets = evaluate_escalation_triggers(standard_lead, reply=pricing_reply)
        
        pricing_tickets = [t for t in tickets if t.trigger == "pricing_mentioned"]
        assert len(pricing_tickets) == 1
        assert pricing_tickets[0].destination == HandoffDestination.AE.value
        assert pricing_tickets[0].priority == HandoffPriority.HIGH.value
    
    def test_pricing_keywords_detected(self):
        """Pricing keywords should be properly detected."""
        pricing_texts = [
            "What's the price for enterprise?",
            "Can you share pricing details?",
            "What's the cost per user?",
            "Do you offer any discounts?",
            "What's the budget needed?",
            "How much does it cost?",
            "What's the ROI typically?"
        ]
        
        for text in pricing_texts:
            assert _contains_keywords(text, PRICING_KEYWORDS) is True, f"'{text}' should contain pricing keywords"
    
    def test_non_pricing_not_detected(self):
        """Non-pricing text should not trigger."""
        non_pricing = "Tell me more about your features and integrations."
        assert _contains_keywords(non_pricing, PRICING_KEYWORDS) is False


class TestStandardEscalationMeetingRequest:
    """Tests for escalation on meeting requests."""
    
    def test_meeting_request_escalation(self, standard_lead, meeting_request_reply):
        """Meeting request should trigger calendar escalation."""
        tickets = evaluate_escalation_triggers(standard_lead, reply=meeting_request_reply)
        
        meeting_tickets = [t for t in tickets if t.trigger == "meeting_request_manual"]
        assert len(meeting_tickets) == 1
        assert meeting_tickets[0].destination == HandoffDestination.AE_CALENDAR.value
        assert meeting_tickets[0].priority == HandoffPriority.MEDIUM.value


class TestStandardEscalationTechnical:
    """Tests for escalation on technical questions."""
    
    def test_technical_question_escalation(self, standard_lead, technical_reply):
        """Technical questions should trigger SE escalation."""
        tickets = evaluate_escalation_triggers(standard_lead, reply=technical_reply)
        
        technical_tickets = [t for t in tickets if t.trigger == "technical_deepdive"]
        assert len(technical_tickets) >= 1
        assert any(t.destination == HandoffDestination.SE.value for t in technical_tickets)


class TestDeferredEscalationHighICP:
    """Tests for deferred escalation based on high ICP score."""
    
    def test_deferred_escalation_high_icp(self, high_icp_lead):
        """ICP score >= 95 should trigger VIP campaign."""
        tickets = evaluate_escalation_triggers(high_icp_lead)
        
        icp_tickets = [t for t in tickets if t.trigger == "icp_score_95_plus"]
        assert len(icp_tickets) == 1
        assert icp_tickets[0].destination == HandoffDestination.VIP_CAMPAIGN.value
        assert icp_tickets[0].priority == HandoffPriority.LOW.value
    
    def test_deferred_escalation_low_sla(self, high_icp_lead):
        """Deferred escalation should have 24-hour SLA."""
        tickets = evaluate_escalation_triggers(high_icp_lead)
        
        icp_tickets = [t for t in tickets if t.trigger == "icp_score_95_plus"]
        ticket = icp_tickets[0]
        
        created = datetime.fromisoformat(ticket.created_at)
        sla_due = datetime.fromisoformat(ticket.sla_due_at)
        delta = (sla_due - created).total_seconds()
        
        assert delta == 24 * 60 * 60
    
    def test_no_high_icp_escalation_for_normal_score(self, standard_lead):
        """Normal ICP score should not trigger VIP escalation."""
        tickets = evaluate_escalation_triggers(standard_lead)
        
        icp_tickets = [t for t in tickets if t.trigger == "icp_score_95_plus"]
        assert len(icp_tickets) == 0


class TestDeferredEscalationMultipleTouchpoints:
    """Tests for escalation based on multiple touchpoints."""
    
    def test_multiple_touchpoints_escalation(self):
        """Lead with 5+ touchpoints should trigger nurture upgrade."""
        lead = {
            "lead_id": "lead_multi_001",
            "name": "Test User",
            "email": "test@example.com",
            "title": "Manager",
            "employee_count": 100,
            "touchpoint_count": 6,
            "campaign_id": "campaign_001"
        }
        
        tickets = evaluate_escalation_triggers(lead)
        
        touchpoint_tickets = [t for t in tickets if t.trigger == "multiple_touchpoints"]
        assert len(touchpoint_tickets) == 1
        assert touchpoint_tickets[0].destination == HandoffDestination.NURTURE_UPGRADE.value


class TestDeferredEscalationEngagementChange:
    """Tests for escalation based on engagement pattern changes."""
    
    def test_engagement_change_escalation(self):
        """Engagement spike should trigger outreach adjustment."""
        lead = {
            "lead_id": "lead_engage_001",
            "name": "Test User",
            "email": "test@example.com",
            "title": "Manager",
            "employee_count": 100,
            "engagement_changed": True,
            "campaign_id": "campaign_001"
        }
        
        tickets = evaluate_escalation_triggers(lead)
        
        engagement_tickets = [t for t in tickets if t.trigger == "engagement_pattern_change"]
        assert len(engagement_tickets) == 1
        assert engagement_tickets[0].destination == HandoffDestination.OUTREACH_ADJUSTMENT.value


class TestDeferredEscalationPersonaMismatch:
    """Tests for escalation based on persona mismatch."""
    
    def test_persona_mismatch_escalation(self):
        """Persona mismatch should trigger re-qualification."""
        lead = {
            "lead_id": "lead_mismatch_001",
            "name": "Test User",
            "email": "test@example.com",
            "title": "Manager",
            "employee_count": 100,
            "persona_mismatch": True,
            "campaign_id": "campaign_001"
        }
        
        tickets = evaluate_escalation_triggers(lead)
        
        mismatch_tickets = [t for t in tickets if t.trigger == "persona_mismatch"]
        assert len(mismatch_tickets) == 1
        assert mismatch_tickets[0].destination == HandoffDestination.RE_QUALIFICATION.value


class TestObjectionRoutingNotInterested:
    """Tests for routing 'not interested' objections."""
    
    def test_objection_routing_not_interested(self, standard_lead, not_interested_reply):
        """Not interested reply should trigger AE review."""
        tickets = evaluate_escalation_triggers(standard_lead, reply=not_interested_reply)
        
        negative_tickets = [t for t in tickets if t.trigger == "negative_reply"]
        assert len(negative_tickets) == 1
        assert negative_tickets[0].destination == HandoffDestination.AE_REVIEW.value
        assert negative_tickets[0].priority == HandoffPriority.HIGH.value
    
    def test_negative_patterns_detected(self):
        """Negative patterns should be properly detected."""
        negative_texts = [
            "Not interested",
            "No thanks",
            "Stop emailing me",
            "Please unsubscribe me",
            "Remove me from your list",
            "Never contact me again",
            "This is spam"
        ]
        
        for text in negative_texts:
            assert _matches_negative_patterns(text) is True, f"'{text}' should match negative pattern"
    
    def test_neutral_text_not_negative(self):
        """Neutral text should not match negative patterns."""
        neutral = "Thanks for reaching out. I'll review this with my team."
        assert _matches_negative_patterns(neutral) is False


class TestObjectionRoutingPricing:
    """Tests for routing pricing objections."""
    
    def test_objection_routing_pricing(self, standard_lead, pricing_reply):
        """Pricing question should route to AE."""
        tickets = evaluate_escalation_triggers(standard_lead, reply=pricing_reply)
        
        pricing_tickets = [t for t in tickets if t.trigger == "pricing_mentioned"]
        assert len(pricing_tickets) == 1
        assert pricing_tickets[0].destination == HandoffDestination.AE.value


class TestObjectionRoutingSecurity:
    """Tests for routing security questions."""
    
    def test_security_question_escalation(self, standard_lead):
        """Security questions should route to SE."""
        reply = {
            "body": "What's your SOC2 compliance status? Do you have penetration test results?",
            "sentiment": "neutral"
        }
        
        tickets = evaluate_escalation_triggers(standard_lead, reply=reply)
        
        security_tickets = [t for t in tickets if t.trigger == "security_question"]
        assert len(security_tickets) == 1
        assert security_tickets[0].destination == HandoffDestination.SE.value
        assert security_tickets[0].priority == HandoffPriority.HIGH.value
    
    def test_security_keywords_detected(self):
        """Security keywords should be properly detected."""
        security_texts = [
            "What about SOC2 compliance?",
            "Do you have GDPR documentation?",
            "Is the data encrypted?",
            "Do you do penetration testing?"
        ]
        
        for text in security_texts:
            assert _contains_keywords(text, SECURITY_KEYWORDS) is True, f"'{text}' should contain security keywords"


class TestBuyingSignalRouting:
    """Tests for routing based on buying signals."""
    
    def test_buying_signals_escalation(self, standard_lead, buying_signal_reply):
        """Buying signals should trigger AE escalation."""
        tickets = evaluate_escalation_triggers(standard_lead, reply=buying_signal_reply)
        
        buying_tickets = [t for t in tickets if t.trigger == "buying_signals"]
        assert len(buying_tickets) == 1
        assert buying_tickets[0].destination == HandoffDestination.AE.value
        assert buying_tickets[0].priority == HandoffPriority.MEDIUM.value
    
    def test_buying_signal_keywords_detected(self):
        """Buying signal keywords should be properly detected."""
        buying_texts = [
            "I'm interested in learning more",
            "Tell me more about this",
            "We're looking for a solution",
            "We're evaluating options",
            "What are the next steps?"
        ]
        
        for text in buying_texts:
            assert _contains_keywords(text, BUYING_SIGNAL_KEYWORDS) is True, f"'{text}' should contain buying signals"


class TestHandoffTicketMetadata:
    """Tests for handoff ticket metadata."""
    
    def test_ticket_contains_lead_info(self, enterprise_lead):
        """Ticket should contain lead metadata."""
        tickets = evaluate_escalation_triggers(enterprise_lead)
        
        ticket = tickets[0]
        assert ticket.lead_id == enterprise_lead["lead_id"]
        assert ticket.lead_name == enterprise_lead["name"]
        assert ticket.lead_email == enterprise_lead["email"]
        assert ticket.lead_company == enterprise_lead["company"]
    
    def test_ticket_contains_reply_snippet(self, standard_lead, pricing_reply):
        """Ticket should contain reply snippet."""
        tickets = evaluate_escalation_triggers(standard_lead, reply=pricing_reply)
        
        pricing_tickets = [t for t in tickets if t.trigger == "pricing_mentioned"]
        assert pricing_tickets[0].reply_snippet is not None
        assert len(pricing_tickets[0].reply_snippet) <= 200


class TestMultipleTriggers:
    """Tests for leads that trigger multiple escalations."""
    
    def test_enterprise_clevel_triggers_both(self):
        """Enterprise C-level should trigger multiple escalations."""
        lead = {
            "lead_id": "lead_enterprise_ceo",
            "name": "Jane Doe",
            "email": "jdoe@megacorp.com",
            "company": "MegaCorp",
            "title": "CEO",
            "employee_count": 5000,
            "icp_score": 98,
            "campaign_id": "campaign_001"
        }
        
        tickets = evaluate_escalation_triggers(lead)
        
        triggers = [t.trigger for t in tickets]
        assert "enterprise_account" in triggers
        assert "c_level_engagement" in triggers
        assert "icp_score_95_plus" in triggers
        assert len(tickets) >= 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
