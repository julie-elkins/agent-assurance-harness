import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "adapter_regression_report.py"
ADAPTER = REPOSITORY / "examples" / "guarded_adapter.py"
REGRESSED_ADAPTER = REPOSITORY / "examples" / "regressed_adapter.py"


def test_adapter_regression_report_passes_without_emitting_commands_or_traces(tmp_path):
    attestation_path = tmp_path / "attestation.json"
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
        "--attestation-output",
        str(attestation_path),
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
    assert report["expected_scenario_count"] == 9
    attestation = report["assurance_attestation"]
    assert attestation["attestation_version"] == 1
    assert attestation["attestation_id"] == "adapter-regression-attestation-v1"
    assert attestation["package_version"] == "0.42.0"
    assert len(attestation["git_commit"]) == 40
    assert len(attestation["pack_set_sha256"]) == 64
    assert len(attestation["pack_manifests"]) == 9
    assert attestation["blocking_finding_count"] == 0
    assert attestation["observation_count"] == 0
    assert json.loads(attestation_path.read_text(encoding="utf-8")) == attestation
    assert report["baseline_harness_change"]["change_id"] == (
        "approved-baseline-2026-10-20"
    )
    assert report["candidate_harness_change"]["change_id"] == (
        "candidate-guardrails-2026-10-20"
    )
    serialized = json.dumps(report)
    assert "adapter_command" not in serialized
    assert '"trace"' not in serialized


def test_adapter_regression_report_negative_control_blocks_degraded_candidate(tmp_path):
    attestation_path = tmp_path / "negative-attestation.json"
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
        "--attestation-output",
        str(attestation_path),
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
    assert report["assurance_attestation"]["passed"] is False
    assert report["assurance_attestation"]["blocking_finding_count"] > 0
    assert json.loads(attestation_path.read_text(encoding="utf-8")) == (
        report["assurance_attestation"]
    )
