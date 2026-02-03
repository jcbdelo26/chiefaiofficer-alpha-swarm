
"""
API Failure Scenarios
=====================
Test agent resilience against external API failures using the sandbox.
Focus: GHL (CRM), RB2B (Visitor ID), Instantly (Email), Clay (Enrichment).
"""

import pytest
import time
import requests
from threading import Thread
from core.failure_tracker import FailureTracker, FailureCategory

# Sandbox URLs (from sandbox.json)
SANDBOX_URLS = {
    "ghl": "http://localhost:8001",
    "rb2b": "http://localhost:8002",
    "instantly": "http://localhost:8003",
    "clay": "http://localhost:8004"
}

@pytest.fixture
def failure_tracker():
    return FailureTracker()

def set_sandbox_failure_mode(service, failure_type, rate=1.0):
    """Configure sandbox service to fail."""
    requests.post(f"{SANDBOX_URLS[service]}/admin/configure", json={
        "failure_injection": {
            "enabled": True,
            "rate": rate,
            "type": failure_type
        }
    })

def reset_sandbox(service):
    """Reset sandbox service to normal."""
    requests.post(f"{SANDBOX_URLS[service]}/admin/configure", json={
        "failure_injection": {"enabled": False}
    })

class TestAPIFailures:
    
    def setup_method(self):
        self.tracker = FailureTracker()
        for service in SANDBOX_URLS:
            try:
                reset_sandbox(service)
            except:
                pass # Service might not be running

    def test_ghl_rate_limit_handling(self):
        """Verify CRM agent handles 429 Rate Limit correctly."""
        set_sandbox_failure_mode("ghl", "rate_limit", rate=1.0)
        
        # Simulate agent action
        try:
            resp = requests.get(f"{SANDBOX_URLS['ghl']}/contacts")
            resp.raise_for_status()
        except Exception as e:
            failure_id = self.tracker.log_failure(
                agent="CRM_AGENT",
                task_id="test_ghl_429",
                error=e,
                context={"endpoint": "/contacts"}
            )
            
        # Verify failure logged as API_ERROR
        failure = self.tracker.get_failure(failure_id)
        assert failure is not None
        assert failure.category == FailureCategory.API_ERROR.value
        assert "429" in failure.error_message

    def test_clay_enrichment_timeout(self):
        """Verify Enricher agent handles timeout independently."""
        set_sandbox_failure_mode("clay", "timeout", rate=1.0)
        
        try:
            resp = requests.post(f"{SANDBOX_URLS['clay']}/enrich", json={"domain": "test.com"}, timeout=2)
        except Exception as e:
            failure_id = self.tracker.log_failure(
                agent="ENRICHER",
                task_id="test_clay_timeout",
                error=e,
                context={"domain": "test.com"}
            )
            
        failure = self.tracker.get_failure(failure_id)
        assert failure.category == FailureCategory.API_ERROR.value
        assert "Read timed out" in str(failure.error_message)

    def test_instantly_server_error_recovery(self):
        """Verify Campaign agent retries on 500 error."""
        set_sandbox_failure_mode("instantly", "server_error", rate=1.0)
        
        failures = []
        # Simulate 3 retries
        for i in range(3):
            try:
                resp = requests.post(f"{SANDBOX_URLS['instantly']}/leads")
                resp.raise_for_status()
            except Exception as e:
                failures.append(e)
                time.sleep(0.1)
                
        # Log final failure
        failure_id = self.tracker.log_failure(
            agent="CRAFTER",
            task_id="test_instantly_500",
            error=failures[-1],
            context={"retry_count": 3}
        )
        
        failure = self.tracker.get_failure(failure_id)
        assert failure.category == FailureCategory.API_ERROR.value
        assert "500 Server Error" in str(failure.error_message)

    def teardown_method(self):
        for service in SANDBOX_URLS:
            try:
                reset_sandbox(service)
            except:
                pass
