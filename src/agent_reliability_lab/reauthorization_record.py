"""Metadata-only validation of human reauthorization decisions.

The bounded rerun executor reports what synthetic checks ran. This module validates
the separate human decision that says whether that exact evidence may be reused.
It never creates a decision, authorizes deployment, or reads content-bearing data.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REAUTHORIZATION_RECORD_VERSION = 1
VALID_DECISIONS = frozenset({"reauthorized", "held", "blocked"})
VALID_EXECUTOR_STATUSES = frozenset(
    {"not_required", "rerun_completed", "blocked", "refused"}
)
VALID_VALIDATION_STATUSES = frozenset(
    {"reauthorized", "held", "blocked", "expired", "refused"}
)


def canonical_digest(value: object) -> str:
    """Return a stable digest for one JSON-compatible metadata artifact."""

    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if any(character.isspace() for character in value):
        raise ValueError(f"{field} must not contain whitespace")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _string_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field} must be a non-empty array")
    result = tuple(_identifier(item, f"{field} item") for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{field} must contain unique values")
    return result


def _digest(value: object, field: str) -> str:
    result = _identifier(value, field)
    if not result.startswith("sha256:") or len(result) != 71:
        raise ValueError(f"{field} must be a sha256 digest")
    return result


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ReauthorizationRecord:
    """A human decision bound to one exact rerun result."""

    decision_id: str
    decision: str
    decision_target: str
    evidence_ids: tuple[str, ...]
    owner_id: str
    decided_by: str
    decided_at: datetime
    expires_at: datetime
    baseline_revisions_digest: str
    current_revisions_digest: str
    rerun_executor_version: int
    selected_check_ids: tuple[str, ...]
    rerun_result_digest: str
    residual_risk: str
    next_action: str

    @classmethod
    def from_dict(cls, value: object) -> "ReauthorizationRecord":
        if not isinstance(value, dict):
            raise ValueError("reauthorization record must be an object")
        allowed = {
            "reauthorization_record_version",
            "decision_id",
            "decision",
            "decision_target",
            "evidence_ids",
            "owner_id",
            "decided_by",
            "decided_at",
            "expires_at",
            "baseline_revisions_digest",
            "current_revisions_digest",
            "rerun_executor_version",
            "selected_check_ids",
            "rerun_result_digest",
            "residual_risk",
            "next_action",
        }
        extra = sorted(set(value) - allowed)
        if extra:
            raise ValueError(
                "reauthorization record contains unsupported fields: "
                + ", ".join(extra)
            )
        if value.get("reauthorization_record_version") != REAUTHORIZATION_RECORD_VERSION:
            raise ValueError(
                "reauthorization_record_version must be "
                f"{REAUTHORIZATION_RECORD_VERSION}"
            )
        decision = _identifier(value.get("decision"), "decision")
        if decision not in VALID_DECISIONS:
            raise ValueError("decision must be reauthorized, held, or blocked")
        executor_version = value.get("rerun_executor_version")
        if executor_version != 1:
            raise ValueError("rerun_executor_version must be 1")
        decided_at = _timestamp(value.get("decided_at"), "decided_at")
        expires_at = _timestamp(value.get("expires_at"), "expires_at")
        if expires_at <= decided_at:
            raise ValueError("expires_at must be after decided_at")
        return cls(
            decision_id=_identifier(value.get("decision_id"), "decision_id"),
            decision=decision,
            decision_target=_identifier(
                value.get("decision_target"), "decision_target"
            ),
            evidence_ids=_string_list(value.get("evidence_ids"), "evidence_ids"),
            owner_id=_identifier(value.get("owner_id"), "owner_id"),
            decided_by=_identifier(value.get("decided_by"), "decided_by"),
            decided_at=decided_at,
            expires_at=expires_at,
            baseline_revisions_digest=_digest(
                value.get("baseline_revisions_digest"),
                "baseline_revisions_digest",
            ),
            current_revisions_digest=_digest(
                value.get("current_revisions_digest"),
                "current_revisions_digest",
            ),
            rerun_executor_version=executor_version,
            selected_check_ids=_string_list(
                value.get("selected_check_ids"), "selected_check_ids"
            ),
            rerun_result_digest=_digest(
                value.get("rerun_result_digest"), "rerun_result_digest"
            ),
            residual_risk=_text(value.get("residual_risk"), "residual_risk"),
            next_action=_text(value.get("next_action"), "next_action"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "reauthorization_record_version": REAUTHORIZATION_RECORD_VERSION,
            "decision_id": self.decision_id,
            "decision": self.decision,
            "decision_target": self.decision_target,
            "evidence_ids": list(self.evidence_ids),
            "owner_id": self.owner_id,
            "decided_by": self.decided_by,
            "decided_at": _timestamp_text(self.decided_at),
            "expires_at": _timestamp_text(self.expires_at),
            "baseline_revisions_digest": self.baseline_revisions_digest,
            "current_revisions_digest": self.current_revisions_digest,
            "rerun_executor_version": self.rerun_executor_version,
            "selected_check_ids": list(self.selected_check_ids),
            "rerun_result_digest": self.rerun_result_digest,
            "residual_risk": self.residual_risk,
            "next_action": self.next_action,
        }


@dataclass(frozen=True)
class ReauthorizationValidation:
    """The validator's explicit reuse decision and required next action."""

    status: str
    decision: str
    reusable: bool
    decision_target: str
    evidence_ids: tuple[str, ...]
    rerun_result_digest: str
    reason_codes: tuple[str, ...]
    required_action: str
    validated_at: datetime
    expires_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "reauthorization_validation_version": REAUTHORIZATION_RECORD_VERSION,
            "status": self.status,
            "decision": self.decision,
            "reusable": self.reusable,
            "decision_target": self.decision_target,
            "evidence_ids": list(self.evidence_ids),
            "rerun_result_digest": self.rerun_result_digest,
            "reason_codes": list(self.reason_codes),
            "required_action": self.required_action,
            "validated_at": _timestamp_text(self.validated_at),
            "expires_at": _timestamp_text(self.expires_at),
            "claim_boundary": (
                "This validation reports whether the named human decision is "
                "currently reusable for the bound evidence. It does not approve "
                "deployment or prove production safety."
            ),
        }

    def to_markdown(self) -> str:
        return "\n".join(
            [
                "# Reauthorization validation",
                "",
                f"- **Status:** `{self.status}`",
                f"- **Decision:** `{self.decision}`",
                f"- **Reusable:** `{self.reusable}`",
                f"- **Decision target:** `{self.decision_target}`",
                f"- **Evidence:** {', '.join(self.evidence_ids)}",
                f"- **Result digest:** `{self.rerun_result_digest}`",
                f"- **Reasons:** {', '.join(self.reason_codes) or 'none'}",
                "",
                f"**Required action:** {self.required_action}",
                "",
                "This is a metadata-only reuse decision. It is not deployment approval.",
                "",
            ]
        )


