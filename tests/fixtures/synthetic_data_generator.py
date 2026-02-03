#!/usr/bin/env python3
"""
Synthetic Data Generator
=========================
Generate realistic test data for sandbox testing.

Features:
- ICP-matched leads
- Off-ICP leads (edge cases)
- Data quality issues (missing fields, bad formats)
- Edge case scenarios (duplicates, unsubscribed)

Usage:
    python tests/fixtures/synthetic_data_generator.py --count=100 --output=leads.json
"""

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any
import argparse

# Real-world company/person data pools
COMPANIES = [
    # ON-ICP (B2B SaaS, 50-500 employees)
    {"name": "CloudForce Inc", "domain": "cloudforce.io", "industry": "SaaS", "employees": 120, "revenue": "$15M", "icp_score": 0.92},
    {"name": "DataStream Solutions", "domain": "datastream.com", "industry": "Data Analytics", "employees": 85, "revenue": "$8M", "icp_score": 0.88},
    {"name": "SalesAI Corp", "domain": "salesai.co", "industry": "Sales Tech", "employees": 200, "revenue": "$25M", "icp_score": 0.95},
    {"name": "RevOps Platform", "domain": "revops.io", "industry": "B2B SaaS", "employees": 150, "revenue": "$18M", "icp_score": 0.90},
    
    # OFF-ICP (too small, wrong industry)
    {"name": "Mom & Pop Shop", "domain": "mompopshop.com", "industry": "Retail", "employees": 5, "revenue": "$500K", "icp_score": 0.15},
    {"name": "Freelancer LLC", "domain": "freelancer-work.com", "industry": "Consulting", "employees": 1, "revenue": "$100K", "icp_score": 0.10},
    {"name": "Non-Profit Org", "domain": "nonprofit.org", "industry": "Non-Profit", "employees": 30, "revenue": "$0", "icp_score": 0.05},
]

FIRST_NAMES = ["John", "Jane", "Michael", "Sarah", "David", "Emily", "Robert", "Lisa", "Chris", "Amanda"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]

TITLES = {
    "vp_level": ["VP of Sales", "VP Revenue", "Chief Revenue Officer", "VP of Marketing"],
    "director": ["Director of Sales", "Sales Director", "Director of RevOps", "Director of Marketing"],
    "manager": ["Sales Manager", "Revenue Operations Manager", "Marketing Manager"],
    "ic": ["Sales Representative", "Account Executive", "Marketing Specialist"]
}

def generate_lead(icp_match: str = "on_icp", quality: str = "good") -> Dict[str, Any]:
    """
    Generate a single lead.
    
    Args:
        icp_match: "on_icp", "off_icp", "edge_case"
        quality: "good", "missing_fields", "invalid_format"
    """
    # Select company based on ICP match
    if icp_match == "on_icp":
        company = random.choice([c for c in COMPANIES if c["icp_score"] > 0.7])
    elif icp_match == "off_icp":
        company = random.choice([c for c in COMPANIES if c["icp_score"] < 0.3])
    else:  # edge_case
        company = random.choice(COMPANIES)
    
    first_name = random.choice(FIRST_NAMES)
    last_name = random.choice(LAST_NAMES)
    
    # Title based on ICP match (VPs for on-icp, ICs for off-icp)
    if icp_match == "on_icp":
        title = random.choice(TITLES["vp_level"] + TITLES["director"])
    else:
        title = random.choice(TITLES["manager"] + TITLES["ic"])
    
    # Base lead data
    lead = {
        "first_name": first_name,
        "last_name": last_name,
        "email": f"{first_name.lower()}.{last_name.lower()}@{company['domain']}",
        "company_name": company["name"],
        "company_domain": company["domain"],
        "title": title,
        "industry": company["industry"],
        "employee_count": company["employees"],
        "revenue": company["revenue"],
        "icp_score": company["icp_score"],
        "source": "synthetic",
        "created_at": datetime.utcnow().isoformat()
    }
    
    # Apply quality issues
    if quality == "missing_fields":
        # Randomly remove fields
        fields_to_remove = random.sample(["title", "company_name", "industry"], k=random.randint(1, 2))
        for field in fields_to_remove:
            del lead[field]
    
    elif quality == "invalid_format":
        # Corrupt data
        lead["email"] = lead["email"].replace("@", "[at]")  # Invalid email
        lead["company_domain"] = lead["company_domain"].replace(".", "_")  # Invalid domain
    
    return lead

