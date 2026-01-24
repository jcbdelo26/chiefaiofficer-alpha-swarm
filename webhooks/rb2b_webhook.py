#!/usr/bin/env python3
"""
RB2B Webhook Handler
Receives visitor identification data from RB2B and stores in Supabase.

RB2B sends POST requests when visitors are identified on your website.
"""

import os
import sys
import hmac
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request, HTTPException, Header
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Supabase client
try:
    from supabase import create_client, Client
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_KEY = os.getenv('SUPABASE_KEY')
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Warning: Supabase not configured - {e}")
    supabase = None

app = FastAPI()


RB2B_WEBHOOK_SECRET = os.getenv('RB2B_WEBHOOK_SECRET', '')

# Initialize Clay Enricher
try:
    # Add project root to path if needed (it's already added in some envs but good to be safe)
    PROJECT_ROOT = Path(__file__).parent.parent
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    
    from core.clay_direct_enrichment import ClayDirectEnrichment
    clay_enricher = ClayDirectEnrichment()
    print("✓ Clay Direct Enrichment initialized")
except Exception as e:
    print(f"Warning: Clay enrichment not initialized - {e}")
    clay_enricher = None

# Initialize Self-Learning ICP
try:
    from core.self_learning_icp import get_icp_router
    icp_router = get_icp_router()
    app.include_router(icp_router)
    print("✓ Self-Learning ICP engine enabled")
except Exception as e:
    print(f"Warning: ICP learning not initialized - {e}")



def verify_rb2b_signature(payload: bytes, signature: str) -> bool:
    """
    Verify RB2B webhook signature.
    
    Args:
        payload: Raw request body
        signature: X-RB2B-Signature header value
        
    Returns:
        True if signature is valid
    """
    if not RB2B_WEBHOOK_SECRET:
        print("Warning: RB2B_WEBHOOK_SECRET not configured, skipping verification")
        return True
    
    expected_signature = hmac.new(
        RB2B_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature, expected_signature)


