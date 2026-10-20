"""Render a reviewer-facing summary from verified assurance metadata."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/+-]*$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Render a pull-request summary from metadata-only assurance reports "
            "and attestations."
        )
    )
    parser.add_argument("--positive-report", type=Path, required=True)
    parser.add_argument("--positive-attestation", type=Path, required=True)
    parser.add_argument("--negative-report", type=Path, required=True)
    parser.add_argument("--negative-attestation", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        positive_report = _read_object(args.positive_report)
        positive_attestation = _read_object(args.positive_attestation)
        negative_report = _read_object(args.negative_report)
        negative_attestation = _read_object(args.negative_attestation)
        summary = render_summary(
            positive_report,
            positive_attestation,
            negative_report,
            negative_attestation,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"assurance summary refused: {error}")
        return 1

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(summary, encoding="utf-8")
    else:
        print(summary, end="")
    return 0


def render_summary(
    positive_report: dict[str, Any],
    positive_attestation: dict[str, Any],
    negative_report: dict[str, Any],
    negative_attestation: dict[str, Any],
) -> str:
    """Return a safe summary without copying report findings or payloads."""

    _validate_pair(positive_report, positive_attestation, expected_passed=True)
    _validate_pair(negative_report, negative_attestation, expected_passed=False)
    _validate_shared_identity(positive_attestation, negative_attestation)

    candidate_change = positive_attestation.get("candidate_harness_change")
    baseline_change = positive_attestation.get("baseline_harness_change")
    identity = _identity_rows(positive_attestation)
    positive_blocking = positive_attestation["blocking_finding_count"]
    negative_blocking = negative_attestation["blocking_finding_count"]

    lines = [
        "# Agent assurance gate",
        "",
        "## Decision",
        "",
        "- **Candidate assurance:** PASS",
        "- **Negative control:** BLOCKED as expected",
        "- **Merge evidence:** PASS — the candidate passed and the degraded control was caught.",
        "",
        "## What was checked",
        "",
        "| Evidence | Value |",
        "| --- | --- |",
    ]
    lines.extend(f"| {label} | `{value}` |" for label, value in identity)
    lines.extend(
        [
            "",
            "## Control results",
            "",
            "| Control | Result | Blocking findings |",
            "| --- | --- | ---: |",
            f"| Candidate adapter | PASS | {positive_blocking} |",
            f"| Degraded negative control | BLOCKED as expected | {negative_blocking} |",
            "",
            "## Change manifests",
            "",
            f"- Baseline: `{_change_label(baseline_change)}`",
            f"- Candidate: `{_change_label(candidate_change)}`",
            "",
            "## What this proves",
            "",
            "- The candidate evaluation completed against the recorded Git revision and "
            "scenario-pack set.",
            "- The positive control produced no blocking regression.",
            "- The deliberately degraded control produced at least one blocking finding.",
            "- The attached evidence is metadata-only and paired with its standalone "
            "attestation.",
            "",
            "## What this does not prove",
            "",
            "- It does not establish general live-model reliability, causality, or "
            "production monitoring coverage.",
            "- It is not a cryptographic signature or a provider billing record.",
            "- It contains no prompts, credentials, raw tool payloads, provider output, "
            "or hidden reasoning.",
            "",
            "Detailed metadata-only JSON is available in the uploaded workflow artifact.",
            "",
        ]
    )
    return "\n".join(lines)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return value


def _validate_pair(
    report: dict[str, Any],
    attestation: dict[str, Any],
    *,
    expected_passed: bool,
) -> None:
    if report.get("assurance_attestation") != attestation:
        raise ValueError("Report and standalone attestation do not match.")
    if attestation.get("package") != "agent-reliability-lab":
        raise ValueError("Attestation package is not agent-reliability-lab.")
    for field in ("package_version", "git_commit", "pack_set_sha256"):
        value = attestation.get(field)
        if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
            raise ValueError(f"Attestation {field} is not a safe identifier.")
    if not isinstance(attestation.get("scenario_count"), int):
        raise ValueError("Attestation scenario count is invalid.")
    if attestation.get("passed") is not expected_passed:
        raise ValueError("Attestation has the wrong control state.")
    blocking_count = attestation.get("blocking_finding_count")
    if not isinstance(blocking_count, int) or blocking_count < 0:
        raise ValueError("Attestation blocking-finding count is invalid.")
    if expected_passed and blocking_count != 0:
        raise ValueError("Positive control contains a blocking finding.")
    if not expected_passed and blocking_count < 1:
        raise ValueError("Negative control did not catch a blocking finding.")


def _validate_shared_identity(
    positive: dict[str, Any],
    negative: dict[str, Any],
) -> None:
    for field in ("package", "package_version", "git_commit", "pack_set_sha256"):
        if positive.get(field) != negative.get(field):
            raise ValueError(f"Controls disagree on {field}.")


def _identity_rows(attestation: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return (
        ("Package", str(attestation["package"])),
        ("Package version", str(attestation["package_version"])),
        ("Git revision", str(attestation["git_commit"])),
        ("Scenario count", str(attestation["scenario_count"])),
        ("Scenario-pack set SHA-256", str(attestation["pack_set_sha256"])),
    )


def _change_label(change: object) -> str:
    if not isinstance(change, dict):
        return "not recorded"
    change_id = change.get("change_id")
    components = change.get("components")
    if (
        not isinstance(change_id, str)
        or _IDENTIFIER.fullmatch(change_id) is None
        or not isinstance(components, list)
        or any(
            not isinstance(item, str) or _IDENTIFIER.fullmatch(item) is None
            for item in components
        )
    ):
        return "invalid manifest"
    return f"{change_id}; components={','.join(str(item) for item in components)}"


if __name__ == "__main__":
    raise SystemExit(main())
