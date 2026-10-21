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
    release_path: Path | None,
) -> tuple[CheckObservation, dict[str, str]]:
    """Bind report identifiers to the current checkout and baseline manifest."""

    reasons: list[str] = []
    values: dict[str, str] = {}
    regression = _read_object(regression_path) if regression_path else {}
    golden = _read_object(golden_path) if golden_path else {}
    rollback = _read_object(rollback_path) if rollback_path else {}
    release = _read_object(release_path) if release_path else {}
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
    release_artifacts = release.get("artifacts")
    if not isinstance(release_artifacts, dict):
        reasons.append("release-artifacts-missing")
        release_artifacts = {}

    observed = {
        "git-commit": attestation.get("git_commit"),
        "package-version": attestation.get("package_version"),
        "scenario-pack-sha256": attestation.get("pack_set_sha256"),
        "golden-trace-sha256": golden.get("candidate_trace_sha256"),
        "rollback-artifact-sha256": recovery.get("restored_tree_sha256"),
        "source-distribution-sha256": release_artifacts.get(
            "source_distribution_sha256"
        ),
        "wheel-sha256": release_artifacts.get("wheel_sha256"),
        "sbom-sha256": release.get("sbom_sha256"),
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
    if _safe_value(release.get("git_commit")) != current_git_commit:
        reasons.append("release-git-commit-mismatch")
    if _safe_value(release.get("package_version")) != current_package_version:
        reasons.append("release-package-version-mismatch")
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
    for field in (
        "source-distribution-sha256",
        "wheel-sha256",
        "sbom-sha256",
    ):
        if _sha256_value(values.get(field)) is None:
            reasons.append(f"{field}-invalid")

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


def _content_assurance_observation(
    check_id: str,
    path: Path,
    *,
    expected: str,
) -> CheckObservation:
    report = _read_object(path)
    cases = report.get("cases")
    case_map = {
        item.get("case_id"): item
        for item in cases
        if isinstance(item, dict)
    } if isinstance(cases, list) else {}
    required_cases = {
        "fresh-approved": ("approved", ()),
        "stale-approved": ("abstain", ("evidence_stale",)),
        "fresh-wrong-source": ("abstain", ("evidence_wrong_source",)),
        "source-drift": ("abstain", ("source_drift",)),
        "claim-unsupported": ("abstain", ("claim_unsupported",)),
        "claim-conflict": ("abstain", ("claim_conflict",)),
        "claim-ambiguous": ("abstain", ("claim_ambiguous",)),
    }
    cases_passed = all(
        isinstance(case_map.get(case_id), dict)
        and case_map[case_id].get("decision") == decision
        and set(case_map[case_id].get("abstention_reasons", [])) == set(reasons)
        for case_id, (decision, reasons) in required_cases.items()
    )
    passed = (
        expected == "pass"
        and report.get("content_assurance_version") == 2
        and report.get("passed") is True
        and report.get("controls_missed") == []
        and cases_passed
    )
    return CheckObservation(
        check_id,
        passed,
        "passed" if passed else "content-assurance-failed",
    )


def _content_adapter_observation(
    check_id: str,
    path: Path,
    *,
    expected: str,
) -> CheckObservation:
    report = _read_object(path)
    expected_packs = {
        "fresh-approved",
        "stale-approved",
        "fresh-wrong-source",
        "source-drift",
        "claim-unsupported",
        "claim-conflict",
        "claim-ambiguous",
    }
    passed = (
        expected == "pass"
        and report.get("conformance_id") == "custom-pack-conformance-v2"
        and report.get("passed") is True
        and report.get("refusal_count") == 0
        and report.get("pack_count") == len(expected_packs)
        and set(report.get("pack_ids", [])) == expected_packs
    )
    return CheckObservation(
        check_id,
        passed,
        "passed" if passed else "content-adapter-conformance-failed",
    )


def _content_pipeline_observation(
    check_id: str,
    path: Path,
    *,
    expected: str,
) -> CheckObservation:
    report = _read_object(path)
    cases = report.get("cases")
    case_map = {
        item.get("case_id"): item
        for item in cases
        if isinstance(item, dict)
    } if isinstance(cases, list) else {}
    required_cases = {
        "pipeline-approved": ("approved", (), None),
        "pipeline-unsupported-claim": (
            "abstain",
            ("claim_unsupported",),
            None,
        ),
        "pipeline-stale-source": ("abstain", ("evidence_stale",), None),
        "pipeline-source-drift": ("abstain", ("source_drift",), None),
        "pipeline-unapproved-host": (
            "refused",
            (),
            "unapproved_source_host",
        ),
    }
    cases_passed = all(
        isinstance(case_map.get(case_id), dict)
        and case_map[case_id].get("decision") == decision
        and set(case_map[case_id].get("abstention_reasons", [])) == set(reasons)
        and case_map[case_id].get("refusal_code") == refusal_code
        for case_id, (decision, reasons, refusal_code) in required_cases.items()
    )
    passed = (
        expected == "pass"
        and report.get("content_pipeline_version") == 1
        and report.get("passed") is True
        and report.get("controls_missed") == []
        and cases_passed
    )
    return CheckObservation(
        check_id,
        passed,
        "passed" if passed else "content-pipeline-failed",
    )


def _course_freshness_observation(
    check_id: str,
    path: Path,
    *,
    expected: str,
) -> CheckObservation:
    report = _read_object(path)
    results = report.get("results")
    expected_courses = {
        "course-pipeline-approved",
        "course-pipeline-unsupported-claim",
        "course-pipeline-stale-source",
        "course-pipeline-source-drift",
        "course-pipeline-unapproved-host",
    }
    result_ids = {
        item.get("course_id")
        for item in results
        if isinstance(item, dict)
    } if isinstance(results, list) else set()
    workers_completed = (
        isinstance(results, list)
        and len(results) == len(expected_courses)
        and all(
            isinstance(item, dict)
            and item.get("worker_status") == "completed"
            for item in results
        )
    )
    counts = report.get("counts")
    passed = (
        expected == "pass"
        and report.get("course_freshness_version") == 1
        and report.get("passed") is True
        and report.get("controls_missed") == []
        and isinstance(counts, dict)
        and counts.get("requested") == len(expected_courses)
        and counts.get("completed") == len(expected_courses)
        and counts.get("unavailable") == 0
        and result_ids == expected_courses
        and workers_completed
    )
    return CheckObservation(
        check_id,
        passed,
        "passed" if passed else "course-freshness-failed",
    )


def _release_artifact_observation(
    check_id: str,
    path: Path,
    *,
    expected: str,
) -> CheckObservation:
    report = _read_object(path)
    artifacts = report.get("artifacts")
    checks = report.get("checks")
    scenario_hashes = report.get("scenario_pack_sha256")
    required_checks = {
        "source_and_artifact_synthetic_cli_match",
        "runtime_dependency_sbom_generated",
    }
    artifact_hashes_valid = (
        isinstance(artifacts, dict)
        and _sha256_value(artifacts.get("wheel_sha256")) is not None
        and _sha256_value(artifacts.get("source_distribution_sha256")) is not None
    )
    scenario_hashes_valid = (
        isinstance(scenario_hashes, dict)
        and bool(scenario_hashes)
        and all(_sha256_value(value) is not None for value in scenario_hashes.values())
    )
    try:
        identity_matches = (
            _safe_value(report.get("git_commit")) == _git_commit()
            and _safe_value(report.get("package_version")) == _package_version()
        )
    except (OSError, subprocess.SubprocessError, KeyError, TypeError):
        identity_matches = False
    passed = (
        expected == "pass"
        and report.get("release_artifact_version") == 1
        and report.get("manifest_version") == 1
        and report.get("passed") is True
        and report.get("package") == "agent-reliability-lab"
        and identity_matches
        and report.get("working_tree_dirty") is False
        and isinstance(checks, list)
        and required_checks.issubset(set(checks))
        and artifact_hashes_valid
        and _sha256_value(report.get("assurance_output_sha256")) is not None
        and _sha256_value(report.get("sbom_sha256")) is not None
        and report.get("sbom_persisted") is True
        and isinstance(report.get("sbom_component_count"), int)
        and report.get("sbom_component_count") > 0
        and scenario_hashes_valid
    )
    return CheckObservation(
        check_id,
        passed,
        "passed" if passed else "release-artifact-invalid",
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
        elif check.report_kind == "content-assurance":
            observations[check.check_id] = _content_assurance_observation(
                check.check_id,
                path,
                expected=check.expected,
            )
        elif check.report_kind == "content-adapter-conformance":
            observations[check.check_id] = _content_adapter_observation(
                check.check_id,
                path,
                expected=check.expected,
            )
        elif check.report_kind == "content-pipeline":
            observations[check.check_id] = _content_pipeline_observation(
                check.check_id,
                path,
                expected=check.expected,
            )
        elif check.report_kind == "course-freshness":
            observations[check.check_id] = _course_freshness_observation(
                check.check_id,
                path,
                expected=check.expected,
            )
        elif check.report_kind == "release-artifact":
            observations[check.check_id] = _release_artifact_observation(
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
    parser.add_argument("--content-assurance", type=Path)
    parser.add_argument("--content-assurance-conformance", type=Path)
    parser.add_argument("--content-assurance-pipeline", type=Path)
    parser.add_argument("--course-freshness", type=Path)
    parser.add_argument("--release-artifact", type=Path)
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
        "content-assurance-reference": args.content_assurance,
        "content-assurance-adapter": args.content_assurance_conformance,
        "content-assurance-pipeline": args.content_assurance_pipeline,
        "course-freshness-sweep": args.course_freshness,
        "release-artifact-integrity": args.release_artifact,
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
            args.release_artifact,
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
