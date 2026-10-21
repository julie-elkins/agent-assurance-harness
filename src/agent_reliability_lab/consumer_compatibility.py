"""Validate version compatibility between a consumer and the assurance action.

Design rules:

1. A consumer declares the minimum action and report versions it expects in a
   checked-in, metadata-only manifest.
2. The action revision is an immutable commit identifier, not a moving branch.
3. Every control run is checked, including negative and restoration paths; a
   passing positive run cannot hide an incompatible negative path.
4. Compatibility failures are stable, blocking metadata and never contain paths,
   prompts, provider output, or credentials.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object.")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer.")
    return value


@dataclass(frozen=True)
class ConsumerCompatibilityManifest:
    """The checked-in version contract for one consumer fixture."""

    compatibility_version: int
    required_action_ref: str
    required_reusable_action_version: int
    required_consumer_validation_version: int
    required_policy_manifest_version: int

    def to_dict(self) -> dict[str, object]:
        """Return the public compatibility declaration."""

        return {
            "compatibility_version": self.compatibility_version,
            "required_action_ref": self.required_action_ref,
            "required_reusable_action_version": self.required_reusable_action_version,
            "required_consumer_validation_version": (
                self.required_consumer_validation_version
            ),
            "required_policy_manifest_version": self.required_policy_manifest_version,
        }


def load_consumer_compatibility_manifest(
    path: Path,
) -> ConsumerCompatibilityManifest:
    """Load and strictly validate the checked-in compatibility manifest."""

    data = _object(json.loads(path.read_text(encoding="utf-8")), "manifest")
    allowed = {
        "compatibility_version",
        "required_action_ref",
        "required_reusable_action_version",
        "required_consumer_validation_version",
        "required_policy_manifest_version",
    }
    if sorted(set(data) - allowed):
        raise ValueError("consumer compatibility manifest contains unknown fields.")
    if data.get("compatibility_version") != 1:
        raise ValueError("compatibility_version must be 1.")
    action_ref = data.get("required_action_ref")
    if not isinstance(action_ref, str) or not _COMMIT_PATTERN.fullmatch(action_ref):
        raise ValueError("required_action_ref must be a 40-character commit.")
    return ConsumerCompatibilityManifest(
        compatibility_version=1,
        required_action_ref=action_ref,
        required_reusable_action_version=_positive_int(
            data.get("required_reusable_action_version"),
            "required_reusable_action_version",
        ),
        required_consumer_validation_version=_positive_int(
            data.get("required_consumer_validation_version"),
            "required_consumer_validation_version",
        ),
        required_policy_manifest_version=_positive_int(
            data.get("required_policy_manifest_version"),
            "required_policy_manifest_version",
        ),
    )


@dataclass(frozen=True)
class CompatibilityFinding:
    """One independent compatibility check."""

    check_id: str
    passed: bool
    message: str
    failure_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a metadata-only compatibility finding."""

        return {
            "check_id": self.check_id,
            "passed": self.passed,
            "message": self.message,
            **(
                {"failure_reason": self.failure_reason}
                if self.failure_reason is not None
                else {}
            ),
        }


@dataclass(frozen=True)
class ConsumerCompatibilityReport:
    """The blocking result of all consumer compatibility checks."""

    manifest: ConsumerCompatibilityManifest
    findings: tuple[CompatibilityFinding, ...]

    @property
    def passed(self) -> bool:
        """Return false when any compatibility requirement failed."""

        return all(finding.passed for finding in self.findings)

    @property
    def failure_reasons(self) -> tuple[str, ...]:
        """Return stable, deduplicated compatibility failure reasons."""

        reasons: list[str] = []
        for finding in self.findings:
            if finding.failure_reason and finding.failure_reason not in reasons:
                reasons.append(finding.failure_reason)
        return tuple(reasons)

    def to_dict(self) -> dict[str, object]:
        """Return the compatibility result without runtime payloads."""

        return {
            "passed": self.passed,
            "manifest": self.manifest.to_dict(),
            "findings": [finding.to_dict() for finding in self.findings],
            "failure_reasons": list(self.failure_reasons),
            "diagnostics": {
                "warnings": [
                    "Compatibility is checked against declared versions and an "
                    "immutable action commit.",
                ],
                "what_it_does_not_show": (
                    "It does not prove that a provider, deployment target, or "
                    "live authorization system implements those versions."
                ),
            },
        }


def evaluate_consumer_compatibility(
    manifest: ConsumerCompatibilityManifest,
    *,
    action_ref: str,
    consumer_validation_version: int,
    runs: dict[str, dict[str, object]],
) -> ConsumerCompatibilityReport:
    """Check the action pin and every consumer control report version."""

    findings: list[CompatibilityFinding] = []
    action_matches = action_ref == manifest.required_action_ref
    findings.append(
        CompatibilityFinding(
            check_id="action-pin",
            passed=action_matches,
            message=(
                "The consumer workflow uses the required action commit."
                if action_matches
                else "The consumer workflow action commit is not approved."
            ),
            failure_reason=None if action_matches else "action_pin_mismatch",
        )
    )
    validation_matches = (
        consumer_validation_version
        == manifest.required_consumer_validation_version
    )
    findings.append(
        CompatibilityFinding(
            check_id="consumer-validation-version",
            passed=validation_matches,
            message=(
                "The consumer validation report uses the required schema version."
                if validation_matches
                else "The consumer validation report schema version is unsupported."
            ),
            failure_reason=(
                None
                if validation_matches
                else "consumer_validation_version_mismatch"
            ),
        )
    )
    for name, run in sorted(runs.items()):
        action_version_matches = (
            run.get("report_version")
            == manifest.required_reusable_action_version
        )
        findings.append(
            CompatibilityFinding(
                check_id=f"action-report-version:{name}",
                passed=action_version_matches,
                message=(
                    "The consumer run emitted the required action report version."
                    if action_version_matches
                    else "The consumer run emitted an unsupported action report version."
                ),
                failure_reason=(
                    None
                    if action_version_matches
                    else "reusable_action_version_mismatch"
                ),
            )
        )
        policy_version_matches = (
            run.get("policy_manifest_version")
            == manifest.required_policy_manifest_version
        )
        findings.append(
            CompatibilityFinding(
                check_id=f"policy-manifest-version:{name}",
                passed=policy_version_matches,
                message=(
                    "The consumer run used the required policy manifest version."
                    if policy_version_matches
                    else "The consumer run used an unsupported policy manifest version."
                ),
                failure_reason=(
                    None
                    if policy_version_matches
                    else "policy_manifest_version_mismatch"
                ),
            )
        )
    return ConsumerCompatibilityReport(
        manifest=manifest,
        findings=tuple(findings),
    )
