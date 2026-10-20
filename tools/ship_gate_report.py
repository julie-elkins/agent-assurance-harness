"""Evaluate the synthetic operational ship gate from metadata-only reports."""

from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from agent_reliability_lab.ship_gate import (
    CheckObservation,
    ShipGateManifest,
    ShipGateReport,
    evaluate_ship_gate,
    load_ship_gate,
)

ROOT = Path(__file__).resolve().parents[1]


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Report must contain a JSON object.")
    return value


def _package_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]["version"]


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _safe_value(value: object) -> str | None:
    if isinstance(value, str) and value and all(
        character.isalnum() or character in "._:/-" for character in value
    ):
        return value
    return None


def _audit_observation(
    check_id: str,
    regression_path: Path | None,
    golden_path: Path | None,
) -> tuple[CheckObservation, dict[str, str]]:
    """Bind report identifiers to the current checkout and baseline manifest."""

    reasons: list[str] = []
    values: dict[str, str] = {}
    regression = _read_object(regression_path) if regression_path else {}
    golden = _read_object(golden_path) if golden_path else {}
    attestation = regression.get("assurance_attestation")
    if not isinstance(attestation, dict):
        reasons.append("assurance-attestation-missing")
        attestation = {}
    manifest = golden.get("manifest")
    if not isinstance(manifest, dict):
        reasons.append("golden-manifest-missing")
        manifest = {}

    observed = {
        "git-commit": attestation.get("git_commit"),
        "package-version": attestation.get("package_version"),
        "scenario-pack-sha256": attestation.get("pack_set_sha256"),
        "golden-trace-sha256": golden.get("candidate_trace_sha256"),
    }
    for field, value in observed.items():
        safe = _safe_value(value)
        if safe is None:
            reasons.append(f"{field}-missing")
        else:
            values[field] = safe

    try:
        current_git_commit = _git_commit()
        current_package_version = _package_version()
    except (OSError, subprocess.SubprocessError, KeyError, TypeError) as error:
        raise ValueError("Current checkout identity could not be read.") from error

    if values.get("git-commit") != current_git_commit:
        reasons.append("git-commit-mismatch")
    if values.get("package-version") != current_package_version:
        reasons.append("package-version-mismatch")
    if values.get("scenario-pack-sha256") != _safe_value(
        manifest.get("pack_set_sha256")
    ):
        reasons.append("scenario-pack-sha256-mismatch")
    if values.get("golden-trace-sha256") != _safe_value(
        manifest.get("trace_sha256")
    ):
        reasons.append("golden-trace-sha256-mismatch")

    return CheckObservation(
        check_id,
        not reasons,
        "matched" if not reasons else ";".join(reasons),
    ), values


def _regression_observation(
    check_id: str,
    path: Path,
    *,
    expected: str,
) -> CheckObservation:
    report = _read_object(path)
    refusal = report.get("refusal")
    findings = report.get("findings")
    if not isinstance(findings, list):
        return CheckObservation(check_id, False, "findings_missing")
    if expected == "pass":
        passed = report.get("passed") is True and refusal is None and not findings
        reason = "passed" if passed else "candidate_regression"
    elif expected == "blocked":
        passed = (
            report.get("passed") is False
            and refusal is None
            and any(
                isinstance(item, dict) and item.get("blocking") is True
                for item in findings
            )
        )
        reason = "blocking-finding-caught" if passed else "negative-control-not-caught"
    else:
        passed = False
        reason = "unsupported-expected-state"
    return CheckObservation(check_id, passed, reason)


def _golden_observation(
    check_id: str,
    path: Path,
    *,
    expected: str,
) -> CheckObservation:
    report = _read_object(path)
    refusal = report.get("refusal")
    drifts = report.get("drifts")
    if not isinstance(drifts, list):
        return CheckObservation(check_id, False, "drifts_missing")
    if expected == "pass":
        passed = report.get("passed") is True and refusal is None and not drifts
        reason = "passed" if passed else "golden-trace-drift"
    elif expected == "drift-caught":
        passed = (
            report.get("passed") is False
            and refusal is None
            and bool(drifts)
        )
        reason = "drift-caught" if passed else "negative-control-not-caught"
    else:
        passed = False
        reason = "unsupported-expected-state"
    return CheckObservation(check_id, passed, reason)


