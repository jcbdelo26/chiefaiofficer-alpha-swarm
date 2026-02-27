#!/usr/bin/env python3
"""
Pre-queue deterministic quality guard.

Runs BEFORE shadow_queue.push() to block drafts that:
- Repeat previously-rejected content for the same lead
- Lack evidence-backed personalization
- Use banned opener patterns
- Exceed the per-lead rejection threshold

Controlled by QUALITY_GUARD_ENABLED env var (default: true).
Set QUALITY_GUARD_MODE=soft to log-only without blocking.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from core.rejection_memory import (
    RejectionMemory,
    compute_draft_fingerprint,
)

logger = logging.getLogger("quality_guard")


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


# ── Banned opener patterns ────────────────────────────────────────

BANNED_OPENERS = [
    r"^Given your role as\b",
    r"^As (?:a |the )?(?:fellow )?\w+ at\b",
    r"^I noticed (?:that )?you(?:'re| are) (?:a |the )?\w+ at\b",
    r"^(?:Hi|Hey|Hello)[,!]?\s+(?:I )?(?:came across|stumbled upon|noticed)\b",
    r"^I hope this (?:email |message )?finds you\b",
    r"^I wanted to reach out\b",
    r"^I'm reaching out\b",
    r"^Quick question\b",
    r"^I saw (?:that )?you(?:'re| are)\b",
    r"^Just wanted to\b",
]

# Known generic AI filler phrases (case-insensitive substring match)
GENERIC_PHRASES = [
    "in today's fast-paced",
    "in today's rapidly evolving",
    "leverage cutting-edge",
    "revolutionize your",
    "transform your business",
    "take your business to the next level",
    "unlock the power of",
    "harness the potential",
    "game-changing",
    "paradigm shift",
    "synergy",
    "best-in-class solution",
    "thought leader",
    "move the needle",
    "low-hanging fruit",
    "circle back",
    "deep dive into",
    "at the end of the day",
    "streamline your workflow",
]


def _is_enabled() -> bool:
    return _env_bool("QUALITY_GUARD_ENABLED", True)


def _is_soft_mode() -> bool:
    return (os.getenv("QUALITY_GUARD_MODE") or "").strip().lower() == "soft"


class QualityGuard:
    """Deterministic pre-queue validator for email drafts."""

    def __init__(self, rejection_memory: Optional[RejectionMemory] = None):
        self.memory = rejection_memory or RejectionMemory()

    def check(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run all quality guard rules against an email draft.

        Args:
            email_data: Shadow email dict with keys: to, subject, body,
                        recipient_data, tier, etc.

        Returns:
            QualityGuardResult dict with:
                passed, blocked_reason, rule_failures,
                draft_fingerprint, personalization_evidence,
                rejection_memory_hit
        """
        if not _is_enabled():
            return self._pass_result(email_data)

        to_email = (email_data.get("to") or "").strip().lower()
        subject = email_data.get("subject") or ""
        body = email_data.get("body") or ""
        recipient = email_data.get("recipient_data") or {}

        fingerprint = compute_draft_fingerprint(subject, body)
        evidence = self._extract_evidence(body, recipient)
        failures: List[Dict[str, str]] = []
        rejection_memory_hit = False

        # GUARD-001: Rejection memory block
        blocked, reason = self.memory.should_block_lead(to_email)
        if blocked:
            rejection_memory_hit = True
            failures.append({"rule_id": "GUARD-001", "message": reason})

        # GUARD-002: Repeat draft detection
        if self.memory.is_repeat_draft(to_email, subject, body):
            rejection_memory_hit = True
            failures.append({
                "rule_id": "GUARD-002",
                "message": f"Draft fingerprint {fingerprint[:12]}... matches a previously rejected draft for this lead.",
            })

        # GUARD-003: Minimum personalization evidence
        company_evidence = [e for e in evidence if e["type"] == "company_specific"]
        role_evidence = [e for e in evidence if e["type"] == "role_impact"]
        sub_agent_context = None
        if len(company_evidence) < 1 or len(role_evidence) < 1:
            # Attempt sub-agent enrichment as fallback before blocking
            sub_agent_context = self._run_sub_agent_enrichment(email_data)
            if sub_agent_context and sub_agent_context.meets_minimum_evidence:
                # Sub-agents found enough — override the evidence shortfall
                logger.info(
                    "Sub-agent enrichment rescued %s: %d company + %d role signals",
                    to_email, sub_agent_context.company_specific_count,
                    sub_agent_context.role_impact_count,
                )
            else:
                failures.append({
                    "rule_id": "GUARD-003",
                    "message": (
                        f"Insufficient personalization evidence. "
                        f"Found {len(company_evidence)} company-specific, {len(role_evidence)} role-impact. "
                        f"Minimum: 1 of each."
                    ),
                })

        # GUARD-004: Banned opener patterns
        body_first_line = (body or "").strip().split("\n")[0].strip()
        # Skip greeting line (e.g., "Hi Chris,") and check the actual opener
        body_lines = [ln.strip() for ln in (body or "").strip().split("\n") if ln.strip()]
        opener_line = ""
        for line in body_lines:
            if re.match(r"^(?:Hi|Hey|Hello|Dear)\b", line, re.IGNORECASE) and len(line) < 40:
                continue  # skip greeting
            opener_line = line
            break

        for pattern in BANNED_OPENERS:
            if re.search(pattern, opener_line, re.IGNORECASE):
                failures.append({
                    "rule_id": "GUARD-004",
                    "message": f"Banned opener pattern detected: '{opener_line[:80]}...'",
                })
                break

        # GUARD-005: Generic phrase density
        generic_count = 0
        body_lower = (body or "").lower()
        for phrase in GENERIC_PHRASES:
            if phrase in body_lower:
                generic_count += 1
        sentences = [s.strip() for s in re.split(r"[.!?]+", body or "") if s.strip()]
        sentence_count = max(len(sentences), 1)
        if sentence_count > 0 and generic_count / sentence_count > 0.4:
            failures.append({
                "rule_id": "GUARD-005",
                "message": f"Generic phrase density too high: {generic_count} generic phrases in {sentence_count} sentences.",
            })

        result = {
            "passed": len(failures) == 0,
            "blocked_reason": failures[0]["message"] if failures else None,
            "rule_failures": failures,
            "draft_fingerprint": fingerprint,
            "personalization_evidence": evidence,
            "rejection_memory_hit": rejection_memory_hit,
            "sub_agent_trace_id": (
                "|".join(sub_agent_context.sub_agent_trace_ids)
                if sub_agent_context else ""
            ),
        }

        if failures:
            if _is_soft_mode():
                logger.warning(
                    "Quality guard SOFT BLOCK for %s: %s",
                    to_email, result["blocked_reason"],
                )
                result["passed"] = True  # soft mode: log but don't block
            else:
                logger.warning(
                    "Quality guard BLOCKED %s: %s",
                    to_email, result["blocked_reason"],
                )

        return result

    def _extract_evidence(
        self, body: str, recipient: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """
        Extract personalization evidence items from the draft body.

        Evidence types:
        - company_specific: company name, initiative, tech stack, hiring signal
        - role_impact: title reference with context, operational/strategic mention
        """
        evidence: List[Dict[str, str]] = []
        body_lower = (body or "").lower()

        company_name = str(
            recipient.get("company") or recipient.get("company_name") or ""
        ).strip()
        title = str(recipient.get("title") or "").strip()

        # Company-specific evidence
        if company_name and len(company_name) > 2:
            cn_lower = company_name.lower()
            if cn_lower in body_lower and cn_lower not in {"your company", "the company"}:
                evidence.append({
                    "type": "company_specific",
                    "value": company_name,
                    "source": "company_name_in_body",
                })

        # Check for specific initiative/tech/hiring references
        initiative_patterns = [
            (r"\b(?:hiring|scaling|expanding|growing|launching|migrating)\b", "initiative_signal"),
            (r"\b(?:tech stack|stack|platform|using|adopted|implemented)\b", "tech_reference"),
            (r"\b(?:event|conference|webinar|summit|workshop)\b", "event_reference"),
            (r"\b(?:article|post|comment|podcast|interview)\b", "content_reference"),
        ]
        for pattern, source in initiative_patterns:
            if re.search(pattern, body_lower):
                evidence.append({
                    "type": "company_specific",
                    "value": pattern,
                    "source": source,
                })
                break  # one is enough for company-specific

        # Role-impact evidence
        if title and len(title) > 1:
            title_lower = title.lower()
            # Check if title or abbreviated title is meaningfully referenced
            # (not just "Given your role as X at Y" which is a banned pattern)
            title_words = set(re.findall(r"\b\w{3,}\b", title_lower))
            body_words = set(re.findall(r"\b\w{3,}\b", body_lower))
            if title_words & body_words:
                evidence.append({
                    "type": "role_impact",
                    "value": title,
                    "source": "title_referenced_in_body",
                })

        # Check for operational/strategic language tied to the role
        role_patterns = [
            (r"\b(?:execution|operating cadence|operational|implementation)\b", "operational_impact"),
            (r"\b(?:strategy|strategic|decision|initiative|roadmap)\b", "strategic_impact"),
            (r"\b(?:revenue|pipeline|growth|efficiency|productivity)\b", "business_impact"),
        ]
        for pattern, source in role_patterns:
            if re.search(pattern, body_lower):
                evidence.append({
                    "type": "role_impact",
                    "value": pattern,
                    "source": source,
                })
                break  # one is enough for role-impact

        return evidence

    def _run_sub_agent_enrichment(self, email_data: Dict[str, Any]):
        """Run sub-agent enrichment to extract deeper signals from lead data."""
        try:
            from core.enrichment_sub_agents import extract_all_signals
            # Build a lead-like dict from the shadow email for sub-agents
            recipient = email_data.get("recipient_data") or {}
            context = email_data.get("context") or {}
            lead_proxy = {
                "email": email_data.get("to", ""),
                "company_name": recipient.get("company", ""),
                "company": recipient.get("company", ""),
                "title": recipient.get("title", ""),
                "industry": recipient.get("industry", ""),
                "employee_count": recipient.get("employees", ""),
                "source_type": email_data.get("source_type", ""),
                "source_name": email_data.get("source_name", ""),
                "personalization_hooks": email_data.get("personalization_hooks", []),
                "engagement_content": email_data.get("engagement_content", ""),
                "hiring_signal": email_data.get("hiring_signal"),
                "icp_tier": context.get("icp_tier", email_data.get("tier", "")),
            }
            return extract_all_signals(lead_proxy)
        except Exception as exc:
            logger.warning("Sub-agent enrichment failed: %s", exc)
            return None

    def _pass_result(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """Return a passing result when guard is disabled."""
        subject = email_data.get("subject") or ""
        body = email_data.get("body") or ""
        return {
            "passed": True,
            "blocked_reason": None,
            "rule_failures": [],
            "draft_fingerprint": compute_draft_fingerprint(subject, body),
            "personalization_evidence": [],
            "rejection_memory_hit": False,
            "sub_agent_trace_id": "",
        }
