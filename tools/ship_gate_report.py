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


def _sha256_value(value: object) -> str | None:
    if (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    ):
        return value
    return None


def _audit_observation(
    check_id: str,
    regression_path: Path | None,
    golden_path: Path | None,
    rollback_path: Path | None,
) -> tuple[CheckObservation, dict[str, str]]:
    """Bind report identifiers to the current checkout and baseline manifest."""

    reasons: list[str] = []
    values: dict[str, str] = {}
    regression = _read_object(regression_path) if regression_path else {}
    golden = _read_object(golden_path) if golden_path else {}
    rollback = _read_object(rollback_path) if rollback_path else {}
    attestation = regression.get("assurance_attestation")
    if not isinstance(attestation, dict):
        reasons.append("assurance-attestation-missing")
        attestation = {}
    manifest = golden.get("manifest")
    if not isinstance(manifest, dict):
        reasons.append("golden-manifest-missing")
        manifest = {}
    recovery = rollback.get("recovery")
    if not isinstance(recovery, dict):
        reasons.append("rollback-recovery-missing")
        recovery = {}

    observed = {
        "git-commit": attestation.get("git_commit"),
        "package-version": attestation.get("package_version"),
        "scenario-pack-sha256": attestation.get("pack_set_sha256"),
        "golden-trace-sha256": golden.get("candidate_trace_sha256"),
        "rollback-artifact-sha256": recovery.get("restored_tree_sha256"),
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
    if values.get("rollback-artifact-sha256") != _safe_value(
        recovery.get("original_tree_sha256")
    ):
        reasons.append("rollback-artifact-mismatch")

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


def _provider_observation(
    check_id: str,
    path: Path,
    *,
    expected: str,
) -> CheckObservation:
    report = _read_object(path)
    providers = report.get("providers")
    negative_control = report.get("negative_control")
    provider_ids = {
        item.get("provider_id")
        for item in providers
        if isinstance(item, dict)
    } if isinstance(providers, list) else set()
    passed = (
        expected == "pass"
        and report.get("provider_assurance_version") == 1
        and report.get("passed") is True
        and provider_ids == {"openai", "anthropic"}
        and isinstance(negative_control, dict)
        and negative_control.get("caught") is True
    )
    return CheckObservation(
        check_id,
        passed,
        "passed" if passed else "provider-assurance-failed",
    )


def _provider_contract_observation(
    check_id: str,
    path: Path,
    *,
    expected: str,
) -> CheckObservation:
    report = _read_object(path)
    contracts = report.get("contracts")
    negative_controls = report.get("negative_controls")
    provider_ids = {
        item.get("provider_id")
        for item in contracts
        if isinstance(item, dict)
    } if isinstance(contracts, list) else set()
    negative_caught = (
        isinstance(negative_controls, list)
        and bool(negative_controls)
        and all(
            isinstance(item, dict) and item.get("caught") is True
            for item in negative_controls
        )
    )
    passed = (
        expected == "pass"
        and report.get("provider_contract_version") == 1
        and report.get("passed") is True
        and provider_ids == {"openai", "anthropic"}
        and negative_caught
    )
    return CheckObservation(
        check_id,
        passed,
        "passed" if passed else "provider-contract-drift",
    )


def _rollback_observation(
    check_id: str,
    path: Path,
    *,
    expected: str,
) -> CheckObservation:
    report = _read_object(path)
    failure_injection = report.get("failure_injection")
    recovery = report.get("recovery")
    side_effects = report.get("side_effects")
    verification = report.get("verification")
    passed = (
        expected == "pass"
        and report.get("rollback_rehearsal_version") == 1
        and report.get("passed") is True
        and isinstance(failure_injection, dict)
        and failure_injection.get("type") == "synthetic-release-marker"
        and failure_injection.get("applied") is True
        and failure_injection.get("detected") is True
        and isinstance(recovery, dict)
        and recovery.get("method") == "git-archive-restore-rehearsal"
        and recovery.get("target") == "last-known-good-commit"
        and _sha256_value(recovery.get("original_tree_sha256")) is not None
        and _sha256_value(recovery.get("failed_tree_sha256")) is not None
        and _sha256_value(recovery.get("restored_tree_sha256")) is not None
        and recovery.get("failed_tree_sha256")
        != recovery.get("original_tree_sha256")
        and recovery.get("restored_tree_sha256")
        == recovery.get("original_tree_sha256")
        and recovery.get("restored_match") is True
        and isinstance(side_effects, dict)
        and side_effects.get("external_writes_attempted") is False
        and side_effects.get("network_used") is False
        and isinstance(verification, dict)
        and verification.get("passed") is True
    )
    return CheckObservation(
        check_id,
        passed,
        "passed" if passed else "rollback-rehearsal-failed",
    )


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
        elif check.report_kind == "provider-assurance":
            observations[check.check_id] = _provider_observation(
                check.check_id,
                path,
                expected=check.expected,
            )
        elif check.report_kind == "provider-contract":
            observations[check.check_id] = _provider_contract_observation(
                check.check_id,
                path,
                expected=check.expected,
            )
        elif check.report_kind == "rollback":
            observations[check.check_id] = _rollback_observation(
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
    parser.add_argument("--provider-assurance", type=Path)
    parser.add_argument("--provider-contract", type=Path)
    parser.add_argument("--rollback-rehearsal", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-block", action="store_true")
    args = parser.parse_args(argv)

    paths = {
        "adapter-regression-positive": args.adapter_regression_positive,
        "golden-trace-positive": args.golden_trace_positive,
        "adapter-regression-negative-control": args.adapter_regression_negative_control,
        "golden-trace-negative-control": args.golden_trace_negative_control,
        "provider-adapter-assurance": args.provider_assurance,
        "provider-contract-drift": args.provider_contract,
        "rollback-rehearsal": args.rollback_rehearsal,
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
            args.rollback_rehearsal,
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
