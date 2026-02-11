#!/usr/bin/env python3
"""
Bootstrap Redis/Inngest runtime reliability settings in an env file.

Usage example:
  python scripts/bootstrap_runtime_reliability.py \
    --mode production \
    --env-file .env \
    --redis-url redis://default:password@host:6379/0 \
    --inngest-signing-key signkey-prod-xxx \
    --inngest-event-key eventkey-prod-xxx \
    --validate --check-connections
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.runtime_reliability import (
    get_runtime_dependency_health,
    merge_runtime_env_values,
    normalize_mode,
    upsert_env_file,
)


def _resolve_required_flag(flag: str, mode: str) -> bool:
    if flag == "true":
        return True
    if flag == "false":
        return False
    return mode in {"staging", "production"}


def _collect_overrides(args: argparse.Namespace) -> Dict[str, str]:
    overrides: Dict[str, str] = {}
    if args.redis_url is not None:
        overrides["REDIS_URL"] = args.redis_url
    if args.inngest_signing_key is not None:
        overrides["INNGEST_SIGNING_KEY"] = args.inngest_signing_key
    if args.inngest_event_key is not None:
        overrides["INNGEST_EVENT_KEY"] = args.inngest_event_key
    if args.inngest_app_id is not None:
        overrides["INNGEST_APP_ID"] = args.inngest_app_id
    if args.inngest_webhook_url is not None:
        overrides["INNGEST_WEBHOOK_URL"] = args.inngest_webhook_url
    return overrides


def _validate_bootstrap_inputs(values: Dict[str, str], *, allow_placeholders: bool) -> list[str]:
    errors: list[str] = []

    redis_required = values.get("REDIS_REQUIRED", "false").lower() == "true"
    inngest_required = values.get("INNGEST_REQUIRED", "false").lower() == "true"
    redis_url = values.get("REDIS_URL", "").strip()
    signing_key = values.get("INNGEST_SIGNING_KEY", "").strip()
    event_key = values.get("INNGEST_EVENT_KEY", "").strip()

    if redis_required:
        if not redis_url:
            if not allow_placeholders:
                errors.append("REDIS_REQUIRED=true but REDIS_URL is empty")
        elif not allow_placeholders and "localhost" in redis_url:
            errors.append("REDIS_REQUIRED=true but REDIS_URL points to localhost")

    if inngest_required:
        if not signing_key or not event_key:
            if not allow_placeholders:
                errors.append("INNGEST_REQUIRED=true but signing/event keys are missing")
        if not allow_placeholders:
            if signing_key.startswith("your_") or event_key.startswith("your_"):
                errors.append("INNGEST keys are placeholder values")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap runtime reliability env settings.")
    parser.add_argument("--env-file", default=".env", help="Target env file path.")
    parser.add_argument(
        "--mode",
        choices=["development", "staging", "production"],
        default=None,
        help="Target runtime mode (defaults to existing ENVIRONMENT or development).",
    )
    parser.add_argument("--redis-url", default=None, help="Redis URL override.")
    parser.add_argument("--inngest-signing-key", default=None, help="Inngest signing key override.")
    parser.add_argument("--inngest-event-key", default=None, help="Inngest event key override.")
    parser.add_argument("--inngest-app-id", default=None, help="Inngest app id override.")
    parser.add_argument("--inngest-webhook-url", default=None, help="Inngest webhook URL override.")
    parser.add_argument(
        "--redis-required",
        choices=["true", "false", "auto"],
        default="auto",
        help="Whether Redis is required. auto=true for staging/production.",
    )
    parser.add_argument(
        "--inngest-required",
        choices=["true", "false", "auto"],
        default="auto",
        help="Whether Inngest is required. auto=true for staging/production.",
    )
    parser.add_argument(
        "--allow-placeholders",
        action="store_true",
        help="Allow placeholder/local values for required settings.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing file.")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run runtime dependency checks after bootstrap.",
    )
    parser.add_argument(
        "--check-connections",
        action="store_true",
        help="When validating, perform active Redis ping checks.",
    )
    args = parser.parse_args()

    env_path = (PROJECT_ROOT / args.env_file).resolve() if not Path(args.env_file).is_absolute() else Path(args.env_file)
    existing_raw = dotenv_values(env_path) if env_path.exists() else {}
    existing = {k: str(v) for k, v in existing_raw.items() if v is not None}

    mode = normalize_mode(args.mode or existing.get("ENVIRONMENT"))
    overrides = _collect_overrides(args)

    merged = merge_runtime_env_values(mode=mode, existing=existing, overrides=overrides)
    merged["REDIS_REQUIRED"] = "true" if _resolve_required_flag(args.redis_required, mode) else "false"
    merged["INNGEST_REQUIRED"] = "true" if _resolve_required_flag(args.inngest_required, mode) else "false"

    input_errors = _validate_bootstrap_inputs(
        merged,
        allow_placeholders=args.allow_placeholders,
    )
    if input_errors:
        print("Bootstrap input validation failed:")
        for error in input_errors:
            print(f"  - {error}")
        return 1

    changes = {"updated_keys": [], "appended_keys": [], "total_keys": len(merged)}
    if not args.dry_run:
        changes = upsert_env_file(env_path, merged)

    validation = None
    if args.validate:
        previous_env: Dict[str, str | None] = {}
        for key, value in merged.items():
            previous_env[key] = os.getenv(key)
            os.environ[key] = value
        try:
            validation = get_runtime_dependency_health(
                check_connections=args.check_connections,
                inngest_route_mounted=None,
            )
        finally:
            for key, old_value in previous_env.items():
                if old_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old_value

    summary = {
        "env_file": str(env_path),
        "mode": mode,
        "dry_run": args.dry_run,
        "changes": changes,
        "requirements": {
            "redis_required": merged["REDIS_REQUIRED"],
            "inngest_required": merged["INNGEST_REQUIRED"],
        },
        "validation": validation,
    }
    print(json.dumps(summary, indent=2))

    if validation is not None and not validation.get("ready", False):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
