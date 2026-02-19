"""
Canonical outbound/inbound email signature + footer enforcement.

This module guarantees a single signature/footer contract across plain-text
and HTML email bodies.
"""

from __future__ import annotations

import html
import re
from typing import Final

CALL_LINK: Final[str] = "https://caio.cx/ai-exec-briefing-call"
SUPPORT_EMAIL: Final[str] = "support@chiefaiofficer.com"
UNSUBSCRIBE_MAILTO: Final[str] = f"mailto:{SUPPORT_EMAIL}?subject=Unsubscribe"

STANDARD_TEXT_SIGNATURE: Final[str] = "\n".join(
    [
        "Best,",
        "Dani Apgar",
        f"Schedule a call with CAIO: {CALL_LINK}",
    ]
)

STANDARD_TEXT_FOOTER: Final[str] = "\n".join(
    [
        "We only reach out to professionals we believe can lead AI strategy inside their organizations. If this isn't you, or now's not the right time, just click here and I'll take care of it personally.",
        "Chief AI Officer Inc.",
        "5700 Harper Dr, Suite 210, Albuquerque, NM 87109",
        SUPPORT_EMAIL,
        "Copyright © 2026 Chief AI Officer. All rights reserved",
    ]
)

STANDARD_HTML_SIGNATURE: Final[str] = (
    f'<p>Best,<br>\n'
    f'<a href="{CALL_LINK}"><strong>Dani Apgar</strong></a><br>\n'
    f'<a href="{CALL_LINK}">Schedule a call with CAIO</a></p>'
)

STANDARD_HTML_FOOTER: Final[str] = (
    '<p style="font-size: 11px; color: #666; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; text-align: center;">'
    "We only reach out to professionals we believe can lead AI strategy inside their organizations. "
    f'If this isn&#39;t you, or now&#39;s not the right time, just <a href="{UNSUBSCRIBE_MAILTO}">click here</a> and I&#39;ll take care of it personally.<br><br>'
    "<strong>Chief AI Officer Inc.</strong><br>"
    "5700 Harper Dr, Suite 210, Albuquerque, NM 87109<br>"
    f'<a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a><br>'
    "Copyright © 2026 Chief AI Officer. All rights reserved"
    "</p>"
)

_LEGACY_HTML_BLOCKS = [
    r"(?is)<p[^>]*>\s*We only reach out to professionals we believe can lead AI strategy inside their organizations\..*?</p>",
    r"(?is)<p[^>]*>\s*Reply STOP to unsubscribe\.?\s*</p>",
    r"(?is)<p[^>]*>\s*(?:Best|Cheers|Thanks),<br>[\s\S]*?</p>",
    r"(?is)Chief AI Officer Inc\.\s*\|\s*5700 Harper Dr, Suite 210, Albuquerque, NM 87109",
]

_LEGACY_TEXT_BLOCKS = [
    r"(?is)\n*We only reach out to professionals we believe can lead AI strategy inside their organizations\.[\s\S]*$",
    r"(?is)\n*(?:Best|Cheers|Thanks),\s*\n[\s\S]*$",
    r"(?is)\n*---\s*\n[\s\S]*$",
    r"(?is)\n*Reply STOP to unsubscribe\.?\s*$",
]


def _normalize_newlines(value: str) -> str:
    return (value or "").replace("\r\n", "\n").replace("\r", "\n")


def _looks_like_html(value: str) -> bool:
    return bool(re.search(r"<[a-z][^>]*>", value or "", flags=re.IGNORECASE))


def _strip_legacy_text(body: str) -> str:
    text = _normalize_newlines(body or "")
    for pattern in _LEGACY_TEXT_BLOCKS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"(?im)^https?://caio\.cx/ai-exec-briefing-call\s*$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _strip_legacy_html(body_html: str) -> str:
    html_body = (body_html or "").strip()
    for pattern in _LEGACY_HTML_BLOCKS:
        html_body = re.sub(pattern, "", html_body, flags=re.IGNORECASE | re.DOTALL)
    html_body = re.sub(r"(?is)(<br\s*/?>\s*){2,}$", "", html_body)
    return html_body.strip()


def enforce_text_signature(body: str) -> str:
    """Return plain-text body with canonical CAIO signature/footer."""
    content = _strip_legacy_text(body)
    if not content:
        content = "Hi there,"
    return f"{content}\n\n{STANDARD_TEXT_SIGNATURE}\n\n{STANDARD_TEXT_FOOTER}".strip()


def enforce_html_signature(body_html: str) -> str:
    """Return HTML body with canonical CAIO signature/footer."""
    content = _strip_legacy_html(body_html)
    if not content:
        content = "<p>Hi there,</p>"
    return f"{content}\n\n{STANDARD_HTML_SIGNATURE}\n\n{STANDARD_HTML_FOOTER}".strip()


def text_to_html_body(body_text: str) -> str:
    """Convert text to simple HTML while preserving line breaks/paragraphs."""
    text = _normalize_newlines(body_text).strip()
    if not text:
        return "<p></p>"

    escaped = html.escape(text)
    escaped = escaped.replace(
        f"Schedule a call with CAIO: {CALL_LINK}",
        f'<a href="{CALL_LINK}">Schedule a call with CAIO</a>',
    )
    escaped = escaped.replace(
        SUPPORT_EMAIL,
        f'<a href="mailto:{SUPPORT_EMAIL}">{SUPPORT_EMAIL}</a>',
    )
    escaped = escaped.replace(
        "just click here and I&#x27;ll take care of it personally.",
        f'just <a href="{UNSUBSCRIBE_MAILTO}">click here</a> and I&#x27;ll take care of it personally.',
    )

    paragraphs = [p.strip() for p in escaped.split("\n\n") if p.strip()]
    return "\n\n".join(f"<p>{p.replace('\n', '<br>')}</p>" for p in paragraphs)


def ensure_outbound_html(body: str) -> str:
    """
    Ensure outbound message is HTML and carries canonical signature/footer.

    - HTML input: strip legacy blocks and append canonical HTML footer.
    - Text input: enforce canonical text footer then convert to HTML.
    """
    if _looks_like_html(body or ""):
        return enforce_html_signature(body or "")
    canonical_text = enforce_text_signature(body or "")
    return enforce_html_signature(text_to_html_body(canonical_text))
