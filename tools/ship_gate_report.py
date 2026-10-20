"""Evaluate the synthetic operational ship gate from metadata-only reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent_reliability_lab.ship_gate import (
    CheckObservation,
    ShipGateManifest,
    ShipGateReport,
    evaluate_ship_gate,
    load_ship_gate,
)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Report must contain a JSON object.")
    return value


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
) -> dict[str, CheckObservation]:
    observations: dict[str, CheckObservation] = {}
    for check in manifest.required_checks:
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
        report = evaluate_ship_gate(manifest, _observations(manifest, paths))
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
