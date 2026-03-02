# Dormant Learning Engines

> **Status**: All engines listed below are DORMANT or PARTIALLY ACTIVE.
> They collect data but do NOT change pipeline behaviour.
> Activation is gated behind individual feature flags (default: `false`).
> Do not enable until `task.md` marks Phase 5 active.

## Summary

| # | Engine | Path | Lines | Feature Flag | Status |
|---|--------|------|-------|--------------|--------|
| 1 | Feedback Loop | `core/feedback_loop.py` | 295 | `FEEDBACK_LOOP_POLICY_ENABLED` | WIRED (Sprint D-4): records tuples + quality_guard integration (GUARD-001 boost, GUARD-004 dynamic openers) |
| 2 | A/B Test Engine | `core/ab_test_engine.py` | 825 | `AB_TEST_ENGINE_ENABLED` | Dormant (harness exists, no active tests) |
| 3 | Self-Annealing Engine | `core/self_annealing_engine.py` | 1,205 | `SELF_ANNEALING_ENGINE_ENABLED` | Dormant (RETRIEVE-JUDGE-DISTILL pipeline, not integrated with CRAFTER) |
| 4 | RL Engine | `execution/rl_engine.py` | 514 | `RL_ENGINE_ENABLED` | Dormant (Q-learning infrastructure, no active policies) |
| 5 | Self-Learning ICP | `core/self_learning_icp.py` | 793 | `SELF_LEARNING_ICP_ENABLED` | Dormant (collects engagement data, doesn't rerank Tier boundaries) |
| 6 | Quality Guard | `core/quality_guard.py` | 329 | N/A (deterministic) | Active but non-adaptive (5 deterministic rules, no ML tuning) |
| 7 | CRAFTER Template Selection | N/A (inline in crafter) | -- | N/A | Not built (template rotation not learning-driven) |

**Total dormant code**: ~3,921 lines across 5 flagged files (excludes quality_guard which is active).

## Activation Criteria

Each engine requires ALL of the following before activation:

1. **Phase gate**: `task.md` marks Phase 5 ("Full Autonomy") as active
2. **Feature flag**: Set the engine's flag to `true` in Railway env vars
3. **Data threshold**: Minimum training data accumulated (see per-engine below)
4. **Rollback switch**: Flag can be set back to `false` to instantly disable
5. **Audit trace**: All decisions logged via `core/trace_envelope.py`

## Per-Engine Details

### 1. Feedback Loop (`FEEDBACK_LOOP_POLICY_ENABLED`)

- **What it does today**: Records (state, action, outcome, reward) training tuples to `.hive-mind/feedback_loop/training_tuples.jsonl` and Redis. Provides `get_lead_approval_count()` and `get_latest_policy_delta()` helpers.
- **What it does when enabled** (Sprint D-4, WIRED): GUARD-001 grants leniency to leads approved 3+ times (bypasses rejection block). GUARD-004 extends banned openers dynamically from `build_policy_deltas()` output. All gated behind `FEEDBACK_LOOP_POLICY_ENABLED=true`.
- **Data threshold**: 200+ training tuples with outcome diversity (at least 50 approved, 50 rejected).
- **Integration points**: `core/quality_guard.py` (GUARD-001, GUARD-004), `execution/operator_outbound.py`
- **Tests**: `tests/test_feedback_integration.py` (12 tests: approval boost, dynamic openers, feature flag gating)

### 2. A/B Test Engine (`AB_TEST_ENGINE_ENABLED`)

- **What it does today**: Provides test harness infrastructure (variant assignment, statistical analysis, winner detection).
- **What it will do when enabled**: Track subject line open/reply rates via Instantly webhooks, auto-promote winning variants, retire losers.
- **Data threshold**: 100+ sends per variant for statistical significance.
- **Integration points**: `execution/crafter_campaign.py`, Instantly webhook consumer

### 3. Self-Annealing Engine (`SELF_ANNEALING_ENGINE_ENABLED`)

- **What it does today**: RETRIEVE-JUDGE-DISTILL-CONSOLIDATE pipeline infrastructure for template/strategy selection using simulated annealing.
- **What it will do when enabled**: Automatically select optimal email templates, angles, and personalization depth per lead tier using temperature-based exploration/exploitation.
- **Data threshold**: 500+ email outcomes with template attribution.
- **Integration points**: `execution/crafter_campaign.py`, `core/feedback_loop.py`

### 4. RL Engine (`RL_ENGINE_ENABLED`)

- **What it does today**: Q-learning infrastructure with state/action spaces, epsilon-greedy exploration, Q-table persistence.
- **What it will do when enabled**: Learn optimal template selection, send timing, personalization depth, and channel selection policies from reward signals.
- **Data threshold**: 1,000+ state-action-reward tuples.
- **Integration points**: `execution/operator_outbound.py`, `core/feedback_loop.py`

### 5. Self-Learning ICP (`SELF_LEARNING_ICP_ENABLED`)

- **What it does today**: Captures deal outcomes (won/lost/ghost) from GHL webhooks, stores lead embeddings.
- **What it will do when enabled**: Reweight Tier boundaries based on reply/meeting conversion rates. Adjust ICP scoring multipliers using pattern analysis from Supabase pgvector.
- **Data threshold**: 50+ closed deals (won + lost) with ICP metadata.
- **Integration points**: `config/icp_config.py`, `core/lead_signals.py`, GHL webhook consumer

### 6. Quality Guard (deterministic -- no flag needed)

- **Current state**: 5 deterministic rules + feedback integration (Sprint D-4). GUARD-001 now supports approval boost for 3x-approved leads. GUARD-004 now supports dynamic banned openers from policy deltas. Both gated behind `FEEDBACK_LOOP_POLICY_ENABLED`.
- **Future**: Full ML-adaptive scoring by ingesting cumulative feedback outcomes. Template-level success rate weighting.

### 7. CRAFTER Template Selection (not yet built)

- **Current state**: Template selection in `execution/crafter_campaign.py` uses static rotation.
- **Future**: Learning-driven template selection based on A/B test results and RL engine policies. Would depend on engines #2 and #4 being active.

## Proven Pattern: Rejection Memory

The only learning engine that currently closes the loop is `core/rejection_memory.py`:
- Blocks repeat rejections per-lead (Redis primary, file fallback, 30-day TTL)
- Proven stable across 10+ consecutive pipeline runs
- **This is the template for activating the other 6 engines**

## Rollback Procedure

To disable any engine in an emergency:
1. Set the feature flag to `false` in Railway env vars (e.g., `RL_ENGINE_ENABLED=false`)
2. Redeploy (Railway auto-deploys on env var change)
3. Engine reverts to data-collection-only mode immediately
4. No data loss -- all collected tuples are preserved
