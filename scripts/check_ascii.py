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


def get_staged_diff_added_lines() -> dict[Path, set[int]]:
    """Get line numbers of added/changed lines in staged .py files.

    Returns a dict mapping file paths to sets of line numbers that were
    added or modified in the staged diff. This allows checking ONLY new
    content, not pre-existing non-ASCII in files being modified.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "-U0", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
            cwd=str(PROJECT_ROOT),
        )
        added_lines: dict[Path, set[int]] = {}
        current_file = None
        for line in result.stdout.splitlines():
            if line.startswith("+++ b/"):
                fname = line[6:]
                if fname.endswith(".py"):
                    current_file = PROJECT_ROOT / fname
                    if current_file not in added_lines:
                        added_lines[current_file] = set()
                else:
                    current_file = None
            elif line.startswith("@@ ") and current_file is not None:
                # Parse hunk header: @@ -old,count +new,count @@
                parts = line.split("+")[1].split(" ")[0]
                if "," in parts:
                    start, count = parts.split(",")
                    start, count = int(start), int(count)
                else:
                    start, count = int(parts), 1
                for i in range(start, start + count):
                    added_lines[current_file].add(i)
        return added_lines
    except Exception:
        return {}


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
        # Only check lines actually added/changed in the diff, not full file
        diff_lines = get_staged_diff_added_lines()
    else:
        files = get_production_py_files()
        diff_lines = {}  # empty = check all lines

    if not files:
        print(f"No .py files to scan in {PRODUCTION_DIRS}")
        return 0

    all_violations = []
    for f in sorted(files):
        violations = find_non_ascii(f, show_fix=args.fix)
        if diff_lines and f in diff_lines:
            # In staged mode: only report violations on new/changed lines
            violations = [v for v in violations if v["line"] in diff_lines[f]]
        elif diff_lines:
            # File is staged but no diff lines found — skip entirely
            violations = []
        all_violations.extend(violations)

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
