#!/usr/bin/env python3
"""
Unified CLI entry point for CAIO Alpha Swarm.

Delegates to existing scripts and provides script discovery.

Usage:
  python cli.py <command> [args...]
  python cli.py list                     # Show all scripts
  python cli.py list --search smoke      # Filter by keyword
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

# Prefix -> category for script discovery
_CATEGORIES = [
    ("check_", "Validation"),
    ("validate_", "Validation"),
    ("verify_", "Validation"),
    ("smoke", "Smoke Tests"),
    ("endpoint_auth", "Smoke Tests"),
    ("webhook_strict", "Smoke Tests"),
    ("deployed_full", "Smoke Tests"),
    ("strict_auth", "Smoke Tests"),
    ("debug_", "Diagnostics"),
    ("diagnose", "Diagnostics"),
    ("inspect_", "Diagnostics"),
    ("trace_", "Diagnostics"),
    ("quick_", "Diagnostics"),
    ("metrics_", "Diagnostics"),
    ("read_", "Diagnostics"),
    ("setup_", "Setup"),
    ("register_", "Setup"),
    ("linkedin_auth", "Setup"),
    ("bootstrap_", "Setup"),
    ("deploy_", "Deployment"),
    ("migrate_", "Deployment"),
    ("canary_", "Pipeline"),
    ("approval_", "Pipeline"),
    ("cleanup_", "Pipeline"),
    ("simulate_", "Pipeline"),
    ("fix_", "Pipeline"),
    ("run_", "Pipeline"),
    ("ingest_", "Pipeline"),
    ("replay_", "Testing"),
    ("regression_", "Testing"),
    ("full_system", "Testing"),
    ("benchmark_", "Testing"),
    ("swarm_replay", "Testing"),
    ("test_", "Testing"),
    ("generate_", "Reporting"),
    ("weekly_", "Reporting"),
    ("capture_", "Reporting"),
]


def _extract_description(script_path: Path) -> str:
    """Extract first meaningful line from script docstring."""
    try:
        content = script_path.read_text(encoding="utf-8", errors="replace")
        in_docstring = False
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith('"""') and not in_docstring:
                if stripped.count('"""') >= 2:
                    return stripped.strip('"').strip()
                in_docstring = True
                continue
            if in_docstring:
                if stripped == '"""':
                    break
                if stripped and not stripped.startswith("="):
                    return stripped[:80]
    except Exception:
        pass
    return "(no description)"


def _get_cli_alias(script_path: Path) -> str | None:
    """Return CLI alias for a script if one exists."""
    for cmd, (rel, _) in COMMANDS.items():
        if rel and (PROJECT_ROOT / rel).resolve() == script_path.resolve():
            return cmd
    return None


def _categorize(name: str) -> str:
    """Assign a category based on script name prefix."""
    for prefix, category in _CATEGORIES:
        if name.startswith(prefix):
            return category
    return "Other"


def _list_all_scripts(search: str | None = None) -> int:
    """Scan scripts/ directory and print categorized inventory."""
    scripts_dir = PROJECT_ROOT / "scripts"
    if not scripts_dir.is_dir():
        print("scripts/ directory not found.")
        return 1

    categorized: dict[str, list[tuple[str, str, str | None]]] = {}
    for script_path in sorted(scripts_dir.glob("*.py")):
        name = script_path.stem
        desc = _extract_description(script_path)
        alias = _get_cli_alias(script_path)

        if search:
            haystack = f"{name} {desc} {alias or ''}".lower()
            if search.lower() not in haystack:
                continue

        cat = _categorize(name)
        categorized.setdefault(cat, []).append((name, desc, alias))

    total = sum(len(v) for v in categorized.values())
    cli_count = sum(
        1 for scripts in categorized.values()
        for _, _, a in scripts if a
    )

    if total == 0:
        if search:
            print(f"No scripts matching '{search}'.")
        else:
            print("No scripts found.")
        return 0

    header = f"CAIO Alpha Swarm -- Script Inventory ({total} scripts, {cli_count} with CLI aliases)"
    if search:
        header += f"  [filter: '{search}']"
    print(header)
    print()

    for cat in sorted(categorized.keys()):
        print(f"  {cat}:")
        for name, desc, alias in categorized[cat]:
            alias_tag = f" [cli: {alias}]" if alias else ""
            print(f"    {name}.py{alias_tag} -- {desc}")
        print()

    return 0


def _print_help():
    print("CAIO Alpha Swarm CLI")
    print(f"Usage: python cli.py <command> [args...]\n")
    print("Available commands:\n")
    max_cmd = max(len(c) for c in COMMANDS)
    for cmd, (script, desc) in sorted(COMMANDS.items()):
        script_path = PROJECT_ROOT / script
        status = "" if script_path.exists() else " [not yet implemented]"
        print(f"  {cmd:<{max_cmd + 2}} {desc}{status}")
    print()
    print("Discovery:")
    print(f"  {'list':<{max_cmd + 2}} List all scripts with descriptions")
    print(f"\nRun 'python cli.py <command> --help' for command-specific options.")
    print(f"Run 'python cli.py list --search <keyword>' to find scripts.")


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        _print_help()
        return 0

    command = sys.argv[1]

    # Handle 'list' specially — no script delegation
    if command == "list":
        search = None
        args = sys.argv[2:]
        if "--search" in args:
            idx = args.index("--search")
            if idx + 1 < len(args):
                search = args[idx + 1]
        return _list_all_scripts(search)

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
