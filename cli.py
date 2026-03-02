#!/usr/bin/env python3
"""
Unified CLI entry point for CAIO Alpha Swarm.

Delegates to existing scripts — zero new logic.

Usage:
  python cli.py <command> [args...]
  python cli.py --help
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# Command -> (script_path_relative_to_root, description)
COMMANDS = {
    "deploy": ("scripts/deploy_shadow_mode.py", "Deploy shadow mode pipeline"),
    "validate": ("scripts/validate_apis.py", "Validate API integrations"),
    "health": ("scripts/check_health.py", "Check system health"),
    "canary": ("scripts/canary_lane_b.py", "Run Lane B canary tests (synthetic leads)"),
    "approve": ("scripts/approval_cli.py", "CLI approval workflow"),
    "smoke": ("scripts/deployed_full_smoke_checklist.py", "Run deployed smoke checklist"),
    "smoke-auth": ("scripts/strict_auth_parity_smoke.py", "Run N1-N7 strict-auth parity smoke"),
    "smoke-all": ("scripts/smoke_all.py", "Run all smoke tests in sequence"),
    "ascii": ("scripts/check_ascii.py", "Check production code for non-ASCII characters"),
    "freshness": ("scripts/check_doc_freshness.py", "Check document freshness (YAML frontmatter)"),
    "validate-ui": ("scripts/validate_dashboard_ui.py", "Validate dashboard UI endpoints"),
    "diagnose": ("scripts/diagnose.py", "Diagnose pipeline/deployment failures"),
    "lesson": ("scripts/capture_lesson.py", "Capture a lesson learned"),
}


def _print_help():
    print("CAIO Alpha Swarm CLI")
    print(f"Usage: python cli.py <command> [args...]\n")
    print("Available commands:\n")
    max_cmd = max(len(c) for c in COMMANDS)
    for cmd, (script, desc) in sorted(COMMANDS.items()):
        script_path = PROJECT_ROOT / script
        status = "" if script_path.exists() else " [not yet implemented]"
        print(f"  {cmd:<{max_cmd + 2}} {desc}{status}")
    print(f"\nRun 'python cli.py <command> --help' for command-specific options.")


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        _print_help()
        return 0

    command = sys.argv[1]

    if command not in COMMANDS:
        print(f"Unknown command: {command}")
        print(f"Run 'python cli.py --help' for available commands.")
        return 1

    script_rel, _ = COMMANDS[command]
    script_path = PROJECT_ROOT / script_rel

    if not script_path.exists():
        print(f"Command '{command}' is not yet implemented.")
        print(f"Expected script: {script_rel}")
        return 1

    # Delegate to the target script, passing through remaining args
    result = subprocess.run(
        [sys.executable, str(script_path)] + sys.argv[2:],
        cwd=str(PROJECT_ROOT),
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
