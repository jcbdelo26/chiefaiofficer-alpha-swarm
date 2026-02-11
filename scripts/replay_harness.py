#!/usr/bin/env python3
"""
Replay Harness for CAIO Alpha Swarm
===================================

Workflow:
1) Record: Executes Golden Set queries and stores raw run artifacts.
2) Replay: Re-runs scenarios through a pluggable runner command.
3) Judge: Scores outputs with a deterministic SME-aligned rubric.
4) Block: Fails process when pass rate drops below threshold.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple


REQUIRED_CASE_FIELDS = {
    "id",
    "input_query",
    "expected_tools",
    "positive_constraints",
    "negative_constraints",
}


@dataclass
class RunnerResult:
    actual_output: str
    tool_trace_log: List[str]
    rag_context_chunks: List[str]
    metadata: Dict[str, Any]


def _normalize_tool_name(name: str) -> str:
    return "".join(name.strip().lower().split())


def _tool_match(expected: str, actual: str) -> bool:
    e = _normalize_tool_name(expected)
    a = _normalize_tool_name(actual)
    return e == a or e in a or a in e


def _constraint_present(text: str, constraint: str) -> bool:
    return constraint.lower() in text.lower()


def _negative_fragment(constraint: str) -> str:
    c = constraint.strip().lower().rstrip(".")
    if c.startswith("do not "):
        return c[7:]
    return c


def load_golden_set(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Golden set must be a JSON array.")
    for idx, case in enumerate(data):
        if not isinstance(case, dict):
            raise ValueError(f"Case #{idx} is not an object.")
        missing = REQUIRED_CASE_FIELDS - set(case.keys())
        if missing:
            raise ValueError(f"Case #{idx} missing fields: {sorted(missing)}")
    return data


def run_case_with_runner(runner_cmd: str, case: Dict[str, Any], timeout_seconds: int = 120) -> RunnerResult:
    cmd = shlex.split(runner_cmd, posix=False)
    proc = subprocess.run(
        cmd,
        input=json.dumps(case),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Runner command failed (exit={proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
        )
    if not proc.stdout.strip():
        raise RuntimeError("Runner produced empty stdout.")

    payload = json.loads(proc.stdout)
    actual_output = str(payload.get("actual_output", ""))
    tool_trace_log = payload.get("tool_trace_log", [])
    rag_context_chunks = payload.get("rag_context_chunks", [])
    metadata = payload.get("metadata", {})

    if not isinstance(tool_trace_log, list):
        tool_trace_log = [str(tool_trace_log)]
    if not isinstance(rag_context_chunks, list):
        rag_context_chunks = [str(rag_context_chunks)]
    if not isinstance(metadata, dict):
        metadata = {"raw_metadata": str(metadata)}

    return RunnerResult(
        actual_output=actual_output,
        tool_trace_log=[str(t) for t in tool_trace_log],
        rag_context_chunks=[str(c) for c in rag_context_chunks],
        metadata=metadata,
    )


def evaluate_case(
    case: Dict[str, Any],
    run: RunnerResult,
    prior_output: Optional[str] = None,
) -> Dict[str, Any]:
    expected_tools = [str(t) for t in case.get("expected_tools", [])]
    actual_tools = [str(t) for t in run.tool_trace_log]

    missing_tools: List[str] = []
    for et in expected_tools:
        if not any(_tool_match(et, at) for at in actual_tools):
            missing_tools.append(et)

    unexpected_tools: List[str] = []
    for at in actual_tools:
        if not any(_tool_match(et, at) for et in expected_tools):
            unexpected_tools.append(at)

    if not expected_tools:
        tool_score = 3
    elif not missing_tools and not unexpected_tools:
        tool_score = 5
    elif not missing_tools:
        tool_score = 4
    elif len(missing_tools) == 1:
        tool_score = 3
    elif len(missing_tools) < len(expected_tools):
        tool_score = 2
    else:
        tool_score = 1

    output_text = run.actual_output or ""
    rag_text = "\n".join(run.rag_context_chunks)

    positive_constraints = [str(c) for c in case.get("positive_constraints", [])]
    positive_met = [c for c in positive_constraints if _constraint_present(output_text, c)]
    positive_missed = [c for c in positive_constraints if c not in positive_met]

    if not positive_constraints:
        completeness_score = 3
    else:
        ratio = len(positive_met) / len(positive_constraints)
        if ratio >= 0.9:
            completeness_score = 5
        elif ratio >= 0.7:
            completeness_score = 4
        elif ratio >= 0.5:
            completeness_score = 3
        elif ratio >= 0.3:
            completeness_score = 2
        else:
            completeness_score = 1

    unsupported_claims: List[str] = []
    if rag_text.strip():
        for c in positive_met:
            if not _constraint_present(rag_text, c):
                unsupported_claims.append(c)
    else:
        if positive_met:
            unsupported_claims.extend(positive_met)

    if not rag_text.strip():
        grounded_score = 1 if output_text.strip() else 3
    elif not unsupported_claims:
        grounded_score = 5
    elif len(unsupported_claims) == 1:
        grounded_score = 3
    else:
        grounded_score = 2

    negative_constraints = [str(c) for c in case.get("negative_constraints", [])]
    negative_violations: List[str] = []
    output_lower = output_text.lower()
    for nc in negative_constraints:
        fragment = _negative_fragment(nc)
        if fragment and fragment in output_lower:
            negative_violations.append(nc)

    if prior_output is None:
        reliability_score = 4
        reliability_reason = "No prior baseline output for this case."
    else:
        similarity = SequenceMatcher(None, prior_output, output_text).ratio()
        if similarity >= 0.90:
            reliability_score = 5
        elif similarity >= 0.75:
            reliability_score = 4
        elif similarity >= 0.60:
            reliability_score = 3
        elif similarity >= 0.40:
            reliability_score = 2
        else:
            reliability_score = 1
        reliability_reason = f"Output similarity vs baseline: {similarity:.2f}"

    overall = round(mean([tool_score, grounded_score, completeness_score, reliability_score]), 2)
    auto_fail = tool_score <= 2 or grounded_score <= 2 or len(negative_violations) > 0
    passed = (not auto_fail) and overall >= 4.0

    result = {
        "overall_score": overall,
        "pass": passed,
        "rubric": {
            "tool_selection_accuracy": {
                "score": tool_score,
                "reason": (
                    "Exact match."
                    if not missing_tools and not unexpected_tools
                    else f"Missing: {missing_tools}; Unexpected: {unexpected_tools}"
                ),
            },
            "groundedness": {
                "score": grounded_score,
                "reason": "All key claims grounded in retrieved context."
                if not unsupported_claims
                else f"Unsupported constraints: {unsupported_claims}",
            },
            "completeness": {
                "score": completeness_score,
                "reason": f"Met {len(positive_met)}/{len(positive_constraints)} positive constraints.",
            },
            "reliability_consistency": {
                "score": reliability_score,
                "reason": reliability_reason,
            },
        },
        "expected_tools_evaluation": {
            "missing_tools": missing_tools,
            "unexpected_tools": unexpected_tools,
            "tool_match_summary": f"{len(expected_tools) - len(missing_tools)}/{len(expected_tools)} expected tools matched.",
        },
        "constraints_evaluation": {
            "positive_constraints_met": positive_met,
            "positive_constraints_missed": positive_missed,
            "negative_constraints_violated": negative_violations,
        },
        "hallucination_check": {
            "unsupported_claims": unsupported_claims,
            "notes": "Deterministic check based on positive-constraint grounding.",
        },
        "final_verdict": (
            "FAIL: Automatic fail condition triggered."
            if auto_fail
            else ("PASS" if passed else "FAIL: Overall score below threshold.")
        ),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run replay harness against Golden Set.")
    parser.add_argument(
        "--golden-set",
        default="tests/golden/caio_alpha_golden_set_v1.json",
        help="Path to Golden Set JSON file.",
    )
    parser.add_argument(
        "--runner-cmd",
        default=f"{sys.executable} scripts/swarm_replay_runner.py",
        help="Runner command that reads a case JSON on stdin and returns run JSON on stdout.",
    )
    parser.add_argument(
        "--output-dir",
        default=".hive-mind/replay_harness",
        help="Directory where replay artifacts are stored.",
    )
    parser.add_argument(
        "--baseline-file",
        default="tests/golden/replay_baseline_outputs.json",
        help="Baseline outputs for reliability drift scoring.",
    )
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=0.95,
        help="Minimum pass rate required to succeed (e.g. 0.95).",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=0,
        help="Optional limit for quick runs (0 means all).",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write current outputs as new baseline file.",
    )

    args = parser.parse_args()

    golden_path = Path(args.golden_set)
    output_dir = Path(args.output_dir)
    baseline_path = Path(args.baseline_file)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / timestamp
    cases_dir = run_dir / "cases"
    cases_dir.mkdir(parents=True, exist_ok=True)

    golden = load_golden_set(golden_path)
    if args.max_cases > 0:
        golden = golden[: args.max_cases]

    baseline_outputs: Dict[str, str] = {}
    if baseline_path.exists():
        try:
            raw = json.loads(baseline_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                baseline_outputs = {str(k): str(v) for k, v in raw.items()}
        except Exception:
            baseline_outputs = {}

    summary_rows: List[Dict[str, Any]] = []
    current_outputs: Dict[str, str] = {}

    for case in golden:
        case_id = str(case["id"])
        record: Dict[str, Any] = {
            "case_id": case_id,
            "input_query": case["input_query"],
            "expected_tools": case["expected_tools"],
            "status": "ok",
        }
        try:
            run_result = run_case_with_runner(args.runner_cmd, case)
            judge_result = evaluate_case(
                case=case,
                run=run_result,
                prior_output=baseline_outputs.get(case_id),
            )
            record["run_result"] = {
                "actual_output": run_result.actual_output,
                "tool_trace_log": run_result.tool_trace_log,
                "rag_context_chunks": run_result.rag_context_chunks,
                "metadata": run_result.metadata,
            }
            record["judge_result"] = judge_result
            current_outputs[case_id] = run_result.actual_output
            summary_rows.append(
                {
                    "case_id": case_id,
                    "pass": judge_result["pass"],
                    "overall_score": judge_result["overall_score"],
                    "tool_score": judge_result["rubric"]["tool_selection_accuracy"]["score"],
                    "groundedness_score": judge_result["rubric"]["groundedness"]["score"],
                }
            )
        except Exception as exc:
            record["status"] = "runner_error"
            record["error"] = str(exc)
            summary_rows.append(
                {
                    "case_id": case_id,
                    "pass": False,
                    "overall_score": 0.0,
                    "tool_score": 0,
                    "groundedness_score": 0,
                    "error": str(exc),
                }
            )
        (cases_dir / f"{case_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    passed_cases = [r for r in summary_rows if r.get("pass")]
    pass_rate = (len(passed_cases) / len(summary_rows)) if summary_rows else 0.0
    avg_score = mean([float(r.get("overall_score", 0.0)) for r in summary_rows]) if summary_rows else 0.0

    summary = {
        "timestamp_utc": timestamp,
        "golden_set_path": str(golden_path),
        "runner_cmd": args.runner_cmd,
        "total_cases": len(summary_rows),
        "passed_cases": len(passed_cases),
        "failed_cases": len(summary_rows) - len(passed_cases),
        "pass_rate": round(pass_rate, 4),
        "min_pass_rate_required": args.min_pass_rate,
        "average_score": round(avg_score, 2),
        "block_build": pass_rate < args.min_pass_rate,
        "results": summary_rows,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.update_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(current_outputs, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 1 if summary["block_build"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
