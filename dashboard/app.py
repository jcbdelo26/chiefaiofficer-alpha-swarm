"""
GATEKEEPER Dashboard - AE Review Interface
Flask-based web dashboard for campaign approval workflow.
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path
from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_cors import CORS

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent
HIVE_MIND = PROJECT_ROOT / ".hive-mind"
CAMPAIGNS_DIR = HIVE_MIND / "campaigns"
SEGMENTED_DIR = HIVE_MIND / "segmented"

# Load environment
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

app = Flask(__name__, 
    template_folder='templates',
    static_folder='static'
)
app.secret_key = os.getenv("DASHBOARD_SECRET_KEY", "alpha-swarm-gatekeeper-secret-change-me")
CORS(app)


# ============================================================================
# Data Access Functions
# ============================================================================

def get_pending_campaigns():
    """Get all campaigns pending review."""
    campaigns = []
    
    if not CAMPAIGNS_DIR.exists():
        return campaigns
    
    for f in CAMPAIGNS_DIR.glob("*.json"):
        if f.name.startswith("_"):
            continue
        try:
            with open(f) as fh:
                data = json.load(fh)
                if data.get("status") == "pending":
                    data["file_path"] = str(f)
                    campaigns.append(data)
        except:
            pass
    
    # Sort by priority (tier1 first)
    priority_order = {"tier1_vip": 0, "tier2_high": 1, "tier3_standard": 2, "tier4_nurture": 3}
    campaigns.sort(key=lambda x: priority_order.get(x.get("segment", ""), 99))
    
    return campaigns


def get_campaign_by_id(campaign_id: str):
    """Get a specific campaign by ID."""
    campaign_file = CAMPAIGNS_DIR / f"{campaign_id}.json"
    
    if not campaign_file.exists():
        return None
    
    try:
        with open(campaign_file) as f:
            data = json.load(f)
            data["file_path"] = str(campaign_file)
            return data
    except:
        return None


def update_campaign_status(campaign_id: str, status: str, reviewer: str = "AE", notes: str = ""):
    """Update campaign status."""
    campaign_file = CAMPAIGNS_DIR / f"{campaign_id}.json"
    
    if not campaign_file.exists():
        return False
    
    try:
        with open(campaign_file) as f:
            data = json.load(f)
        
        data["status"] = status
        data["reviewed_by"] = reviewer
        data["reviewed_at"] = datetime.now().isoformat()
        data["review_notes"] = notes
        
        with open(campaign_file, "w") as f:
            json.dump(data, f, indent=2)
        
        # Log the action
        log_review_action(campaign_id, status, reviewer, notes)
        
        return True
    except Exception as e:
        print(f"Error updating campaign: {e}")
        return False


def log_review_action(campaign_id: str, action: str, reviewer: str, notes: str):
    """Log review actions for the learning system."""
    log_file = HIVE_MIND / "review_log.json"
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "campaign_id": campaign_id,
        "action": action,
        "reviewer": reviewer,
        "notes": notes
    }
    
    try:
        if log_file.exists():
            with open(log_file) as f:
                log_data = json.load(f)
        else:
            log_data = {"reviews": []}
        
        log_data["reviews"].append(log_entry)
        
        with open(log_file, "w") as f:
            json.dump(log_data, f, indent=2)
    except:
        pass


def get_dashboard_stats():
    """Get dashboard statistics."""
    stats = {
        "pending": 0,
        "approved_today": 0,
        "rejected_today": 0,
        "total_leads": 0,
        "by_segment": {}
    }
    
    if not CAMPAIGNS_DIR.exists():
        return stats
    
    today = datetime.now().date()
    
    for f in CAMPAIGNS_DIR.glob("*.json"):
        if f.name.startswith("_"):
            continue
        try:
            with open(f) as fh:
                data = json.load(fh)
                
                status = data.get("status", "")
                segment = data.get("segment", "unknown")
                leads = data.get("lead_count", len(data.get("leads", [])))
                
                if status == "pending":
                    stats["pending"] += 1
                    stats["total_leads"] += leads
                    stats["by_segment"][segment] = stats["by_segment"].get(segment, 0) + 1
                
                elif data.get("reviewed_at"):
                    reviewed_date = datetime.fromisoformat(data["reviewed_at"]).date()
                    if reviewed_date == today:
                        if status == "approved":
                            stats["approved_today"] += 1
                        elif status == "rejected":
                            stats["rejected_today"] += 1
        except:
            pass
    
    return stats


def get_rejection_patterns():
    """Analyze rejection patterns for self-annealing."""
    log_file = HIVE_MIND / "review_log.json"
    
    if not log_file.exists():
        return {"patterns": [], "total_rejections": 0}
    
    try:
        with open(log_file) as f:
            log_data = json.load(f)
        
        rejections = [r for r in log_data.get("reviews", []) if r.get("action") == "rejected"]
        
        # Count by reason
        reasons = {}
        for r in rejections:
            notes = r.get("notes", "No reason given")
            reasons[notes] = reasons.get(notes, 0) + 1
        
        patterns = [{"reason": k, "count": v} for k, v in sorted(reasons.items(), key=lambda x: -x[1])]
        
        return {
            "patterns": patterns[:10],
            "total_rejections": len(rejections)
        }
    except:
        return {"patterns": [], "total_rejections": 0}


# ============================================================================
# Routes
# ============================================================================

@app.route("/")
def index():
    """Dashboard home page."""
    stats = get_dashboard_stats()
    pending = get_pending_campaigns()
    
    return render_template("index.html", 
        stats=stats,
        pending_campaigns=pending[:10],  # Show first 10
        total_pending=len(pending)
    )


@app.route("/campaigns")
def campaigns_list():
    """List all pending campaigns."""
    pending = get_pending_campaigns()
    return render_template("campaigns.html", campaigns=pending)


@app.route("/campaign/<campaign_id>")
def campaign_detail(campaign_id):
    """View campaign details."""
    campaign = get_campaign_by_id(campaign_id)
    
    if not campaign:
        flash("Campaign not found", "error")
        return redirect(url_for("campaigns_list"))
    
    return render_template("campaign_detail.html", campaign=campaign)


@app.route("/api/campaign/<campaign_id>/approve", methods=["POST"])
def api_approve_campaign(campaign_id):
    """API endpoint to approve a campaign."""
    data = request.json or {}
    reviewer = data.get("reviewer", "AE")
    notes = data.get("notes", "")
    
    success = update_campaign_status(campaign_id, "approved", reviewer, notes)
    
    if success:
        return jsonify({"success": True, "message": "Campaign approved"})
    else:
        return jsonify({"success": False, "message": "Failed to approve"}), 400


@app.route("/api/campaign/<campaign_id>/reject", methods=["POST"])
def api_reject_campaign(campaign_id):
    """API endpoint to reject a campaign."""
    data = request.json or {}
    reviewer = data.get("reviewer", "AE")
    notes = data.get("notes", "")
    
    if not notes:
        return jsonify({"success": False, "message": "Rejection reason required"}), 400
    
    success = update_campaign_status(campaign_id, "rejected", reviewer, notes)
    
    if success:
        return jsonify({"success": True, "message": "Campaign rejected"})
    else:
        return jsonify({"success": False, "message": "Failed to reject"}), 400


@app.route("/api/campaign/<campaign_id>/edit", methods=["POST"])
def api_edit_campaign(campaign_id):
    """API endpoint to edit campaign content."""
    data = request.json or {}
    
    campaign_file = CAMPAIGNS_DIR / f"{campaign_id}.json"
    
    if not campaign_file.exists():
        return jsonify({"success": False, "message": "Campaign not found"}), 404
    
    try:
        with open(campaign_file) as f:
            campaign = json.load(f)
        
        # Update editable fields
        if "emails" in data:
            campaign["emails"] = data["emails"]
        if "subject" in data:
            campaign["subject"] = data["subject"]
        
        campaign["last_edited"] = datetime.now().isoformat()
        campaign["edited_by"] = data.get("editor", "AE")
        
        with open(campaign_file, "w") as f:
            json.dump(campaign, f, indent=2)
        
        return jsonify({"success": True, "message": "Campaign updated"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@app.route("/api/batch/approve", methods=["POST"])
def api_batch_approve():
    """Batch approve multiple campaigns."""
    data = request.json or {}
    campaign_ids = data.get("campaign_ids", [])
    reviewer = data.get("reviewer", "AE")
    
    approved = 0
    for cid in campaign_ids:
        if update_campaign_status(cid, "approved", reviewer):
            approved += 1
    
    return jsonify({
        "success": True,
        "approved": approved,
        "total": len(campaign_ids)
    })


@app.route("/api/batch/reject", methods=["POST"])
def api_batch_reject():
    """Batch reject multiple campaigns."""
    data = request.json or {}
    campaign_ids = data.get("campaign_ids", [])
    reviewer = data.get("reviewer", "AE")
    notes = data.get("notes", "Batch rejection")
    
    rejected = 0
    for cid in campaign_ids:
        if update_campaign_status(cid, "rejected", reviewer, notes):
            rejected += 1
    
    return jsonify({
        "success": True,
        "rejected": rejected,
        "total": len(campaign_ids)
    })


@app.route("/api/stats")
def api_stats():
    """API endpoint for dashboard stats."""
    return jsonify(get_dashboard_stats())


@app.route("/api/rejection-patterns")
def api_rejection_patterns():
    """API endpoint for rejection analysis."""
    return jsonify(get_rejection_patterns())


@app.route("/analytics")
def analytics():
    """Analytics page with rejection patterns."""
    patterns = get_rejection_patterns()
    stats = get_dashboard_stats()
    
    return render_template("analytics.html", 
        patterns=patterns,
        stats=stats
    )


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "campaigns_pending": get_dashboard_stats()["pending"]
    })


# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", error="Page not found"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", error="Server error"), 500


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    # Create sample campaign for testing
    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    
    sample_campaign = {
        "id": "sample_001",
        "name": "Gong Competitor Displacement - Jan 2026",
        "segment": "tier1_vip",
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "lead_count": 25,
        "leads": [
            {
                "id": "lead_1",
                "name": "John Smith",
                "title": "VP of Sales",
                "company": "TechCorp Inc",
                "icp_score": 92
            },
            {
                "id": "lead_2",
                "name": "Sarah Johnson",
                "title": "Director of RevOps",
                "company": "SaaS Solutions",
                "icp_score": 88
            }
        ],
        "emails": [
            {
                "step": 1,
                "subject": "Quick question about your Gong setup, {{first_name}}",
                "body": "Hi {{first_name}},\n\nI noticed you're following Gong on LinkedIn..."
            },
            {
                "step": 2,
                "subject": "Re: Quick question",
                "body": "Following up on my previous note..."
            }
        ]
    }
    
    sample_file = CAMPAIGNS_DIR / "sample_001.json"
    if not sample_file.exists():
        with open(sample_file, "w") as f:
            json.dump(sample_campaign, f, indent=2)
    
    print("\n" + "="*60)
    print("  🚪 GATEKEEPER Dashboard Starting")
    print("="*60)
    print(f"  URL: http://localhost:5000")
    print(f"  Project: {PROJECT_ROOT}")
    print("="*60 + "\n")
    
    app.run(host="0.0.0.0", port=5000, debug=True)
