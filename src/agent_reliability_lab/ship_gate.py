"""Metadata-only operational ship-gate configuration and evaluation.

The ship gate turns assurance results into a release decision with an explicit
observer, blocking policy, rollback path, audit record, and stop condition.
It never carries prompts, traces, provider output, credentials, or contacts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


SHIP_GATE_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{field} must be a non-empty identifier.")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer.")
    return value


@dataclass(frozen=True)
class RequiredCheck:
    """One metadata-only check that must be satisfied before shipping."""

    check_id: str
    report_kind: str
    expected: str
    blocking: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "report_kind": self.report_kind,
            "expected": self.expected,
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class FailurePolicy:
    """Who notices a failure and what the delivery path does next."""

    condition: str
    notice: str
    action: str
    audit_event: str
    rollback: str

    def to_dict(self) -> dict[str, object]:
        return {
            "condition": self.condition,
            "notice": self.notice,
            "action": self.action,
            "audit_event": self.audit_event,
            "rollback": self.rollback,
        }


@dataclass(frozen=True)
class RollbackPolicy:
    """The synthetic rollback contract for a blocked release."""

    method: str
    target: str
    verification: str
    max_minutes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "target": self.target,
            "verification": self.verification,
            "max_minutes": self.max_minutes,
        }


@dataclass(frozen=True)
class AuditPolicy:
    """The metadata that must survive a ship-gate decision."""

    required: bool
    fields: tuple[str, ...]
    storage: str

    def to_dict(self) -> dict[str, object]:
        return {
            "required": self.required,
            "fields": list(self.fields),
            "storage": self.storage,
        }


@dataclass(frozen=True)
class StopCondition:
    """A bounded execution contract for unattended or repeated checks."""

    max_iterations: int
    max_elapsed_seconds: int
    unattended_allowed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "max_iterations": self.max_iterations,
            "max_elapsed_seconds": self.max_elapsed_seconds,
            "unattended_allowed": self.unattended_allowed,
        }


@dataclass(frozen=True)
class ShipGateManifest:
    """A validated operational ship-gate manifest."""

    ship_gate_version: int
    gate_id: str
    owner: str
    observer: str
    required_checks: tuple[RequiredCheck, ...]
    failure_policies: tuple[FailurePolicy, ...]
    rollback: RollbackPolicy
    audit: AuditPolicy
    stop_condition: StopCondition

    def to_dict(self) -> dict[str, object]:
        return {
            "ship_gate_version": self.ship_gate_version,
            "gate_id": self.gate_id,
            "owner": self.owner,
            "observer": self.observer,
            "required_checks": [item.to_dict() for item in self.required_checks],
            "failure_policies": [
                item.to_dict() for item in self.failure_policies
            ],
            "rollback": self.rollback.to_dict(),
            "audit": self.audit.to_dict(),
            "stop_condition": self.stop_condition.to_dict(),
        }


@dataclass(frozen=True)
class CheckObservation:
    """The result of one report-level ship-gate observation."""

    check_id: str
    passed: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "passed": self.passed,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AuditEvidence:
    """Observed audit identifiers and their completeness state."""

    values: tuple[tuple[str, str], ...]
    missing_fields: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.missing_fields

    def to_dict(self) -> dict[str, object]:
        return {
            "values": dict(self.values),
            "complete": self.complete,
            "missing_fields": list(self.missing_fields),
        }


@dataclass(frozen=True)
class ShipGateReport:
    """A release decision containing identifiers and operational metadata only."""

    gate_id: str
    decision: str
    owner: str
    observer: str
    checks: tuple[CheckObservation, ...]
    blocking_reasons: tuple[str, ...]
    rollback: RollbackPolicy
    audit: AuditPolicy
    audit_evidence: AuditEvidence
    stop_condition: StopCondition

    @property
    def passed(self) -> bool:
        return self.decision == "ready"

    def to_dict(self) -> dict[str, object]:
        return {
            "ship_gate_version": SHIP_GATE_VERSION,
            "gate_id": self.gate_id,
            "decision": self.decision,
            "passed": self.passed,
            "owner": self.owner,
            "observer": self.observer,
            "checks": [item.to_dict() for item in self.checks],
            "blocking_reasons": list(self.blocking_reasons),
            "rollback": self.rollback.to_dict(),
            "audit": self.audit.to_dict(),
            "audit_evidence": self.audit_evidence.to_dict(),
            "stop_condition": self.stop_condition.to_dict(),
            "diagnostics": {
                "warnings": [
                    "This report proves the configured delivery path observed "
                    "the required metadata-only checks; it does not prove "
                    "production deployment health or live-model quality.",
                    "Owner, observer, rollback, and stop-condition values are "
                    "synthetic identifiers for this public repository.",
                ],
                "what_it_does_not_show": (
                    "It does not show prompts, traces, provider output, "
                    "credentials, private contacts, or deployment state."
                ),
            },
        }

    def to_markdown(self) -> str:
        status = "READY" if self.passed else "BLOCKED"
        lines = [
            "# Operational ship gate",
            "",
            f"- **Decision:** {status}",
            f"- **Gate:** `{self.gate_id}`",
            f"- **Observer:** `{self.observer}`",
            f"- **Owner:** `{self.owner}`",
            "",
            "## Required checks",
            "",
            "| Check | Result | Reason |",
            "| --- | --- | --- |",
        ]
        lines.extend(
            f"| `{item.check_id}` | "
            f"{'PASS' if item.passed else 'BLOCKED'} | {item.reason} |"
            for item in self.checks
        )
        lines.extend(
            [
                "",
                "## Recovery contract",
                "",
                f"- **Rollback:** `{self.rollback.method}` to "
                f"`{self.rollback.target}`.",
                f"- **Verification:** `{self.rollback.verification}`.",
                f"- **Audit storage:** `{self.audit.storage}`.",
                f"- **Audit evidence:** "
                f"{'complete' if self.audit_evidence.complete else 'incomplete'}.",
                f"- **Stop condition:** "
                f"{self.stop_condition.max_iterations} iteration(s), "
                f"{self.stop_condition.max_elapsed_seconds} seconds.",
                "",
            ]
        )
        lines.extend(
            [
                "## Audit evidence",
                "",
                "| Field | Value |",
                "| --- | --- |",
            ]
        )
        lines.extend(
            f"| `{field}` | `{value}` |"
            for field, value in self.audit_evidence.values
        )
        lines.append("")
        if self.blocking_reasons:
            lines.extend(
                ["## Blocking reasons", ""]
                + [f"- `{reason}`" for reason in self.blocking_reasons]
                + [""]
            )
        return "\n".join(lines)


def load_ship_gate(path: Path) -> ShipGateManifest:
    """Load and strictly validate a ship-gate manifest."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Ship-gate manifest must be an object.")
    allowed = {
        "ship_gate_version",
        "gate_id",
        "owner",
        "observer",
        "required_checks",
        "failure_policies",
        "rollback",
        "audit",
        "stop_condition",
    }
    if set(data) - allowed:
        raise ValueError("Ship-gate manifest contains unknown fields.")
    if data.get("ship_gate_version") != SHIP_GATE_VERSION:
        raise ValueError("ship_gate_version is not supported.")
    required_checks = _parse_required_checks(data.get("required_checks"))
    failure_policies = _parse_failure_policies(data.get("failure_policies"))
    rollback = _parse_rollback(data.get("rollback"))
    audit = _parse_audit(data.get("audit"))
    stop_condition = _parse_stop_condition(data.get("stop_condition"))
    return ShipGateManifest(
        ship_gate_version=SHIP_GATE_VERSION,
        gate_id=_text(data.get("gate_id"), "gate_id"),
        owner=_text(data.get("owner"), "owner"),
        observer=_text(data.get("observer"), "observer"),
        required_checks=required_checks,
        failure_policies=failure_policies,
        rollback=rollback,
        audit=audit,
        stop_condition=stop_condition,
    )


