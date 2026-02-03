#!/usr/bin/env python3
"""
Mock GoHighLevel API Server
============================
Flask-based mock server simulating GHL API for sandbox testing.

Features:
- Contact CRUD operations
- Opportunity management
- Tag management
- Workflow triggers
- Configurable failure injection

Usage:
    python tests/mocks/mock_ghl_server.py
    # Server runs on http://localhost:8001
"""

from flask import Flask, request, jsonify
from datetime import datetime
import random
import time
from typing import Dict, Any, List

app = Flask(__name__)

# In-memory storage
contacts_db: Dict[str, Dict[str, Any]] = {}
opportunities_db: Dict[str, Dict[str, Any]] = {}

# Configuration
FAILURE_INJECTION_RATE = 0.0  # 0-1, probability of injected failure
SIMULATE_LATENCY = True
BASE_LATENCY_MS = 50

def inject_latency():
    """Simulate API latency."""
    if SIMULATE_LATENCY:
        delay = BASE_LATENCY_MS / 1000.0
        jitter = random.uniform(-0.02, 0.02)
        time.sleep(max(0, delay + jitter))

def maybe_inject_failure():
    """Randomly inject failures for chaos testing."""
    if random.random() < FAILURE_INJECTION_RATE:
        failure_type = random.choice(['rate_limit', 'server_error', 'timeout'])
        
        if failure_type == 'rate_limit':
            return jsonify({"error": "Rate limit exceeded"}), 429
        elif failure_type == 'server_error':
            return jsonify({"error": "Internal server error"}), 500
        elif failure_type == 'timeout':
            time.sleep(30)  # Simulate timeout
            return jsonify({"error": "Request timeout"}), 504
    
    return None

# ============================================================================
# CONTACTS API
# ============================================================================

@app.route('/contacts', methods=['GET'])
def list_contacts():
    inject_latency()
    if failure := maybe_inject_failure():
        return failure
    
    # Filter by query params
    email = request.args.get('email')
    tags = request.args.get('tags', '').split(',') if request.args.get('tags') else []
    
    results = []
    for contact in contacts_db.values():
        if email and contact.get('email') != email:
            continue
        if tags and not any(tag in contact.get('tags', []) for tag in tags):
            continue
        results.append(contact)
    
    return jsonify({"contacts": results, "total": len(results)})

@app.route('/contacts/<contact_id>', methods=['GET'])
def get_contact(contact_id):
    inject_latency()
    if failure := maybe_inject_failure():
        return failure
    
    contact = contacts_db.get(contact_id)
    if not contact:
        return jsonify({"error": "Contact not found"}), 404
    
    return jsonify(contact)

