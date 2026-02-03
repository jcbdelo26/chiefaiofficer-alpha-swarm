"""
Test Data Generator - Wrapper for generate_sample_data.py
Provides additional test data generation helpers for sandbox testing and pipeline validation.
"""

import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

# Re-export all key items from generate_sample_data
# Support both package import and direct execution
try:
    from .generate_sample_data import (
        FIRST_NAMES,
        LAST_NAMES,
        COMPANIES,
        TITLES,
        SEGMENTS,
        SEGMENT_WEIGHTS,
        CAMPAIGN_TEMPLATES,
        generate_lead,
        generate_campaign,
        generate_all_sample_data,
    )
except ImportError:
    from generate_sample_data import (
        FIRST_NAMES,
        LAST_NAMES,
        COMPANIES,
        TITLES,
        SEGMENTS,
        SEGMENT_WEIGHTS,
        CAMPAIGN_TEMPLATES,
        generate_lead,
        generate_campaign,
        generate_all_sample_data,
    )

__all__ = [
    # Re-exports
    "FIRST_NAMES",
    "LAST_NAMES",
    "COMPANIES",
    "TITLES",
    "SEGMENTS",
    "SEGMENT_WEIGHTS",
    "CAMPAIGN_TEMPLATES",
    "generate_lead",
    "generate_campaign",
    "generate_all_sample_data",
    # New helpers
    "generate_intent_signal",
    "generate_campaign_outcome",
    "generate_enrichment_data",
    "generate_test_batch",
]

# Intent signal types and their weights
INTENT_SIGNALS = [
    ("website_visit", 0.3),
    ("content_download", 0.2),
    ("pricing_page", 0.15),
    ("demo_request", 0.1),
    ("competitor_comparison", 0.1),
    ("case_study_view", 0.1),
    ("feature_page", 0.05),
]

CONTENT_TOPICS = [
    "sales automation",
    "pipeline management",
    "revenue operations",
    "sales analytics",
    "CRM integration",
    "lead scoring",
    "outreach automation",
]


def generate_intent_signal(lead_id: str) -> Dict[str, Any]:
    """Generate mock intent signal data for a lead."""
    signal_type, _ = random.choices(
        INTENT_SIGNALS, weights=[w for _, w in INTENT_SIGNALS]
    )[0]
    
    # Higher intensity for more valuable signals
    intensity_map = {
        "demo_request": random.randint(80, 100),
        "pricing_page": random.randint(70, 90),
        "competitor_comparison": random.randint(65, 85),
        "content_download": random.randint(50, 75),
        "case_study_view": random.randint(45, 70),
        "website_visit": random.randint(20, 50),
        "feature_page": random.randint(30, 60),
    }
    
    return {
        "lead_id": lead_id,
        "signal_type": signal_type,
        "intensity": intensity_map.get(signal_type, 50),
        "topic": random.choice(CONTENT_TOPICS),
        "source": random.choice(["6sense", "Bombora", "ZoomInfo", "internal"]),
        "detected_at": (datetime.now() - timedelta(hours=random.randint(1, 72))).isoformat(),
        "confidence": round(random.uniform(0.6, 0.95), 2),
        "metadata": {
            "page_views": random.randint(1, 15),
            "time_on_site": random.randint(30, 600),
            "return_visitor": random.random() > 0.6,
        }
    }


def generate_campaign_outcome(lead: Dict[str, Any], template: str) -> Dict[str, Any]:
    """Generate mock campaign result for a lead."""
    # Base probabilities influenced by ICP score
    icp_score = lead.get("icp_score", 50)
    score_modifier = icp_score / 100
    
    opened = random.random() < (0.35 + 0.25 * score_modifier)
    clicked = opened and random.random() < (0.15 + 0.15 * score_modifier)
    replied = opened and random.random() < (0.05 + 0.08 * score_modifier)
    
    reply_sentiment = None
    meeting_booked = False
    
    if replied:
        sentiment_choices = ["positive", "neutral", "negative", "objection"]
        sentiment_weights = [0.3, 0.25, 0.2, 0.25]
        reply_sentiment = random.choices(sentiment_choices, weights=sentiment_weights)[0]
        meeting_booked = reply_sentiment == "positive" and random.random() < 0.6
    
    return {
        "lead_id": lead.get("id"),
        "campaign_template": template,
        "sent_at": (datetime.now() - timedelta(days=random.randint(1, 14))).isoformat(),
        "opened": opened,
        "opened_at": (datetime.now() - timedelta(days=random.randint(0, 7))).isoformat() if opened else None,
        "clicked": clicked,
        "replied": replied,
        "reply_sentiment": reply_sentiment,
        "meeting_booked": meeting_booked,
        "unsubscribed": not replied and random.random() < 0.02,
        "bounced": random.random() < 0.03,
    }


