#!/usr/bin/env python3
"""
One-time migration utility: file state -> Redis state store.

Usage:
  python scripts/migrate_file_state_to_redis.py --hive-dir .hive-mind
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.state_store import StateStore


def _read_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def migrate(hive_dir: Path, dry_run: bool = False) -> Dict[str, Any]:
    store = StateStore(hive_dir=hive_dir)
    summary: Dict[str, Any] = {
        "hive_dir": str(hive_dir),
        "backend": store.backend,
        "redis_available": bool(getattr(store, "_redis_client", None) is not None),
        "dry_run": dry_run,
        "operator_state_migrated": 0,
        "batches_migrated": 0,
        "cadence_states_migrated": 0,
        "errors": [],
    }

    # operator daily state
    operator_state_file = hive_dir / "operator_state.json"
    operator_payload = _read_json(operator_state_file)
    if operator_payload and operator_payload.get("date"):
        if not dry_run:
            try:
                store.save_operator_daily_state(str(operator_payload["date"]), operator_payload)
                summary["operator_state_migrated"] = 1
            except Exception as exc:
                summary["errors"].append(f"operator_state: {exc}")
        else:
            summary["operator_state_migrated"] = 1

    # operator batches
    batch_dir = hive_dir / "operator_batches"
    if batch_dir.exists():
        for batch_file in batch_dir.glob("batch_*.json"):
            payload = _read_json(batch_file)
            if not payload:
                continue
            batch_id = str(payload.get("batch_id") or batch_file.stem).strip()
            if not batch_id:
                continue
            if not dry_run:
                try:
                    store.save_batch(batch_id, payload)
                    summary["batches_migrated"] += 1
                except Exception as exc:
                    summary["errors"].append(f"batch:{batch_id}: {exc}")
            else:
                summary["batches_migrated"] += 1

    # cadence state
    cadence_dir = hive_dir / "cadence_state"
    if cadence_dir.exists():
        for cadence_file in cadence_dir.glob("*.json"):
            payload = _read_json(cadence_file)
            if not payload:
                continue
            email = str(payload.get("email", "")).strip()
            if not email:
                continue
            if not dry_run:
                try:
                    store.save_cadence_lead_state(email, payload)
                    summary["cadence_states_migrated"] += 1
                except Exception as exc:
                    summary["errors"].append(f"cadence:{email}: {exc}")
            else:
                summary["cadence_states_migrated"] += 1

    summary["ok"] = len(summary["errors"]) == 0
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate CAIO file state into Redis-backed state store.")
    parser.add_argument("--hive-dir", default=".hive-mind", help="Path to hive state directory.")
    parser.add_argument("--dry-run", action="store_true", help="Preview migration counts without writing.")
    args = parser.parse_args()

    hive_dir = Path(args.hive_dir)
    if not hive_dir.is_absolute():
        hive_dir = (PROJECT_ROOT / hive_dir).resolve()
    hive_dir.mkdir(parents=True, exist_ok=True)

    summary = migrate(hive_dir=hive_dir, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2))
    return 0 if summary.get("ok", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
