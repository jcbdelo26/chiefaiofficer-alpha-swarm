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

from fastapi import FastAPI, Request, HTTPException, Header, APIRouter, BackgroundTasks
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

# Use APIRouter instead of FastAPI app for better integration
app = FastAPI()
router = APIRouter()

RB2B_WEBHOOK_SECRET = os.getenv('RB2B_WEBHOOK_SECRET', '')

# =============================================================================
# ROBUST IMPORT PATH SETUP
# =============================================================================
try:
    # 1. Calculate project root (2 levels up from webhooks/rb2b_webhook.py)
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent
    
    # 2. Add to sys.path if missing
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    # 3. Import Core Modules
    try:
        from core.clay_direct_enrichment import ClayDirectEnrichment
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "clay_direct_enrichment", 
            project_root / "core" / "clay_direct_enrichment.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        ClayDirectEnrichment = module.ClayDirectEnrichment

    clay_enricher = ClayDirectEnrichment()
    print("✓ Clay Direct Enrichment initialized")
    
except Exception as e:
    print(f"Warning: Clay enrichment not initialized - {e}")
    clay_enricher = None

# Initialize Website Intent Monitor
website_monitor = None
try:
    from core.website_intent_monitor import get_website_monitor
    website_monitor = get_website_monitor()
    print("✓ Website Intent Monitor initialized")
except Exception as e:
    print(f"Warning: Website Intent Monitor not initialized - {e}")
    website_monitor = None


# Initialize Self-Learning ICP
icp_enabled = False
icp_error = None
icp_router = None

try:
    from core.self_learning_icp import get_icp_router
    icp_router = get_icp_router()
    icp_enabled = True
    print("✓ Self-Learning ICP engine enabled")
except Exception as e:
    icp_error = str(e)
    # Try fallback import
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "self_learning_icp", 
            project_root / "core" / "self_learning_icp.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        get_icp_router = module.get_icp_router
        icp_router = get_icp_router()
        icp_enabled = True
        print("✓ Self-Learning ICP engine enabled (fallback)")
    except Exception as e2:
        icp_error = f"{e} | {e2}"
        print(f"Warning: ICP router failed to initialize - {icp_error}")


