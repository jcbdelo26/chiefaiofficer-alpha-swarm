#!/usr/bin/env python3
"""Tests for canonical email signature/footer enforcement."""

from core.email_signature import (
    CALL_LINK,
    ensure_outbound_html,
    enforce_html_signature,
    enforce_text_signature,
)


def test_enforce_text_signature_replaces_legacy_footer():
    body = (
        "Hi Celia,\n\nQuick note.\n\nBest,\nDani Apgar\nChief AI Officer\n"
        "https://caio.cx/ai-exec-briefing-call\n\n---\nReply STOP to unsubscribe.\n"
        "Chief AI Officer Inc. | 5700 Harper Dr, Suite 210, Albuquerque, NM 87109"
    )
    output = enforce_text_signature(body)
    assert "Reply STOP to unsubscribe." in output
    assert "Schedule a call with CAIO" in output
    assert CALL_LINK in output
    assert "support@chiefaiofficer.com" in output
    assert output.count("Best,") == 1
    assert output.strip().endswith("Reply STOP to unsubscribe.")
    assert output.find("Copyright © 2026 Chief AI Officer. All rights reserved") < output.find("Reply STOP to unsubscribe.")


def test_enforce_html_signature_replaces_legacy_signoff_and_footer():
    body = """
<p>Hi Celia,</p>
<p>Worth a brief chat?</p>
<p>Best,<br><strong>Dani Apgar</strong><br>Chief AI Officer<br><a href="https://old.example.com">Book a 30 min. briefing</a></p>
<p style="font-size: 11px; color: #666;">We only reach out to professionals we believe can lead AI strategy inside their organizations.</p>
"""
    output = enforce_html_signature(body)
    assert "old.example.com" not in output
    assert "Schedule a call with CAIO" in output
    assert CALL_LINK in output
    assert "Reply STOP to unsubscribe." in output
    assert "support@chiefaiofficer.com" in output
    assert "<center>" in output.lower()
    assert output.lower().find("copyright © 2026 chief ai officer. all rights reserved") < output.lower().find("reply stop to unsubscribe.")


def test_ensure_outbound_html_converts_text_and_links_schedule_cta():
    body = "Hi there,\n\nWould this be useful?\n\nBest,\nDani Apgar"
    html_output = ensure_outbound_html(body)
    assert "<p>" in html_output
    assert f'href="{CALL_LINK}"' in html_output
    assert "Schedule a call with CAIO" in html_output
    assert "Reply STOP to unsubscribe." in html_output
    assert "<center>" in html_output.lower()
