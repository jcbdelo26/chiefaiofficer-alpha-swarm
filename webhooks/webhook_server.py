#!/usr/bin/env python3
"""
Webhook Server for Alpha Swarm
==============================

A lightweight Flask-based webhook receiver for Instantly and GoHighLevel callbacks.

Features:
- Signature verification for security
- Event queuing for async processing
- Health check and statistics endpoints
- Integration with FeedbackCollector for RL training

SETUP INSTRUCTIONS
==================

1. INSTANTLY WEBHOOKS:
   - Log into Instantly (https://app.instantly.ai)
   - Go to Settings > Integrations > Webhooks
   - Add webhook URL: https://your-domain.com/webhooks/instantly
   - Select events: email_opened, email_clicked, email_replied, email_bounced, email_unsubscribed
   - Copy the webhook secret and set INSTANTLY_WEBHOOK_SECRET env var

2. GOHIGHLEVEL WEBHOOKS:
   - Log into GoHighLevel (https://app.gohighlevel.com)
   - Go to Settings > Integrations > Webhooks
   - Add webhook URL: https://your-domain.com/webhooks/ghl
   - Select triggers: Contact Create, Contact Update, Appointment, etc.
   - Note: GHL uses API key or custom header for verification
   - Set GHL_WEBHOOK_SECRET env var if using custom verification

3. NGROK FOR LOCAL TESTING:
   - Install ngrok: https://ngrok.com/download
   - Start webhook server: python webhook_server.py
   - In another terminal: ngrok http 5000
   - Copy the https URL (e.g., https://abc123.ngrok.io)
   - Use https://abc123.ngrok.io/webhooks/instantly for Instantly
   - Use https://abc123.ngrok.io/webhooks/ghl for GHL

Environment Variables:
- WEBHOOK_PORT: Port to run server (default: 5000)
- WEBHOOK_SECRET: General webhook secret
- INSTANTLY_WEBHOOK_SECRET: Instantly-specific secret
- GHL_WEBHOOK_SECRET: GoHighLevel-specific secret

Usage:
    python webhook_server.py
    python webhook_server.py --port 8080
"""

import os
import sys
import json
import hmac
import hashlib
import logging
import threading
import time
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from typing import Dict, Any, Optional, List
from enum import Enum

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("webhook_server")


# ============================================================================
# Configuration
# ============================================================================

WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "5000"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
INSTANTLY_WEBHOOK_SECRET = os.getenv("INSTANTLY_WEBHOOK_SECRET", "")
GHL_WEBHOOK_SECRET = os.getenv("GHL_WEBHOOK_SECRET", "")

PROJECT_ROOT = Path(__file__).parent.parent
HIVE_MIND_DIR = PROJECT_ROOT / ".hive-mind"
QUEUE_FILE = HIVE_MIND_DIR / "webhook_queue.json"


# ============================================================================
# Data Models
# ============================================================================

class WebhookSource(Enum):
    INSTANTLY = "instantly"
    GHL = "gohighlevel"
    UNKNOWN = "unknown"


@dataclass
class WebhookEvent:
    """Represents a received webhook event."""
    source: str
    event_type: str
    payload: Dict[str, Any]
    received_at: str
    processed: bool = False
    processed_at: Optional[str] = None
    event_id: Optional[str] = None
    signature_valid: bool = True
    error: Optional[str] = None
    
    def __post_init__(self):
        if not self.event_id:
            self.event_id = f"{self.source}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WebhookEvent":
        return cls(**data)


# ============================================================================
# Event Queue Manager
# ============================================================================

