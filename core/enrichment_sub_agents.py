#!/usr/bin/env python3
"""
Enrichment sub-agents for deep personalization signal extraction.

When the quality guard blocks a lead for insufficient personalization evidence
(or when a lead has prior rejections), these sub-agents attempt to extract
deeper signals from existing data before the CRAFTER generates a draft.

Sub-agents are pure functions — no external API calls, no LLM calls.
They mine the enrichment data already collected by the pipeline.

Architecture:
    ┌─────────────────────────┐
    │  Enriched Lead Data     │
    │  (Apollo/BetterContact) │
    └────────┬────────────────┘
             │
    ┌────────▼────────────────┐
    │  SignalRouter            │
    │  dispatches to sub-agents│
    └────────┬────────────────┘
             │
    ┌────────┼────────────────────────────────┐
    │        │        │        │              │
    ▼        ▼        ▼        ▼              ▼
  Company  Hiring   Tech    Content     Role-Impact
  Intel    Signal   Stack   Engagement  Analyzer
    │        │        │        │              │
    └────────┼────────┴────────┼──────────────┘
             │                 │
    ┌────────▼─────────────────▼──┐
    │  MergedPersonalizationContext│
    │  (confidence-scored signals) │
    └─────────────────────────────┘
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("enrichment_sub_agents")


@dataclass
class PersonalizationSignal:
    """A single evidence-backed personalization signal."""
    signal_type: str        # company_intel, hiring, tech_stack, content, role_impact
    value: str              # the actual signal text
    confidence: float       # 0.0–1.0
    source: str             # where the signal was extracted from
    usable_in_opener: bool  # can this anchor an opening line?


@dataclass
class MergedPersonalizationContext:
    """Aggregated output from all sub-agents."""
    signals: List[PersonalizationSignal] = field(default_factory=list)
    company_specific_count: int = 0
    role_impact_count: int = 0
    overall_confidence: float = 0.0
    recommended_opener_signal: Optional[PersonalizationSignal] = None
    sub_agent_trace_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signals": [asdict(s) for s in self.signals],
            "company_specific_count": self.company_specific_count,
            "role_impact_count": self.role_impact_count,
            "overall_confidence": self.overall_confidence,
            "recommended_opener_signal": asdict(self.recommended_opener_signal) if self.recommended_opener_signal else None,
            "sub_agent_trace_ids": self.sub_agent_trace_ids,
        }

    @property
    def meets_minimum_evidence(self) -> bool:
        """True if context has at least 1 company-specific + 1 role-impact signal."""
        return self.company_specific_count >= 1 and self.role_impact_count >= 1


# ── Sub-Agent 1: Company Intel ────────────────────────────────────


def extract_company_intel(lead: Dict[str, Any]) -> List[PersonalizationSignal]:
    """Extract company-level signals: industry, size, recent funding, description keywords."""
    signals = []
    company = lead.get("company", {})
    if isinstance(company, str):
        company = {"name": company}

    company_name = str(company.get("name") or lead.get("company_name") or "").strip()
    description = str(company.get("description") or lead.get("company_description") or "").strip()
    industry = str(company.get("industry") or lead.get("industry") or "").strip()
    employee_count = company.get("employee_count") or lead.get("employee_count") or lead.get("employees")

    if company_name and company_name.lower() not in {"your company", "unknown", "n/a", ""}:
        signals.append(PersonalizationSignal(
            signal_type="company_intel",
            value=company_name,
            confidence=0.9,
            source="company_name",
            usable_in_opener=True,
        ))

    if industry and industry.lower() not in {"unknown", "n/a", "other", ""}:
        signals.append(PersonalizationSignal(
            signal_type="company_intel",
            value=f"Industry: {industry}",
            confidence=0.7,
            source="industry",
            usable_in_opener=True,
        ))

    if description and len(description) > 30:
        # Extract key business phrases from company description
        keywords = _extract_business_keywords(description)
        if keywords:
            signals.append(PersonalizationSignal(
                signal_type="company_intel",
                value=f"Focus: {', '.join(keywords[:3])}",
                confidence=0.6,
                source="company_description",
                usable_in_opener=False,
            ))

    if employee_count:
        try:
            count = int(employee_count)
            if count > 0:
                signals.append(PersonalizationSignal(
                    signal_type="company_intel",
                    value=f"{count} employees",
                    confidence=0.8,
                    source="employee_count",
                    usable_in_opener=False,
                ))
        except (ValueError, TypeError):
            pass

    return signals


# ── Sub-Agent 2: Hiring Signal Detector ───────────────────────────


def extract_hiring_signals(lead: Dict[str, Any]) -> List[PersonalizationSignal]:
    """Detect hiring-related signals indicating growth, team build, or tech adoption."""
    signals = []

    hiring_signal = lead.get("hiring_signal") or lead.get("hiring_revops")
    if hiring_signal:
        signals.append(PersonalizationSignal(
            signal_type="hiring",
            value=str(hiring_signal) if isinstance(hiring_signal, str) else "Active hiring detected",
            confidence=0.85,
            source="hiring_signal",
            usable_in_opener=True,
        ))

    # Check personalization hooks for hiring-related content
    hooks = lead.get("personalization_hooks") or []
    for hook in hooks:
        hook_str = str(hook).lower()
        if any(kw in hook_str for kw in ["hiring", "scaling", "growing", "expanding", "new role"]):
            signals.append(PersonalizationSignal(
                signal_type="hiring",
                value=str(hook),
                confidence=0.75,
                source="personalization_hook",
                usable_in_opener=True,
            ))
            break

    # Check intent signals
    intent = lead.get("intent") or {}
    if isinstance(intent, dict):
        if intent.get("hiring_revops"):
            signals.append(PersonalizationSignal(
                signal_type="hiring",
                value="RevOps hiring detected",
                confidence=0.8,
                source="intent_signal",
                usable_in_opener=True,
            ))

    return signals


# ── Sub-Agent 3: Tech Stack Analyzer ──────────────────────────────


def extract_tech_stack(lead: Dict[str, Any]) -> List[PersonalizationSignal]:
    """Extract technology signals from enrichment data."""
    signals = []

    company = lead.get("company", {})
    if isinstance(company, str):
        company = {}

    technologies = company.get("technologies") or lead.get("technologies") or []
    if isinstance(technologies, list) and technologies:
        # Filter for relevant tech (AI, automation, sales tech, marketing tech)
        relevant_tech = [
            t for t in technologies
            if any(kw in str(t).lower() for kw in [
                "ai", "ml", "salesforce", "hubspot", "marketo", "outreach",
                "gong", "chorus", "clari", "drift", "intercom", "segment",
                "snowflake", "databricks", "tableau", "looker", "dbt",
            ])
        ]
        if relevant_tech:
            signals.append(PersonalizationSignal(
                signal_type="tech_stack",
                value=f"Uses: {', '.join(relevant_tech[:3])}",
                confidence=0.8,
                source="technology_list",
                usable_in_opener=True,
            ))

    # Check hooks for tech stack mentions
    hooks = lead.get("personalization_hooks") or []
    for hook in hooks:
        hook_str = str(hook).lower()
        if hook_str.startswith("tech stack signal:"):
            payload = str(hook).split(":", 1)[1].strip()
            if payload:
                signals.append(PersonalizationSignal(
                    signal_type="tech_stack",
                    value=payload,
                    confidence=0.85,
                    source="tech_stack_hook",
                    usable_in_opener=True,
                ))
                break

    return signals


# ── Sub-Agent 4: Content Engagement ───────────────────────────────


def extract_content_engagement(lead: Dict[str, Any]) -> List[PersonalizationSignal]:
    """Extract engagement signals: events attended, content downloaded, posts commented."""
    signals = []

    source_type = str(lead.get("source_type") or "").strip().lower()
    source_name = str(lead.get("source_name") or "").strip()
    engagement_content = str(lead.get("engagement_content") or "").strip()

    if source_type in {"event_attendee", "webinar_registrant"} and source_name:
        signals.append(PersonalizationSignal(
            signal_type="content",
            value=f"Attended: {source_name}",
            confidence=0.85,
            source=f"source_type:{source_type}",
            usable_in_opener=True,
        ))

    if source_type == "post_commenter" and engagement_content:
        signals.append(PersonalizationSignal(
            signal_type="content",
            value=f"Commented on: {engagement_content[:100]}",
            confidence=0.8,
            source="engagement_content",
            usable_in_opener=True,
        ))

    if source_type == "content_downloader" and source_name:
        signals.append(PersonalizationSignal(
            signal_type="content",
            value=f"Downloaded: {source_name}",
            confidence=0.75,
            source="content_download",
            usable_in_opener=True,
        ))

    if source_type == "website_visitor" and source_name:
        signals.append(PersonalizationSignal(
            signal_type="content",
            value=f"Visited: {source_name}",
            confidence=0.7,
            source="website_visit",
            usable_in_opener=True,
        ))

    if source_type == "competitor_follower" and source_name:
        signals.append(PersonalizationSignal(
            signal_type="content",
            value=f"Follows: {source_name}",
            confidence=0.65,
            source="competitor_follow",
            usable_in_opener=True,
        ))

    return signals


# ── Sub-Agent 5: Role-Impact Analyzer ─────────────────────────────


def extract_role_impact(lead: Dict[str, Any]) -> List[PersonalizationSignal]:
    """Map job title to operational pain points and strategic context."""
    signals = []

    title = str(lead.get("title") or "").strip()
    if not title:
        return signals

    title_lower = title.lower()

    # Map titles to operational pain points
    ROLE_IMPACT_MAP = {
        ("cro", "chief revenue", "revenue"): {
            "pain": "pipeline velocity and forecast accuracy",
            "impact": "revenue execution cadence",
        },
        ("cmo", "chief marketing", "marketing"): {
            "pain": "campaign attribution and pipeline contribution",
            "impact": "marketing-to-revenue alignment",
        },
        ("coo", "chief operating", "operations", "vp ops"): {
            "pain": "cross-functional execution speed",
            "impact": "operating cadence and process efficiency",
        },
        ("ceo", "chief executive", "founder", "president"): {
            "pain": "strategic alignment between teams",
            "impact": "enterprise AI readiness",
        },
        ("cto", "chief technology", "vp engineering"): {
            "pain": "build vs buy decisions and tech debt",
            "impact": "AI infrastructure and toolchain decisions",
        },
        ("revops", "revenue operations", "sales operations"): {
            "pain": "data quality and process automation",
            "impact": "GTM efficiency and tool consolidation",
        },
        ("vp sales", "sales director", "head of sales"): {
            "pain": "rep productivity and deal velocity",
            "impact": "sales execution and enablement",
        },
    }

    for role_keywords, impact_data in ROLE_IMPACT_MAP.items():
        if any(kw in title_lower for kw in role_keywords):
            signals.append(PersonalizationSignal(
                signal_type="role_impact",
                value=f"Role pain point: {impact_data['pain']}",
                confidence=0.7,
                source="role_title_mapping",
                usable_in_opener=False,
            ))
            signals.append(PersonalizationSignal(
                signal_type="role_impact",
                value=f"Impact area: {impact_data['impact']}",
                confidence=0.7,
                source="role_title_mapping",
                usable_in_opener=False,
            ))
            break

    # Generic seniority signal if no specific mapping matched
    if not signals:
        seniority_keywords = ["vp", "director", "head of", "chief", "senior"]
        if any(kw in title_lower for kw in seniority_keywords):
            signals.append(PersonalizationSignal(
                signal_type="role_impact",
                value=f"Senior role: {title}",
                confidence=0.5,
                source="seniority_detection",
                usable_in_opener=False,
            ))

    return signals


# ── Signal Router (Orchestrator) ──────────────────────────────────


def extract_all_signals(lead: Dict[str, Any]) -> MergedPersonalizationContext:
    """
    Run all sub-agents and merge results into a single context.

    This is the entry point called by the CRAFTER or quality guard
    when deeper personalization evidence is needed.
    """
    all_signals: List[PersonalizationSignal] = []
    trace_ids: List[str] = []

    sub_agents = [
        ("company_intel", extract_company_intel),
        ("hiring_signal", extract_hiring_signals),
        ("tech_stack", extract_tech_stack),
        ("content_engagement", extract_content_engagement),
        ("role_impact", extract_role_impact),
    ]

    for agent_name, agent_fn in sub_agents:
        try:
            signals = agent_fn(lead)
            all_signals.extend(signals)
            trace_ids.append(f"sub:{agent_name}:{len(signals)}")
        except Exception as exc:
            logger.warning("Sub-agent %s failed: %s", agent_name, exc)
            trace_ids.append(f"sub:{agent_name}:ERROR")

    # Count by type
    company_count = sum(1 for s in all_signals if s.signal_type in {"company_intel", "tech_stack", "content", "hiring"})
    role_count = sum(1 for s in all_signals if s.signal_type == "role_impact")

    # Pick best opener signal (highest confidence, usable_in_opener=True)
    opener_candidates = sorted(
        [s for s in all_signals if s.usable_in_opener],
        key=lambda s: s.confidence,
        reverse=True,
    )
    best_opener = opener_candidates[0] if opener_candidates else None

    # Overall confidence = weighted average of top signals
    if all_signals:
        top_signals = sorted(all_signals, key=lambda s: s.confidence, reverse=True)[:5]
        overall = sum(s.confidence for s in top_signals) / len(top_signals)
    else:
        overall = 0.0

    return MergedPersonalizationContext(
        signals=all_signals,
        company_specific_count=company_count,
        role_impact_count=role_count,
        overall_confidence=round(overall, 3),
        recommended_opener_signal=best_opener,
        sub_agent_trace_ids=trace_ids,
    )


# ── Helpers ───────────────────────────────────────────────────────


def _extract_business_keywords(text: str) -> List[str]:
    """Extract meaningful business keywords from a company description."""
    text_lower = text.lower()
    keyword_sets = [
        "saas", "platform", "automation", "analytics", "ai", "machine learning",
        "data", "cloud", "enterprise", "b2b", "marketplace", "fintech",
        "healthtech", "martech", "devops", "cybersecurity", "ecommerce",
        "logistics", "supply chain", "real estate", "insurance",
    ]
    found = [kw for kw in keyword_sets if kw in text_lower]
    return found
