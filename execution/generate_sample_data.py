"""
Sample Data Generator
Creates realistic test data to demonstrate the system without real API connections.
Useful for testing and demos.

Enhanced for sandbox testing with:
- Realistic test leads matching ICP criteria
- Test companies with intent signals
- Sample replies (positive, negative, objections)
- Sample campaign outcomes
- Saves to .hive-mind/sandbox/test_*.json
"""

import os
import sys
import json
import random
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

PROJECT_ROOT = Path(__file__).parent.parent
HIVE_MIND = PROJECT_ROOT / ".hive-mind"
SANDBOX_DIR = HIVE_MIND / "sandbox"

# Sample data pools
FIRST_NAMES = ["James", "Sarah", "Michael", "Emily", "David", "Jessica", "Robert", "Amanda", "William", "Jennifer",
               "John", "Ashley", "Christopher", "Stephanie", "Daniel", "Nicole", "Matthew", "Elizabeth", "Anthony", "Megan"]

LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
              "Wilson", "Anderson", "Taylor", "Thomas", "Hernandez", "Moore", "Jackson", "Martin", "Lee", "Thompson"]

COMPANIES = [
    ("TechForward Inc", "SaaS", 150),
    ("CloudScale Solutions", "Technology", 280),
    ("DataDriven Corp", "Analytics", 95),
    ("RevOps Pro", "Professional Services", 45),
    ("SalesBoost AI", "SaaS", 200),
    ("GrowthPath", "Marketing Tech", 120),
    ("PipelineX", "Sales Tech", 180),
    ("LeadGen Masters", "Marketing", 75),
    ("CloserAI", "SaaS", 220),
    ("RevenueStack", "Technology", 350),
    ("DealFlow Systems", "CRM", 90),
    ("Quota Crushers", "Sales Enablement", 160),
    ("Prospect Pro", "Lead Gen", 110),
    ("WinRate Analytics", "Analytics", 85),
    ("FunnelForce", "Marketing Tech", 190),
]

TITLES = [
    ("VP of Sales", 25),
    ("VP of Revenue Operations", 25),
    ("Director of Sales", 15),
    ("CRO", 25),
    ("Head of RevOps", 20),
    ("Sales Operations Manager", 10),
    ("Director of Revenue", 18),
    ("VP of Business Development", 22),
    ("Chief Revenue Officer", 25),
    ("Sales Enablement Director", 16),
]

SEGMENTS = ["tier1_vip", "tier2_high", "tier3_standard", "tier4_nurture"]
SEGMENT_WEIGHTS = [0.1, 0.25, 0.45, 0.2]

CAMPAIGN_TEMPLATES = [
    {
        "type": "competitor_displacement",
        "subjects": [
            "Quick question about your {competitor} setup, {first_name}",
            "Noticed you're using {competitor}...",
            "{first_name}, curious about your sales stack",
        ],
        "competitors": ["Gong", "Clari", "Chorus", "Outreach", "SalesLoft"]
    },
    {
        "type": "event_followup",
        "subjects": [
            "Great connecting at {event}",
            "Following up from {event}",
            "{first_name} - quick thought after {event}",
        ],
        "events": ["SaaStr", "Dreamforce", "RevOps Summit", "Sales 3.0"]
    },
    {
        "type": "community_outreach",
        "subjects": [
            "Fellow {community} member here",
            "Saw your post in {community}",
            "Love what you shared in {community}",
        ],
        "communities": ["RevOps Co-op", "Pavilion", "Modern Sales Pros"]
    }
]