@app.route('/contacts', methods=['POST'])
def create_contact():
    inject_latency()
    if failure := maybe_inject_failure():
        return failure
    
    data = request.json
    
    # Validation
    if not data.get('email'):
        return jsonify({"error": "Email required"}), 400
    
    # Check for duplicate
    for contact in contacts_db.values():
        if contact.get('email') == data.get('email'):
            return jsonify({"error": "Contact already exists", "contact_id": contact['id']}), 409
    
    # Create contact
    contact_id = f"ghl_{len(contacts_db) + 1}"
    contact = {
        "id": contact_id,
        "email": data.get('email'),
        "first_name": data.get('first_name', ''),
        "last_name": data.get('last_name', ''),
        "company": data.get('company', ''),
        "tags": data.get('tags', []),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    contacts_db[contact_id] = contact
    return jsonify(contact), 201

@app.route('/contacts/<contact_id>', methods=['PUT'])
def update_contact(contact_id):
    inject_latency()
    if failure := maybe_inject_failure():
        return failure
    
    contact = contacts_db.get(contact_id)
    if not contact:
        return jsonify({"error": "Contact not found"}), 404
    
    data = request.json
    
    # Update fields
    for key in ['email', 'first_name', 'last_name', 'company']:
        if key in data:
            contact[key] = data[key]
    
    if 'tags' in data:
        contact['tags'] = data['tags']
    
    contact['updated_at'] = datetime.utcnow().isoformat()
    
    return jsonify(contact)

@app.route('/contacts/<contact_id>/tags', methods=['POST'])
def add_tags(contact_id):
    inject_latency()
    if failure := maybe_inject_failure():
        return failure
    
    contact = contacts_db.get(contact_id)
    if not contact:
        return jsonify({"error": "Contact not found"}), 404
    
    tags_to_add = request.json.get('tags', [])
    contact['tags'] = list(set(contact.get('tags', []) + tags_to_add))
    contact['updated_at'] = datetime.utcnow().isoformat()
    
    return jsonify(contact)

# ============================================================================
# OPPORTUNITIES API
# ============================================================================

@app.route('/opportunities', methods=['POST'])
def create_opportunity():
    inject_latency()
    if failure := maybe_inject_failure():
        return failure
    
    data = request.json
    
    opp_id = f"opp_{len(opportunities_db) + 1}"
    opportunity = {
        "id": opp_id,
        "contact_id": data.get('contact_id'),
        "name": data.get('name', 'Untitled Opportunity'),
        "status": data.get('status', 'open'),
        "value": data.get('value', 0),
        "created_at": datetime.utcnow().isoformat()
    }
    
    opportunities_db[opp_id] = opportunity
    return jsonify(opportunity), 201

@app.route('/opportunities/<opp_id>', methods=['PUT'])
def update_opportunity(opp_id):
    inject_latency()
    if failure := maybe_inject_failure():
        return failure
    
    opp = opportunities_db.get(opp_id)
    if not opp:
        return jsonify({"error": "Opportunity not found"}), 404
    
    data = request.json
    for key in ['name', 'status', 'value']:
        if key in data:
            opp[key] = data[key]
    
    return jsonify(opp)

# ============================================================================
# WORKFLOWS API
# ============================================================================

@app.route('/workflows/<workflow_id>/trigger', methods=['POST'])
def trigger_workflow(workflow_id):
    inject_latency()
    if failure := maybe_inject_failure():
        return failure
    
    data = request.json
    
    return jsonify({
        "workflow_id": workflow_id,
        "status": "triggered",
        "contact_id": data.get('contact_id'),
        "triggered_at": datetime.utcnow().isoformat()
    })

# ============================================================================
# ADMIN / CONFIG
# ============================================================================

@app.route('/mock/config', methods=['POST'])
def update_config():
    """Update mock server configuration."""
    global FAILURE_INJECTION_RATE, SIMULATE_LATENCY, BASE_LATENCY_MS
    
    data = request.json
    
    if 'failure_rate' in data:
        FAILURE_INJECTION_RATE = float(data['failure_rate'])
    
    if 'simulate_latency' in data:
        SIMULATE_LATENCY = bool(data['simulate_latency'])
    
    if 'latency_ms' in data:
        BASE_LATENCY_MS = int(data['latency_ms'])
    
    return jsonify({
        "failure_rate": FAILURE_INJECTION_RATE,
        "simulate_latency": SIMULATE_LATENCY,
        "latency_ms": BASE_LATENCY_MS
    })

@app.route('/mock/reset', methods=['POST'])
def reset_data():
    """Reset all mock data."""
    global contacts_db, opportunities_db
    contacts_db = {}
    opportunities_db = {}
    return jsonify({"status": "reset"})

@app.route('/mock/stats', methods=['GET'])
def get_stats():
    """Get current state stats."""
    return jsonify({
        "contacts_count": len(contacts_db),
        "opportunities_count": len(opportunities_db),
        "config": {
            "failure_rate": FAILURE_INJECTION_RATE,
            "simulate_latency": SIMULATE_LATENCY,
            "latency_ms": BASE_LATENCY_MS
        }
    })

# ============================================================================
# SERVER
# ============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("Mock GoHighLevel API Server")
    print("=" * 60)
    print("Running on: http://localhost:8001")
    print("Admin endpoints:")
    print("  POST /mock/config - Update config")
    print("  POST /mock/reset - Reset data")
    print("  GET /mock/stats - View stats")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=8001, debug=False)
