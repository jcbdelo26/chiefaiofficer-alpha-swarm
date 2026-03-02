#!/usr/bin/env python3
"""
Document freshness checker for CAIO Alpha Swarm.

Scans markdown files for YAML frontmatter `last_updated` field and
reports stale docs based on freshness policy.

Freshness policy:
  - runtime-truth / sprint-tracker canonical docs: 7 days max
  - All other docs with frontmatter: 30 days max

Usage:
  python scripts/check_doc_freshness.py           # check all docs
  python scripts/check_doc_freshness.py --warn-only  # exit 0 even if stale
  python scripts/check_doc_freshness.py --days 14    # override threshold
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Directories to scan for markdown files
SCAN_DIRS = [PROJECT_ROOT, PROJECT_ROOT / "docs"]
EXCLUDE_DIRS = {"archive", "google_drive_docs", "research", "revenue_swarm", ".git", "node_modules"}

# Frontmatter regex (matches YAML between --- delimiters)
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_DATE_RE = re.compile(r"last_updated:\s*['\"]?(\d{4}-\d{2}-\d{2})['\"]?")
_CANONICAL_RE = re.compile(r"canonical_for:\s*\[([^\]]*)\]")

# Freshness thresholds (days)
CRITICAL_THRESHOLD = 7   # runtime-truth, sprint-tracker
DEFAULT_THRESHOLD = 30   # everything else

CRITICAL_CANONICALS = {"runtime-truth", "deploy-state", "sprint-tracker", "task-status"}


def _parse_frontmatter(content: str) -> dict:
    """Extract last_updated and canonical_for from YAML frontmatter."""
    match = _FM_RE.match(content)
    if not match:
        return {}

    fm_text = match.group(1)
    result = {}

    date_match = _DATE_RE.search(fm_text)
    if date_match:
        result["last_updated"] = date_match.group(1)

    canon_match = _CANONICAL_RE.search(fm_text)
    if canon_match:
        canonicals = {c.strip().strip("'\"") for c in canon_match.group(1).split(",")}
        result["canonical_for"] = canonicals

    return result


def _check_file(file_path: Path, override_days: Optional[int] = None) -> Optional[dict]:
    """Check a single file for staleness. Returns violation dict or None."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return None

    fm = _parse_frontmatter(content)
    if "last_updated" not in fm:
        return None  # No frontmatter date — skip

    try:
        updated = datetime.strptime(fm["last_updated"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None

    now = datetime.now(timezone.utc)
    age_days = (now - updated).days

    canonicals = fm.get("canonical_for", set())
    is_critical = bool(canonicals & CRITICAL_CANONICALS)

    if override_days is not None:
        threshold = override_days
    elif is_critical:
        threshold = CRITICAL_THRESHOLD
    else:
        threshold = DEFAULT_THRESHOLD

    if age_days > threshold:
        return {
            "file": str(file_path.relative_to(PROJECT_ROOT)),
            "last_updated": fm["last_updated"],
            "age_days": age_days,
            "threshold": threshold,
            "is_critical": is_critical,
            "overdue_days": age_days - threshold,
        }

    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check document freshness based on YAML frontmatter last_updated."
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help="Exit 0 even if stale docs found (advisory mode)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Override freshness threshold (days) for all docs",
    )
    args = parser.parse_args()

    files_checked = 0
    stale = []

    for scan_dir in SCAN_DIRS:
        if not scan_dir.is_dir():
            continue
        # Only scan immediate .md files in root, recursive in docs/
        if scan_dir == PROJECT_ROOT:
            md_files = list(scan_dir.glob("*.md"))
        else:
            md_files = list(scan_dir.glob("**/*.md"))

        for md_file in md_files:
            # Skip excluded subdirs
            rel = md_file.relative_to(scan_dir)
            if any(part in EXCLUDE_DIRS for part in rel.parts):
                continue

            files_checked += 1
            violation = _check_file(md_file, override_days=args.days)
            if violation:
                stale.append(violation)

    if not stale:
        print(f"[PASS] {files_checked} docs checked, all within freshness thresholds.")
        return 0

    # Sort by overdue severity
    stale.sort(key=lambda v: v["overdue_days"], reverse=True)

    critical = [v for v in stale if v["is_critical"]]
    normal = [v for v in stale if not v["is_critical"]]

    label = "[WARN]" if args.warn_only else "[STALE]"
    print(f"{label} {len(stale)} stale doc(s) found ({files_checked} checked):\n")

    if critical:
        print("  CRITICAL (runtime-truth / sprint-tracker):")
        for v in critical:
            print(f"    {v['file']}: {v['age_days']}d old (threshold: {v['threshold']}d, overdue: +{v['overdue_days']}d)")
        print()

    if normal:
        print("  Standard:")
        for v in normal:
            print(f"    {v['file']}: {v['age_days']}d old (threshold: {v['threshold']}d, overdue: +{v['overdue_days']}d)")
        print()

    print("Fix: Update the `last_updated` field in each file's YAML frontmatter.")

    return 0 if args.warn_only else 1


if __name__ == "__main__":
    raise SystemExit(main())
