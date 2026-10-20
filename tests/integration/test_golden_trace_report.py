import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "golden_trace_report.py"
GOLDEN_REPLAY = REPOSITORY / "examples" / "traces" / "guarded.json"
GOLDEN_MANIFEST = REPOSITORY / "examples" / "traces" / "golden-manifest.json"


def _command(adapter: str, *extra: str) -> list[str]:
    return [
        sys.executable,
        str(TOOL),
        "--golden-replay",
        str(GOLDEN_REPLAY),
        "--golden-manifest",
        str(GOLDEN_MANIFEST),
        "--agent-id",
        "external",
        "--candidate-adapter-command",
        sys.executable,
        "--candidate-adapter-command",
        str(REPOSITORY / "examples" / adapter),
        "--candidate-change-id",
        "candidate-golden-test",
        "--candidate-component",
        "guardrails",
        *extra,
    ]


def test_golden_trace_report_passes_guarded_adapter():
    completed = subprocess.run(
        _command("guarded_adapter.py", "--fail-on-drift"),
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    data = json.loads(completed.stdout)
    assert data["passed"] is True
    assert data["drifts"] == []
    assert '"trace"' not in json.dumps(data)


def test_golden_trace_report_detects_degraded_adapter():
    completed = subprocess.run(
        _command("regressed_adapter.py", "--expect-drift"),
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    data = json.loads(completed.stdout)
    assert data["passed"] is False
    assert data["drifts"]
    assert data["candidate_evaluation_passed"] is False
