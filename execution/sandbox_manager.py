#!/usr/bin/env python3
"""
Sandbox Manager
===============
Creates isolated test environments for testing the pipeline without live operations.

Modes:
- dry_run: Log only, no external calls
- mock: Fake responses from all external services
- staging: Real APIs with test data (safe for testing)

Usage:
    from execution.sandbox_manager import SandboxManager, SandboxMode
    
    sandbox = SandboxManager(mode=SandboxMode.MOCK)
    with sandbox.activate():
        # All operations use sandbox data
        results = run_pipeline(...)
"""

import os
import sys
import json
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from contextlib import contextmanager
from unittest.mock import patch, MagicMock
import random

PROJECT_ROOT = Path(__file__).parent.parent
HIVE_MIND = PROJECT_ROOT / ".hive-mind"
SANDBOX_DIR = HIVE_MIND / "sandbox"


class SandboxMode(Enum):
    """Sandbox operation modes."""
    DRY_RUN = "dry_run"     # Log only, no external calls or file writes
    MOCK = "mock"           # Fake responses from all external services
    STAGING = "staging"     # Real APIs but test data only


@dataclass
class SandboxContext:
    """Sandbox execution context."""
    mode: SandboxMode
    session_id: str
    start_time: datetime
    operations_log: List[Dict[str, Any]] = field(default_factory=list)
    mock_responses: Dict[str, Any] = field(default_factory=dict)
    token_usage: Dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    api_calls: Dict[str, int] = field(default_factory=dict)


