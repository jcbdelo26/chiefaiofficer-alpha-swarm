#!/usr/bin/env python3
"""
Unified smoke test orchestrator for CAIO Alpha Swarm.

Runs all smoke tests in sequence against a deployed instance and
reports combined pass/fail results.

Scripts executed (in order):
  1. scripts/deployed_full_smoke_checklist.py
  2. scripts/strict_auth_parity_smoke.py
  3. scripts/validate_dashboard_ui.py

Usage:
  python scripts/smoke_all.py --base-url <URL> --token <TOKEN>
  python scripts/smoke_all.py --base-url <URL> --token <TOKEN> --timeout 30
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SMOKE_SCRIPTS = [
    {
        "name": "deployed_full_smoke_checklist",
        "script": "scripts/deployed_full_smoke_checklist.py",
        "args_template": ["--base-url", "{base_url}", "--token", "{token}"],
    },
    {
        "name": "strict_auth_parity_smoke",
        "script": "scripts/strict_auth_parity_smoke.py",
        "args_template": ["--base-url", "{base_url}", "--token", "{token}", "--timeout", "{timeout}"],
    },
    {
        "name": "validate_dashboard_ui",
        "script": "scripts/validate_dashboard_ui.py",
        "args_template": ["--base-url", "{base_url}", "--token", "{token}", "--timeout", "{timeout}"],
    },
]


def _run_script(
    script_rel: str,
    args: list[str],
    timeout_sec: int = 120,
) -> dict:
    """Run a smoke script and capture result."""
    script_path = PROJECT_ROOT / script_rel

    if not script_path.exists():
        return {
            "name": script_rel,
            "status": "skipped",
            "reason": f"Script not found: {script_rel}",
            "exit_code": None,
        }

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)] + args,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=str(PROJECT_ROOT),
        )
        return {
            "name": script_rel,
            "status": "passed" if result.returncode == 0 else "failed",
            "exit_code": result.returncode,
            "stdout_tail": result.stdout[-500:] if result.stdout else "",
            "stderr_tail": result.stderr[-500:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {
            "name": script_rel,
            "status": "timeout",
            "exit_code": None,
            "reason": f"Timed out after {timeout_sec}s",
        }
    except Exception as exc:
        return {
            "name": script_rel,
            "status": "error",
            "exit_code": None,
            "reason": str(exc),
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run all smoke tests against a deployed CAIO instance."
    )
    parser.add_argument("--base-url", required=True, help="Deployed dashboard base URL.")
    parser.add_argument("--token", required=True, help="Dashboard auth token.")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout per request (passed to sub-scripts).")
    parser.add_argument("--script-timeout", type=int, default=120, help="Max seconds per script execution.")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable.")
    args = parser.parse_args()

    results = []
    for spec in SMOKE_SCRIPTS:
        script_args = [
            a.format(base_url=args.base_url, token=args.token, timeout=str(args.timeout))
            for a in spec["args_template"]
        ]

        print(f"--- Running: {spec['name']} ---")
        result = _run_script(spec["script"], script_args, timeout_sec=args.script_timeout)
        result["name"] = spec["name"]
        results.append(result)

        status_str = result["status"].upper()
        print(f"    Result: {status_str}")
        if result.get("reason"):
            print(f"    Reason: {result['reason']}")
        print()

    # Summary
    all_passed = all(r["status"] == "passed" for r in results)
    passed_count = sum(1 for r in results if r["status"] == "passed")
    total = len(results)

    summary = {
        "base_url": args.base_url.rstrip("/"),
        "all_passed": all_passed,
        "passed": passed_count,
        "total": total,
        "results": results,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("=" * 50)
        print(f"SMOKE TEST SUMMARY: {passed_count}/{total} passed")
        print("=" * 50)
        for r in results:
            icon = "PASS" if r["status"] == "passed" else "FAIL"
            print(f"  [{icon}] {r['name']}")
        print()
        if all_passed:
            print("All smoke tests PASSED.")
        else:
            failed = [r for r in results if r["status"] != "passed"]
            print(f"{len(failed)} script(s) did not pass. Review output above.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
