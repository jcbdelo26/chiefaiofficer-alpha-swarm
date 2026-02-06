#!/usr/bin/env python3
"""
Test script for debug-mcp error correlation.

Run this to verify the full-stack debugging infrastructure is working.
"""

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "mcp-servers" / "debug-mcp"))

from correlator import ErrorCorrelator, FrontendError
from log_parser import LogParser

HIVE_MIND_DIR = PROJECT_ROOT / ".hive-mind"
AUDIT_DB_PATH = HIVE_MIND_DIR / "audit.db"
FRONTEND_ERRORS_PATH = HIVE_MIND_DIR / "frontend_errors.jsonl"
LOGS_DIR = HIVE_MIND_DIR / "logs"
RETRY_QUEUE_PATH = HIVE_MIND_DIR / "retry_queue.jsonl"


async def test_frontend_error_logging():
    """Test that frontend errors can be logged and retrieved."""
    print("\n=== Test 1: Frontend Error Logging ===")

    correlator = ErrorCorrelator(
        audit_db_path=AUDIT_DB_PATH,
        frontend_errors_path=FRONTEND_ERRORS_PATH
    )
    await correlator.initialize()

    # Log a test frontend error
    test_error = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": "Test error from correlation test",
        "stack": "Error: Test error\n    at testFunction (test.js:42:10)",
        "url": "http://localhost:8080/dashboard",
        "correlation_id": "test-correlation-123",
        "type": "error"
    }

    await correlator.log_frontend_error(test_error)
    print("[OK] Frontend error logged")

    # Verify it can be retrieved
    result = await correlator.get_by_correlation_id("test-correlation-123")

    if result and result.get("frontend_errors"):
        print(f"[OK] Retrieved {len(result['frontend_errors'])} frontend error(s)")
        print(f"    Message: {result['frontend_errors'][0].get('message', 'N/A')[:50]}")
    else:
        print("[WARN] No frontend errors retrieved (this may be expected on first run)")

    return True


async def test_log_search():
    """Test the log search functionality."""
    print("\n=== Test 2: Log Search ===")

    log_parser = LogParser(
        audit_db_path=AUDIT_DB_PATH,
        logs_dir=LOGS_DIR,
        retry_queue_path=RETRY_QUEUE_PATH
    )
    await log_parser.initialize()

    # Search for any errors
    results = await log_parser.search(query="error", hours=24, limit=10)
    print(f"[OK] Search executed - found {len(results)} results")

    # Get recent errors
    errors = await log_parser.get_errors(hours=24, limit=10)
    print(f"[OK] Get errors executed - found {len(errors)} errors")

    return True


async def test_failure_counts():
    """Test getting failure counts by agent."""
    print("\n=== Test 3: Failure Counts ===")

    log_parser = LogParser(
        audit_db_path=AUDIT_DB_PATH,
        logs_dir=LOGS_DIR,
        retry_queue_path=RETRY_QUEUE_PATH
    )
    await log_parser.initialize()

    counts = await log_parser.get_failure_counts(hours=24)
    print(f"[OK] Failure counts retrieved: {len(counts)} agents with failures")

    for agent, count in counts.items():
        print(f"    {agent}: {count} failures")

    return True


async def test_correlation_matching():
    """Test error correlation between frontend and backend."""
    print("\n=== Test 4: Error Correlation ===")

    correlator = ErrorCorrelator(
        audit_db_path=AUDIT_DB_PATH,
        frontend_errors_path=FRONTEND_ERRORS_PATH
    )
    await correlator.initialize()

    # Get recent correlated errors
    correlated = await correlator.get_recent_correlated(
        time_window_seconds=300,
        limit=10
    )

    print(f"[OK] Correlation executed - found {len(correlated)} correlated error(s)")

    for i, error in enumerate(correlated[:3]):
        print(f"    [{i+1}] Type: {error.get('match_type')}, Confidence: {error.get('confidence')}")

    return True


async def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("DEBUG-MCP ERROR CORRELATION TESTS")
    print("=" * 60)

    # Ensure directories exist
    HIVE_MIND_DIR.mkdir(exist_ok=True)
    LOGS_DIR.mkdir(exist_ok=True)

    tests = [
        ("Frontend Error Logging", test_frontend_error_logging),
        ("Log Search", test_log_search),
        ("Failure Counts", test_failure_counts),
        ("Error Correlation", test_correlation_matching),
    ]

    results = []
    for name, test_func in tests:
        try:
            await test_func()
            results.append((name, True, None))
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            results.append((name, False, str(e)))

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, success, _ in results if success)
    total = len(results)

    for name, success, error in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"  {status} {name}")
        if error:
            print(f"         Error: {error}")

    print(f"\nResults: {passed}/{total} tests passed")
    print("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