def generate_enrichment_data(lead: Dict[str, Any]) -> Dict[str, Any]:
    """Generate mock enrichment response for a lead."""
    company_data = random.choice(COMPANIES)
    
    technologies = random.sample([
        "Salesforce", "HubSpot", "Outreach", "Gong", "ZoomInfo",
        "Slack", "Microsoft 365", "Google Workspace", "Snowflake",
        "Tableau", "Looker", "Marketo", "Pardot", "Drift"
    ], k=random.randint(3, 8))
    
    return {
        "lead_id": lead.get("id"),
        "enriched_at": datetime.now().isoformat(),
        "source": random.choice(["Apollo", "ZoomInfo", "Clearbit", "Lusha"]),
        "company": {
            "name": lead.get("company", company_data[0]),
            "industry": lead.get("industry", company_data[1]),
            "employee_count": lead.get("company_size", company_data[2]),
            "revenue_range": random.choice(["$1M-$10M", "$10M-$50M", "$50M-$100M", "$100M-$500M"]),
            "funding_stage": random.choice(["Seed", "Series A", "Series B", "Series C", "Private", "Public"]),
            "technologies": technologies,
            "headquarters": random.choice(["San Francisco, CA", "New York, NY", "Austin, TX", "Boston, MA", "Seattle, WA"]),
        },
        "contact": {
            "verified_email": lead.get("email"),
            "phone": f"+1-{random.randint(200,999)}-{random.randint(100,999)}-{random.randint(1000,9999)}",
            "linkedin_verified": random.random() > 0.2,
            "tenure_months": random.randint(6, 60),
        },
        "signals": {
            "hiring": random.random() > 0.7,
            "recent_funding": random.random() > 0.8,
            "tech_changes": random.random() > 0.75,
        },
        "confidence_score": round(random.uniform(0.7, 0.98), 2),
    }


def generate_test_batch(count: int, scenario: str) -> List[Dict[str, Any]]:
    """
    Generate a batch of test data for specific test scenarios.
    
    Scenarios:
    - high_intent: Leads with high ICP scores and strong intent signals
    - cold_outreach: Standard leads for cold outreach testing
    - competitor_displacement: Leads using competitor products
    - event_followup: Leads from event attendance
    """
    leads = []
    
    for i in range(count):
        lead = generate_lead(i)
        
        if scenario == "high_intent":
            # Boost ICP score and add intent signals
            lead["icp_score"] = random.randint(80, 100)
            lead["icp_tier"] = "tier1_vip"
            lead["intent_signals"] = [generate_intent_signal(lead["id"]) for _ in range(random.randint(2, 5))]
            lead["source"] = random.choice(["demo_request", "pricing_page_visit", "content_download"])
            
        elif scenario == "cold_outreach":
            # Standard cold leads
            lead["icp_score"] = random.randint(40, 70)
            lead["icp_tier"] = random.choice(["tier2_high", "tier3_standard"])
            lead["source"] = "list_import"
            lead["intent_signals"] = []
            
        elif scenario == "competitor_displacement":
            # Leads using competitor products
            competitors = ["Gong", "Clari", "Chorus", "Outreach", "SalesLoft"]
            lead["competitor"] = random.choice(competitors)
            lead["source"] = "competitor_follower"
            lead["icp_score"] = random.randint(65, 90)
            lead["icp_tier"] = random.choice(["tier1_vip", "tier2_high"])
            lead["displacement_signals"] = {
                "competitor": lead["competitor"],
                "contract_end_q": random.choice(["Q1", "Q2", "Q3", "Q4"]),
                "sentiment": random.choice(["frustrated", "evaluating", "neutral"]),
            }
            
        elif scenario == "event_followup":
            # Event attendee leads
            events = ["SaaStr 2024", "Dreamforce", "RevOps Summit", "Sales 3.0", "Pavilion CMO Summit"]
            lead["event"] = random.choice(events)
            lead["source"] = "event_attendee"
            lead["icp_score"] = random.randint(55, 85)
            lead["icp_tier"] = random.choice(["tier2_high", "tier3_standard"])
            lead["event_data"] = {
                "event_name": lead["event"],
                "attended_session": random.choice(["keynote", "workshop", "networking", "booth_visit"]),
                "scanned_at": (datetime.now() - timedelta(days=random.randint(1, 14))).isoformat(),
            }
        
        leads.append(lead)
    
    return leads


if __name__ == "__main__":
    print("\n[TEST] Test Data Generator Demo\n")
    print("=" * 60)
    
    # Generate a sample lead
    print("\n1. Sample Lead:")
    lead = generate_lead(1)
    print(f"   {lead['name']} - {lead['title']} at {lead['company']}")
    print(f"   ICP Score: {lead['icp_score']}, Tier: {lead['icp_tier']}")
    
    # Generate intent signal
    print("\n2. Intent Signal for lead:")
    signal = generate_intent_signal(lead["id"])
    print(f"   Type: {signal['signal_type']}, Intensity: {signal['intensity']}")
    print(f"   Topic: {signal['topic']}, Source: {signal['source']}")
    
    # Generate enrichment
    print("\n3. Enrichment Data:")
    enrichment = generate_enrichment_data(lead)
    print(f"   Revenue: {enrichment['company']['revenue_range']}")
    print(f"   Technologies: {', '.join(enrichment['company']['technologies'][:4])}...")
    
    # Generate campaign outcome
    print("\n4. Campaign Outcome:")
    outcome = generate_campaign_outcome(lead, "competitor_displacement")
    print(f"   Opened: {outcome['opened']}, Replied: {outcome['replied']}")
    print(f"   Meeting Booked: {outcome['meeting_booked']}")
    
    # Generate test batches
    print("\n5. Test Batches (5 leads each):")
    for scenario in ["high_intent", "cold_outreach", "competitor_displacement", "event_followup"]:
        batch = generate_test_batch(5, scenario)
        avg_score = sum(l["icp_score"] for l in batch) / len(batch)
        print(f"   {scenario}: avg ICP score = {avg_score:.1f}")
    
    print("\n" + "=" * 60)
    print("[OK] Test data generation helpers ready for use!")
    print("\nUsage:")
    print("  from generate_test_data import generate_test_batch, generate_intent_signal")
    print("  leads = generate_test_batch(10, 'high_intent')")
    print()
