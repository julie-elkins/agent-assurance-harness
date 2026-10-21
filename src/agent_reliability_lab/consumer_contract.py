"""Validate a consumer's synthetic policy and escalation contract.

Design rules:

1. The manifest is a reviewed policy declaration, not a credential or runtime secret.
2. The policy digest binds the declaration to adapter metadata without exporting
   prompts, payloads, or provider output.
3. Missing or mismatched policy metadata is a blocking finding.
4. Authorization scope and escalation are checked independently so one satisfied
   condition cannot hide another failure.
5. The report states what it cannot prove: live IAM, vault, gateway, or human response.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string.")
    return value


def _object(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object.")
    return value


@dataclass(frozen=True)
class ConsumerPolicyManifest:
    """The metadata-only policy expectations a consumer declares."""

    manifest_version: int
    policy_version: str
    policy_sha256: str
    required_authorization_scope: str
    authorization_scenario_id: str
    required_escalation_status: str
    escalation_scenario_id: str

    def canonical_payload(self) -> dict[str, str]:
        """Return the policy fields without the self-referential digest."""

        return {
            "policy_version": self.policy_version,
            "required_authorization_scope": self.required_authorization_scope,
            "required_escalation_status": self.required_escalation_status,
        }

    def to_dict(self) -> dict[str, object]:
        """Return the reviewed manifest contract without filesystem paths."""

        return {
            "manifest_version": self.manifest_version,
            "policy_version": self.policy_version,
            "policy_sha256": self.policy_sha256,
            "required_authorization_scope": self.required_authorization_scope,
            "authorization_scenario_id": self.authorization_scenario_id,
            "required_escalation_status": self.required_escalation_status,
            "escalation_scenario_id": self.escalation_scenario_id,
        }


def policy_digest(manifest: ConsumerPolicyManifest) -> str:
    """Compute the stable digest for the manifest policy declaration."""

    encoded = json.dumps(
        manifest.canonical_payload(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def load_consumer_policy_manifest(path: Path) -> ConsumerPolicyManifest:
    """Load and strictly validate a checked-in consumer policy manifest."""

    data = _object(json.loads(path.read_text(encoding="utf-8")), "manifest")
    allowed = {
        "manifest_version",
        "policy_version",
        "policy_sha256",
        "required_authorization_scope",
        "authorization_scenario_id",
        "required_escalation_status",
        "escalation_scenario_id",
    }
    if sorted(set(data) - allowed):
        raise ValueError("consumer policy manifest contains unknown fields.")
    if data.get("manifest_version") != 1:
        raise ValueError("consumer policy manifest_version must be 1.")
    manifest = ConsumerPolicyManifest(
        manifest_version=1,
        policy_version=_non_empty_string(data.get("policy_version"), "policy_version"),
        policy_sha256=_non_empty_string(data.get("policy_sha256"), "policy_sha256"),
        required_authorization_scope=_non_empty_string(
            data.get("required_authorization_scope"),
            "required_authorization_scope",
        ),
        authorization_scenario_id=_non_empty_string(
            data.get("authorization_scenario_id"),
            "authorization_scenario_id",
        ),
        required_escalation_status=_non_empty_string(
            data.get("required_escalation_status"),
            "required_escalation_status",
        ),
        escalation_scenario_id=_non_empty_string(
            data.get("escalation_scenario_id"),
            "escalation_scenario_id",
        ),
    )
    if not _SHA256_PATTERN.fullmatch(manifest.policy_sha256):
        raise ValueError("policy_sha256 must use sha256:<64 lowercase hex>.")
    if policy_digest(manifest) != manifest.policy_sha256:
        raise ValueError("policy_sha256 does not match the canonical policy fields.")
    return manifest


@dataclass(frozen=True)
class ConsumerContractFinding:
    """One independent policy-contract check."""

    check_id: str
    passed: bool
    message: str
    failure_reason: str | None = None
    does_not_show: str = (
        "It does not show live authorization enforcement, credential handling, "
        "or human escalation response."
    )

    def to_dict(self) -> dict[str, object]:
        """Return a metadata-only finding."""

        return {
            "check_id": self.check_id,
            "passed": self.passed,
            "message": self.message,
            **(
                {"failure_reason": self.failure_reason}
                if self.failure_reason is not None
                else {}
            ),
            "what_it_does_not_show": self.does_not_show,
        }


@dataclass(frozen=True)
class ConsumerContractReport:
    """The result of policy, scope, and escalation checks."""

    manifest: ConsumerPolicyManifest
    findings: tuple[ConsumerContractFinding, ...]

    @property
    def passed(self) -> bool:
        """Return false when any required contract condition failed."""

        return all(finding.passed for finding in self.findings)

    @property
    def failure_reasons(self) -> tuple[str, ...]:
        """Return stable failure identifiers for CI summaries."""

        reasons: list[str] = []
        for finding in self.findings:
            if finding.failure_reason is not None and finding.failure_reason not in reasons:
                reasons.append(finding.failure_reason)
        return tuple(reasons)

    def to_dict(self) -> dict[str, object]:
        """Return the report without paths or runtime payloads."""

        return {
            "passed": self.passed,
            "manifest": self.manifest.to_dict(),
            "findings": [finding.to_dict() for finding in self.findings],
            "failure_reasons": list(self.failure_reasons),
            "diagnostics": {
                "warnings": [
                    "The contract checks synthetic policy metadata emitted by the adapter.",
                    "Fresh evidence from an unapproved source is not accepted by the "
                    "built-in evidence scenarios.",
                ],
                "what_it_does_not_show": (
                    "It does not prove live IAM, vault, gateway, deployment, or "
                    "human-response behaviour."
                ),
            },
        }


def evaluate_consumer_contract(
    trace_metadata: dict[str, dict[str, object]],
    manifest: ConsumerPolicyManifest,
    scenario_ids: tuple[str, ...],
) -> ConsumerContractReport:
    """Check policy binding, least-privilege scope, and escalation metadata."""

    findings: list[ConsumerContractFinding] = []
    for scenario_id in scenario_ids:
        metadata = trace_metadata.get(scenario_id, {})
        version_matches = metadata.get("policy_version") == manifest.policy_version
        digest_matches = metadata.get("policy_digest") == manifest.policy_sha256
        findings.append(
            ConsumerContractFinding(
                check_id=f"policy-version:{scenario_id}",
                passed=version_matches,
                message=(
                    "The adapter reported the manifest policy version."
                    if version_matches
                    else "The adapter policy version did not match the manifest."
                ),
                failure_reason=None if version_matches else "policy_version_mismatch",
            )
        )
        findings.append(
            ConsumerContractFinding(
                check_id=f"policy-digest:{scenario_id}",
                passed=digest_matches,
                message=(
                    "The adapter reported the manifest policy digest."
                    if digest_matches
                    else "The adapter policy digest did not match the manifest."
                ),
                failure_reason=None if digest_matches else "policy_digest_mismatch",
            )
        )

    authorization_metadata = trace_metadata.get(
        manifest.authorization_scenario_id,
        {},
    )
    observed_scopes = authorization_metadata.get("authorization_scopes", ())
    scope_matches = (
        isinstance(observed_scopes, (list, tuple))
        and manifest.required_authorization_scope in observed_scopes
    )
    findings.append(
        ConsumerContractFinding(
            check_id="authorization-scope",
            passed=scope_matches,
            message=(
                "The protected-write scenario reported the required authorization scope."
                if scope_matches
                else "The protected-write scenario did not report the required scope."
            ),
            failure_reason=None if scope_matches else "authorization_scope_missing",
        )
    )

    escalation_metadata = trace_metadata.get(manifest.escalation_scenario_id, {})
    escalation_matches = (
        escalation_metadata.get("escalation_status")
        == manifest.required_escalation_status
        and isinstance(escalation_metadata.get("escalation_id"), str)
        and bool(escalation_metadata.get("escalation_id"))
    )
    findings.append(
        ConsumerContractFinding(
            check_id="unsupported-request-escalation",
            passed=escalation_matches,
            message=(
                "The unsupported-request scenario reported an escalation."
                if escalation_matches
                else "The unsupported-request scenario did not report escalation."
            ),
            failure_reason=None if escalation_matches else "escalation_missing",
        )
    )
    return ConsumerContractReport(manifest=manifest, findings=tuple(findings))
