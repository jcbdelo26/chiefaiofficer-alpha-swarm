# Replay Harness

This harness enforces regression safety for `chiefaiofficer-alpha-swarm`:

1. Record: captures `input_query`, `actual_output`, `tool_trace_log`, `rag_context_chunks`.
2. Replay: runs the Golden Set through a runner command.
3. Judge: deterministic rubric scoring aligned to SME criteria.
4. Block: exits non-zero when pass rate is below threshold.

## Golden Set

- File: `tests/golden/caio_alpha_golden_set_v1.json`
- Cases: 50
- Required fields per case:
  - `id`
  - `input_query`
  - `expected_tools`
  - `positive_constraints`
  - `negative_constraints`

## Run

```bash
python scripts/replay_harness.py \
  --golden-set tests/golden/caio_alpha_golden_set_v1.json \
  --runner-cmd "python scripts/swarm_replay_runner.py" \
  --min-pass-rate 0.95
```

Artifacts are written to:

- `.hive-mind/replay_harness/<timestamp>/summary.json`
- `.hive-mind/replay_harness/<timestamp>/cases/<case_id>.json`

## Baseline Drift

Capture baseline outputs:

```bash
python scripts/replay_harness.py --update-baseline
```

Baseline file:

- `tests/golden/replay_baseline_outputs.json`

## CI Gate

Use this command in CI on each push:

```bash
python scripts/replay_harness.py --min-pass-rate 0.95
```

If pass rate regresses below threshold, process exits with status `1` and should fail the build.
