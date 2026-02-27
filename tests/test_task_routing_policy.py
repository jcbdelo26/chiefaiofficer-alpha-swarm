#!/usr/bin/env python3
"""
Task-based LLM routing policy tests.
"""

from __future__ import annotations

from core.task_routing_policy import (
    get_task_routes,
    resolve_route_for_task,
    resolve_task_class,
    routes_ready,
)


def test_task_routes_defaults_match_phase1_contract(monkeypatch):
    monkeypatch.delenv("LLM_ROUTE_HIVEMIND_PRIMARY", raising=False)
    monkeypatch.delenv("LLM_ROUTE_HIVEMIND_FALLBACK", raising=False)
    monkeypatch.delenv("LLM_ROUTE_DAILY_PRIMARY", raising=False)
    monkeypatch.delenv("LLM_ROUTE_DAILY_FALLBACK", raising=False)
    monkeypatch.delenv("LLM_ROUTE_DETERMINISTIC_PRIMARY", raising=False)
    monkeypatch.delenv("LLM_ROUTE_DETERMINISTIC_FALLBACK", raising=False)

    routes = get_task_routes()

    assert routes["hive_mind"]["primary"] == "opus-4.6"
    assert routes["hive_mind"]["fallback"] == "sonnet-4.5"
    assert routes["daily"]["primary"] == "sonnet-4.5"
    assert routes["daily"]["fallback"] == "opus-4.6"
    assert routes["deterministic_microtasks"]["primary"] == "gpt-5.1-mini"
    assert routes["deterministic_microtasks"]["fallback"] == "sonnet-4.5"
    assert routes_ready(routes) is True


def test_task_routes_allow_env_overrides(monkeypatch):
    monkeypatch.setenv("LLM_ROUTE_HIVEMIND_PRIMARY", "custom-hive")
    monkeypatch.setenv("LLM_ROUTE_HIVEMIND_FALLBACK", "custom-hive-fallback")
    monkeypatch.setenv("LLM_ROUTE_DAILY_PRIMARY", "custom-daily")
    monkeypatch.setenv("LLM_ROUTE_DAILY_FALLBACK", "custom-daily-fallback")
    monkeypatch.setenv("LLM_ROUTE_DETERMINISTIC_PRIMARY", "custom-det")
    monkeypatch.setenv("LLM_ROUTE_DETERMINISTIC_FALLBACK", "custom-det-fallback")

    routes = get_task_routes()
    assert routes["hive_mind"]["primary"] == "custom-hive"
    assert routes["daily"]["primary"] == "custom-daily"
    assert routes["deterministic_microtasks"]["primary"] == "custom-det"
    assert routes_ready(routes) is True


def test_task_class_resolution_and_route_selection():
    assert resolve_task_class("planning") == "hive_mind"
    assert resolve_task_class("email_creation") == "daily"
    assert resolve_task_class("scheduling") == "deterministic_microtasks"
    assert resolve_task_class("unknown_task_name") == "daily"

    hive_route = resolve_route_for_task("strategy")
    daily_route = resolve_route_for_task("research")
    det_route = resolve_route_for_task("etc")

    assert hive_route["task_class"] == "hive_mind"
    assert daily_route["task_class"] == "daily"
    assert det_route["task_class"] == "deterministic_microtasks"
    assert hive_route["primary"]
    assert hive_route["fallback"]


def test_routes_ready_false_when_primary_or_fallback_missing():
    assert routes_ready(
        {
            "daily": {"primary": "sonnet-4.5", "fallback": ""},
        }
    ) is False
    assert routes_ready(
        {
            "daily": {"primary": "", "fallback": "opus-4.6"},
        }
    ) is False