def evaluate_ship_gate(
    manifest: ShipGateManifest,
    observations: Mapping[str, CheckObservation],
    audit_values: Mapping[str, str] | None = None,
) -> ShipGateReport:
    """Evaluate required observations and return a bounded ship decision."""

    checks: list[CheckObservation] = []
    blocking: list[str] = []
    audit_evidence = _audit_evidence(manifest, audit_values or {})
    for required in manifest.required_checks:
        observation = observations.get(required.check_id)
        if observation is None:
            observation = CheckObservation(
                check_id=required.check_id,
                passed=False,
                reason="missing_observation",
            )
        checks.append(observation)
        if required.blocking and not observation.passed:
            blocking.append(f"{required.check_id}:{observation.reason}")
    for field in audit_evidence.missing_fields:
        blocking.append(f"audit:{field}:missing")
    return ShipGateReport(
        gate_id=manifest.gate_id,
        decision="ready" if not blocking else "blocked",
        owner=manifest.owner,
        observer=manifest.observer,
        checks=tuple(checks),
        blocking_reasons=tuple(blocking),
        rollback=manifest.rollback,
        audit=manifest.audit,
        audit_evidence=audit_evidence,
        stop_condition=manifest.stop_condition,
    )


def _audit_evidence(
    manifest: ShipGateManifest,
    values: Mapping[str, str],
) -> AuditEvidence:
    """Keep only declared, identifier-only audit values and expose omissions."""

    declared = set(manifest.audit.fields)
    unknown = set(values) - declared
    if unknown:
        raise ValueError("Audit evidence contains undeclared fields.")
    safe_values: list[tuple[str, str]] = []
    missing: list[str] = []
    for field in manifest.audit.fields:
        value = values.get(field)
        if isinstance(value, str) and value and _IDENTIFIER.fullmatch(value):
            safe_values.append((field, value))
        else:
            missing.append(field)
    return AuditEvidence(tuple(safe_values), tuple(missing))


