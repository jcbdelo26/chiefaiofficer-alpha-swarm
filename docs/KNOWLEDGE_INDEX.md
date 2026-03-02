---
title: Knowledge Index
version: "1.0"
last_updated: 2026-03-02
audience: [all-agents, engineers, pto-gtm]
tags: [index, knowledge, documentation, discovery]
canonical_for: [knowledge-index, doc-catalog]
---

# CAIO Alpha Swarm — Knowledge Index

Master index of all documentation, organized by category. Use this to discover docs by topic.

**Total**: 55 active docs + 15 archived | **Last scanned**: 2026-03-02

---

## Session Config (Mandatory Read Order)

| # | File | Purpose |
|---|------|---------|
| 1 | `CLAUDE.md` | Master session config — pitfalls, directives, API gotchas, safety controls |
| 2 | `task.md` | Source-of-truth sprint tracker, phase progress, graduation checklist |
| 3 | `docs/CAIO_CLAUDE_MEMORY.md` | Living runtime truth — deploy state, verified behaviors |
| 4 | `CAIO_IMPLEMENTATION_PLAN.md` | Canonical 6-phase roadmap (v4.7) — architecture, decision log |
| 5 | `docs/CAIO_UIUX_BULLETPROOF_HANDOFF_FOR_CLAUDE_2026-02-19.md` | UI/UX state machine, dashboard architecture |

## Implementation & Roadmap

| File | Purpose |
|------|---------|
| `CAIO_IMPLEMENTATION_PLAN.md` | Phased roadmap from Foundation through Phase 6 Full Autonomy |
| `docs/IMPLEMENTATION_ROADMAP.md` | High-level validation strategy and scaling principles |
| `docs/PRODUCTION_IMPLEMENTATION_ROADMAP.md` | Component readiness matrix (78% production-ready) |
| `docs/CAIO_OPERATIONAL_ROADMAP.md` | Non-technical GTM playbook for supervised live sends |
| `docs/CAIO_ALPHA_GTM_OPERATOR_ROADMAP.md` | Operational roadmap for non-technical GTM operators |
| `docs/RAMP_UP_PLAN.md` | Collaborative ramp-up plan to full operational status |
| `docs/CONTEXT_ENGINEERING_IMPLEMENTATION_ROADMAP.md` | FIC integration for 99% workflow success |

## Deployment & Operations

| File | Purpose |
|------|---------|
| `DEPLOYMENT_GUIDE.md` | Step-by-step Railway deployment (local/Docker/one-click) |
| `DEPLOYMENT_CHECKLIST.md` | Pre-deployment verification and safety checks |
| `docs/PRODUCTION_QUICK_START.md` | Fast-track production readiness checklist |
| `docs/PRODUCTION_TOOLKIT_README.md` | Production launch toolkit documentation |
| `docs/RUNBOOK.md` | Daily operational guide — management, troubleshooting, maintenance |
| `docs/STAGING_WEBHOOK_STRICT_MODE_ROLLOUT.md` | Webhook strict mode enablement checklist |
| `docs/PTO_NON_TECH_REAL_PIPELINE_AND_DEPLOYED_SMOKE_GUIDE.md` | Non-technical pipeline and smoke guide |
| `docs/PRELIVE_INPUT_GUIDE_FOR_PTO.md` | Pre-live operational inputs walkthrough |
| `docs/CAIO_PTO_INPUTS_NON_TECH_SETUP_GUIDE.md` | Non-technical setup guide for GTM inputs |
| `docs/CAIO_PTO_GTM_ONE_PAGE_EXECUTION_CHECKLIST.md` | Single-page execution readiness checklist |

## API & Integration

| File | Purpose |
|------|---------|
| `docs/API_INTEGRATION_GUIDE.md` | Phased integration roadmap for all external APIs |
| `docs/GHL_WEBHOOK_SETUP.md` | GoHighLevel webhook setup for hot lead detection |
| `docs/RB2B_WEBHOOK_SETUP.md` | RB2B webhook integration setup and validation |
| `docs/CLAY_DIRECT_ENRICHMENT_SETUP.md` | Clay enrichment API configuration |
| `docs/GOOGLE_DRIVE_SETUP_GUIDE.md` | Google Drive OAuth setup for document management |
| `docs/GOOGLE_CALENDAR_SETUP_GUIDE.md` | Meeting booking agent calendar integration |

