#!/usr/bin/env python3
"""
Capture a lesson learned and append it to docs/LESSONS_LEARNED.md.

Agents and engineers call this after resolving bugs, discovering gotchas,
or completing sprints to build a compound knowledge base.

Usage:
  python scripts/capture_lesson.py --category api --description "Apollo fuzzy matching returns competitors"
  python scripts/capture_lesson.py --category deployment --description "Missing itsdangerous in requirements.txt caused Railway 502"
  python scripts/capture_lesson.py --category data --description "shadow_queue prefix mismatch between local and Railway"
  python scripts/capture_lesson.py --list
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LESSONS_FILE = PROJECT_ROOT / "docs" / "LESSONS_LEARNED.md"

VALID_CATEGORIES = ["api", "deployment", "data", "testing", "security", "pipeline", "dashboard", "other"]


def _get_commit_hash() -> str:
    """Get current git HEAD short hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=str(PROJECT_ROOT),
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _ensure_lessons_file():
    """Create LESSONS_LEARNED.md if it doesn't exist."""
    if LESSONS_FILE.exists():
        return
    LESSONS_FILE.write_text(
        "---\n"
        "title: Lessons Learned\n"
        'version: "1.0"\n'
        f"last_updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n"
        "audience: [all-agents, engineers]\n"
        "tags: [lessons, gotchas, debugging, compound]\n"
        "canonical_for: [lessons-learned]\n"
        "---\n\n"
        "# CAIO Alpha Swarm -- Lessons Learned\n\n"
        "Compound knowledge base. Entries added via `python scripts/capture_lesson.py`.\n\n"
        "---\n\n",
        encoding="utf-8",
    )


def _append_lesson(category: str, description: str, commit: str):
    """Append a lesson entry to the file."""
    _ensure_lessons_file()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"### [{date_str}] {category.upper()} (commit `{commit}`)\n\n"
        f"{description}\n\n"
        f"---\n\n"
    )
    with open(LESSONS_FILE, "a", encoding="utf-8") as f:
        f.write(entry)
    print(f"Lesson captured: [{category}] {description[:80]}...")
    print(f"  File: {LESSONS_FILE.relative_to(PROJECT_ROOT)}")


def _list_lessons():
    """Print existing lessons summary."""
    if not LESSONS_FILE.exists():
        print("No lessons captured yet.")
        return
    content = LESSONS_FILE.read_text(encoding="utf-8")
    # Count entries by looking for ### headers
    entries = [line for line in content.splitlines() if line.startswith("### [")]
    print(f"Total lessons: {len(entries)}")
    for entry in entries:
        print(f"  {entry}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture a lesson learned to docs/LESSONS_LEARNED.md."
    )
    parser.add_argument("--category", choices=VALID_CATEGORIES,
                        help=f"Lesson category: {', '.join(VALID_CATEGORIES)}")
    parser.add_argument("--description", help="What was learned (1-3 sentences).")
    parser.add_argument("--commit", help="Override commit hash (default: current HEAD).")
    parser.add_argument("--list", action="store_true", help="List existing lessons.")
    args = parser.parse_args()

    if args.list:
        _list_lessons()
        return 0

    if not args.category or not args.description:
        parser.error("--category and --description are required (or use --list).")

    commit = args.commit or _get_commit_hash()
    _append_lesson(args.category, args.description, commit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