def generate_lead(lead_id: int) -> dict:
    """Generate a realistic sample lead."""
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    company, industry, size = random.choice(COMPANIES)
    title, title_score = random.choice(TITLES)
    
    # Calculate ICP score
    base_score = 40
    
    # Title impact
    base_score += title_score
    
    # Company size impact
    if 51 <= size <= 500:
        base_score += 15
    elif size > 500:
        base_score += 5
    
    # Industry impact
    if industry in ["SaaS", "Technology"]:
        base_score += 10
    
    # Add some randomness
    base_score += random.randint(-10, 10)
    base_score = max(20, min(100, base_score))
    
    # Assign tier
    if base_score >= 85:
        tier = "tier1_vip"
    elif base_score >= 70:
        tier = "tier2_high"
    elif base_score >= 50:
        tier = "tier3_standard"
    elif base_score >= 30:
        tier = "tier4_nurture"
    else:
        tier = "dq"
    
    return {
        "id": f"lead_{lead_id:04d}",
        "name": f"{first} {last}",
        "first_name": first,
        "last_name": last,
        "email": f"{first.lower()}.{last.lower()}@{company.lower().replace(' ', '')}.com",
        "title": title,
        "company": company,
        "company_size": size,
        "industry": industry,
        "linkedin_url": f"https://linkedin.com/in/{first.lower()}{last.lower()}",
        "icp_score": base_score,
        "icp_tier": tier,
        "source": random.choice(["competitor_follower", "event_attendee", "post_engager", "group_member"]),
        "scraped_at": (datetime.now() - timedelta(days=random.randint(0, 7))).isoformat(),
        "enriched": True
    }


def generate_campaign(campaign_id: int, leads: list) -> dict:
    """Generate a sample campaign."""
    template = random.choice(CAMPAIGN_TEMPLATES)
    
    # Select leads for this campaign
    campaign_leads = random.sample(leads, min(len(leads), random.randint(10, 30)))
    
    # Generate subject line
    subject_template = random.choice(template["subjects"])
    if "{competitor}" in subject_template:
        subject = subject_template.replace("{competitor}", random.choice(template["competitors"]))
    elif "{event}" in subject_template:
        subject = subject_template.replace("{event}", random.choice(template["events"]))
    elif "{community}" in subject_template:
        subject = subject_template.replace("{community}", random.choice(template["communities"]))
    else:
        subject = subject_template
    
    return {
        "id": f"campaign_{campaign_id:03d}",
        "name": f"{template['type'].replace('_', ' ').title()} - {datetime.now().strftime('%b %Y')}",
        "segment": random.choice(["tier1_vip", "tier2_high", "tier3_standard"]),
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "lead_count": len(campaign_leads),
        "leads": campaign_leads[:5],  # Only include first 5 for preview
        "emails": [
            {
                "step": 1,
                "subject": subject.replace("{first_name}", "{{first_name}}"),
                "body": f"""Hi {{{{first_name}}}},

I noticed you're leading {template['type'].replace('_', ' ')} efforts at {{{{company}}}}.

Quick question - are you seeing the same challenges we hear from other {campaign_leads[0]['industry'] if campaign_leads else 'tech'} leaders around pipeline visibility?

Worth a 15-minute chat?

Best,
Chris
Chief AI Officer"""
            },
            {
                "step": 2,
                "subject": "Re: " + subject.replace("{first_name}", "{{first_name}}"),
                "body": """{{first_name}},

Following up on my previous note. 

Happy to share how similar companies are solving this.

Open to a quick call this week?

Chris"""
            }
        ]
    }


