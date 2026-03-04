#!/usr/bin/env python3
"""Unit tests for deployed_full_smoke_checklist helpers."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from deployed_full_smoke_checklist import _sales_page_refresh_signal


def test_sales_page_refresh_signal_accepts_active_refresh_wiring():
    html = """
    <script>
      async function fetchPendingEmails(){ return fetch('/api/pending-emails'); }
      setInterval(() => fetchPendingEmails(), 10000);
      document.addEventListener('visibilitychange', () => fetchPendingEmails());
    </script>
    """
    passed, details = _sales_page_refresh_signal(html)
    assert passed is True
    assert details["has_setInterval"] is True
    assert details["has_visibilitychange"] is True
    assert details["has_pending_fetch"] is True
    assert details["has_login_gate"] is False


def test_sales_page_refresh_signal_accepts_login_gated_dashboard():
    html = """
    <html><body>
      <h1>CAIO Dashboard Login</h1>
      <form method="post" action="/login">
        <input type="password" name="password" />
      </form>
    </body></html>
    """
    passed, details = _sales_page_refresh_signal(html)
    assert passed is True
    assert details["has_login_gate"] is True
    assert details["has_setInterval"] is False


def test_sales_page_refresh_signal_rejects_missing_wiring_and_not_login():
    html = "<html><body><h1>Sales</h1><p>No wiring here.</p></body></html>"
    passed, details = _sales_page_refresh_signal(html)
    assert passed is False
    assert details["has_login_gate"] is False

