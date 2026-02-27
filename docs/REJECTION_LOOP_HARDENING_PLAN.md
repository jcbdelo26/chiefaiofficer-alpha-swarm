# Rejection-Loop Personalization Hardening — Decision-Complete Plan

## Phase 1 Findings: Root-Cause Analysis

### Why rejected patterns reappear (Andrew/Celia failure mode)

**Root cause #1 — CRAFTER learns aggregate, not per-lead.**
`CampaignCrafter._load_feedback_profile()` (crafter_campaign.py:564-618) reads the last 200 lines of `agent_feedback.jsonl` and counts rejection tags globally. It does NOT query "was THIS specific lead previously rejected?" When the pipeline re-runs for the same lead, it gets the same template selection logic with the same data and produces similar output.

**Root cause #2 — No rejection-memory gate before queue insertion.**
`_stage_send()` in run_pipeline.py (line 766) calls `shadow_queue.push()` for every lead in approved campaigns. There is zero check for prior rejections on the same `to` email address. A lead rejected 3 times can be re-queued a 4th time with identical content.

**Root cause #3 — No draft fingerprinting or repeat detection.**
When an email is pushed to the shadow queue, it contains `subject`, `body`, `to`, and metadata — but no hash/fingerprint comparing against prior drafts. Two emails with nearly identical body text for the same recipient are treated as independent items.

**Root cause #4 — Template selection is deterministic for same inputs.**
`_select_template()` (crafter_campaign.py:761-792) uses `hash(lead["email"]) % len(templates)` for tier-based selection. Same email address → same template every time. Combined with identical lead data, the output is structurally identical across runs.

**Root cause #5 — Regeneration path has same blind spots.**
`website_intent_monitor.regenerate_active_queue()` re-generates pending emails but uses the same template selection and variable building, producing similar outputs. It does not consult rejection history.

### Where rejection feedback is dropped or weakly encoded

| Signal | Where Stored | Where Read | Gap |
|--------|-------------|-----------|-----|
| rejection_tag | shadow_queue, agent_feedback.jsonl, email_approvals.jsonl, feedback_loop tuples | `_load_feedback_profile()` reads agent_feedback.jsonl | Only aggregate counts — no per-lead lookup |
| feedback text | agent_feedback.jsonl, feedback_loop tuples | `_load_feedback_profile()` checks for "abbreviat" and "full title" keywords | Not passed to template context; not checked per-lead |
| lead_email on rejected item | feedback_loop tuples (lead_features.lead_email) | `build_policy_deltas()` — not used for per-lead gating | Never queried at push time |
| rejection_tag counts | `build_policy_deltas()` output | Nothing consumes the output | Policy deltas written to disk but never read back |

---

## Decision-Complete Implementation Plan

### Component 1: Rejection Memory Store (`core/rejection_memory.py`) — NEW FILE

**Purpose**: Per-lead rejection history with TTL, queryable at draft time and push time.

**Data model** (stored in Redis hash + filesystem fallback):
```python
RejectionRecord = {
    "lead_email": str,           # normalized lowercase
    "rejection_count": int,      # total rejections within TTL window
    "last_rejected_at": str,     # ISO timestamp
    "rejection_tags": List[str], # tags from each rejection
    "rejected_subjects": List[str],  # subjects that were rejected
    "rejected_body_hashes": List[str],  # SHA-256 of first 500 chars of body
    "feedback_texts": List[str], # HoS feedback strings (last 5)
    "ttl_days": 30,              # configurable, default 30
}
```

**Redis key pattern**: `{CONTEXT_REDIS_PREFIX}:rejection_memory:{lead_email_hash}`

**API**:
- `record_rejection(lead_email, rejection_tag, subject, body, feedback_text)` — called from `reject_email()` endpoint
- `get_rejection_history(lead_email) -> Optional[RejectionRecord]` — called from CRAFTER and pre-queue gate
- `compute_draft_fingerprint(subject, body) -> str` — SHA-256 of normalized content
- `is_repeat_draft(lead_email, fingerprint) -> bool` — checks against `rejected_body_hashes`
- `should_block_lead(lead_email, max_rejections=2) -> (bool, str)` — returns block decision + reason

**Defaults**:
- TTL: 30 days
- Max rejections before hard block: 2 (3rd attempt blocked unless new evidence signals)
- Repeat suppression window: 7 days for same lead+campaign

### Component 2: Pre-Queue Quality Guard (`core/quality_guard.py`) — NEW FILE

**Purpose**: Deterministic validator that runs BEFORE `shadow_queue.push()`. Fails drafts that lack evidence-backed personalization.

