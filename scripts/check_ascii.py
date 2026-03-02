#!/usr/bin/env python3
"""
ASCII-only enforcement for production Python code.

Scans .py files in core/, execution/, dashboard/, config/, and webhooks/
for non-ASCII characters. Fails with exit code 1 if any are found.

Background: Windows cp1252 crashes caused by emoji/unicode in production
code (gatekeeper_queue.py had 24 emojis). This script prevents
reintroduction via pre-commit.

Usage:
  python scripts/check_ascii.py            # scan production dirs
  python scripts/check_ascii.py --staged   # scan only git-staged .py files
  python scripts/check_ascii.py --fix      # show suggested replacements
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
from pathlib import Path

# Force UTF-8 stdout on Windows to avoid cp1252 crashes when printing violations
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PRODUCTION_DIRS = ["core", "execution", "dashboard", "config", "webhooks"]

# Directories always excluded from scanning
EXCLUDE_DIRS = {"__pycache__", ".venv", "venv", "node_modules", ".git"}

# Common replacements for non-ASCII characters found in Python code
REPLACEMENTS = {
    "\u2714": "[OK]",      # check mark
    "\u2718": "[FAIL]",    # cross mark
    "\u2705": "[OK]",      # white check mark
    "\u274c": "[FAIL]",    # cross mark
    "\u26a0": "[WARN]",    # warning sign
    "\U0001f4cb": "",      # clipboard
    "\U0001f3e5": "",      # hospital
    "\u2192": "->",        # right arrow
    "\u2190": "<-",        # left arrow
    "\u2026": "...",       # ellipsis
    "\u00a0": " ",         # non-breaking space
}


def is_ascii(text: str) -> bool:
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def find_non_ascii(file_path: Path, show_fix: bool = False) -> list[dict]:
    """Find non-ASCII characters in a file. Returns list of violations."""
    violations = []
    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return violations

    for line_num, line in enumerate(content.splitlines(), start=1):
        if is_ascii(line):
            continue
        for col, char in enumerate(line, start=1):
            if ord(char) > 127:
                entry = {
                    "file": str(file_path.relative_to(PROJECT_ROOT)),
                    "line": line_num,
                    "col": col,
                    "char": char,
                    "codepoint": f"U+{ord(char):04X}",
                    "context": line.strip()[:80],
                }
                if show_fix and char in REPLACEMENTS:
                    entry["suggested"] = REPLACEMENTS[char]
                violations.append(entry)
    return violations


def get_staged_py_files() -> list[Path]:
    """Get list of staged .py files from git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        files = []
        for name in result.stdout.strip().splitlines():
            if name.endswith(".py"):
                p = PROJECT_ROOT / name
                if p.exists():
                    files.append(p)
        return files
    except Exception:
        return []


def get_production_py_files() -> list[Path]:
    """Get all .py files in production directories."""
    files = []
    for dir_name in PRODUCTION_DIRS:
        dir_path = PROJECT_ROOT / dir_name
        if not dir_path.is_dir():
            continue
        for py_file in dir_path.rglob("*.py"):
            if not any(part in EXCLUDE_DIRS for part in py_file.parts):
                files.append(py_file)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan production Python files for non-ASCII characters."
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Only scan git-staged .py files",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Show suggested ASCII replacements",
    )
    args = parser.parse_args()

    if args.staged:
        files = get_staged_py_files()
        # Filter to production dirs only
        prod_prefixes = tuple(
            str(PROJECT_ROOT / d) for d in PRODUCTION_DIRS
        )
        files = [f for f in files if str(f).startswith(prod_prefixes)]
    else:
        files = get_production_py_files()

    if not files:
        print(f"No .py files to scan in {PRODUCTION_DIRS}")
        return 0

    all_violations = []
    for f in sorted(files):
        all_violations.extend(find_non_ascii(f, show_fix=args.fix))

    if not all_violations:
        print(f"[PASS] {len(files)} production .py files are ASCII-clean.")
        return 0

    # Group by file
    by_file: dict[str, list] = {}
    for v in all_violations:
        by_file.setdefault(v["file"], []).append(v)

    print(f"[FAIL] Found {len(all_violations)} non-ASCII character(s) "
          f"in {len(by_file)} file(s):\n")

    for file_path, violations in sorted(by_file.items()):
        print(f"  {file_path}:")
        for v in violations:
            fix_hint = ""
            if "suggested" in v:
                fix_hint = f" -> replace with: {v['suggested']!r}"
            print(f"    line {v['line']}:{v['col']}  "
                  f"{v['codepoint']} ({v['char']!r}){fix_hint}")
            print(f"      {v['context']}")
        print()

    print("Fix: Replace non-ASCII characters with ASCII equivalents.")
    print("Run with --fix to see suggested replacements.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
