#!/usr/bin/env python3
"""
Mock RB2B API Server
====================
Simulates RB2B visitor identification API for sandbox testing.

Features:
- Visitor identification
- Company data enrichment
- Confidence scoring
- Edge case simulation (PII, low confidence)

Usage:
    python tests/mocks/mock_rb2b_server.py
    # Server runs on http://localhost:8002
"""

from flask import Flask, request, jsonify
from datetime import datetime
import random
import time

app = Flask(__name__)

# Mock company database
MOCK_COMPANIES = [
    {"domain": "acme.com", "name": "Acme Corporation", "industry": "Technology", "employee_count": 250, "confidence": 0.95},
    {"domain": "techstartup.io", "name": "TechStartup Inc", "industry": "SaaS", "employee_count": 45, "confidence": 0.88},
    {"domain": "enterprise.com", "name": "Enterprise Solutions", "industry": "Consulting", "employee_count": 1200, "confidence": 0.92},
    {"domain": "unknown.xyz", "name": "Unknown Visitor", "industry": "Unknown", "employee_count": 0, "confidence": 0.25},
]

@app.route('/identify', methods=['POST'])
def identify_visitor():
    """Identify visitor from IP address or session data."""
    time.sleep(0.05)  # Simulate latency
    
    data = request.json
    ip_address = data.get('ip_address', '')
    session_id = data.get('session_id', '')
    
    # Simulate identification
    # 80% chance of successful identification
    if random.random() < 0.8:
        company = random.choice(MOCK_COMPANIES[:-1])  # Exclude "unknown"
    else:
        company = MOCK_COMPANIES[-1]  # Return low-confidence result
    
    return jsonify({
        "visitor_id": f"vis_{random.randint(1000, 9999)}",
        "ip_address": ip_address,
        "identified": company['confidence'] > 0.5,
        "confidence": company['confidence'],
        "company": {
            "domain": company['domain'],
            "name": company['name'],
            "industry": company['industry'],
            "employee_count": company['employee_count']
        },
        "timestamp": datetime.utcnow().isoformat()
    })

@app.route('/enrich/<domain>', methods=['GET'])
def enrich_company(domain):
    """Enrich company data by domain."""
    time.sleep(0.08)
    
    # Find company in mock database
    company = next((c for c in MOCK_COMPANIES if c['domain'] == domain), None)
    
    if not company:
        return jsonify({"error": "Company not found"}), 404
    
    return jsonify({
        "domain": domain,
        "name": company['name'],
        "industry": company['industry'],
        "employee_count": company['employee_count'],
        "revenue_estimate": f"${company['employee_count'] * 150000:,}",
        "tech_stack": ["Salesforce", "HubSpot", "Slack"],
        "confidence": company['confidence']
    })

@app.route('/mock/stats', methods=['GET'])
def get_stats():
    """Get mock server stats."""
    return jsonify({
        "companies_in_db": len(MOCK_COMPANIES),
        "avg_confidence": sum(c['confidence'] for c in MOCK_COMPANIES) / len(MOCK_COMPANIES)
    })

if __name__ == '__main__':
    print("=" * 60)
    print("Mock RB2B API Server")
    print("=" * 60)
    print("Running on: http://localhost:8002")
    print("Endpoints:")
    print("  POST /identify - Identify visitor")
    print("  GET /enrich/<domain> - Enrich company")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=8002, debug=False)
