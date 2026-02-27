#!/usr/bin/env python3
"""
Task-based LLM routing policy (Phase-1 hardening).

Primary purpose:
- deterministic model route mapping per task class
- explicit primary + single fallback contract
"""

from __future__ import annotations

import os
from typing import Dict, Mapping

_ROUTE_CONFIG = {
    "hive_mind": {
        "primary_env": "LLM_ROUTE_HIVEMIND_PRIMARY",
        "fallback_env": "LLM_ROUTE_HIVEMIND_FALLBACK",
        "default_primary": "opus-4.6",
        "default_fallback": "sonnet-4.5",
    },
    "daily": {
        "primary_env": "LLM_ROUTE_DAILY_PRIMARY",
        "fallback_env": "LLM_ROUTE_DAILY_FALLBACK",
        "default_primary": "sonnet-4.5",
        "default_fallback": "opus-4.6",
    },
    "deterministic_microtasks": {
        "primary_env": "LLM_ROUTE_DETERMINISTIC_PRIMARY",
        "fallback_env": "LLM_ROUTE_DETERMINISTIC_FALLBACK",
        "default_primary": "gpt-5.1-mini",
        "default_fallback": "sonnet-4.5",
    },
}

_TASK_CLASS_ALIASES = {
    "hive_mind": {
        "hive_mind",
        "orchestration",
        "planning",
        "strategy",
        "queen",
        "decision",
    },
    "daily": {
        "daily",
        "email_creation",
        "enrichment",
        "research",
        "copywriting",
        "campaign_copy",
    },
    "deterministic_microtasks": {
        "deterministic_microtasks",
        "scheduler",
        "scheduling",
        "etc",
        "microtask",
        "fast_task",
    },
}


def get_task_routes(env: Mapping[str, str] | None = None) -> Dict[str, Dict[str, str]]:
    """
    Return deterministic task->model route map with primary + single fallback.
    """
    source = env if env is not None else os.environ
    routes: Dict[str, Dict[str, str]] = {}
    for task_class, config in _ROUTE_CONFIG.items():
        primary = str(source.get(config["primary_env"], config["default_primary"])).strip()
        fallback = str(source.get(config["fallback_env"], config["default_fallback"])).strip()
        routes[task_class] = {
            "primary": primary or config["default_primary"],
            "fallback": fallback or config["default_fallback"],
        }
    return routes


def resolve_task_class(task_name: str) -> str:
    """
    Resolve an arbitrary task name into one of the three route classes.
    """
    normalized = str(task_name or "").strip().lower()
    if not normalized:
        return "daily"
    for task_class, aliases in _TASK_CLASS_ALIASES.items():
        if normalized in aliases:
            return task_class
    return "daily"


def resolve_route_for_task(task_name: str, env: Mapping[str, str] | None = None) -> Dict[str, str]:
    """
    Resolve route policy for a task with explicit class + models.
    """
    task_class = resolve_task_class(task_name)
    routes = get_task_routes(env=env)
    selected = routes[task_class]
    return {
        "task_class": task_class,
        "primary": selected["primary"],
        "fallback": selected["fallback"],
    }


def routes_ready(routes: Mapping[str, Mapping[str, str]] | None = None) -> bool:
    """
    Basic readiness check: every class has non-empty primary + fallback.
    """
    values = routes if routes is not None else get_task_routes()
    for route in values.values():
        if not str(route.get("primary") or "").strip():
            return False
        if not str(route.get("fallback") or "").strip():
            return False
    return True

