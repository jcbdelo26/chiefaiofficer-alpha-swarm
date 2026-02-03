#!/usr/bin/env python3
"""
Mock Clay Waterfall Server
===========================
Simulates Clay enrichment waterfall for sandbox testing.

Features:
- Company lookup (multiple providers)
- Contact enrichment
- Waterfall logic simulation
- Confidence scoring

Usage:
    python tests/mocks/mock_clay_waterfall.py
    # Server runs on http://localhost:8004
"""

from flask import Flask, request, jsonify
from datetime import datetime
import random
import time

app = Flask(__name__)

# Mock enrichment providers
PROVIDERS = {
    "clearbit": {"latency": 0.05, "success_rate": 0.85, "cost": 0.02},
    "hunter": {"latency": 0.08, "success_rate": 0.75, "cost": 0.01},
    "apollo": {"latency": 0.06, "success": 0.9, "cost": 0.015},
}

@app.route('/enrich/company', methods=['POST'])
def enrich_company():
    """Enrich company data using waterfall logic."""
    data = request.json
    domain = data.get('domain', '')
    
    # Simulate waterfall: try providers in order until success
    for provider_name, config in PROVIDERS.items():
        time.sleep(config['latency'])
        
        # Simulate success/failure based on success rate
        if random.random() < config.get('success_rate', config.get('success', 0.8)):
            # Success! Return enriched data
            return jsonify({
                "domain": domain,
                "company_name": f"{domain.split('.')[0].title()} Inc",
                "industry": random.choice(["Technology", "SaaS", "Consulting", "Finance"]),
                "employee_count": random.randint(20, 500),
                "revenue_estimate": f"${random.randint(1, 50)}M",
                "founded_year": random.randint(2010, 2023),
                "tech_stack": ["Salesforce", "HubSpot", "Slack"],
                "provider": provider_name,
                "cost": config['cost'],
                "confidence": 0.8 + (random.random() * 0.15)
            })
    
    # All providers failed
    return jsonify({"error": "Enrichment failed - all providers exhausted"}), 404

@app.route('/enrich/contact', methods=['POST'])
def enrich_contact():
    """Enrich contact data."""
    data = request.json
    email = data.get('email', '')
    
    time.sleep(0.07)
    
    # 85% success rate
    if random.random() < 0.85:
        return jsonify({
            "email": email,
            "first_name": "John",
            "last_name": "Doe",
            "title": random.choice(["VP Sales", "CRO", "Director of Revenue"]),
            "linkedin_url": f"https://linkedin.com/in/{email.split('@')[0]}",
            "phone": f"+1-555-{random.randint(100, 999)}-{random.randint(1000, 9999)}",
            "seniority": random.choice(["VP", "Director", "Manager"]),
            "department": "Sales",
            "confidence": 0.75 + (random.random() * 0.2)
        })
    else:
        return jsonify({"error": "Contact not found"}), 404

@app.route('/waterfall/stats', methods=['GET'])
def get_waterfall_stats():
    """Get waterfall performance stats."""
    return jsonify({
        "providers": PROVIDERS,
        "total_requests": 0,  # Would track in production
        "avg_cost_per_enrichment": sum(p['cost'] for p in PROVIDERS.values()) / len(PROVIDERS)
    })

if __name__ == '__main__':
    print("=" * 60)
    print("Mock Clay Waterfall API Server")
    print("=" * 60)
    print("Running on: http://localhost:8004")
    print("Endpoints:")
    print("  POST /enrich/company - Enrich company")
    print("  POST /enrich/contact - Enrich contact")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=8004, debug=False)