## Security & Compliance

| File | Purpose |
|------|---------|
| `docs/AGENTIC_ENGINEERING_AUDIT_HANDOFF.md` | 5-pillar audit baseline (v1.1) — scorecard, gap analysis, remediation plan |
| `docs/SYSTEM_CONFIGURATION_STATUS.md` | Security and system configuration readiness summary |

## Architecture & Design

| File | Purpose |
|------|---------|
| `docs/WIRED_ARCHITECTURE.md` | System architecture — orchestration to execution layers |
| `docs/COLD_WARM_ROUTING_ARCHITECTURE.md` | Intelligent lead routing based on warmth signals |
| `docs/ARCHITECTURE_OPTIMIZATION_PLAN.md` | Solutions for API rate limits, slow actions, and cost |
| `docs/sme_architectural_review_prompt.md` | Principal architect prompt for agentic systems review |

## Dashboard & UI

| File | Purpose |
|------|---------|
| `docs/CAIO_DASHBOARD_EMAIL_REFRESH_ROOT_CAUSE_AND_SUSTAINABLE_FIX.md` | Root cause analysis for dashboard email refresh |
| `docs/CAIO_UIUX_BULLETPROOF_HANDOFF_FOR_CLAUDE_2026-02-19.md` | Full UI/UX architecture and implementation handoff |

## Agent & Pipeline

| File | Purpose |
|------|---------|
| `docs/AGENT_MANAGER_COMMANDS.md` | Terminal command cheat sheet for Agent Manager |
| `docs/DORMANT_ENGINES.md` | Status catalog for 7 inactive learning engines + feature flags |
| `docs/GLOSSARY.md` | Domain terminology definitions (80+ terms, 14 categories) |
| `docs/MONACO_SIGNAL_LOOP_GUIDE.md` | Monaco-inspired signal loop implementation guide |
| `docs/REJECTION_LOOP_HARDENING_PLAN.md` | Decision-complete plan for rejection loop personalization |
| `docs/AGENTIC_DOCUMENT_EXTRACTION_INTEGRATION.md` | ADE implementation status from DeepLearning.AI course |

## Testing & Validation

| File | Purpose |
|------|---------|
| `docs/REPLAY_HARNESS.md` | Regression safety enforcement system |
| `docs/CODEX_HANDOFF_TDD_TESTING.md` | TDD & testing feedback loops handoff for Codex |
| `docs/PTO_GTM_SAFE_TRAINING_EVAL_REGIMEN.md` | Safe training and evaluation process for GTM |

## Handoffs & Codex

| File | Purpose |
|------|---------|
| `docs/CODEX_HANDOFF_HOS_REVIEW.md` | HoS requirements integration audit (26 bugs found) |
| `docs/CODEX_HANDOFF_SPRINTS_B_C.md` | Sprint B + C task specs for Codex handoff (11 tasks) |
| `docs/CAIO_HANDOFF_FOR_CLAUDE_2026-02-24.md` | Claude handoff aligned to task tracker (Feb 24) |
| `docs/HOS_EMAIL_REVIEW_GUIDE.md` | Head of Sales email review and feedback guide |
| `docs/HOS_ACTION_ITEMS_GUIDE.md` | HoS action items checklist |
| `docs/PTO_GTM_NEXT_STEPS_TASKS.md` | PTO/GTM next steps task list |
| `docs/PTO_GTM_INPUT_COMPLETION_RUNBOOK.md` | Runbook for closing remaining operational inputs |
| `docs/CAIO_RUNTIME_RELIABILITY_VALIDATION_AND_NEXT_STEPS_2026-02-11.md` | Runtime reliability validation approach |
| `CONTEXT_HANDOFF.md` | Template for context transition between agent sessions |

## Business & GTM