**Rules**:
1. **GUARD-001: Rejection memory block** — If lead has >=2 prior rejections and no new enrichment signals, BLOCK.
2. **GUARD-002: Repeat draft detection** — If `draft_fingerprint` matches any prior rejected draft for this lead, BLOCK.
3. **GUARD-003: Minimum personalization evidence** — Draft must contain >=2 evidence items: one company-specific, one role-impact-specific. Evidence = non-generic references to company name, initiative, tech stack, hiring signal, event, or content engagement.
4. **GUARD-004: Banned opener patterns** — Draft body must not start with any pattern in the banned list (loaded from rejection memory + hardcoded defaults).
5. **GUARD-005: Generic phrase density** — If >40% of sentences match known generic AI patterns, BLOCK.

**Return type**:
```python
QualityGuardResult = {
    "passed": bool,
    "blocked_reason": Optional[str],
    "rule_failures": List[{"rule_id": str, "message": str}],
    "draft_fingerprint": str,
    "personalization_evidence": List[{"type": str, "value": str, "source": str}],
    "rejection_memory_hit": bool,
}
```

**Banned opener patterns** (initial set, extended from rejection memory):
```python
BANNED_OPENERS = [
    r"^Given your role as\b",
    r"^As (?:a |the )?(?:fellow )?\w+ at\b",
    r"^I noticed (?:that )?you(?:'re| are) (?:a |the )?\w+ at\b",
    r"^(?:Hi|Hey|Hello)[,!]?\s+(?:I )?(?:came across|stumbled upon|noticed)\b",
    r"^I hope this (?:email |message )?finds you\b",
    r"^I wanted to reach out\b",
    r"^I'm reaching out\b",
    r"^Quick question\b",
]
```

### Component 3: CRAFTER Prompt Hardening (patch `crafter_campaign.py`)

**Changes**:

1. **Add per-lead rejection context to `_build_template_variables()`** (line 803):
   - Query `rejection_memory.get_rejection_history(lead["email"])`
   - If history exists, add to template context:
     - `rejection_count`, `rejected_tags`, `feedback_texts`
     - Banned subjects (from prior rejected subjects)
   - Template can reference `{{ rejection_context }}` to avoid repeating patterns

2. **Modify `_select_template()` to avoid previously-rejected templates** (line 761):
   - If rejection history includes the template that would be selected by hash, rotate to next template in tier list
   - Track `rejected_template_ids` in rejection memory

3. **Add `personalization_evidence` extraction** in `generate_email()` (line 897):
   - After rendering, extract evidence items from the final body
   - Evidence = company name mentions, specific initiative references, tech stack mentions, hiring signals
   - Attach as `personalization_evidence` field on the output dict

### Component 4: Wire Rejection Memory into Dashboard (`health_app.py`)

**In `reject_email()` endpoint** (line 2048), after existing rejection logging, add:
```python
from core.rejection_memory import record_rejection
record_rejection(
    lead_email=email_data.get("to", ""),
    rejection_tag=validated_tag,
    subject=email_data.get("subject", ""),
    body=email_data.get("body", ""),
    feedback_text=validated_reason,
)
```

### Component 5: Wire Quality Guard into Pipeline (`run_pipeline.py`)

**In `_stage_send()`**, before `shadow_queue.push()` call (line 766), add:
```python
from core.quality_guard import QualityGuard
guard = QualityGuard()
result = guard.check(shadow_email)
if not result["passed"]:
    blocked += 1
    logger.warning("Quality guard blocked email to %s: %s", shadow_email["to"], result["blocked_reason"])
    continue  # skip this lead
shadow_email["quality_guard_result"] = result
shadow_email["draft_fingerprint"] = result["draft_fingerprint"]
shadow_email["personalization_evidence"] = result["personalization_evidence"]
```

### Component 6: Wire Per-Lead Context into Feedback Loop

**In `FeedbackLoop.build_policy_deltas()`** (feedback_loop.py:172), extend to also produce per-lead rejection summaries that the crafter can query. This is already handled by Component 1 (rejection_memory) — the feedback_loop continues to record tuples as-is, and rejection_memory provides the per-lead query interface.

### Component 7: Sub-Agent Enrichment Architecture (`core/enrichment_sub_agents.py`) — NEW FILE

**Purpose**: When the quality guard detects insufficient personalization evidence (GUARD-003), sub-agents mine existing lead data for deeper signals before blocking.

**Architecture**:
```
Enriched Lead Data → SignalRouter → 5 Sub-Agents → MergedPersonalizationContext
```

**5 specialist sub-agents**:

