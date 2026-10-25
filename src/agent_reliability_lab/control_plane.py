"""Metadata-only control-plane decisions and append-only audit storage.

The hosted control plane follows four design rules:

1. Reuse the local run-manifest evaluator as the only decision source.
2. Reject unknown fields before they can become an unreviewed content channel.
3. Store decision metadata and digests, never prompts, tool payloads, or model output.
4. Append records with an enforced expiry; a missing record must never read as approval.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from .run_manifest import (
    REQUIRED_REVISION_KEYS,
    RunManifest,
    RunManifestValidationError,
    evaluate_reauthorization,
)


# MODELLING ASSUMPTION: thirty days is a bounded demonstration retention window.
# It must be replaced by an approved retention requirement before deployment.
AUDIT_RETENTION_DAYS = 30

# MODELLING ASSUMPTION: API requests are metadata-only and should remain small.
MAX_SUBMISSION_BYTES = 64 * 1024
MAX_IDENTIFIER_LENGTH = 256

_IDENTIFIER_PATTERN = re.compile(r"^[^\s]+$")
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

_MANIFEST_FIELDS = frozenset(
    {
        "manifest_version",
        "run_id",
        "decision_target",
        "actor_id",
        "agent_id",
        "provider",
        "model",
        "revisions",
        "tool_scope",
        "budget",
        "checkpoint",
        "repeatability",
        "grader_version",
        "evidence",
        "created_at",
    }
)
_BUDGET_FIELDS = frozenset({"observed", "limits", "stop_condition"})
_BUDGET_OBSERVED_FIELDS = frozenset(
    {"requests", "output_tokens", "elapsed_seconds", "estimated_cost_usd"}
)
_BUDGET_LIMIT_FIELDS = frozenset(
    {
        "max_requests",
        "max_output_tokens",
        "max_elapsed_seconds",
        "max_estimated_cost_usd",
    }
)
_CHECKPOINT_FIELDS = frozenset(
    {"checkpoint_id", "checkpoint_revision", "resume_supported"}
)
_REPEATABILITY_FIELDS = frozenset(
    {"run_count", "successful_run_count", "variance"}
)
_EVIDENCE_FIELDS = frozenset(
    {"scope", "digest", "expires_at", "observed_outcome"}
)


class ControlPlaneValidationError(ValueError):
    """Raised when a metadata-only control-plane submission is unsafe."""

    def __init__(self, errors: tuple[str, ...]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _reject_unknown(value: object, allowed: frozenset[str], field: str) -> None:
    if not isinstance(value, dict):
        raise ControlPlaneValidationError((f"{field} must be an object",))
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ControlPlaneValidationError(
            (f"{field} contains unsupported fields: {', '.join(unknown)}",)
        )


def _safe_identifier(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_IDENTIFIER_LENGTH
        or not _IDENTIFIER_PATTERN.fullmatch(value)
    ):
        raise ControlPlaneValidationError(
            (
                f"{field} must be a non-empty identifier of at most "
                f"{MAX_IDENTIFIER_LENGTH} characters",
            )
        )
    return value


def _validate_metadata_shape(manifest_value: object) -> None:
    """Reject extra nested fields before the shared parser normalises the record."""

    _reject_unknown(manifest_value, _MANIFEST_FIELDS, "manifest")
    assert isinstance(manifest_value, dict)
    _reject_unknown(manifest_value.get("budget"), _BUDGET_FIELDS, "manifest.budget")
    budget = manifest_value["budget"]
    assert isinstance(budget, dict)
    _reject_unknown(
        budget.get("observed"),
        _BUDGET_OBSERVED_FIELDS,
        "manifest.budget.observed",
    )
    _reject_unknown(
        budget.get("limits"),
        _BUDGET_LIMIT_FIELDS,
        "manifest.budget.limits",
    )
    _reject_unknown(
        manifest_value.get("checkpoint"),
        _CHECKPOINT_FIELDS,
        "manifest.checkpoint",
    )
    _reject_unknown(
        manifest_value.get("repeatability"),
        _REPEATABILITY_FIELDS,
        "manifest.repeatability",
    )
    _reject_unknown(
        manifest_value.get("evidence"),
        _EVIDENCE_FIELDS,
        "manifest.evidence",
    )


def _validate_current_revisions(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ControlPlaneValidationError(
            ("current_revisions must be an object",)
        )
    expected = set(REQUIRED_REVISION_KEYS)
    missing = sorted(expected - set(value))
    extra = sorted(set(value) - expected)
    errors = []
    if missing:
        errors.append("current_revisions missing: " + ", ".join(missing))
    if extra:
        errors.append(
            "current_revisions contains unsupported keys: " + ", ".join(extra)
        )
    if errors:
        raise ControlPlaneValidationError(tuple(errors))
    return {
        key: _safe_identifier(value[key], f"current_revisions.{key}")
        for key in REQUIRED_REVISION_KEYS
    }


def _record_id(recorded_at: datetime, manifest_digest: str) -> str:
    return f"{recorded_at.isoformat()}#{manifest_digest.removeprefix('sha256:')[:16]}"


@dataclass(frozen=True)
class ControlPlaneSubmission:
    """The safe response and audit record for one reauthorization request."""

    response: dict[str, object]
    audit_record: dict[str, object]


class AuditStore(Protocol):
    """Minimal storage boundary used by the service and its local tests."""

    def append(self, record: dict[str, object]) -> None:
        """Append one record without updating or deleting an existing record."""

    def latest(self, run_id: str) -> dict[str, object] | None:
        """Return the newest record for a run, if one exists."""


class InMemoryAuditStore:
    """Deterministic store used by local tests; it never contacts AWS."""

    def __init__(self) -> None:
        self._records: list[dict[str, object]] = []

    def append(self, record: dict[str, object]) -> None:
        self._records.append(copy.deepcopy(record))

    def latest(self, run_id: str) -> dict[str, object] | None:
        matches = [record for record in self._records if record["run_id"] == run_id]
        if not matches:
            return None
        return copy.deepcopy(max(matches, key=lambda record: str(record["event_id"])))


class DynamoAuditStore:
    """DynamoDB adapter with only append, query, and read permissions."""

    def __init__(self, table_name: str) -> None:
        # boto3 is supplied by the AWS Lambda Python runtime. Keeping this import
        # inside the deployment adapter lets the local evaluator remain dependency-free.
        import boto3
        from boto3.dynamodb.conditions import Key

        self._key = Key
        self._table = boto3.resource("dynamodb").Table(table_name)

    def append(self, record: dict[str, object]) -> None:
        self._table.put_item(
            Item=record,
            ConditionExpression=(
                "attribute_not_exists(run_id) AND attribute_not_exists(event_id)"
            ),
        )

    def latest(self, run_id: str) -> dict[str, object] | None:
        result = self._table.query(
            KeyConditionExpression=self._key("run_id").eq(run_id),
            ScanIndexForward=False,
            Limit=1,
            ConsistentRead=True,
        )
        items = result.get("Items", [])
        return dict(items[0]) if items else None


def prepare_submission(
    payload: object,
    *,
    principal_id: str,
    now: datetime | None = None,
) -> ControlPlaneSubmission:
    """Validate, evaluate, and reduce a request to safe metadata."""

    if not isinstance(payload, dict):
        raise ControlPlaneValidationError(("request must be an object",))
    allowed_request_fields = frozenset({"manifest", "current_revisions"})
    _reject_unknown(payload, allowed_request_fields, "request")
    if "manifest" not in payload or "current_revisions" not in payload:
        raise ControlPlaneValidationError(
            ("request must contain manifest and current_revisions",)
        )
    _safe_identifier(principal_id, "principal_id")
    _validate_metadata_shape(payload["manifest"])
    try:
        manifest = RunManifest.from_dict(payload["manifest"])
    except RunManifestValidationError as error:
        raise ControlPlaneValidationError(error.errors) from error
    if not _RUN_ID_PATTERN.fullmatch(manifest.run_id):
        raise ControlPlaneValidationError(
            ("manifest.run_id contains unsupported characters",)
        )
    current_revisions = _validate_current_revisions(payload["current_revisions"])
    recorded_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    decision = evaluate_reauthorization(
        manifest,
        current_revisions,
        now=recorded_at,
    )
    event_id = _record_id(recorded_at, decision.manifest_digest)
    expires_at_epoch = int(
        (recorded_at + timedelta(days=AUDIT_RETENTION_DAYS)).timestamp()
    )
    audit_record: dict[str, object] = {
        "run_id": manifest.run_id,
        "event_id": event_id,
        "manifest_digest": decision.manifest_digest,
        "current_revisions_digest": decision.current_revisions_digest,
        "status": decision.status,
        "supports_decision": decision.supports_decision,
        "changed_dependencies": list(decision.changed_dependencies),
        "reasons": list(decision.reasons),
        "required_action": decision.required_action,
        "decision_target": manifest.decision_target,
        "actor_id": manifest.actor_id,
        "agent_id": manifest.agent_id,
        "provider": manifest.provider,
        "model": manifest.model,
        "submitted_by": principal_id,
        "recorded_at": recorded_at.isoformat(),
        "expires_at_epoch": expires_at_epoch,
    }
    response = {
        "run_id": manifest.run_id,
        "audit_id": event_id,
        "recorded_at": recorded_at.isoformat(),
        **decision.to_dict(),
    }
    return ControlPlaneSubmission(response=response, audit_record=audit_record)


def submit(
    payload: object,
    *,
    principal_id: str,
    store: AuditStore,
    now: datetime | None = None,
) -> dict[str, object]:
    """Evaluate one request and append its metadata-only audit record."""

    prepared = prepare_submission(payload, principal_id=principal_id, now=now)
    store.append(prepared.audit_record)
    return prepared.response


def get_latest(run_id: str, *, store: AuditStore) -> dict[str, object] | None:
    """Read the latest bounded audit record for a safe run identifier."""

    if not _RUN_ID_PATTERN.fullmatch(run_id):
        raise ControlPlaneValidationError(
            ("run_id contains unsupported characters",)
        )
    return store.latest(run_id)


__all__ = [
    "AUDIT_RETENTION_DAYS",
    "ControlPlaneSubmission",
    "ControlPlaneValidationError",
    "DynamoAuditStore",
    "InMemoryAuditStore",
    "MAX_SUBMISSION_BYTES",
    "get_latest",
    "prepare_submission",
    "submit",
]
