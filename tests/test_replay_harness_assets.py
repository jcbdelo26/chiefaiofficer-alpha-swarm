import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_PATH = PROJECT_ROOT / "tests" / "golden" / "caio_alpha_golden_set_v1.json"
RUNNER_PATH = PROJECT_ROOT / "scripts" / "swarm_replay_runner.py"
HARNESS_PATH = PROJECT_ROOT / "scripts" / "replay_harness.py"


def test_golden_set_has_50_cases_and_required_fields():
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 50

    ids = [case["id"] for case in data]
    assert len(ids) == len(set(ids))

    required = {"id", "input_query", "expected_tools", "positive_constraints", "negative_constraints"}
    for case in data:
        assert required.issubset(case.keys())
        assert isinstance(case["expected_tools"], list)
        assert isinstance(case["positive_constraints"], list)
        assert isinstance(case["negative_constraints"], list)


def test_swarm_replay_runner_outputs_contract():
    first_case = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))[0]
    proc = subprocess.run(
        [sys.executable, str(RUNNER_PATH)],
        input=json.dumps(first_case),
        text=True,
        capture_output=True,
        check=False,
        cwd=str(PROJECT_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert "actual_output" in payload
    assert "tool_trace_log" in payload
    assert "rag_context_chunks" in payload
    assert isinstance(payload["tool_trace_log"], list)
    assert isinstance(payload["rag_context_chunks"], list)


def test_replay_harness_runs_small_batch(tmp_path: Path):
    output_dir = tmp_path / "replay_out"
    proc = subprocess.run(
        [
            sys.executable,
            str(HARNESS_PATH),
            "--max-cases",
            "3",
            "--min-pass-rate",
            "0.0",
            "--output-dir",
            str(output_dir),
            "--runner-cmd",
            f"{sys.executable} scripts/swarm_replay_runner.py",
        ],
        text=True,
        capture_output=True,
        check=False,
        cwd=str(PROJECT_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    assert summary["total_cases"] == 3
    assert "pass_rate" in summary