| Sub-Agent | Input | Output | Confidence |
|-----------|-------|--------|------------|
| `extract_company_intel` | company name, description, industry, employee count | Company-specific signals | 0.6–0.9 |
| `extract_hiring_signals` | hiring_signal, hooks, intent signals | Growth/hiring evidence | 0.75–0.85 |
| `extract_tech_stack` | company.technologies, tech stack hooks | Tech adoption signals | 0.8–0.85 |
| `extract_content_engagement` | source_type, source_name, engagement_content | Event/content signals | 0.65–0.85 |
| `extract_role_impact` | job title → ROLE_IMPACT_MAP | Pain point + impact area | 0.5–0.7 |

**Output schema** (`MergedPersonalizationContext`):
```python
{
    "signals": [PersonalizationSignal(signal_type, value, confidence, source, usable_in_opener)],
    "company_specific_count": int,
    "role_impact_count": int,
    "overall_confidence": float,  # weighted avg of top 5 signals
    "recommended_opener_signal": PersonalizationSignal | None,
    "sub_agent_trace_ids": ["sub:company_intel:3", "sub:hiring_signal:1", ...]
}
```

**Merge strategy**: Quality guard calls `extract_all_signals(lead)` when GUARD-003 fails. If `meets_minimum_evidence` is True (>=1 company + >=1 role signal), GUARD-003 is overridden and the draft passes.

**Confidence scoring**: Each signal has a confidence (0.0–1.0). The `recommended_opener_signal` is the highest-confidence signal where `usable_in_opener=True`. Overall confidence is the weighted average of the top 5 signals.

**Fallback behavior**: If all sub-agents fail (exception), the guard continues with the original GUARD-003 failure. Sub-agent failure never blocks additional emails — it only reduces the chance of rescue.

### Component 8: Documentation/Memory Update Protocol

**CLAUDE.md updates** (already applied):
- Added rejection memory gate, quality guard, sub-agent enrichment, and CRAFTER hardening descriptions to the "Phase 1" validation section.
- Added `rejection_memory/` and `feedback_loop/` to the `.hive-mind/` directory tree.
- Added test file references.

**AGENTS.md governance**:
- `AGENTS.md` is auto-generated by `skills-sync.py` from `.claude/skills/` (26 skills).
- **DO NOT EDIT AGENTS.md DIRECTLY** — update the source skill file, then run `python skills-sync.py --target codex`.
- No rejection-hardening-specific skill needed: the guard is infrastructure, not a task-facing skill.

**Memory update protocol**:
1. After each deploy with rejection hardening changes, update `docs/CAIO_CLAUDE_MEMORY.md` with the commit hash and a note like: "Rejection memory gate + quality guard live".
2. Sync key truth back to `CLAUDE.md` — deploy hash, gate status, active risk notes.
3. If `QUALITY_GUARD_MODE` or `REJECTION_MEMORY_MAX_REJECTIONS` env vars change, document the new values in CLAUDE.md's safety section.

---

## Patch Map By File

| File | Action | Description |
|------|--------|-------------|
| `core/rejection_memory.py` | CREATE | Per-lead rejection memory (Redis + filesystem), TTL, fingerprinting |
| `core/quality_guard.py` | CREATE | Pre-queue deterministic validator (5 rules) |
| `core/enrichment_sub_agents.py` | CREATE | 5 sub-agents for deep signal extraction |
| `execution/crafter_campaign.py` | MODIFY | Per-lead rejection context, template rotation, evidence on output |
| `dashboard/health_app.py` | MODIFY | Wire rejection memory into reject endpoint |
| `execution/run_pipeline.py` | MODIFY | Quality guard gate before shadow_queue.push() |
| `CLAUDE.md` | MODIFY | Document new modules, tests, env vars |
| `tests/test_rejection_memory.py` | CREATE | 26 tests — per-lead memory, TTL, fingerprinting, replay |
| `tests/test_quality_guard.py` | CREATE | 16 tests — all 5 guard rules, soft/disabled mode, replay |
| `tests/test_crafter_rejection_hardening.py` | CREATE | 8 tests — template rotation, feedback context, sub-agents |

---

## Test Plan

### Implemented tests (50 total, all passing):