def generate_dataset(
    count: int = 100,
    icp_on_ratio: float = 0.6,
    quality_good_ratio: float = 0.8
) -> List[Dict[str, Any]]:
    """
    Generate a dataset of leads.
    
    Args:
        count: Total number of leads
        icp_on_ratio: Ratio of on-ICP leads (0-1)
        quality_good_ratio: Ratio of good quality leads (0-1)
    """
    leads = []
    
    for i in range(count):
        # Determine ICP match
        if random.random() < icp_on_ratio:
            icp_match = "on_icp"
        elif random.random() < 0.8:  # 80% of remaining are off-icp
            icp_match = "off_icp"
        else:
            icp_match = "edge_case"
        
        # Determine quality
        if random.random() < quality_good_ratio:
            quality = "good"
        elif random.random() < 0.5:
            quality = "missing_fields"
        else:
            quality = "invalid_format"
        
        lead = generate_lead(icp_match, quality)
        lead["lead_id"] = f"synthetic_{i+1}"
        leads.append(lead)
    
    return leads

def generate_edge_cases() -> List[Dict[str, Any]]:
    """Generate specific edge case scenarios."""
    edge_cases = []
    
    # Duplicate email
    duplicate_lead = generate_lead("on_icp", "good")
    duplicate_lead["lead_id"] = "edge_duplicate_1"
    edge_cases.append(duplicate_lead)
    edge_cases.append(duplicate_lead.copy())  # Exact duplicate
    
    # Unsubscribed
    unsubscribed_lead = generate_lead("on_icp", "good")
    unsubscribed_lead["lead_id"] = "edge_unsubscribed"
    unsubscribed_lead["unsubscribed"] = True
    edge_cases.append(unsubscribed_lead)
    
    # Character encoding issues
    encoding_lead = generate_lead("on_icp", "good")
    encoding_lead["lead_id"] = "edge_encoding"
    encoding_lead["first_name"] = "José"
    encoding_lead["last_name"] = "García"
    encoding_lead["company_name"] = "Compañía Tech 🚀"
    edge_cases.append(encoding_lead)
    
    # Conflicting tags
    conflict_lead = generate_lead("on_icp", "good")
    conflict_lead["lead_id"] = "edge_conflict"
    conflict_lead["tags"] = ["VIP", "Disqualified"]  # Conflicting
    edge_cases.append(conflict_lead)
    
    return edge_cases

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic lead data")
    parser.add_argument('--count', type=int, default=100, help="Number of leads to generate")
    parser.add_argument('--output', type=str, default="tests/fixtures/synthetic_leads.json", help="Output file")
    parser.add_argument('--icp-ratio', type=float, default=0.6, help="Ratio of on-ICP leads (0-1)")
    parser.add_argument('--quality-ratio', type=float, default=0.8, help="Ratio of good quality (0-1)")
    parser.add_argument('--include-edge-cases', action='store_true', help="Include edge cases")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Synthetic Data Generator")
    print("=" * 60)
    
    # Generate main dataset
    leads = generate_dataset(args.count, args.icp_ratio, args.quality_ratio)
    
    # Add edge cases if requested
    if args.include_edge_cases:
        edge_cases = generate_edge_cases()
        leads.extend(edge_cases)
        print(f"Added {len(edge_cases)} edge case scenarios")
    
    # Save to file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(leads, f, indent=2)
    
    # Stats
    on_icp_count = sum(1 for l in leads if l.get('icp_score', 0) > 0.7)
    off_icp_count = sum(1 for l in leads if l.get('icp_score', 0) < 0.3)
    
    print(f"Generated {len(leads)} leads")
    print(f"  - On-ICP: {on_icp_count} ({on_icp_count/len(leads)*100:.1f}%)")
    print(f"  - Off-ICP: {off_icp_count} ({off_icp_count/len(leads)*100:.1f}%)")
    print(f"Saved to: {output_path}")
    print("=" * 60)

if __name__ == '__main__':
    main()