def _parse_required_checks(value: object) -> tuple[RequiredCheck, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("required_checks must be a non-empty list.")
    parsed: list[RequiredCheck] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Each required check must be an object.")
        if set(item) - {"check_id", "report_kind", "expected", "blocking"}:
            raise ValueError("Required checks contain unknown fields.")
        check_id = _text(item.get("check_id"), "check_id")
        if check_id in seen:
            raise ValueError("Required check IDs must be unique.")
        seen.add(check_id)
        report_kind = _text(item.get("report_kind"), "report_kind")
        expected = _text(item.get("expected"), "expected")
        if not isinstance(item.get("blocking"), bool):
            raise ValueError("Required check blocking must be boolean.")
        parsed.append(
            RequiredCheck(
                check_id=check_id,
                report_kind=report_kind,
                expected=expected,
                blocking=item["blocking"],
            )
        )
    return tuple(parsed)


def _parse_failure_policies(value: object) -> tuple[FailurePolicy, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("failure_policies must be a non-empty list.")
    parsed: list[FailurePolicy] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Each failure policy must be an object.")
        if set(item) - {"condition", "notice", "action", "audit_event", "rollback"}:
            raise ValueError("Failure policies contain unknown fields.")
        parsed.append(
            FailurePolicy(
                condition=_text(item.get("condition"), "condition"),
                notice=_text(item.get("notice"), "notice"),
                action=_text(item.get("action"), "action"),
                audit_event=_text(item.get("audit_event"), "audit_event"),
                rollback=_text(item.get("rollback"), "rollback"),
            )
        )
    return tuple(parsed)


def _parse_rollback(value: object) -> RollbackPolicy:
    if not isinstance(value, dict):
        raise ValueError("rollback must be an object.")
    if set(value) - {"method", "target", "verification", "max_minutes"}:
        raise ValueError("rollback contains unknown fields.")
    return RollbackPolicy(
        method=_text(value.get("method"), "rollback.method"),
        target=_text(value.get("target"), "rollback.target"),
        verification=_text(value.get("verification"), "rollback.verification"),
        max_minutes=_positive_int(value.get("max_minutes"), "rollback.max_minutes"),
    )


def _parse_audit(value: object) -> AuditPolicy:
    if not isinstance(value, dict):
        raise ValueError("audit must be an object.")
    if set(value) - {"required", "fields", "storage"}:
        raise ValueError("audit contains unknown fields.")
    if value.get("required") is not True:
        raise ValueError("audit.required must be true.")
    fields = value.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ValueError("audit.fields must be a non-empty list.")
    parsed_fields = tuple(_text(item, "audit field") for item in fields)
    if len(set(parsed_fields)) != len(parsed_fields):
        raise ValueError("audit.fields must be unique.")
    return AuditPolicy(
        required=True,
        fields=parsed_fields,
        storage=_text(value.get("storage"), "audit.storage"),
    )


def _parse_stop_condition(value: object) -> StopCondition:
    if not isinstance(value, dict):
        raise ValueError("stop_condition must be an object.")
    if set(value) - {
        "max_iterations",
        "max_elapsed_seconds",
        "unattended_allowed",
    }:
        raise ValueError("stop_condition contains unknown fields.")
    if not isinstance(value.get("unattended_allowed"), bool):
        raise ValueError("stop_condition.unattended_allowed must be boolean.")
    return StopCondition(
        max_iterations=_positive_int(
            value.get("max_iterations"), "stop_condition.max_iterations"
        ),
        max_elapsed_seconds=_positive_int(
            value.get("max_elapsed_seconds"),
            "stop_condition.max_elapsed_seconds",
        ),
        unattended_allowed=value["unattended_allowed"],
    )