**test_rejection_memory.py (26 tests)**:
1. `test_fingerprint_deterministic` — same input → same hash
2. `test_fingerprint_differs_for_different_content` — different input → different hash
3. `test_fingerprint_normalizes_whitespace` — "  A  " == "A"
4. `test_fingerprint_uses_first_500_chars` — body truncated to 500 chars
5. `test_record_rejection_stores_and_retrieves` — round-trip persistence
6. `test_record_rejection_increments_count` — 2 rejections → count=2
7. `test_record_rejection_empty_email_returns_empty` — empty email → {}
8. `test_record_rejection_stores_template_id` — template ID tracked
9. `test_record_rejection_deduplicates_subjects` — same subject stored once
10. `test_no_history_returns_none` — unknown lead → None
11. `test_email_normalization` — case-insensitive email lookup
12. `test_ttl_expired_returns_none` — 31-day-old record → None
13. `test_ttl_not_expired_returns_record` — 29-day-old record → valid
14. `test_repeat_draft_detected` — same fingerprint → True
15. `test_different_draft_not_flagged` — different fingerprint → False
16. `test_no_history_not_repeat` — unknown lead → False
17. `test_should_not_block_first_rejection` — 1 rejection → not blocked
18. `test_should_block_after_two_rejections` — 2 rejections → blocked
19. `test_should_not_block_with_new_evidence` — 2 rejections + evidence → not blocked
20. `test_should_not_block_unknown_lead` — unknown → not blocked
21. `test_rejected_template_ids` — template IDs accumulated
22. `test_rejected_template_ids_empty_for_unknown` — unknown → []
23. `test_feedback_context_shape` — context dict has correct keys
24. `test_feedback_context_empty_for_unknown` — unknown → {}
25. `test_andrew_celia_replay_blocked` — 2 rejections → 3rd blocked + repeat detection
26. `test_filesystem_persistence_across_instances` — data survives restart

**test_quality_guard.py (16 tests)**:
27. `test_guard_blocks_after_two_rejections` — GUARD-001
28. `test_guard_passes_first_rejection` — below threshold
29. `test_guard_blocks_repeat_draft` — GUARD-002
30. `test_guard_passes_different_draft` — different content OK
31. `test_guard_blocks_no_company_evidence` — GUARD-003
32. `test_guard_passes_evidence_backed_draft` — company + role evidence OK
33. `test_guard_blocks_banned_opener_given_your_role` — GUARD-004
34. `test_guard_blocks_hope_this_finds_you` — GUARD-004
35. `test_guard_passes_signal_based_opener` — non-banned opener OK
36. `test_guard_blocks_high_generic_density` — GUARD-005
37. `test_guard_passes_low_generic_density` — specific content OK
38. `test_soft_mode_logs_but_passes` — soft mode override
39. `test_disabled_guard_passes_everything` — QUALITY_GUARD_ENABLED=false
40. `test_result_contains_all_fields` — output shape
41. `test_andrew_replay_blocked_by_guard` — full scenario
42. `test_celia_different_content_still_blocked_on_count` — count-based block

**test_crafter_rejection_hardening.py (8 tests)**:
43. `test_template_rotation_after_rejection` — rotates away from rejected template
44. `test_template_rotation_exhausted_falls_back` — all rejected → still returns valid
45. `test_template_rotation_different_lead_unaffected` — no cross-lead leakage
46. `test_feedback_text_appears_in_template_variables` — feedback in context
47. `test_no_rejection_context_for_new_lead` — new lead → empty context
48. `test_generate_email_includes_rejection_context` — output field present
49. `test_sub_agent_enrichment_extracts_signals` — signals from rich data
50. `test_sub_agent_fallback_on_sparse_data` — graceful on empty lead

---

## Rollout + Rollback Plan

**Phase A — Soft Mode (current)**: Implemented with `shadow_mode: true`. Quality guard is ENABLED by default. Set `QUALITY_GUARD_MODE=soft` for log-only (no blocking). Verify via pipeline runs that guard catches the Andrew/Celia repeats.

**Phase B — Hard Mode**: Remove `QUALITY_GUARD_MODE=soft` (or set to empty). Guard now blocks failing drafts and they are skipped in `_stage_send()`. Monitor `Quality guard BLOCKED` log lines.

**Phase C — Tune thresholds**: Adjust `REJECTION_MEMORY_MAX_REJECTIONS` (default: 2) and `REJECTION_MEMORY_TTL_DAYS` (default: 30) based on observed false positives.

**Rollback**: Set `QUALITY_GUARD_ENABLED=false` to bypass all guard checks instantly. Rejection memory continues recording (for visibility) but guard does not block. Zero code rollback needed.

**Env vars reference**:
| Var | Default | Effect |
|-----|---------|--------|
| `QUALITY_GUARD_ENABLED` | `true` | Master switch for quality guard |
| `QUALITY_GUARD_MODE` | (empty = hard) | Set `soft` for log-only |
| `REJECTION_MEMORY_TTL_DAYS` | `30` | How long rejection records persist |
| `REJECTION_MEMORY_MAX_REJECTIONS` | `2` | Block threshold (3rd attempt blocked) |

---

## Open Inputs Needed From PTO

1. **Confirmation**: Is the 2-rejection threshold before hard block acceptable, or should it be 3?
2. **Enrichment retry**: When a lead is blocked due to exceeded rejections, should the system automatically trigger a re-enrichment via Apollo, or just skip the lead?
3. **Template exclusion scope**: Should template rotation apply only to the specific template that was rejected, or to the entire tier's template set? (Currently: specific template only.)
