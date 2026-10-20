import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
REPORT_TOOL = REPOSITORY / "tools" / "adapter_regression_report.py"
SUMMARY_TOOL = REPOSITORY / "tools" / "render_assurance_summary.py"
ADAPTER = REPOSITORY / "examples" / "guarded_adapter.py"
REGRESSED_ADAPTER = REPOSITORY / "examples" / "regressed_adapter.py"


def _run_report(
    tmp_path: Path,
    *,
    candidate: Path,
    prefix: str,
    expect_blocking: bool = False,
) -> tuple[Path, Path]:
    report_path = tmp_path / f"{prefix}-report.json"
    attestation_path = tmp_path / f"{prefix}-attestation.json"
    command = [
        sys.executable,
        str(REPORT_TOOL),
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
        f"{prefix}-baseline",
        "--baseline-component",
        "guardrails",
        "--candidate-change-id",
        f"{prefix}-candidate",
        "--candidate-component",
        "guardrails",
        "--output",
        str(report_path),
        "--attestation-output",
        str(attestation_path),
    ]
    if expect_blocking:
        command.append("--expect-blocking")
    completed = subprocess.run(
        command,
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    return report_path, attestation_path


def test_summary_renders_safe_control_evidence(tmp_path):
    positive_report, positive_attestation = _run_report(
        tmp_path,
        candidate=ADAPTER,
        prefix="positive",
    )
    negative_report, negative_attestation = _run_report(
        tmp_path,
        candidate=REGRESSED_ADAPTER,
        prefix="negative",
        expect_blocking=True,
    )
    summary_path = tmp_path / "summary.md"

    completed = subprocess.run(
        [
            sys.executable,
            str(SUMMARY_TOOL),
            "--positive-report",
            str(positive_report),
            "--positive-attestation",
            str(positive_attestation),
            "--negative-report",
            str(negative_report),
            "--negative-attestation",
            str(negative_attestation),
            "--output",
            str(summary_path),
        ],
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    summary = summary_path.read_text(encoding="utf-8")
    assert "Candidate assurance:** PASS" in summary
    assert "Negative control:** BLOCKED as expected" in summary
    assert "Scenario-pack set SHA-256" in summary
    assert "prompts, credentials, raw tool payloads" in summary
    assert "adapter_command" not in summary
    assert "private provider output" not in summary


def test_summary_omits_unsafe_change_manifest_values(tmp_path):
    positive_report, positive_attestation = _run_report(
        tmp_path,
        candidate=ADAPTER,
        prefix="positive",
    )
    negative_report, negative_attestation = _run_report(
        tmp_path,
        candidate=REGRESSED_ADAPTER,
        prefix="negative",
        expect_blocking=True,
    )
    report = json.loads(positive_report.read_text(encoding="utf-8"))
    attestation = json.loads(
        positive_attestation.read_text(encoding="utf-8")
    )
    unsafe_change_id = "candidate`-injected"
    report["assurance_attestation"]["candidate_harness_change"]["change_id"] = (
        unsafe_change_id
    )
    attestation["candidate_harness_change"]["change_id"] = unsafe_change_id
    positive_report.write_text(json.dumps(report), encoding="utf-8")
    positive_attestation.write_text(json.dumps(attestation), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(SUMMARY_TOOL),
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
    assert "invalid manifest" in completed.stdout
    assert unsafe_change_id not in completed.stdout


def test_summary_refuses_mismatched_attestation(tmp_path):
    positive_report, positive_attestation = _run_report(
        tmp_path,
        candidate=ADAPTER,
        prefix="positive",
    )
    negative_report, negative_attestation = _run_report(
        tmp_path,
        candidate=REGRESSED_ADAPTER,
        prefix="negative",
        expect_blocking=True,
    )
    attestation = json.loads(positive_attestation.read_text(encoding="utf-8"))
    attestation["git_commit"] = "0" * 40
    positive_attestation.write_text(json.dumps(attestation), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(SUMMARY_TOOL),
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

    assert completed.returncode == 1
    assert "Report and standalone attestation do not match." in completed.stdout