| File | Purpose |
|------|---------|
| `README.md` | Project overview — revenue operations for Chiefaiofficer.com |
| `docs/EXECUTIVE_SUMMARY.md` | High-level mission statement for stakeholders |
| `docs/AI_SALES_EXECUTIVE_SUMMARY.md` | AI Sales enhancement executive summary |
| `docs/AE_SIMPLE_GUIDE.md` | Simple guide for Account Executives on AI team |
| `docs/AE_ASSET_REQUIREMENTS.md` | Sales Ops assets needed for full CAIO contextualization |
| `docs/CAIO_ALPHA_MAJOR_INPUTS_REQUIRED.md` | Leadership inputs required for implementation |
| `docs/PLAN_LINKEDIN_SUSTAINABILITY_PHASE3_PREREQS.md` | LinkedIn sustainability prerequisites |
| `docs/AMPCODE_LIVE_FIRE_PHASE_DAYS_31_35.md` | Transition from shadow mode to production |
| `docs/AMPCODE_LIVE_FIRE_PHASE_DAYS_36_40.md` | Vercel lead agent patterns and acceleration |
| `docs/AI_ASSISTED_INTEGRATION_GUIDE.md` | Structured approach to AI coding assistant leverage |
| `docs/GITHUB_REPOSITORY_PATTERNS.md` | Key patterns for bulletproofing the unified swarm |

## Archive (Superseded)

| File | Purpose |
|------|---------|
| `docs/archive/CAIO_HANDOFF_PHASE2_BURN_IN_2026-02-13.md` | Phase 2 burn-in handoff (superseded) |
| `docs/archive/CAIO_HANDOFF_PRELIVE_INPUTS_FOR_CLAUDE_2026-02-18.md` | Pre-live inputs guide (superseded) |
| `docs/archive/CAIO_HANDOFF_RUNTIME_RELIABILITY_2026-02-11.md` | Runtime reliability handoff (superseded) |
| `docs/archive/CAIO_PRODUCTION_CUTOVER_HANDOFF_FOR_CLAUDE.md` | Production cutover handoff (superseded) |
| `docs/archive/CAIO_REDIS_INNGEST_HANDOFF_NON_TECH_2026-02-11.md` | Redis/Inngest setup guide (superseded) |
| `docs/archive/CODEX_HANDOFF.md` | Deep code review handoff (superseded) |
| `docs/archive/CODEX_HANDOFF_SHADOW_QUEUE.md` | Shadow queue implementation handoff (superseded) |
| `docs/archive/IMPLEMENTATION_COMPLETE.md` | Phase 1-5 SDR automation completion record |
| `docs/archive/PRODUCTION_LAUNCH_GUIDE.md` | Non-technical GTM launch guide (superseded) |
| `docs/archive/PRODUCTION_LAUNCH_README.md` | Beta-era production launch documentation |
| `docs/archive/PRODUCTION_READINESS.md` | Production readiness assessment (superseded) |
| `docs/archive/PRODUCTION_READINESS_CHECKLIST.md` | Readiness checklist from Jan 26, 2026 |
| `docs/archive/PRODUCTION_STATUS.md` | Previous phase status snapshot |
| `docs/archive/PRODUCTION_STEPS.md` | Historical step-by-step production guide |
| `docs/archive/SUBDOMAIN_SETUP_HANDOFF.md` | business.chiefaiofficer.com subdomain setup |

---

## Navigation Quick-Start

1. **New session**: CLAUDE.md > task.md > CAIO_CLAUDE_MEMORY.md
2. **Implementation**: CAIO_IMPLEMENTATION_PLAN.md (all phases) + task.md (current sprint)
3. **Deployment**: DEPLOYMENT_GUIDE.md > DEPLOYMENT_CHECKLIST.md > PRODUCTION_QUICK_START.md
4. **API setup**: API_INTEGRATION_GUIDE.md (priority order) > individual setup guides
5. **Operations**: RUNBOOK.md (daily ops) + CAIO_OPERATIONAL_ROADMAP.md (GTM guidance)
6. **Testing**: REPLAY_HARNESS.md + CODEX_HANDOFF_TDD_TESTING.md (regression safety)
7. **Architecture**: WIRED_ARCHITECTURE.md (design) + ARCHITECTURE_OPTIMIZATION_PLAN.md (improvements)
8. **Security**: AGENTIC_ENGINEERING_AUDIT_HANDOFF.md (audit) + DORMANT_ENGINES.md (engine status)

---

*Auto-generated. Run `python scripts/check_doc_freshness.py` to detect stale docs.*