def _observations(
    manifest: ShipGateManifest,
    paths: dict[str, Path],
    audit_observation: CheckObservation,
) -> dict[str, CheckObservation]:
    observations: dict[str, CheckObservation] = {}
    for check in manifest.required_checks:
        if check.report_kind == "audit":
            observations[check.check_id] = audit_observation
            continue
        path = paths.get(check.check_id)
        if path is None:
            continue
        if check.report_kind == "adapter-regression":
            observations[check.check_id] = _regression_observation(
                check.check_id,
                path,
                expected=check.expected,
            )
        elif check.report_kind == "golden-trace":
            observations[check.check_id] = _golden_observation(
                check.check_id,
                path,
                expected=check.expected,
            )
        else:
            observations[check.check_id] = CheckObservation(
                check.check_id,
                False,
                "unsupported-report-kind",
            )
    return observations


def _refused_data(error: Exception) -> dict[str, object]:
    return {
        "ship_gate_version": 1,
        "decision": "blocked",
        "passed": False,
        "blocking_reasons": ["ship-gate-refused"],
        "refusal": {
            "error": "ship_gate_refused",
            "message": "The operational ship gate could not be evaluated.",
            "guidance": "Repair the manifest or metadata-only reports before retrying.",
            "source": type(error).__name__,
        },
        "diagnostics": {
            "warnings": [
                "A refusal is a blocked decision, not a passing empty result."
            ],
            "what_it_does_not_show": (
                "It does not identify report paths or expose report contents."
            ),
        },
    }


def _render(data: dict[str, object], report: ShipGateReport | None) -> str:
    if report is None:
        return json.dumps(data, indent=2, sort_keys=True) + "\n"
    return report.to_markdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate the metadata-only operational ship gate and block when "
            "required assurance evidence is missing or fails."
        )
    )
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--adapter-regression-positive", type=Path)
    parser.add_argument("--golden-trace-positive", type=Path)
    parser.add_argument("--adapter-regression-negative-control", type=Path)
    parser.add_argument("--golden-trace-negative-control", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-block", action="store_true")
    args = parser.parse_args(argv)

    paths = {
        "adapter-regression-positive": args.adapter_regression_positive,
        "golden-trace-positive": args.golden_trace_positive,
        "adapter-regression-negative-control": args.adapter_regression_negative_control,
        "golden-trace-negative-control": args.golden_trace_negative_control,
    }
    paths = {key: value for key, value in paths.items() if value is not None}
    try:
        manifest = load_ship_gate(args.gate)
        audit_check_id = next(
            (
                check.check_id
                for check in manifest.required_checks
                if check.report_kind == "audit"
            ),
            "audit-evidence-integrity",
        )
        audit_observation, audit_values = _audit_observation(
            audit_check_id,
            args.adapter_regression_positive,
            args.golden_trace_positive,
        )
        observations = _observations(manifest, paths, audit_observation)
        audit_values["decision"] = "pending"
        preliminary = evaluate_ship_gate(manifest, observations, audit_values)
        audit_values["decision"] = preliminary.decision
        report = evaluate_ship_gate(manifest, observations, audit_values)
        data = report.to_dict()
        rendered = _render(data, report) if args.markdown else (
            json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        exit_code = int(args.fail_on_block and not report.passed)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        data = _refused_data(error)
        report = None
        rendered = _render(data, report) if not args.markdown else (
            "## Operational ship gate\n\n- **Decision:** BLOCKED\n"
            "- **Reason:** `ship-gate-refused`\n"
        )
        exit_code = 1

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(rendered, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
