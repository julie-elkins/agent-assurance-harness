import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "adapter_regression_report.py"
ADAPTER = REPOSITORY / "examples" / "guarded_adapter.py"
REGRESSED_ADAPTER = REPOSITORY / "examples" / "regressed_adapter.py"


def test_adapter_regression_report_passes_without_emitting_commands_or_traces():
    command = [
        sys.executable,
        str(TOOL),
        "--agent-id",
        "external",
        "--baseline-adapter-command",
        sys.executable,
        "--baseline-adapter-command",
        str(ADAPTER),
        "--candidate-adapter-command",
        sys.executable,
        "--candidate-adapter-command",
        str(ADAPTER),
        "--baseline-change-id",
        "approved-baseline-2026-10-20",
        "--baseline-component",
        "guardrails",
        "--candidate-change-id",
        "candidate-guardrails-2026-10-20",
        "--candidate-component",
        "guardrails",
        "--fail-on-findings",
    ]

    completed = subprocess.run(
        command,
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    report = json.loads(completed.stdout)
    assert report["passed"] is True
    assert report["expected_scenario_count"] == 5
    assert report["baseline_harness_change"]["change_id"] == (
        "approved-baseline-2026-10-20"
    )
    assert report["candidate_harness_change"]["change_id"] == (
        "candidate-guardrails-2026-10-20"
    )
    serialized = json.dumps(report)
    assert "adapter_command" not in serialized
    assert '"trace"' not in serialized


def test_adapter_regression_report_negative_control_blocks_degraded_candidate():
    command = [
        sys.executable,
        str(TOOL),
        "--agent-id",
        "external",
        "--baseline-adapter-command",
        sys.executable,
        "--baseline-adapter-command",
        str(ADAPTER),
        "--candidate-adapter-command",
        sys.executable,
        "--candidate-adapter-command",
        str(REGRESSED_ADAPTER),
        "--baseline-change-id",
        "approved-baseline-2026-10-20",
        "--baseline-component",
        "guardrails",
        "--candidate-change-id",
        "candidate-regression-control-2026-10-20",
        "--candidate-component",
        "guardrails",
        "--expect-blocking",
    ]

    completed = subprocess.run(
        command,
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    report = json.loads(completed.stdout)
    assert report["passed"] is False
    assert any(finding["blocking"] for finding in report["findings"])
