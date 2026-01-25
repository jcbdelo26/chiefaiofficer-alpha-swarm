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
    
    print(f"✓ Python path updated: {project_root}")
    
    # 3. Import Core Modules
    try:
        # Try standard absolute import
        from core.clay_direct_enrichment import ClayDirectEnrichment
    except ImportError:
        # Fallback to direct path import
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
    init_error = str(e)
    print(f"Warning: Clay enrichment not initialized - {e}")
    clay_enricher = None


# Initialize Self-Learning ICP
icp_enabled = False
icp_error = None

try:
    # Try standard absolute import first
    from core.self_learning_icp import get_icp_router
except ImportError:
    try:
        # Fallback to direct path import using the project_root calculated earlier
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "self_learning_icp", 
            project_root / "core" / "self_learning_icp.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        get_icp_router = module.get_icp_router
    except Exception as e:
        icp_error = str(e)
        get_icp_router = None

if get_icp_router:
    try:
        icp_router = get_icp_router()
        app.include_router(icp_router)
        icp_enabled = True
        print("✓ Self-Learning ICP engine enabled")
    except Exception as e:
        icp_error = str(e)
        print(f"Warning: ICP router failed to initialize - {e}")
else:
    print(f"Warning: Could not import self_learning_icp - {icp_error}")


# [Existing verify_rb2b_signature function...]


# ... (skipping to health check)

@app.get("/webhooks/rb2b/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "webhook": "rb2b",
        "supabase_configured": supabase is not None,
        "secret_configured": bool(RB2B_WEBHOOK_SECRET),
        "inngest_enabled": inngest_enabled,
        "icp_engine_enabled": icp_enabled,
        "icp_error": icp_error
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