def generate_all_sample_data(num_leads: int = 100, num_campaigns: int = 5):
    """Generate all sample data for testing."""
    
    print("\n🎲 Generating Sample Data for Testing\n")
    print("=" * 50)
    
    # Create directories
    directories = [
        HIVE_MIND / "scraped",
        HIVE_MIND / "enriched",
        HIVE_MIND / "segmented",
        HIVE_MIND / "campaigns",
        HIVE_MIND / "knowledge" / "campaigns",
        HIVE_MIND / "knowledge" / "templates",
        HIVE_MIND / "knowledge" / "deals",
        HIVE_MIND / "knowledge" / "voice_samples",
    ]
    
    for d in directories:
        d.mkdir(parents=True, exist_ok=True)
    
    # Generate leads
    print(f"\n  📋 Generating {num_leads} sample leads...")
    leads = [generate_lead(i) for i in range(num_leads)]
    
    # Save scraped data
    scraped_file = HIVE_MIND / "scraped" / f"sample_{datetime.now().strftime('%Y-%m-%d')}.json"
    with open(scraped_file, "w") as f:
        json.dump(leads, f, indent=2)
    print(f"     Saved to: {scraped_file.name}")
    
    # Save enriched data
    enriched_file = HIVE_MIND / "enriched" / f"enriched_{datetime.now().strftime('%Y-%m-%d')}.json"
    with open(enriched_file, "w") as f:
        json.dump(leads, f, indent=2)
    print(f"     Saved to: {enriched_file.name}")
    
    # Copy to latest
    latest_file = HIVE_MIND / "enriched" / "latest.json"
    with open(latest_file, "w") as f:
        json.dump(leads, f, indent=2)
    
    # Save segmented data
    segmented_file = HIVE_MIND / "segmented" / f"segmented_{datetime.now().strftime('%Y-%m-%d')}.json"
    with open(segmented_file, "w") as f:
        json.dump(leads, f, indent=2)
    print(f"     Saved to: {segmented_file.name}")
    
    # Generate campaigns
    print(f"\n  📧 Generating {num_campaigns} sample campaigns...")
    for i in range(num_campaigns):
        campaign = generate_campaign(i + 1, leads)
        campaign_file = HIVE_MIND / "campaigns" / f"{campaign['id']}.json"
        with open(campaign_file, "w") as f:
            json.dump(campaign, f, indent=2)
        print(f"     Created: {campaign['name']}")
    
    # Generate baseline metrics
    print("\n  📊 Generating baseline metrics...")
    baselines = {
        "calculated_at": datetime.now().isoformat(),
        "campaigns_analyzed": 25,
        "overall": {
            "total_emails_sent": 12500,
            "average_open_rate": 0.48,
            "average_reply_rate": 0.085,
            "meeting_rate": 0.025
        },
        "by_segment": {
            "competitor_displacement": {
                "campaigns": 8,
                "emails_sent": 4000,
                "open_rate": 0.52,
                "reply_rate": 0.095,
                "meeting_rate": 0.03
            },
            "event_followup": {
                "campaigns": 10,
                "emails_sent": 5000,
                "open_rate": 0.55,
                "reply_rate": 0.11,
                "meeting_rate": 0.035
            }
        }
    }
    
    baselines_file = HIVE_MIND / "knowledge" / "campaigns" / "_baselines.json"
    with open(baselines_file, "w") as f:
        json.dump(baselines, f, indent=2)
    print(f"     Saved to: _baselines.json")
    
    # Update learnings
    learnings = {
        "version": "1.0",
        "created_at": datetime.now().isoformat(),
        "last_anneal": datetime.now().isoformat(),
        "learnings": [
            {
                "type": "template_performance",
                "summary": "Subject lines with questions perform 23% better",
                "source": "sample_data",
                "timestamp": datetime.now().isoformat()
            }
        ],
        "error_patterns": []
    }
    
    learnings_file = HIVE_MIND / "learnings.json"
    with open(learnings_file, "w") as f:
        json.dump(learnings, f, indent=2)
    print(f"     Updated: learnings.json")
    
    # Summary
    print("\n" + "=" * 50)
    print("\n✅ Sample data generated successfully!")
    print(f"\n   Leads: {num_leads}")
    print(f"   Campaigns: {num_campaigns}")
    print(f"\n   Now run: python execution\\health_check.py")
    print("   And try: .\\scripts\\start_dashboard.ps1\n")


def main():
    parser = argparse.ArgumentParser(description="Generate sample data for testing")
    parser.add_argument("--leads", type=int, default=100, help="Number of leads to generate")
    parser.add_argument("--campaigns", type=int, default=5, help="Number of campaigns to generate")
    
    args = parser.parse_args()
    
    generate_all_sample_data(args.leads, args.campaigns)


if __name__ == "__main__":
    main()
