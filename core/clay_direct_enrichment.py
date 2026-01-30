#!/usr/bin/env python3
"""
Clay Direct Enrichment Integration
===================================

Optimizes the RB2B → Clay → GHL pipeline by:
1. Receiving RB2B webhook data directly
2. Pushing to Clay workbook via webhook (your existing table)
3. Polling for enrichment completion OR receiving Clay webhook callback
4. Syncing enriched data to GHL with proper tags

Current Architecture (Manual):
    RB2B → Webhook → Clay Workbook (manual) → Export → GHL

Optimized Architecture (Automated):
    RB2B → Swarm Webhook → Clay Webhook API → Clay Enrichment → Callback → GHL Sync

Clay Workbook: https://app.clay.com/shared-workbook/share_0t9c5h2Dt6hzzFrz4Gv

Usage:
    from core.clay_direct_enrichment import ClayDirectEnrichment
    
    enricher = ClayDirectEnrichment()
    result = await enricher.enrich_visitor(visitor_data)
"""

import os
import sys
import json
import asyncio
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import time

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env', override=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('clay_direct')


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class ClayConfig:
    """Clay integration configuration."""
    # Your Clay workbook webhook URL (from the workbook settings)
    workbook_webhook_url: str = ""
    
    # Clay API key (for HTTP API actions if on Enterprise)
    api_key: str = ""
    
    # Callback webhook URL (your server receives enrichment results)
    callback_webhook_url: str = ""
    
    # Polling settings (if not using callbacks)
    poll_interval_seconds: int = 30
    max_poll_attempts: int = 10
    
    # GHL sync settings
    ghl_api_key: str = ""
    ghl_location_id: str = ""
    
    def __post_init__(self):
        self.api_key = os.getenv("CLAY_API_KEY", "")
        self.ghl_api_key = os.getenv("GHL_PROD_API_KEY", "")
        self.ghl_location_id = os.getenv("GHL_LOCATION_ID", "")
        # Your Clay workbook webhook - UPDATE THIS with your actual webhook URL
        self.workbook_webhook_url = os.getenv(
            "CLAY_WORKBOOK_WEBHOOK_URL",
            ""  # Will be populated from Clay workbook settings
        )