class EventQueue:
    """
    Thread-safe event queue persisted to JSON file.
    
    Events are saved to .hive-mind/webhook_queue.json for processing
    by the FeedbackCollector.
    """
    
    def __init__(self, queue_file: Optional[Path] = None):
        self.queue_file = queue_file or QUEUE_FILE
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._events: List[WebhookEvent] = []
        self._load()
        
        # Statistics
        self.stats = {
            "total_received": 0,
            "instantly_events": 0,
            "ghl_events": 0,
            "processed": 0,
            "errors": 0,
            "started_at": datetime.now(timezone.utc).isoformat()
        }
    
    def _load(self):
        """Load queue from disk."""
        if self.queue_file.exists():
            try:
                with open(self.queue_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._events = [WebhookEvent.from_dict(e) for e in data.get("events", [])]
                    logger.info(f"Loaded {len(self._events)} events from queue")
            except Exception as e:
                logger.error(f"Failed to load queue: {e}")
                self._events = []
    
    def _save(self):
        """Save queue to disk."""
        try:
            with open(self.queue_file, "w", encoding="utf-8") as f:
                json.dump({
                    "events": [e.to_dict() for e in self._events],
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save queue: {e}")
    
    def add(self, event: WebhookEvent):
        """Add event to queue."""
        with self._lock:
            self._events.append(event)
            self.stats["total_received"] += 1
            
            if event.source == WebhookSource.INSTANTLY.value:
                self.stats["instantly_events"] += 1
            elif event.source == WebhookSource.GHL.value:
                self.stats["ghl_events"] += 1
            
            if event.error:
                self.stats["errors"] += 1
            
            self._save()
            logger.info(f"Queued event: {event.event_id} ({event.source}/{event.event_type})")
    
    def get_unprocessed(self) -> List[WebhookEvent]:
        """Get all unprocessed events."""
        with self._lock:
            return [e for e in self._events if not e.processed]
    
    def mark_processed(self, event_id: str, error: Optional[str] = None):
        """Mark an event as processed."""
        with self._lock:
            for event in self._events:
                if event.event_id == event_id:
                    event.processed = True
                    event.processed_at = datetime.now(timezone.utc).isoformat()
                    event.error = error
                    self.stats["processed"] += 1
                    if error:
                        self.stats["errors"] += 1
                    break
            self._save()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        with self._lock:
            return {
                **self.stats,
                "pending": len([e for e in self._events if not e.processed]),
                "queue_size": len(self._events)
            }
    
    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent events for display."""
        with self._lock:
            recent = self._events[-limit:]
            return [
                {
                    "event_id": e.event_id,
                    "source": e.source,
                    "event_type": e.event_type,
                    "received_at": e.received_at,
                    "processed": e.processed,
                    "error": e.error
                }
                for e in reversed(recent)
            ]


# ============================================================================
# Signature Verification
# ============================================================================

def verify_instantly_signature(request_data: bytes, signature: str) -> bool:
    """
    Verify Instantly webhook signature.
    
    Instantly uses HMAC-SHA256 with the webhook secret.
    The signature is typically in the X-Instantly-Signature header.
    
    Args:
        request_data: Raw request body bytes
        signature: Signature from request header
        
    Returns:
        True if signature is valid or no secret configured
    """
    if not INSTANTLY_WEBHOOK_SECRET:
        logger.warning("INSTANTLY_WEBHOOK_SECRET not set - skipping verification")
        return True
    
    if not signature:
        logger.warning("No signature provided in Instantly webhook")
        return False
    
    try:
        expected = hmac.new(
            INSTANTLY_WEBHOOK_SECRET.encode("utf-8"),
            request_data,
            hashlib.sha256
        ).hexdigest()
        
        # Handle both raw and prefixed signatures
        sig_to_check = signature.replace("sha256=", "")
        
        return hmac.compare_digest(expected, sig_to_check)
    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False


def verify_ghl_signature(request_data: bytes, signature: str) -> bool:
    """
    Verify GoHighLevel webhook signature.
    
    GHL may use different verification methods:
    - Custom header with shared secret
    - HMAC signature
    - API key in query params
    
    Args:
        request_data: Raw request body bytes
        signature: Signature from request header
        
    Returns:
        True if signature is valid or no secret configured
    """
    if not GHL_WEBHOOK_SECRET:
        logger.warning("GHL_WEBHOOK_SECRET not set - skipping verification")
        return True
    
    if not signature:
        logger.warning("No signature provided in GHL webhook")
        return False
    
    try:
        expected = hmac.new(
            GHL_WEBHOOK_SECRET.encode("utf-8"),
            request_data,
            hashlib.sha256
        ).hexdigest()
        
        sig_to_check = signature.replace("sha256=", "")
        
        return hmac.compare_digest(expected, sig_to_check)
    except Exception as e:
        logger.error(f"GHL signature verification error: {e}")
        return False


# ============================================================================
# Queue Processor (Background Thread)
# ============================================================================

def process_queue(event_queue: EventQueue, interval: int = 30):
    """
    Background processor for queued webhook events.
    
    Runs in a separate thread and processes events using FeedbackCollector.
    
    Args:
        event_queue: The event queue to process
        interval: Seconds between processing cycles
    """
    logger.info(f"Starting queue processor (interval: {interval}s)")
    
    # Import FeedbackCollector here to avoid circular imports
    try:
        from core.feedback_collector import FeedbackCollector
        collector = FeedbackCollector()
        logger.info("FeedbackCollector initialized")
    except ImportError as e:
        logger.error(f"Failed to import FeedbackCollector: {e}")
        collector = None
    
    while True:
        try:
            unprocessed = event_queue.get_unprocessed()
            
            if unprocessed:
                logger.info(f"Processing {len(unprocessed)} queued events")
            
            for event in unprocessed:
                try:
                    if collector:
                        # Route to appropriate processor
                        if event.source == WebhookSource.INSTANTLY.value:
                            collector.process_instantly_webhook(event.payload)
                        elif event.source == WebhookSource.GHL.value:
                            collector.process_ghl_webhook(event.payload)
                    
                    event_queue.mark_processed(event.event_id)
                    logger.info(f"Processed event: {event.event_id}")
                    
                except Exception as e:
                    logger.error(f"Error processing event {event.event_id}: {e}")
                    event_queue.mark_processed(event.event_id, error=str(e))
            
        except Exception as e:
            logger.error(f"Queue processor error: {e}")
        
        time.sleep(interval)


# ============================================================================
# Flask Application
# ============================================================================

def create_app(event_queue: Optional[EventQueue] = None) -> "Flask":
    """
    Create and configure the Flask webhook server.
    
    Args:
        event_queue: Optional event queue (creates new if not provided)
        
    Returns:
        Configured Flask application
    """
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        logger.error("Flask not installed. Run: pip install flask")
        raise ImportError("Flask is required: pip install flask")
    
    app = Flask(__name__)
    queue = event_queue or EventQueue()
    
    # ========================================================================
    # Health Check Endpoint
    # ========================================================================
    
    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint."""
        return jsonify({
            "status": "healthy",
            "service": "webhook-server",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "1.0.0"
        })
    
    # ========================================================================
    # Statistics Endpoint
    # ========================================================================
    
    @app.route("/stats", methods=["GET"])
    def stats():
        """Webhook statistics endpoint."""
        queue_stats = queue.get_stats()
        recent = queue.get_recent(limit=10)
        
        return jsonify({
            "statistics": queue_stats,
            "recent_events": recent
        })
    
    # ========================================================================
    # Instantly Webhook Endpoint
    # ========================================================================
    
    @app.route("/webhooks/instantly", methods=["POST"])
    def instantly_webhook():
        """
        Receive Instantly webhook events.
        
        Events: email_opened, email_clicked, email_replied, email_bounced, email_unsubscribed
        
        Headers:
        - X-Instantly-Signature: HMAC signature for verification
        """
        signature = request.headers.get("X-Instantly-Signature", "")
        raw_data = request.get_data()
        
        # Verify signature
        signature_valid = verify_instantly_signature(raw_data, signature)
        
        if not signature_valid and INSTANTLY_WEBHOOK_SECRET:
            logger.warning("Invalid Instantly webhook signature")
            return jsonify({"error": "Invalid signature"}), 401
        
        try:
            payload = request.get_json(force=True) or {}
        except Exception as e:
            logger.error(f"Failed to parse Instantly payload: {e}")
            return jsonify({"error": "Invalid JSON"}), 400
        
        # Extract event type
        event_type = payload.get("event_type", payload.get("event", "unknown"))
        
        # Create and queue event
        event = WebhookEvent(
            source=WebhookSource.INSTANTLY.value,
            event_type=event_type,
            payload=payload,
            received_at=datetime.now(timezone.utc).isoformat(),
            signature_valid=signature_valid
        )
        
        queue.add(event)
        
        logger.info(f"Instantly webhook received: {event_type}")
        
        return jsonify({
            "status": "received",
            "event_id": event.event_id,
            "event_type": event_type
        })
    
    # ========================================================================
    # GoHighLevel Webhook Endpoint
    # ========================================================================
    
    @app.route("/webhooks/ghl", methods=["POST"])
    def ghl_webhook():
        """
        Receive GoHighLevel webhook events.
        
        Events: ContactCreate, ContactUpdate, AppointmentCreate, OpportunityStageUpdate, etc.
        
        Headers:
        - X-GHL-Signature: HMAC signature for verification (if configured)
        """
        signature = request.headers.get("X-GHL-Signature", "")
        raw_data = request.get_data()
        
        # Verify signature
        signature_valid = verify_ghl_signature(raw_data, signature)
        
        if not signature_valid and GHL_WEBHOOK_SECRET:
            logger.warning("Invalid GHL webhook signature")
            return jsonify({"error": "Invalid signature"}), 401
        
        try:
            payload = request.get_json(force=True) or {}
        except Exception as e:
            logger.error(f"Failed to parse GHL payload: {e}")
            return jsonify({"error": "Invalid JSON"}), 400
        
        # Extract event type (GHL uses 'type' field)
        event_type = payload.get("type", payload.get("event", "unknown"))
        
        # Create and queue event
        event = WebhookEvent(
            source=WebhookSource.GHL.value,
            event_type=event_type,
            payload=payload,
            received_at=datetime.now(timezone.utc).isoformat(),
            signature_valid=signature_valid
        )
        
        queue.add(event)
        
        logger.info(f"GHL webhook received: {event_type}")
        
        # Real-time hot lead detection
        hot_lead_alert = None
        try:
            from core.hot_lead_detector import HotLeadDetector
            import asyncio
            
            detector = HotLeadDetector()
            # Run async detection in sync context
            loop = asyncio.new_event_loop()
            hot_lead_alert = loop.run_until_complete(detector.process_webhook_event(payload))
            loop.close()
            
            if hot_lead_alert:
                logger.info(f"🔥 HOT LEAD DETECTED: {hot_lead_alert.contact_name} - {hot_lead_alert.temperature}")
        except Exception as e:
            logger.warning(f"Hot lead detection skipped: {e}")
        
        return jsonify({
            "status": "received",
            "event_id": event.event_id,
            "event_type": event_type,
            "hot_lead_detected": hot_lead_alert is not None,
            "alert_id": hot_lead_alert.alert_id if hot_lead_alert else None,
        })
    
    # ========================================================================
    # Queue Management Endpoints
    # ========================================================================
    
    @app.route("/queue/pending", methods=["GET"])
    def pending_events():
        """Get pending (unprocessed) events."""
        unprocessed = queue.get_unprocessed()
        return jsonify({
            "count": len(unprocessed),
            "events": [e.to_dict() for e in unprocessed[:50]]
        })
    
    @app.route("/queue/recent", methods=["GET"])
    def recent_events():
        """Get recent events."""
        limit = request.args.get("limit", 20, type=int)
        return jsonify({
            "events": queue.get_recent(limit=min(limit, 100))
        })
    
    # ========================================================================
    # Hot Lead Alerts Endpoints
    # ========================================================================
    
    @app.route("/alerts/hot-leads", methods=["GET"])
    def hot_lead_alerts():
        """Get recent hot lead alerts."""
        try:
            from core.hot_lead_detector import HotLeadDetector
            detector = HotLeadDetector()
            limit = request.args.get("limit", 20, type=int)
            alerts = detector.get_recent_alerts(limit=min(limit, 100))
            return jsonify({
                "count": len(alerts),
                "alerts": alerts,
                "stats": detector.get_stats()
            })
        except Exception as e:
            logger.error(f"Failed to get hot lead alerts: {e}")
            return jsonify({"error": str(e)}), 500
    
    @app.route("/alerts/hot-leads/stats", methods=["GET"])
    def hot_lead_stats():
        """Get hot lead detection statistics."""
        try:
            from core.hot_lead_detector import HotLeadDetector
            detector = HotLeadDetector()
            return jsonify(detector.get_stats())
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    return app


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Start the webhook server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Webhook Server for Alpha Swarm")
    parser.add_argument("--port", type=int, default=WEBHOOK_PORT, help="Port to listen on")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--no-processor", action="store_true", help="Disable background processor")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    
    args = parser.parse_args()
    
    # Create shared event queue
    event_queue = EventQueue()
    
    # Start background processor
    if not args.no_processor:
        processor_thread = threading.Thread(
            target=process_queue,
            args=(event_queue,),
            daemon=True
        )
        processor_thread.start()
        logger.info("Background queue processor started")
    
    # Create Flask app
    app = create_app(event_queue)
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║              Alpha Swarm Webhook Server                      ║
╠══════════════════════════════════════════════════════════════╣
║  Listening on: http://{args.host}:{args.port}                       
║                                                              ║
║  Endpoints:                                                  ║
║    POST /webhooks/instantly  - Instantly events              ║
║    POST /webhooks/ghl        - GoHighLevel events            ║
║    GET  /health              - Health check                  ║
║    GET  /stats               - Webhook statistics            ║
║    GET  /queue/pending       - Pending events                ║
║    GET  /queue/recent        - Recent events                 ║
║                                                              ║
║  Queue file: {str(QUEUE_FILE)[:45]}...
║                                                              ║
║  Press Ctrl+C to stop                                        ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    # Run Flask
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
        threaded=True
    )


if __name__ == "__main__":
    main()
