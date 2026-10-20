import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
REGRESSION_TOOL = REPOSITORY / "tools" / "adapter_regression_report.py"
VERIFY_TOOL = REPOSITORY / "tools" / "verify_assurance_evidence.py"
ADAPTER = REPOSITORY / "examples" / "guarded_adapter.py"
REGRESSED_ADAPTER = REPOSITORY / "examples" / "regressed_adapter.py"


def test_verify_assurance_evidence_accepts_both_control_reports(tmp_path):
    positive_report = tmp_path / "positive-report.json"
    positive_attestation = tmp_path / "positive-attestation.json"
    negative_report = tmp_path / "negative-report.json"
    negative_attestation = tmp_path / "negative-attestation.json"

    _run_regression(
        ADAPTER,
        positive_report,
        positive_attestation,
        "approved-baseline-verifier",
        "candidate-verifier",
        "--fail-on-findings",
    )
    _run_regression(
        REGRESSED_ADAPTER,
        negative_report,
        negative_attestation,
        "approved-baseline-verifier-negative",
        "candidate-verifier-negative",
        "--expect-blocking",
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(VERIFY_TOOL),
            "--positive-report",
            str(positive_report),
            "--positive-attestation",
            str(positive_attestation),
            "--negative-report",
            str(negative_report),
            "--negative-attestation",
            str(negative_attestation),
        ],
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    result = json.loads(completed.stdout)
    assert result["verified"] is True
    assert result["positive_blocking_finding_count"] == 0
    assert result["negative_blocking_finding_count"] > 0


def _run_regression(
    candidate: Path,
    report: Path,
    attestation: Path,
    baseline_change_id: str,
    candidate_change_id: str,
    expected_flag: str,
) -> None:
    command = [
        sys.executable,
        str(REGRESSION_TOOL),
        "--agent-id",
        "external",
        "--baseline-adapter-command",
        sys.executable,
        "--baseline-adapter-command",
        str(ADAPTER),
        "--candidate-adapter-command",
        sys.executable,
        "--candidate-adapter-command",
        str(candidate),
        "--baseline-change-id",
        baseline_change_id,
        "--baseline-component",
        "guardrails",
        "--candidate-change-id",
        candidate_change_id,
        "--candidate-component",
        "guardrails",
        "--output",
        str(report),
        "--attestation-output",
        str(attestation),
        expected_flag,
    ]
    completed = subprocess.run(
        command,
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0