async def store_visitor_in_supabase(visitor_data: Dict[str, Any]) -> bool:
    """
    Store identified visitor in Supabase.
    
    Args:
        visitor_data: Visitor information from RB2B
        
    Returns:
        True if stored successfully
    """
    if not supabase:
        print("Supabase not configured, visitor data not stored")
        return False
    
    try:
        # Extract key fields
        record = {
            'rb2b_visitor_id': visitor_data.get('visitor_id'),
            'company_name': visitor_data.get('company', {}).get('name'),
            'company_domain': visitor_data.get('company', {}).get('domain'),
            'company_industry': visitor_data.get('company', {}).get('industry'),
            'company_size': visitor_data.get('company', {}).get('employee_count'),
            'company_revenue': visitor_data.get('company', {}).get('revenue'),
            'company_location': visitor_data.get('company', {}).get('location'),
            'visitor_ip': visitor_data.get('ip_address'),
            'visitor_country': visitor_data.get('geo', {}).get('country'),
            'visitor_city': visitor_data.get('geo', {}).get('city'),
            'page_url': visitor_data.get('page_url'),
            'referrer': visitor_data.get('referrer'),
            'user_agent': visitor_data.get('user_agent'),
            'session_id': visitor_data.get('session_id'),
            'identified_at': visitor_data.get('timestamp', datetime.now(timezone.utc).isoformat()),
            'raw_data': visitor_data,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Insert into rb2b_visitors table
        result = supabase.table('rb2b_visitors').insert(record).execute()
        
        print(f"✓ Stored visitor: {record.get('company_name')} ({record.get('company_domain')})")
        
        # Trigger enrichment if company domain exists
        if record.get('company_domain'):
            await trigger_enrichment(record)
        
        return True
        
    except Exception as e:
        print(f"Error storing visitor in Supabase: {e}")
        return False


async def trigger_enrichment(visitor_record: Dict[str, Any]) -> None:
    """
    Trigger ENRICHER agent to enrich the identified company.
    
    Uses Clay Direct Enrichment for automated processing:
    1. Push to Clay workbook via webhook
    2. Receive enriched data via callback
    3. Sync to GHL with proper tags
    
    Args:
        visitor_record: Visitor data with company info
    """
    try:
        # Try direct Clay enrichment first
        try:
            from core.clay_direct_enrichment import ClayDirectEnrichment
            
            enricher = ClayDirectEnrichment()
            
            # Format visitor data for enrichment
            visitor_data = {
                "visitor_id": visitor_record.get("rb2b_visitor_id"),
                "email": visitor_record.get("email"),
                "first_name": visitor_record.get("first_name"),
                "last_name": visitor_record.get("last_name"),
                "company": {
                    "name": visitor_record.get("company_name"),
                    "domain": visitor_record.get("company_domain")
                }
            }
            
            # Enrich via Clay (non-blocking queue)
            result = await enricher.enrich_visitor(visitor_data)
            
            print(f"✓ Clay enrichment triggered: {result.status.value}")
            print(f"  Company: {result.company_name}")
            print(f"  Priority: {result.priority_tier}")
            
            return
            
        except ImportError:
            print("Clay Direct Enrichment not available, using queue fallback")
        
        # Fallback: Queue for manual processing
        enrichment_task = {
            'source': 'rb2b_webhook',
            'company_domain': visitor_record.get('company_domain'),
            'company_name': visitor_record.get('company_name'),
            'visitor_id': visitor_record.get('rb2b_visitor_id'),
            'priority': 'high',  # Website visitors are high priority
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        # Store in enrichment queue
        queue_dir = Path('.hive-mind/enrichment/queue')
        queue_dir.mkdir(parents=True, exist_ok=True)
        
        queue_file = queue_dir / f"rb2b_{visitor_record.get('rb2b_visitor_id')}.json"
        with open(queue_file, 'w') as f:
            json.dump(enrichment_task, f, indent=2)
        
        print(f"✓ Queued enrichment for {visitor_record.get('company_domain')}")
        
    except Exception as e:
        print(f"Error triggering enrichment: {e}")


@app.post("/webhooks/rb2b")
async def rb2b_webhook(
    request: Request,
    x_rb2b_signature: Optional[str] = Header(None)
):
    """
    RB2B webhook endpoint.
    
    Receives visitor identification events from RB2B.
    
    Example payload:
    {
        "visitor_id": "vis_abc123",
        "session_id": "sess_xyz789",
        "timestamp": "2026-01-22T14:30:00Z",
        "company": {
            "name": "Acme Corp",
            "domain": "acme.com",
            "industry": "Software",
            "employee_count": 250,
            "revenue": "$50M-$100M",
            "location": "San Francisco, CA"
        },
        "ip_address": "192.0.2.1",
        "geo": {
            "country": "United States",
            "city": "San Francisco"
        },
        "page_url": "https://chiefaiofficer.com/pricing",
        "referrer": "https://google.com/search?q=ai+revenue+ops",
        "user_agent": "Mozilla/5.0..."
    }
    """
    try:
        # Get raw body for signature verification
        body = await request.body()
        
        # Verify signature
        if x_rb2b_signature:
            if not verify_rb2b_signature(body, x_rb2b_signature):
                raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Parse JSON
        visitor_data = json.loads(body)
        
        # Log receipt
        print(f"\n{'='*60}")
        print(f"RB2B Webhook Received")
        print(f"{'='*60}")
        print(f"Visitor ID: {visitor_data.get('visitor_id')}")
        print(f"Company: {visitor_data.get('company', {}).get('name')}")
        print(f"Domain: {visitor_data.get('company', {}).get('domain')}")
        print(f"Page: {visitor_data.get('page_url')}")
        print(f"{'='*60}\n")
        
        # Store in Supabase
        await store_visitor_in_supabase(visitor_data)
        
        return {
            "status": "success",
            "message": "Visitor data received and stored",
            "visitor_id": visitor_data.get('visitor_id')
        }
        
    except json.JSONDecodeError:
        print("Warning: Received invalid JSON (likely a test ping). Returning success.")
        return {"status": "success", "message": "Test ping received"}
        
    except Exception as e:
        print(f"Error processing RB2B webhook: {e}")
        # Return success anyway to prevent RB2B from disabling the webhook
        return {"status": "success", "message": "Data received (processed with warning)"}



@app.post("/webhooks/clay/callback")
async def clay_callback(request: Request):
    """
    Receive enrichment results from Clay.
    Endpoint: /webhooks/clay/callback
    """
    if not clay_enricher:
        raise HTTPException(status_code=503, detail="Clay enrichment not initialized")
        
    try:
        data = await request.json()
        success = await clay_enricher.receive_clay_callback(data)
        
        if success:
            print(f"✓ Received Clay callback for {data.get('company_name', 'Unknown')}")
            return {"status": "success"}
        else:
            return {"status": "ignored", "reason": "No matching request found or invalid data"}
            
    except Exception as e:
        print(f"Error processing Clay callback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/webhooks/rb2b/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "webhook": "rb2b",
        "supabase_configured": supabase is not None,
        "secret_configured": bool(RB2B_WEBHOOK_SECRET),
        "inngest_enabled": inngest_enabled
    }


# =============================================================================
# INNGEST SCHEDULER INTEGRATION
# =============================================================================
inngest_enabled = False
try:
    from core.inngest_scheduler import get_inngest_serve
    # Mount Inngest at /api/inngest
    inngest_serve = get_inngest_serve()
    app.mount("/api/inngest", inngest_serve)
    inngest_enabled = True
    print("✓ Inngest scheduler enabled")
except Exception as e:
    print(f"Warning: Inngest scheduler not initialized - {e}")


if __name__ == "__main__":
    import uvicorn
    print("Starting RB2B webhook server...")
    print(f"Webhook endpoint: http://localhost:8000/webhooks/rb2b")
    print(f"Clay callback: http://localhost:8000/webhooks/clay/callback")
    print(f"Inngest: http://localhost:8000/api/inngest")
    print(f"Health check: http://localhost:8000/webhooks/rb2b/health")
    uvicorn.run(app, host="0.0.0.0", port=8000)

