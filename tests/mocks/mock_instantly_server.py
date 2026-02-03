#!/usr/bin/env python3
"""
Mock Instantly API Server
==========================
Simulates Instantly email campaign API for sandbox testing.

Features:
- Campaign creation/management
- Lead upload
- Email sending simulation
- Bounce/spam/unsubscribe handling

Usage:
    python tests/mocks/mock_instantly_server.py
    # Server runs on http://localhost:8003
"""

from flask import Flask, request, jsonify
from datetime import datetime
import random
import time

app = Flask(__name__)

campaigns_db = {}
leads_db = {}

@app.route('/campaigns', methods=['POST'])
def create_campaign():
    """Create new email campaign."""
    time.sleep(0.06)
    
    data = request.json
    
    campaign_id = f"camp_{len(campaigns_db) + 1}"
    campaign = {
        "id": campaign_id,
        "name": data.get('name', 'Untitled Campaign'),
        "subject": data.get('subject', ''),
        "body": data.get('body', ''),
        "status": "draft",
        "leads_count": 0,
        "sent_count": 0,
        "opened_count": 0,
        "replied_count": 0,
        "bounced_count": 0,
        "created_at": datetime.utcnow().isoformat()
    }
    
    campaigns_db[campaign_id] = campaign
    return jsonify(campaign), 201

@app.route('/campaigns/<campaign_id>/leads', methods=['POST'])
def add_leads(campaign_id):
    """Add leads to campaign."""
    time.sleep(0.04)
    
    campaign = campaigns_db.get(campaign_id)
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404
    
    leads = request.json.get('leads', [])
    
    for lead_data in leads:
        lead_id = f"lead_{len(leads_db) + 1}"
        lead = {
            "id": lead_id,
            "campaign_id": campaign_id,
            "email": lead_data.get('email'),
            "first_name": lead_data.get('first_name', ''),
            "last_name": lead_data.get('last_name', ''),
            "company": lead_data.get('company', ''),
            "status": "pending",
            "added_at": datetime.utcnow().isoformat()
        }
        leads_db[lead_id] = lead
    
    campaign['leads_count'] += len(leads)
    
    return jsonify({"added": len(leads), "campaign": campaign})

@app.route('/campaigns/<campaign_id>/send', methods=['POST'])
def send_campaign(campaign_id):
    """Send campaign (simulated)."""
    time.sleep(0.1)
    
    campaign = campaigns_db.get(campaign_id)
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404
    
    # Simulate sending
    campaign['status'] = "sending"
    
    # Simulate outcomes (in sandbox, just set stats)
    total_leads = campaign['leads_count']
    campaign['sent_count'] = total_leads
    campaign['opened_count'] = int(total_leads * 0.35)  # 35% open rate
    campaign['replied_count'] = int(total_leads * 0.05)  # 5% reply rate
    campaign['bounced_count'] = int(total_leads * 0.02)  # 2% bounce rate
    
    campaign['status'] = "sent"
    
    return jsonify(campaign)

@app.route('/campaigns/<campaign_id>', methods=['GET'])
def get_campaign(campaign_id):
    """Get campaign status."""
    campaign = campaigns_db.get(campaign_id)
    if not campaign:
        return jsonify({"error": "Campaign not found"}), 404
    
    return jsonify(campaign)

@app.route('/unsubscribe', methods=['POST'])
def handle_unsubscribe():
    """Handle unsubscribe request."""
    data = request.json
    email = data.get('email')
    
    # Find and mark lead as unsubscribed
    for lead in leads_db.values():
        if lead['email'] == email:
            lead['status'] = 'unsubscribed'
    
    return jsonify({"status": "unsubscribed", "email": email})

@app.route('/mock/stats', methods=['GET'])
def get_stats():
    """Get mock server stats."""
    return jsonify({
        "campaigns_count": len(campaigns_db),
        "leads_count": len(leads_db)
    })

@app.route('/mock/reset', methods=['POST'])
def reset_data():
    """Reset all data."""
    global campaigns_db, leads_db
    campaigns_db = {}
    leads_db = {}
    return jsonify({"status": "reset"})

if __name__ == '__main__':
    print("=" * 60)
    print("Mock Instantly API Server")
    print("=" * 60)
    print("Running on: http://localhost:8003")
    print("Endpoints:")
    print("  POST /campaigns - Create campaign")
    print("  POST /campaigns/<id>/leads - Add leads")
    print("  POST /campaigns/<id>/send - Send campaign")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=8003, debug=False)
