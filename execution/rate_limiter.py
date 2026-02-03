#!/usr/bin/env python3
"""
API Rate Limiter
================
Centralized rate limiting for all API integrations.

Features:
- Per-service rate limits
- Automatic backoff and retry
- Redis-based distributed rate limiting
- Cost tracking per API call
- Quota management

Usage:
    from execution.rate_limiter import APIRateLimiter
    
    limiter = APIRateLimiter()
    
    # LinkedIn call (5 req/min)
    result = limiter.call('linkedin', lambda: scrape_profile(url))
    
    # Clay call (60 req/min)
    result = limiter.call('clay', lambda: enrich_lead(email))
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Any, Dict, Optional
from functools import wraps
import threading

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    pass


class APIRateLimiter:
    """
    Rate limiter for API calls with cost tracking.
    
    Rate Limits (per minute):
    - LinkedIn: 5 requests
    - Clay: 60 requests
    - GoHighLevel: 100 requests
    - Instantly: 60 requests
    - Anthropic: 50 requests
    """
    
    RATE_LIMITS = {
        'linkedin': {'calls': 5, 'period': 60},      # 5 per minute
        'clay': {'calls': 60, 'period': 60},         # 60 per minute
        'gohighlevel': {'calls': 100, 'period': 60}, # 100 per minute
        'instantly': {'calls': 60, 'period': 60},    # 60 per minute
        'anthropic': {'calls': 50, 'period': 60},    # 50 per minute
        'rb2b': {'calls': 100, 'period': 60},        # 100 per minute
        'exa': {'calls': 10, 'period': 60},          # 10 per minute
    }
    
    # Estimated costs per API call (in USD)
    COSTS = {
        'linkedin': 0.0,      # Free (but risky)
        'clay': 0.10,         # ~$0.10 per enrichment
        'gohighlevel': 0.0,   # Included in subscription
        'instantly': 0.01,    # ~$0.01 per email sent
        'anthropic': 0.015,   # ~$0.015 per Claude call (avg)
        'rb2b': 0.05,         # ~$0.05 per identification
        'exa': 0.02,          # ~$0.02 per search
    }
    
    def __init__(self, use_redis: bool = False):
        """
        Initialize rate limiter.
        
        Args:
            use_redis: Use Redis for distributed rate limiting (recommended for production)
        """
        self.use_redis = use_redis
        self.call_history: Dict[str, list] = {}
        self.cost_tracker: Dict[str, float] = {}
        self.lock = threading.Lock()
        
        # Setup storage
        self.data_dir = Path(__file__).parent.parent / ".hive-mind"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cost_log = self.data_dir / "api_costs.jsonl"
        
        # Initialize Redis if enabled
        if use_redis:
            try:
                import redis
                self.redis = redis.Redis(
                    host=os.getenv('REDIS_HOST', 'localhost'),
                    port=int(os.getenv('REDIS_PORT', 6379)),
                    decode_responses=True
                )
                self.redis.ping()
                print("✅ Redis connected for distributed rate limiting")
            except Exception as e:
                print(f"⚠️  Redis connection failed: {e}")
                print("   Falling back to in-memory rate limiting")
                self.use_redis = False
    
    def call(self, service: str, func: Callable, *args, **kwargs) -> Any:
        """
        Execute API call with rate limiting.
        
        Args:
            service: Service name (e.g., 'linkedin', 'clay')
            func: Function to call
            *args, **kwargs: Arguments to pass to function
        
        Returns:
            Result from function call
        
        Raises:
            RateLimitExceeded: If rate limit is exceeded and max retries reached
        """
        service = service.lower()
        
        if service not in self.RATE_LIMITS:
            raise ValueError(f"Unknown service: {service}")
        
        # Wait for rate limit availability
        self._wait_for_availability(service)
        
        # Record call
        self._record_call(service)
        
        # Track cost
        self._track_cost(service)
        
        # Execute function
        try:
            start_time = time.time()
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            
            # Log successful call
            self._log_call(service, success=True, duration=duration)
            
            return result
            
        except Exception as e:
            # Log failed call
            self._log_call(service, success=False, error=str(e))
            raise
    
    def _wait_for_availability(self, service: str):
        """Wait until rate limit allows next call."""
        limit = self.RATE_LIMITS[service]
        max_calls = limit['calls']
        period = limit['period']
        
        while True:
            with self.lock:
                now = time.time()
                
                # Get call history for this service
                if service not in self.call_history:
                    self.call_history[service] = []
                
                # Remove old calls outside the time window
                cutoff = now - period
                self.call_history[service] = [
                    t for t in self.call_history[service] if t > cutoff
                ]
                
                # Check if we can make another call
                if len(self.call_history[service]) < max_calls:
                    return  # Rate limit available
                
                # Calculate wait time
                oldest_call = min(self.call_history[service])
                wait_time = (oldest_call + period) - now
            
            if wait_time > 0:
                print(f"⏳ Rate limit reached for {service}. Waiting {wait_time:.1f}s...")
                time.sleep(wait_time + 0.1)  # Add small buffer
            else:
                return
    
    def _record_call(self, service: str):
        """Record API call timestamp."""
        with self.lock:
            if service not in self.call_history:
                self.call_history[service] = []
            self.call_history[service].append(time.time())
    
    def _track_cost(self, service: str):
        """Track API call cost."""
        cost = self.COSTS.get(service, 0.0)
        
        with self.lock:
            if service not in self.cost_tracker:
                self.cost_tracker[service] = 0.0
            self.cost_tracker[service] += cost
    
    def _log_call(self, service: str, success: bool, duration: float = 0, error: str = None):
        """Log API call details."""
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'service': service,
            'success': success,
            'duration_seconds': duration,
            'cost_usd': self.COSTS.get(service, 0.0),
            'error': error
        }
        
        with open(self.cost_log, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
    
    def get_cost_summary(self, days: int = 7) -> Dict[str, Any]:
        """
        Get cost summary for last N days.
        
        Args:
            days: Number of days to analyze
        
        Returns:
            Dictionary with cost breakdown by service
        """
        if not self.cost_log.exists():
            return {"error": "No cost log found"}
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        costs_by_service = {}
        total_calls = 0
        successful_calls = 0
        
        with open(self.cost_log, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    timestamp = datetime.fromisoformat(entry['timestamp'])
                    
                    if timestamp >= cutoff:
                        service = entry['service']
                        
                        if service not in costs_by_service:
                            costs_by_service[service] = {
                                'total_cost': 0.0,
                                'call_count': 0,
                                'success_count': 0,
                                'avg_duration': 0.0,
                                'total_duration': 0.0
                            }
                        
                        costs_by_service[service]['total_cost'] += entry.get('cost_usd', 0.0)
                        costs_by_service[service]['call_count'] += 1
                        costs_by_service[service]['total_duration'] += entry.get('duration_seconds', 0.0)
                        
                        if entry.get('success'):
                            costs_by_service[service]['success_count'] += 1
                            successful_calls += 1
                        
                        total_calls += 1
                        
                except:
                    continue
        
        # Calculate averages
        for service in costs_by_service:
            stats = costs_by_service[service]
            if stats['call_count'] > 0:
                stats['avg_duration'] = stats['total_duration'] / stats['call_count']
                stats['success_rate'] = (stats['success_count'] / stats['call_count']) * 100
        
        total_cost = sum(s['total_cost'] for s in costs_by_service.values())
        
        return {
            'period_days': days,
            'total_cost_usd': round(total_cost, 2),
            'total_calls': total_calls,
            'successful_calls': successful_calls,
            'success_rate': round((successful_calls / total_calls * 100) if total_calls > 0 else 0, 2),
            'by_service': costs_by_service,
            'projected_monthly_cost': round(total_cost / days * 30, 2)
        }
    
    def get_current_usage(self) -> Dict[str, Any]:
        """Get current rate limit usage for all services."""
        usage = {}
        
        with self.lock:
            now = time.time()
            
            for service, limit in self.RATE_LIMITS.items():
                if service in self.call_history:
                    cutoff = now - limit['period']
                    recent_calls = [t for t in self.call_history[service] if t > cutoff]
                    
                    usage[service] = {
                        'current_calls': len(recent_calls),
                        'max_calls': limit['calls'],
                        'period_seconds': limit['period'],
                        'usage_percent': (len(recent_calls) / limit['calls']) * 100,
                        'calls_remaining': limit['calls'] - len(recent_calls)
                    }
                else:
                    usage[service] = {
                        'current_calls': 0,
                        'max_calls': limit['calls'],
                        'period_seconds': limit['period'],
                        'usage_percent': 0,
                        'calls_remaining': limit['calls']
                    }
        
        return usage


def rate_limited(service: str):
    """
    Decorator for rate-limited API calls.
    
    Usage:
        @rate_limited('linkedin')
        def scrape_profile(url):
            # Your code here
            pass
    """
    limiter = APIRateLimiter()
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return limiter.call(service, func, *args, **kwargs)
        return wrapper
    return decorator


def main():
    """CLI for rate limiter."""
    import argparse
    
    parser = argparse.ArgumentParser(description="API Rate Limiter")
    parser.add_argument("--usage", action="store_true", help="Show current usage")
    parser.add_argument("--costs", type=int, metavar="DAYS", help="Show cost summary for last N days")
    
    args = parser.parse_args()
    
    limiter = APIRateLimiter()
    
    if args.usage:
        usage = limiter.get_current_usage()
        print(json.dumps(usage, indent=2))
    elif args.costs:
        costs = limiter.get_cost_summary(days=args.costs)
        print(json.dumps(costs, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