class EnrichmentStatus(Enum):
    """Status of enrichment request."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class EnrichmentRequest:
    """Request to enrich a visitor."""
    request_id: str
    visitor_id: str
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    source: str = "rb2b"
    priority: str = "high"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_clay_payload(self) -> Dict[str, Any]:
        """Convert to Clay webhook payload format."""
        return {
            "request_id": self.request_id,
            "visitor_id": self.visitor_id,
            "email": self.email or "",
            "linkedin_url": self.linkedin_url or "",
            "first_name": self.first_name or "",
            "last_name": self.last_name or "",
            "full_name": f"{self.first_name or ''} {self.last_name or ''}".strip(),
            "company_name": self.company_name or "",
            "company_domain": self.company_domain or "",
            "source": self.source,
            "priority": self.priority,
            "timestamp": self.created_at
        }


@dataclass
class EnrichmentResult:
    """Result from Clay enrichment."""
    request_id: str
    status: EnrichmentStatus
    
    # Person data
    email: Optional[str] = None
    email_verified: bool = False
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    job_title: Optional[str] = None
    
    # Company data
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    company_industry: Optional[str] = None
    company_size: Optional[str] = None
    company_revenue: Optional[str] = None
    company_linkedin: Optional[str] = None
    
    # Scoring
    icp_fit_score: float = 0.0
    priority_tier: str = "low"
    
    # Metadata
    enrichment_sources: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    enriched_at: str = ""
    error_message: Optional[str] = None
    
    def __post_init__(self):
        if not self.enriched_at:
            self.enriched_at = datetime.now(timezone.utc).isoformat()


# =============================================================================
# CLAY DIRECT ENRICHMENT
# =============================================================================

class ClayDirectEnrichment:
    """
    Direct integration with Clay for automated enrichment.
    
    Workflow:
    1. Receive visitor data (from RB2B or other source)
    2. Push to Clay workbook via webhook
    3. Wait for enrichment (poll or callback)
    4. Sync enriched data to GHL
    """
    
    # Cache TTLs (in days)
    ENRICHMENT_CACHE_TTL_DAYS = 7
    COST_PER_ENRICHMENT = 0.03  # Estimated cost saved per cache hit
    
    def __init__(self, config: Optional[ClayConfig] = None):
        self.config = config or ClayConfig()
        self.storage_dir = PROJECT_ROOT / ".hive-mind" / "clay_enrichment"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache directory
        self.cache_dir = PROJECT_ROOT / ".hive-mind" / "enrichment_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Track pending enrichments
        self._pending: Dict[str, EnrichmentRequest] = {}
        self._results: Dict[str, EnrichmentResult] = {}
        
        # Cache stats
        self._cache_hits: int = 0
        self._cache_misses: int = 0
        
        self._load_state()
        self._load_cache_stats()
        logger.info("Clay Direct Enrichment initialized")
    
    def _load_state(self):
        """Load pending requests from disk."""
        pending_file = self.storage_dir / "pending.json"
        if pending_file.exists():
            try:
                with open(pending_file) as f:
                    data = json.load(f)
                    for req_id, req_data in data.items():
                        self._pending[req_id] = EnrichmentRequest(**req_data)
            except Exception as e:
                logger.warning(f"Failed to load pending state: {e}")
    
    def _save_state(self):
        """Save pending requests to disk."""
        pending_file = self.storage_dir / "pending.json"
        try:
            with open(pending_file, 'w') as f:
                json.dump({k: asdict(v) for k, v in self._pending.items()}, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save state: {e}")
    
    def _load_cache_stats(self):
        """Load cache stats from disk."""
        stats_file = self.cache_dir / "stats.json"
        if stats_file.exists():
            try:
                with open(stats_file) as f:
                    data = json.load(f)
                    self._cache_hits = data.get("cache_hits", 0)
                    self._cache_misses = data.get("cache_misses", 0)
            except Exception as e:
                logger.warning(f"Failed to load cache stats: {e}")
    
    def _save_cache_stats(self):
        """Save cache stats to disk."""
        stats_file = self.cache_dir / "stats.json"
        try:
            with open(stats_file, 'w') as f:
                json.dump({
                    "cache_hits": self._cache_hits,
                    "cache_misses": self._cache_misses,
                    "cost_saved_estimate": self._cache_hits * self.COST_PER_ENRICHMENT
                }, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache stats: {e}")
    
    def _get_cache_key(self, identifier: str) -> str:
        """Generate cache key from email or domain."""
        return hashlib.md5(identifier.lower().encode()).hexdigest()
    
    def _get_cached_enrichment(self, email: Optional[str], domain: Optional[str]) -> Optional[EnrichmentResult]:
        """Check cache for existing enrichment data."""
        identifiers = []
        if email:
            identifiers.append(f"enrichment:{email}")
        if domain:
            identifiers.append(f"enrichment:{domain}")
        
        for identifier in identifiers:
            cache_key = self._get_cache_key(identifier)
            cache_file = self.cache_dir / f"{cache_key}.json"
            
            if cache_file.exists():
                try:
                    with open(cache_file) as f:
                        data = json.load(f)
                    
                    cached_at = datetime.fromisoformat(data.get("cached_at", ""))
                    ttl = timedelta(days=self.ENRICHMENT_CACHE_TTL_DAYS)
                    
                    if datetime.now(timezone.utc) - cached_at < ttl:
                        logger.info(f"Cache HIT for {email or domain}")
                        self._cache_hits += 1
                        self._save_cache_stats()
                        
                        result_data = data.get("result", {})
                        return EnrichmentResult(
                            request_id=result_data.get("request_id", "cached"),
                            status=EnrichmentStatus(result_data.get("status", "completed")),
                            email=result_data.get("email"),
                            email_verified=result_data.get("email_verified", False),
                            phone=result_data.get("phone"),
                            linkedin_url=result_data.get("linkedin_url"),
                            first_name=result_data.get("first_name"),
                            last_name=result_data.get("last_name"),
                            job_title=result_data.get("job_title"),
                            company_name=result_data.get("company_name"),
                            company_domain=result_data.get("company_domain"),
                            company_industry=result_data.get("company_industry"),
                            company_size=result_data.get("company_size"),
                            company_revenue=result_data.get("company_revenue"),
                            company_linkedin=result_data.get("company_linkedin"),
                            icp_fit_score=result_data.get("icp_fit_score", 0.0),
                            priority_tier=result_data.get("priority_tier", "low"),
                            enrichment_sources=result_data.get("enrichment_sources", []),
                            raw_data=result_data.get("raw_data", {}),
                            enriched_at=result_data.get("enriched_at", "")
                        )
                    else:
                        logger.debug(f"Cache expired for {email or domain}")
                except Exception as e:
                    logger.warning(f"Failed to read cache: {e}")
        
        return None
    
    def _cache_enrichment(self, result: EnrichmentResult, email: Optional[str], domain: Optional[str]):
        """Cache enrichment result."""
        identifiers = []
        if email:
            identifiers.append(f"enrichment:{email}")
        if domain:
            identifiers.append(f"enrichment:{domain}")
        
        cache_data = {
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "ttl_days": self.ENRICHMENT_CACHE_TTL_DAYS,
            "result": {
                "request_id": result.request_id,
                "status": result.status.value,
                "email": result.email,
                "email_verified": result.email_verified,
                "phone": result.phone,
                "linkedin_url": result.linkedin_url,
                "first_name": result.first_name,
                "last_name": result.last_name,
                "job_title": result.job_title,
                "company_name": result.company_name,
                "company_domain": result.company_domain,
                "company_industry": result.company_industry,
                "company_size": result.company_size,
                "company_revenue": result.company_revenue,
                "company_linkedin": result.company_linkedin,
                "icp_fit_score": result.icp_fit_score,
                "priority_tier": result.priority_tier,
                "enrichment_sources": result.enrichment_sources,
                "raw_data": result.raw_data,
                "enriched_at": result.enriched_at
            }
        }
        
        for identifier in identifiers:
            cache_key = self._get_cache_key(identifier)
            cache_file = self.cache_dir / f"{cache_key}.json"
            try:
                with open(cache_file, 'w') as f:
                    json.dump(cache_data, f, indent=2)
                logger.info(f"Cached enrichment for {email or domain}")
            except Exception as e:
                logger.warning(f"Failed to cache enrichment: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cost_saved_estimate": round(self._cache_hits * self.COST_PER_ENRICHMENT, 2),
            "hit_rate": round(self._cache_hits / max(1, self._cache_hits + self._cache_misses) * 100, 1)
        }
    
    async def enrich_visitor(self, visitor_data: Dict[str, Any]) -> EnrichmentResult:
        """
        Enrich a website visitor from RB2B.
        
        Args:
            visitor_data: RB2B visitor data
            
        Returns:
            EnrichmentResult with enriched data
        """
        email = visitor_data.get("email")
        company_domain = visitor_data.get("company", {}).get("domain")
        
        # Check cache BEFORE calling Clay
        cached_result = self._get_cached_enrichment(email, company_domain)
        if cached_result:
            return cached_result
        
        # Cache miss - track it
        self._cache_misses += 1
        self._save_cache_stats()
        
        # Create enrichment request
        request_id = f"enr_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{visitor_data.get('visitor_id', 'unknown')[:8]}"
        
        request = EnrichmentRequest(
            request_id=request_id,
            visitor_id=visitor_data.get("visitor_id", ""),
            email=email,
            linkedin_url=visitor_data.get("linkedin_url"),
            first_name=visitor_data.get("first_name"),
            last_name=visitor_data.get("last_name"),
            company_name=visitor_data.get("company", {}).get("name"),
            company_domain=company_domain,
            source="rb2b",
            priority="high"
        )
        
        logger.info(f"Enriching visitor: {request.company_domain or request.email}")
        
        # Push to Clay workbook
        success = await self._push_to_clay(request)
        
        if not success:
            return EnrichmentResult(
                request_id=request_id,
                status=EnrichmentStatus.FAILED,
                error_message="Failed to push to Clay workbook"
            )
        
        # Track pending
        self._pending[request_id] = request
        self._save_state()
        
        # Poll for results (or wait for callback in production)
        result = await self._poll_for_result(request)
        
        # Remove from pending
        self._pending.pop(request_id, None)
        self._save_state()
        
        # Sync to GHL if successful
        if result.status == EnrichmentStatus.COMPLETED:
            # Cache the result AFTER getting Clay results
            self._cache_enrichment(result, email, company_domain)
            await self._sync_to_ghl(result)
        
        return result
    
    async def _push_to_clay(self, request: EnrichmentRequest) -> bool:
        """Push enrichment request to Clay workbook webhook."""
        import httpx
        
        if not self.config.workbook_webhook_url:
            logger.warning("Clay workbook webhook URL not configured")
            # Fallback: save to local queue for manual processing
            return await self._queue_for_manual_processing(request)
        
        payload = request.to_clay_payload()
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    self.config.workbook_webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code in [200, 201, 202]:
                    logger.info(f"Pushed to Clay: {request.request_id}")
                    return True
                else:
                    logger.error(f"Clay webhook failed: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to push to Clay: {e}")
            return False
    
    async def _queue_for_manual_processing(self, request: EnrichmentRequest) -> bool:
        """Queue for manual processing when webhook not configured."""
        queue_dir = self.storage_dir / "queue"
        queue_dir.mkdir(parents=True, exist_ok=True)
        
        queue_file = queue_dir / f"{request.request_id}.json"
        try:
            with open(queue_file, 'w') as f:
                json.dump(request.to_clay_payload(), f, indent=2)
            logger.info(f"Queued for manual Clay processing: {queue_file.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to queue: {e}")
            return False
    
    async def _poll_for_result(self, request: EnrichmentRequest) -> EnrichmentResult:
        """
        Poll for enrichment result.
        
        In production with callback webhook, this would receive push notifications.
        For now, we simulate enrichment completion or check a results directory.
        """
        # Check if we already have result (from callback)
        if request.request_id in self._results:
            return self._results[request.request_id]
        
        # Check results directory for completed enrichments
        results_dir = self.storage_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        
        for attempt in range(self.config.max_poll_attempts):
            result_file = results_dir / f"{request.request_id}.json"
            
            if result_file.exists():
                try:
                    with open(result_file) as f:
                        data = json.load(f)
                    return self._parse_clay_result(request.request_id, data)
                except Exception as e:
                    logger.warning(f"Failed to parse result: {e}")
            
            # If no webhook configured, simulate enrichment for demo
            if not self.config.workbook_webhook_url:
                return self._simulate_enrichment(request)
            
            logger.info(f"Waiting for enrichment result... ({attempt + 1}/{self.config.max_poll_attempts})")
            await asyncio.sleep(self.config.poll_interval_seconds)
        
        # Timeout
        return EnrichmentResult(
            request_id=request.request_id,
            status=EnrichmentStatus.TIMEOUT,
            error_message=f"Enrichment timed out after {self.config.max_poll_attempts * self.config.poll_interval_seconds}s"
        )
    
    def _simulate_enrichment(self, request: EnrichmentRequest) -> EnrichmentResult:
        """Simulate enrichment for demo/testing when Clay webhook not configured."""
        logger.info("Simulating Clay enrichment (webhook not configured)")
        
        # Calculate ICP score based on available data
        icp_score = 0.5
        if request.company_domain:
            icp_score += 0.2
        if request.email:
            icp_score += 0.15
        if request.linkedin_url:
            icp_score += 0.15
        
        tier = "high" if icp_score >= 0.8 else "medium" if icp_score >= 0.5 else "low"
        
        return EnrichmentResult(
            request_id=request.request_id,
            status=EnrichmentStatus.COMPLETED,
            email=request.email,
            email_verified=bool(request.email),
            linkedin_url=request.linkedin_url,
            first_name=request.first_name,
            last_name=request.last_name,
            company_name=request.company_name,
            company_domain=request.company_domain,
            icp_fit_score=icp_score,
            priority_tier=tier,
            enrichment_sources=["simulated"],
            raw_data=request.to_clay_payload()
        )
    
    def _parse_clay_result(self, request_id: str, data: Dict[str, Any]) -> EnrichmentResult:
        """Parse Clay enrichment result into EnrichmentResult."""
        return EnrichmentResult(
            request_id=request_id,
            status=EnrichmentStatus.COMPLETED,
            email=data.get("work_email") or data.get("email"),
            email_verified=data.get("email_verified", False),
            phone=data.get("phone") or data.get("mobile_phone"),
            linkedin_url=data.get("linkedin_url"),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            job_title=data.get("job_title") or data.get("title"),
            company_name=data.get("company_name") or data.get("company"),
            company_domain=data.get("company_domain") or data.get("website"),
            company_industry=data.get("industry"),
            company_size=data.get("employee_count") or data.get("company_size"),
            company_revenue=data.get("revenue"),
            company_linkedin=data.get("company_linkedin_url"),
            icp_fit_score=float(data.get("icp_score", 0)),
            priority_tier=data.get("priority", "low"),
            enrichment_sources=data.get("sources", []),
            raw_data=data
        )
    
    async def _sync_to_ghl(self, result: EnrichmentResult) -> bool:
        """Sync enriched data to GHL."""
        import httpx
        
        if not self.config.ghl_api_key:
            logger.warning("GHL API key not configured, skipping sync")
            return False
        
        # Prepare GHL contact payload
        payload = {
            "locationId": self.config.ghl_location_id,
            "firstName": result.first_name,
            "lastName": result.last_name,
            "email": result.email,
            "phone": result.phone,
            "companyName": result.company_name,
            "website": f"https://{result.company_domain}" if result.company_domain else None,
            "source": "Clay Enrichment",
            "tags": [
                f"clay-enriched",
                f"priority-{result.priority_tier}",
                "rb2b-visitor"
            ],
            "customFields": []
        }
        
        # Add custom fields for enrichment data
        if result.job_title:
            payload["customFields"].append({"key": "job_title", "value": result.job_title})
        if result.company_industry:
            payload["customFields"].append({"key": "industry", "value": result.company_industry})
        if result.company_size:
            payload["customFields"].append({"key": "company_size", "value": result.company_size})
        if result.icp_fit_score:
            payload["customFields"].append({"key": "icp_score", "value": str(result.icp_fit_score)})
        
        headers = {
            "Authorization": f"Bearer {self.config.ghl_api_key}",
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                # Check if contact exists
                search_url = f"https://services.leadconnectorhq.com/contacts/search"
                search_response = await client.post(
                    search_url,
                    json={
                        "locationId": self.config.ghl_location_id,
                        "query": result.email
                    },
                    headers=headers
                )
                
                if search_response.status_code == 200:
                    existing = search_response.json().get("contacts", [])
                    if existing:
                        # Update existing contact
                        contact_id = existing[0]["id"]
                        update_url = f"https://services.leadconnectorhq.com/contacts/{contact_id}"
                        response = await client.put(update_url, json=payload, headers=headers)
                        logger.info(f"Updated GHL contact: {contact_id}")
                    else:
                        # Create new contact
                        create_url = "https://services.leadconnectorhq.com/contacts/"
                        response = await client.post(create_url, json=payload, headers=headers)
                        logger.info(f"Created new GHL contact")
                    
                    return response.status_code in [200, 201]
                else:
                    logger.error(f"GHL search failed: {search_response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to sync to GHL: {e}")
            return False
    
    async def receive_clay_callback(self, callback_data: Dict[str, Any]) -> bool:
        """
        Receive enrichment result from Clay callback webhook.
        
        Your Clay workbook should have an HTTP API action that posts results
        back to your webhook endpoint when enrichment completes.
        """
        request_id = callback_data.get("request_id")
        
        if not request_id:
            logger.warning("Callback missing request_id")
            return False
        
        result = self._parse_clay_result(request_id, callback_data)
        self._results[request_id] = result
        
        # Save result
        results_dir = self.storage_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        
        result_file = results_dir / f"{request_id}.json"
        with open(result_file, 'w') as f:
            json.dump(callback_data, f, indent=2)
        
        logger.info(f"Received Clay callback for {request_id}")
        
        # Sync to GHL
        await self._sync_to_ghl(result)
        
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """Get enrichment status."""
        queue_dir = self.storage_dir / "queue"
        results_dir = self.storage_dir / "results"
        
        queued = len(list(queue_dir.glob("*.json"))) if queue_dir.exists() else 0
        completed = len(list(results_dir.glob("*.json"))) if results_dir.exists() else 0
        
        cache_stats = self.get_cache_stats()
        
        return {
            "pending": len(self._pending),
            "queued_for_manual": queued,
            "completed": completed,
            "webhook_configured": bool(self.config.workbook_webhook_url),
            "ghl_configured": bool(self.config.ghl_api_key),
            "cache": cache_stats
        }
    
    def print_status(self):
        """Print enrichment status."""
        status = self.get_status()
        cache = status.get("cache", {})
        
        print("\n" + "=" * 60)
        print("  CLAY DIRECT ENRICHMENT STATUS")
        print("=" * 60)
        print(f"\n  Pending Enrichments: {status['pending']}")
        print(f"  Queued for Manual Processing: {status['queued_for_manual']}")
        print(f"  Completed: {status['completed']}")
        print(f"\n  Clay Webhook Configured: {'Yes' if status['webhook_configured'] else 'No'}")
        print(f"  GHL Sync Configured: {'Yes' if status['ghl_configured'] else 'No'}")
        print(f"\n  --- Cache Stats ---")
        print(f"  Cache Hits: {cache.get('cache_hits', 0)}")
        print(f"  Cache Misses: {cache.get('cache_misses', 0)}")
        print(f"  Hit Rate: {cache.get('hit_rate', 0)}%")
        print(f"  Est. Cost Saved: ${cache.get('cost_saved_estimate', 0):.2f}")
        print("\n" + "=" * 60)


# =============================================================================
# WEBHOOK ENDPOINT FOR CLAY CALLBACKS
# =============================================================================

def create_callback_app():
    """Create FastAPI app for receiving Clay callbacks."""
    from fastapi import FastAPI, Request
    
    app = FastAPI(title="Clay Enrichment Callback")
    enricher = ClayDirectEnrichment()
    
    @app.post("/webhooks/clay/callback")
    async def clay_callback(request: Request):
        """Receive enrichment results from Clay."""
        data = await request.json()
        success = await enricher.receive_clay_callback(data)
        return {"status": "ok" if success else "error"}
    
    @app.get("/webhooks/clay/status")
    async def clay_status():
        """Get enrichment status."""
        return enricher.get_status()
    
    return app


# =============================================================================
# CLI
# =============================================================================

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Clay Direct Enrichment")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--test", action="store_true", help="Test with sample data")
    parser.add_argument("--serve", action="store_true", help="Start callback webhook server")
    parser.add_argument("--port", type=int, default=8001, help="Webhook server port")
    
    args = parser.parse_args()
    
    enricher = ClayDirectEnrichment()
    
    if args.status:
        enricher.print_status()
    
    if args.test:
        print("\nTesting Clay enrichment with sample visitor data...")
        
        test_visitor = {
            "visitor_id": "test_visitor_001",
            "email": "john.smith@testcompany.com",
            "first_name": "John",
            "last_name": "Smith",
            "company": {
                "name": "Test Company Inc",
                "domain": "testcompany.com"
            }
        }
        
        result = await enricher.enrich_visitor(test_visitor)
        
        print(f"\nResult:")
        print(f"  Status: {result.status.value}")
        print(f"  Email: {result.email}")
        print(f"  Company: {result.company_name}")
        print(f"  ICP Score: {result.icp_fit_score}")
        print(f"  Priority: {result.priority_tier}")
    
    if args.serve:
        import uvicorn
        app = create_callback_app()
        print(f"\nStarting Clay callback webhook server on port {args.port}...")
        print(f"Callback URL: http://localhost:{args.port}/webhooks/clay/callback")
        uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    asyncio.run(main())
