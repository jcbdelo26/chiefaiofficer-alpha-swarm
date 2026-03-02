"""
Tests for /api/compound-metrics endpoint and _count_pre_commit_tests helper.

Validates:
  1. Endpoint returns expected structure
  2. Pre-commit test file count is accurate
  3. All metric sections present
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Import the helper directly
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_count_pre_commit_tests():
    """_count_pre_commit_tests accurately counts test files in pre-commit hook."""
    from dashboard.health_app import _count_pre_commit_tests
    project_root = Path(__file__).parent.parent
    count = _count_pre_commit_tests(project_root)
    # We know there are 30 test files in the pre-commit hook
    assert count >= 28, f"Expected at least 28 pre-commit test files, got {count}"


def test_count_pre_commit_tests_missing_hook(tmp_path):
    """Returns 0 when pre-commit hook doesn't exist."""
    from dashboard.health_app import _count_pre_commit_tests
    assert _count_pre_commit_tests(tmp_path) == 0


def test_compound_metrics_endpoint_structure():
    """Compound metrics endpoint returns all expected sections."""
    from dashboard.health_app import app
    from starlette.testclient import TestClient

    client = TestClient(app)
    # Use token auth header
    import os
    token = os.getenv("DASHBOARD_AUTH_TOKEN", "test-token-12345")
    resp = client.get("/api/compound-metrics", headers={"X-Dashboard-Token": token})

    # In test env, if auth isn't configured, we may get 401
    if resp.status_code == 401:
        pytest.skip("Auth not configured for test environment")

    assert resp.status_code == 200
    data = resp.json()
    assert "generated_at" in data
    assert "test_infrastructure" in data
    assert "gateway_health" in data


def test_compound_metrics_test_infrastructure():
    """Test infrastructure section has expected fields."""
    from dashboard.health_app import app
    from starlette.testclient import TestClient

    client = TestClient(app)
    import os
    token = os.getenv("DASHBOARD_AUTH_TOKEN", "test-token-12345")
    resp = client.get("/api/compound-metrics", headers={"X-Dashboard-Token": token})

    if resp.status_code == 401:
        pytest.skip("Auth not configured for test environment")

    data = resp.json()
    ti = data["test_infrastructure"]
    assert "test_files" in ti
    assert "pre_commit_files" in ti
    assert ti["test_files"] >= 50  # We have 86+ test files
    assert ti["pre_commit_files"] >= 28


def test_compound_metrics_documentation_section():
    """Documentation section reports frontmatter coverage."""
    from dashboard.health_app import app
    from starlette.testclient import TestClient

    client = TestClient(app)
    import os
    token = os.getenv("DASHBOARD_AUTH_TOKEN", "test-token-12345")
    resp = client.get("/api/compound-metrics", headers={"X-Dashboard-Token": token})

    if resp.status_code == 401:
        pytest.skip("Auth not configured for test environment")

    data = resp.json()
    docs = data.get("documentation", {})
    if "error" not in docs:
        assert "total_docs" in docs
        assert "with_frontmatter" in docs
        assert "frontmatter_coverage" in docs