async def verify_rb2b_signature(request: Request, x_signature: str = Header(None)):
    """Verify RB2B webhook signature."""
    if not RB2B_WEBHOOK_SECRET:
        # If secret is not configured, skip verification (WARN: Insecure)
        # In production, this should likely fail or log a warning
        return True
        
    if not x_signature:
        raise HTTPException(status_code=401, detail="Missing signature header")
    
    body = await request.body()
    
    # Calculate HMAC SHA256 signature
    signature = hmac.new(
        RB2B_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(signature, x_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    return True


def normalize_rb2b_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize RB2B webhook payload to Website Intent Monitor format.
    
    RB2B payloads vary but typically include profile data under 'leading_profile' or 'person'.
    """
    import hashlib
    
    profile = payload.get('leading_profile', {}) or payload.get('person', {}) or payload
    
    email = (
        profile.get('email') or 
        profile.get('work_email') or 
        payload.get('email') or
        ""
    )
    
    linkedin_url = (
        profile.get('linkedin_url') or 
        profile.get('linkedin') or 
        profile.get('linkedinUrl') or
        payload.get('linkedin_url') or
        ""
    )
    
    first_name = profile.get('first_name') or profile.get('firstName') or payload.get('first_name') or ""
    last_name = profile.get('last_name') or profile.get('lastName') or payload.get('last_name') or ""
    
    company_name = (
        profile.get('company', {}).get('name') if isinstance(profile.get('company'), dict) 
        else profile.get('company_name') or profile.get('companyName') or 
        payload.get('company_name') or ""
    )
    
    company_domain = (
        profile.get('company', {}).get('domain') if isinstance(profile.get('company'), dict)
        else profile.get('company_domain') or profile.get('companyDomain') or
        payload.get('company_domain') or ""
    )
    
    job_title = profile.get('job_title') or profile.get('title') or profile.get('jobTitle') or ""
    
    pages_viewed = []
    if payload.get('page_url'):
        pages_viewed.append(payload.get('page_url'))
    elif payload.get('url'):
        pages_viewed.append(payload.get('url'))
    elif payload.get('page'):
        pages_viewed.append(payload.get('page'))
    elif payload.get('pages'):
        pages_viewed = payload.get('pages', [])
    elif payload.get('events'):
        for evt in payload.get('events', []):
            if evt.get('page') or evt.get('url'):
                pages_viewed.append(evt.get('page') or evt.get('url'))
    
    visitor_id = payload.get('visitor_id') or payload.get('id')
    if not visitor_id:
        id_base = f"{email}:{linkedin_url}:{datetime.now().isoformat()}"
        visitor_id = hashlib.md5(id_base.encode()).hexdigest()[:12]
    
    work_history = []
    if profile.get('work_history'):
        work_history = profile.get('work_history')
    elif profile.get('experience'):
        for exp in profile.get('experience', []):
            work_history.append({
                "company_name": exp.get('company') or exp.get('company_name', ''),
                "company_domain": exp.get('domain') or exp.get('company_domain', ''),
                "years": exp.get('years') or f"{exp.get('start_year', '')}-{exp.get('end_year', '')}"
            })
    
    return {
        "visitor_id": visitor_id,
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "linkedin_url": linkedin_url,
        "company_name": company_name,
        "company_domain": company_domain,
        "job_title": job_title,
        "pages_viewed": pages_viewed,
        "work_history": work_history,
        "raw_payload": payload
    }


async def process_visitor_intent(visitor_data: Dict[str, Any]):
    """Background task to process visitor through Website Intent Monitor."""
    try:
        if website_monitor:
            result = await website_monitor.process_visitor(visitor_data)
            if result:
                print(f"✓ Intent processed: visitor={result.visitor_id}, score={result.intent_score}, queued={result.queued_for_approval}")
            else:
                print(f"Intent processing: No triggers matched for visitor {visitor_data.get('visitor_id')}")
    except Exception as e:
        print(f"Intent processing error: {e}")


@router.post("/webhooks/rb2b")
async def handle_rb2b_webhook(
    request: Request, 
    background_tasks: BackgroundTasks,
    x_signature: str = Header(None)
):
    """
    Handle incoming RB2B webhook.
    1. Verify signature
    2. Store raw data in Supabase
    3. Trigger enrichment (Clay)
    4. Trigger Website Intent Monitor (email queue generation)
    5. Feed to ICP Learning Engine
    """
    await verify_rb2b_signature(request, x_signature)
    
    try:
        payload = await request.json()
        print(f"Received RB2B payload: {json.dumps(payload)[:100]}...")
        
        # 1. Store in Supabase
        if supabase:
            try:
                supabase.table("webhook_logs").insert({
                    "source": "rb2b",
                    "payload": payload,
                    "processed": False,
                    "created_at": datetime.now(timezone.utc).isoformat()
                }).execute()
            except Exception as e:
                print(f"Supabase storage error: {e}")
        
        # 2. Trigger Enrichment (async, don't block)
        enrichment_result = None
        if clay_enricher:
            profile = payload.get('leading_profile', {})
            linkedin_url = profile.get('linkedin_url') or profile.get('linkedin')
            email = profile.get('email') or profile.get('work_email')
            
            identifier = linkedin_url or email
            
            if identifier:
                print(f"Triggering Clay enrichment for: {identifier}")
                try:
                    enrichment_result = clay_enricher.enrich_lead(identifier)
                    print(f"Enrichment initiated: {enrichment_result}")
                except Exception as e:
                    print(f"Enrichment trigger failed (continuing without): {e}")
        
        # 3. NEW: Trigger Website Intent Monitor (generates pending emails)
        intent_triggered = False
        if website_monitor:
            try:
                visitor_data = normalize_rb2b_payload(payload)
                background_tasks.add_task(process_visitor_intent, visitor_data)
                intent_triggered = True
                print(f"Intent monitor triggered for: {visitor_data.get('email') or visitor_data.get('visitor_id')}")
            except Exception as e:
                print(f"Intent monitor trigger failed: {e}")
        
        # 4. Self-Learning ICP (logging/learning)
        
        return {
            "status": "processed", 
            "enrichment": enrichment_result,
            "intent_triggered": intent_triggered
        }
        
    except Exception as e:
        print(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/webhooks/rb2b/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "webhook": "rb2b",
        "supabase_configured": supabase is not None,
        "secret_configured": bool(RB2B_WEBHOOK_SECRET),
        "icp_engine_enabled": icp_enabled,
        "icp_error": icp_error
    }

# =============================================================================
# CLAY WEBHOOK HANDLER
# =============================================================================

@router.post("/webhooks/clay")
async def handle_clay_callback(request: Request):
    """
    Handle incoming Clay enrichment callback.
    Receives JSON with enriched data and syncing to GHL.
    """
    try:
        payload = await request.json()
        print(f"Received Clay callback: {json.dumps(payload)[:100]}...")
        
        if clay_enricher:
            # Async processing
            await clay_enricher.receive_clay_callback(payload)
            return {"status": "processed"}
        else:
             print("Warning: Clay enricher not initialized")
             return {"status": "error", "detail": "Enricher not initialized"}
             
    except Exception as e:
        print(f"Clay callback error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/webhooks/clay/health")
async def clay_health_check():
    """Health check for Clay webhook."""
    return {
        "status": "healthy", 
        "enricher_initialized": clay_enricher is not None
    }


# Include the router in the main app (for standalone running)
app.include_router(router)
if icp_router:
    app.include_router(icp_router)

if __name__ == "__main__":
    import uvicorn
    print("Starting RB2B webhook server...")
    print(f"Webhook endpoint: http://localhost:8000/webhooks/rb2b")
    uvicorn.run(app, host="0.0.0.0", port=8000)
