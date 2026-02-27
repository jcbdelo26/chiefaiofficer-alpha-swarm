from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_trace_module():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "trace_outbound_ghl_queue.py"
    spec = importlib.util.spec_from_file_location("trace_outbound_ghl_queue", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def test_api_get_uses_header_token_not_query_param(monkeypatch):
    module = _load_trace_module()
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True}

    def fake_get(url, *, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(module.requests, "get", fake_get)

    result = module._api_get(
        "https://example.com",
        "/api/pending-emails",
        "test-token-123",
    )

    assert result == {"ok": True}
    assert captured["url"] == "https://example.com/api/pending-emails"
    assert captured["headers"] == {"X-Dashboard-Token": "test-token-123"}
    assert captured["params"] in (None, {})
    assert captured["timeout"] == 30


def test_api_get_preserves_include_non_dispatchable_query_param(monkeypatch):
    module = _load_trace_module()
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"pending_emails": []}

    def fake_get(url, *, params=None, headers=None, timeout=None):
        captured["params"] = params
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(module.requests, "get", fake_get)

    module._api_get(
        "https://example.com",
        "/api/pending-emails",
        "test-token-123",
        include_non_dispatchable=True,
    )

    assert captured["headers"] == {"X-Dashboard-Token": "test-token-123"}
    assert captured["params"] == {"include_non_dispatchable": "true"}