def load_reauthorization_record(path: str | Path) -> ReauthorizationRecord:
    with open(path, encoding="utf-8") as handle:
        return ReauthorizationRecord.from_dict(json.load(handle))


def _validate_rerun_result(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("rerun result must be an object")
    allowed = {
        "rerun_executor_version",
        "plan_status",
        "status",
        "decision_targets",
        "revision_digests",
        "evidence_ids",
        "selected_check_ids",
        "results",
        "summary",
        "limits",
        "reason_codes",
        "required_action",
        "claim_boundary",
    }
    extra = sorted(set(value) - allowed)
    if extra:
        raise ValueError(
            "rerun result contains unsupported fields: " + ", ".join(extra)
        )
    if value.get("rerun_executor_version") != 1:
        raise ValueError("rerun_executor_version must be 1")
    if value.get("status") not in VALID_EXECUTOR_STATUSES:
        raise ValueError("rerun result has an unsupported status")
    targets = _string_list(value.get("decision_targets"), "decision_targets")
    digests = value.get("revision_digests")
    if not isinstance(digests, dict) or set(digests) != {"baseline", "current"}:
        raise ValueError("rerun result revision_digests must contain baseline and current")
    _digest(digests.get("baseline"), "revision_digests.baseline")
    _digest(digests.get("current"), "revision_digests.current")
    _string_list(value.get("evidence_ids"), "evidence_ids")
    _string_list(value.get("selected_check_ids"), "selected_check_ids")
    results = value.get("results")
    if not isinstance(results, list):
        raise ValueError("rerun result results must be an array")
    result_fields = {
        "check_id",
        "status",
        "checked_count",
        "passed_count",
        "negative_control_caught",
        "reason_codes",
        "required_action",
    }
    for index, result in enumerate(results):
        if not isinstance(result, dict) or set(result) != result_fields:
            raise ValueError(f"rerun result results[{index}] is malformed")
        _identifier(result.get("check_id"), f"results[{index}].check_id")
        if result.get("status") not in {"completed", "failed"}:
            raise ValueError(f"results[{index}].status is unsupported")
        if not isinstance(result.get("checked_count"), int) or not isinstance(
            result.get("passed_count"), int
        ):
            raise ValueError(f"results[{index}] counts must be integers")
        if not isinstance(result.get("negative_control_caught"), bool):
            raise ValueError(
                f"results[{index}].negative_control_caught must be boolean"
            )
        if not isinstance(result.get("reason_codes"), list):
            raise ValueError(f"results[{index}].reason_codes must be an array")
        _text(result.get("required_action"), f"results[{index}].required_action")
    summary = value.get("summary")
    if not isinstance(summary, dict) or set(summary) != {
        "checks_selected",
        "checks_completed",
        "checks_failed",
        "negative_controls_caught",
        "suite_runs",
        "elapsed_seconds",
    }:
        raise ValueError("rerun result summary is malformed")
    for field in (
        "checks_selected",
        "checks_completed",
        "checks_failed",
        "negative_controls_caught",
        "suite_runs",
    ):
        if not isinstance(summary[field], int) or summary[field] < 0:
            raise ValueError(
                f"rerun result summary.{field} must be a non-negative integer"
            )
    if not isinstance(summary["elapsed_seconds"], (int, float)):
        raise ValueError("rerun result summary.elapsed_seconds must be numeric")
    if summary["elapsed_seconds"] < 0:
        raise ValueError("rerun result summary.elapsed_seconds must be non-negative")
    limits = value.get("limits")
    if not isinstance(limits, dict) or set(limits) != {
        "max_checks",
        "max_elapsed_seconds",
    }:
        raise ValueError("rerun result limits are malformed")
    if not isinstance(limits["max_checks"], int) or limits["max_checks"] < 1:
        raise ValueError("rerun result limits.max_checks must be positive")
    if not isinstance(limits["max_elapsed_seconds"], (int, float)):
        raise ValueError("rerun result limits.max_elapsed_seconds must be numeric")
    if limits["max_elapsed_seconds"] <= 0:
        raise ValueError("rerun result limits.max_elapsed_seconds must be positive")
    if not isinstance(value.get("reason_codes"), list):
        raise ValueError("rerun result reason_codes must be an array")
    _text(value.get("required_action"), "rerun result required_action")
    _text(value.get("claim_boundary"), "rerun result claim_boundary")
    if tuple(value["decision_targets"]) != targets:
        raise ValueError("rerun result decision_targets are malformed")
    return value


def validate_reauthorization(
    record: ReauthorizationRecord,
    rerun_result: Mapping[str, object],
    *,
    now: datetime | None = None,
) -> ReauthorizationValidation:
    """Validate a record without making or changing the human decision."""

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    result = _validate_rerun_result(dict(rerun_result))
    reasons: list[str] = []
    result_digest = canonical_digest(result)
    if record.rerun_result_digest != result_digest:
        reasons.append("rerun_result_digest_mismatch")
    if len(result["decision_targets"]) != 1:
        reasons.append("rerun_has_multiple_decision_targets")
    elif record.decision_target != result["decision_targets"][0]:
        reasons.append("decision_target_mismatch")
    if tuple(record.evidence_ids) != tuple(result["evidence_ids"]):
        reasons.append("evidence_ids_mismatch")
    if record.baseline_revisions_digest != result["revision_digests"]["baseline"]:
        reasons.append("baseline_revision_digest_mismatch")
    if record.current_revisions_digest != result["revision_digests"]["current"]:
        reasons.append("current_revision_digest_mismatch")
    if record.selected_check_ids != tuple(result["selected_check_ids"]):
        reasons.append("selected_check_ids_mismatch")
    if record.rerun_executor_version != result["rerun_executor_version"]:
        reasons.append("executor_version_mismatch")
    if record.decided_at > current_time:
        reasons.append("decision_in_future")

    summary = result["summary"]
    selected = len(result["selected_check_ids"])
    if summary["checks_selected"] != selected:
        reasons.append("summary_check_count_mismatch")
    if result["status"] == "rerun_completed":
        if summary["checks_completed"] != selected:
            reasons.append("rerun_checks_incomplete")
        if summary["negative_controls_caught"] != selected:
            reasons.append("negative_controls_incomplete")
        if summary["suite_runs"] != 1:
            reasons.append("rerun_suite_count_invalid")
        if any(
            item["status"] != "completed"
            or not item["negative_control_caught"]
            for item in result["results"]
        ):
            reasons.append("rerun_result_contains_failed_check")
    elif record.decision == "reauthorized":
        reasons.append("rerun_not_completed")

    if reasons:
        status = "blocked"
        reusable = False
        action = "Repair the binding or rerun result before reusing the evidence."
    elif record.decision == "held":
        status = "held"
        reusable = False
        action = record.next_action
    elif record.decision == "blocked":
        status = "blocked"
        reusable = False
        action = record.next_action
    elif current_time >= record.expires_at:
        status = "expired"
        reusable = False
        action = "Rerun the affected checks and create a new reauthorization record."
        reasons.append("reauthorization_expired")
    else:
        status = "reauthorized"
        reusable = True
        action = (
            "Evidence may be reused only for this decision target until expiration; "
            "this is not deployment approval."
        )

    return ReauthorizationValidation(
        status=status,
        decision=record.decision,
        reusable=reusable,
        decision_target=record.decision_target,
        evidence_ids=record.evidence_ids,
        rerun_result_digest=result_digest,
        reason_codes=tuple(dict.fromkeys(reasons)),
        required_action=action,
        validated_at=current_time,
        expires_at=record.expires_at,
    )


__all__ = [
    "REAUTHORIZATION_RECORD_VERSION",
    "ReauthorizationRecord",
    "ReauthorizationValidation",
    "canonical_digest",
    "load_reauthorization_record",
    "validate_reauthorization",
]