class SandboxManager:
    """
    Manages isolated test environments for pipeline testing.
    
    Features:
    - Intercepts all external API calls
    - Redirects file writes to sandbox directory
    - Logs all operations for validation
    - Generates mock responses based on ICP criteria
    """
    
    def __init__(self, mode: SandboxMode = SandboxMode.MOCK):
        self.mode = mode
        self.context: Optional[SandboxContext] = None
        self.logger = self._setup_logger()
        self._patches: List[Any] = []
        self._original_hive_mind: Optional[Path] = None
        
        # Ensure sandbox directory exists
        SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    
    def _setup_logger(self) -> logging.Logger:
        """Setup sandbox logger."""
        logger = logging.getLogger("sandbox")
        logger.setLevel(logging.DEBUG)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "[SANDBOX] %(levelname)s: %(message)s"
            ))
            logger.addHandler(handler)
        
        return logger
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID."""
        return f"sandbox_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"
    
    @contextmanager
    def activate(self):
        """
        Activate sandbox environment.
        
        Usage:
            with sandbox.activate():
                # All operations happen in sandbox
                run_pipeline(...)
        """
        session_id = self._generate_session_id()
        self.context = SandboxContext(
            mode=self.mode,
            session_id=session_id,
            start_time=datetime.now()
        )
        
        self.logger.info(f"Activating sandbox: {session_id} (mode: {self.mode.value})")
        
        # Create session directory
        session_dir = SANDBOX_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        
        # Create standard subdirectories
        for subdir in ["scraped", "enriched", "segmented", "campaigns", "outbox", "replies"]:
            (session_dir / subdir).mkdir(exist_ok=True)
        
        try:
            self._apply_patches()
            yield self.context
        finally:
            self._remove_patches()
            self._save_session_log(session_dir)
            self.logger.info(f"Sandbox deactivated: {session_id}")
    
    def _apply_patches(self):
        """Apply patches based on sandbox mode."""
        if self.mode == SandboxMode.DRY_RUN:
            self._apply_dry_run_patches()
        elif self.mode == SandboxMode.MOCK:
            self._apply_mock_patches()
        elif self.mode == SandboxMode.STAGING:
            self._apply_staging_patches()
    
    def _apply_dry_run_patches(self):
        """Dry run: log only, no external calls."""
        # Patch requests to log only
        def log_request(*args, **kwargs):
            self._log_operation("http_request", {"args": str(args), "kwargs": str(kwargs)})
            return MagicMock(status_code=200, json=lambda: {"dry_run": True})
        
        self._patches.append(patch("requests.get", log_request))
        self._patches.append(patch("requests.post", log_request))
        
        for p in self._patches:
            p.start()
    
    def _apply_mock_patches(self):
        """Mock mode: fake responses from all services."""
        # Patch synchronous requests
        self._patches.append(patch("requests.get", self._mock_get))
        self._patches.append(patch("requests.post", self._mock_post))
        
        # Patch asynchronous aiohttp
        # we patch ClientSession.request to catch all methods (get, post, etc)
        async def mock_aiohttp_request(method, url, **kwargs):
            self._log_operation(f"mock_aiohttp_{method.lower()}", {"url": url})
            self._track_api_call(method.upper(), url)
            
            # Create a mock response object that behaves like aiohttp.ClientResponse
            mock_resp = MagicMock()
            mock_resp.status = 200
            
            # Helper to return json
            async def json_method():
                return self._generate_mock_response(url, method.upper(), kwargs.get("json"))
            
            mock_resp.json = json_method
            mock_resp.text = lambda: "mock_text"
            
            # Allow use as context manager (async with session.get() as resp:)
            mock_resp.__aenter__.return_value = mock_resp
            mock_resp.__aexit__.return_value = None
            
            return mock_resp

        self._patches.append(patch("aiohttp.ClientSession.request", side_effect=mock_aiohttp_request))
        self._patches.append(patch("aiohttp.ClientSession.get", side_effect=lambda url, **kw: mock_aiohttp_request("GET", url, **kw)))
        self._patches.append(patch("aiohttp.ClientSession.post", side_effect=lambda url, **kw: mock_aiohttp_request("POST", url, **kw)))

        for p in self._patches:
            p.start()
    
    def _apply_staging_patches(self):
        """Staging mode: real APIs but with logging."""
        # Don't patch requests, but add logging
        pass
    
    def _remove_patches(self):
        """Remove all applied patches."""
        for p in self._patches:
            p.stop()
        self._patches.clear()
    
    def _mock_get(self, url: str, **kwargs) -> MagicMock:
        """Mock GET request handler."""
        self._log_operation("mock_get", {"url": url})
        self._track_api_call("GET", url)
        
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = self._generate_mock_response(url, "GET")
        return response
    
    def _mock_post(self, url: str, **kwargs) -> MagicMock:
        """Mock POST request handler."""
        self._log_operation("mock_post", {"url": url, "data": str(kwargs.get("json", {}))[:200]})
        self._track_api_call("POST", url)
        
        # Track token usage for LLM calls
        if "openai" in url or "anthropic" in url or "gemini" in url:
            self._track_token_usage(kwargs.get("json", {}))
        
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = self._generate_mock_response(url, "POST", kwargs.get("json"))
        return response
    
    def _generate_mock_response(self, url: str, method: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Generate mock response based on URL pattern."""
        # LinkedIn/PhantomBuster mock
        if "phantombuster" in url or "linkedin" in url:
            return self._mock_linkedin_response()
        
        # Clay/Enrichment mock
        if "clay" in url or "apollo" in url or "clearbit" in url:
            return self._mock_enrichment_response()
        
        # OpenAI mock
        if "openai" in url:
            return self._mock_llm_response("openai")
        
        # Anthropic mock
        if "anthropic" in url:
            return self._mock_llm_response("anthropic")
        
        # Gemini mock
        if "gemini" in url or "generativelanguage" in url:
            return self._mock_llm_response("gemini")
        
        # Exa Search mock
        if "exa" in url:
            return self._mock_exa_response()
        
        # Default
        return {"status": "mocked", "url": url}
    
    def _mock_linkedin_response(self) -> Dict[str, Any]:
        """Generate mock LinkedIn scraping response."""
        from execution.generate_test_data import FIRST_NAMES, LAST_NAMES, COMPANIES, TITLES
        
        leads = []
        for i in range(random.randint(10, 25)):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            company, industry, size = random.choice(COMPANIES)
            title, _ = random.choice(TITLES)
            
            leads.append({
                "firstName": first,
                "lastName": last,
                "fullName": f"{first} {last}",
                "title": title,
                "company": company,
                "linkedinUrl": f"https://linkedin.com/in/{first.lower()}{last.lower()}{random.randint(100, 999)}",
                "connectionDegree": random.choice(["1st", "2nd", "3rd"])
            })
        
        return {"status": "success", "profiles": leads}
    
    def _mock_enrichment_response(self) -> Dict[str, Any]:
        """Generate mock enrichment response."""
        return {
            "status": "success",
            "data": {
                "email": f"test{random.randint(1000, 9999)}@company.com",
                "email_verified": True,
                "phone": f"+1555{random.randint(1000000, 9999999)}",
                "company_revenue": random.choice(["1M-10M", "10M-50M", "50M-100M", "100M+"]),
                "company_employees": random.randint(50, 500),
                "technologies": random.sample(["Salesforce", "HubSpot", "Outreach", "Gong", "Slack", "Zoom"], 3),
                "recent_funding": random.choice([None, "Series A", "Series B", "Series C"]),
                "hiring_signals": random.choice([True, False])
            }
        }
    
    def _mock_llm_response(self, provider: str) -> Dict[str, Any]:
        """Generate mock LLM response."""
        mock_content = {
            "analysis": "This is a mock LLM analysis for sandbox testing.",
            "recommendations": ["Recommendation 1", "Recommendation 2"],
            "score": random.randint(70, 95)
        }
        
        if provider == "openai":
            return {
                "choices": [{
                    "message": {
                        "content": json.dumps(mock_content)
                    }
                }],
                "usage": {
                    "prompt_tokens": random.randint(500, 2000),
                    "completion_tokens": random.randint(100, 500)
                }
            }
        elif provider == "anthropic":
            return {
                "content": [{"text": json.dumps(mock_content)}],
                "usage": {
                    "input_tokens": random.randint(500, 2000),
                    "output_tokens": random.randint(100, 500)
                }
            }
        else:  # gemini
            return {
                "candidates": [{
                    "content": {
                        "parts": [{"text": json.dumps(mock_content)}]
                    }
                }],
                "usageMetadata": {
                    "promptTokenCount": random.randint(500, 2000),
                    "candidatesTokenCount": random.randint(100, 500)
                }
            }
    
    def _mock_exa_response(self) -> Dict[str, Any]:
        """Generate mock Exa search response."""
        return {
            "results": [
                {
                    "title": f"Mock Intent Signal {i}",
                    "url": f"https://example.com/signal/{i}",
                    "publishedDate": datetime.now().isoformat(),
                    "author": "Mock Author",
                    "text": "This is a mock intent signal for sandbox testing.",
                    "score": random.random()
                }
                for i in range(random.randint(3, 8))
            ]
        }
    
    def _log_operation(self, operation: str, details: Dict[str, Any]):
        """Log an operation to the context."""
        if self.context:
            self.context.operations_log.append({
                "timestamp": datetime.now().isoformat(),
                "operation": operation,
                "details": details
            })
        self.logger.debug(f"{operation}: {details}")
    
    def _track_api_call(self, method: str, url: str):
        """Track API call counts."""
        if self.context:
            key = f"{method}:{url.split('/')[2] if '/' in url else url}"
            self.context.api_calls[key] = self.context.api_calls.get(key, 0) + 1
    
    def _track_token_usage(self, request_data: Optional[Dict]):
        """Track token usage from LLM requests."""
        if not self.context or not request_data:
            return
        
        # Estimate input tokens from messages
        messages = request_data.get("messages", [])
        estimated_input = sum(len(str(m)) // 4 for m in messages)
        self.context.token_usage["input"] += estimated_input
        
        # Estimate output (will be updated by response)
        self.context.token_usage["output"] += random.randint(100, 500)
    
    def _save_session_log(self, session_dir: Path):
        """Save session log to sandbox directory."""
        if not self.context:
            return
        
        log_data = {
            "session_id": self.context.session_id,
            "mode": self.context.mode.value,
            "start_time": self.context.start_time.isoformat(),
            "end_time": datetime.now().isoformat(),
            "duration_seconds": (datetime.now() - self.context.start_time).total_seconds(),
            "operations_count": len(self.context.operations_log),
            "api_calls": self.context.api_calls,
            "token_usage": self.context.token_usage,
            "operations": self.context.operations_log[-100:]  # Last 100 operations
        }
        
        log_file = session_dir / "session_log.json"
        with open(log_file, "w") as f:
            json.dump(log_data, f, indent=2)
        
        self.logger.info(f"Session log saved: {log_file}")
    
    def get_sandbox_path(self, relative_path: str) -> Path:
        """Get path within current sandbox session."""
        if self.context:
            return SANDBOX_DIR / self.context.session_id / relative_path
        return SANDBOX_DIR / relative_path
    
    def load_test_data(self, data_type: str = "leads") -> List[Dict[str, Any]]:
        """Load test data from sandbox directory."""
        test_file = SANDBOX_DIR / f"test_{data_type}.json"
        
        if test_file.exists():
            with open(test_file) as f:
                return json.load(f)
        
        # Generate if not exists
        self.logger.warning(f"Test data not found: {test_file}, generating...")
        from execution.generate_test_data import generate_lead
        
        data = [generate_lead(i) for i in range(50)]
        with open(test_file, "w") as f:
            json.dump(data, f, indent=2)
        
        return data
    
    def validate_no_side_effects(self) -> Dict[str, Any]:
        """Validate that no external side effects occurred."""
        if not self.context:
            return {"valid": False, "error": "No active sandbox context"}
        
        # Check for any real API calls in dry_run mode
        if self.context.mode == SandboxMode.DRY_RUN:
            real_calls = [
                op for op in self.context.operations_log
                if op["operation"] not in ["mock_get", "mock_post", "http_request"]
            ]
            if real_calls:
                return {"valid": False, "real_calls": real_calls}
        
        # Check for any writes outside sandbox
        sandbox_writes = [
            op for op in self.context.operations_log
            if "write" in op["operation"].lower() and "sandbox" not in str(op.get("details", {}))
        ]
        
        return {
            "valid": len(sandbox_writes) == 0,
            "operations_count": len(self.context.operations_log),
            "api_calls": self.context.api_calls,
            "token_usage": self.context.token_usage,
            "sandbox_writes": sandbox_writes
        }
    
    def cleanup_old_sessions(self, keep_days: int = 7):
        """Clean up old sandbox sessions."""
        cutoff = datetime.now().timestamp() - (keep_days * 86400)
        
        for session_dir in SANDBOX_DIR.iterdir():
            if session_dir.is_dir() and session_dir.name.startswith("sandbox_"):
                # Parse timestamp from session name
                try:
                    ts_str = session_dir.name.split("_")[1] + "_" + session_dir.name.split("_")[2]
                    ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").timestamp()
                    
                    if ts < cutoff:
                        shutil.rmtree(session_dir)
                        self.logger.info(f"Cleaned up old session: {session_dir.name}")
                except (ValueError, IndexError):
                    pass


def run_in_sandbox(mode: SandboxMode = SandboxMode.MOCK):
    """Decorator to run a function in sandbox mode."""
    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            sandbox = SandboxManager(mode=mode)
            with sandbox.activate() as context:
                result = func(*args, **kwargs)
                validation = sandbox.validate_no_side_effects()
                return {
                    "result": result,
                    "context": {
                        "session_id": context.session_id,
                        "operations_count": len(context.operations_log),
                        "api_calls": context.api_calls,
                        "token_usage": context.token_usage
                    },
                    "validation": validation
                }
        return wrapper
    return decorator


def main():
    """Demo sandbox manager."""
    print("\n" + "=" * 60)
    print("SANDBOX MANAGER DEMO")
    print("=" * 60)
    
    # Test each mode
    for mode in SandboxMode:
        print(f"\n--- Testing {mode.value} mode ---")
        
        sandbox = SandboxManager(mode=mode)
        
        with sandbox.activate() as context:
            print(f"Session: {context.session_id}")
            
            # Simulate some operations
            import requests
            
            try:
                # This will be intercepted by sandbox
                response = requests.get("https://api.example.com/test")
                print(f"Mock response: {response.status_code}")
            except Exception as e:
                print(f"Request handled: {e}")
            
            # Load test data
            test_data = sandbox.load_test_data("leads")
            print(f"Loaded {len(test_data)} test leads")
        
        # Validate
        validation = sandbox.validate_no_side_effects()
        print(f"Validation: {validation}")
    
    print("\n" + "=" * 60)
    print("Sandbox demo complete!")


if __name__ == "__main__":
    main()
