"""Portable run manifests and evidence reauthorization decisions.

The run manifest is the provider-neutral record that binds one evidence result to
the inputs that made it possible. It contains metadata and digests only; it never
stores prompts, tool payloads, provider output, or credentials.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping


RUN_MANIFEST_VERSION = 1
RUN_MANIFEST_STATUS_REAUTHORIZED = "reauthorized"
RUN_MANIFEST_STATUS_REAUTHORIZATION_REQUIRED = "reauthorization_required"
RUN_MANIFEST_STATUS_BLOCKED = "blocked"

REQUIRED_REVISION_KEYS = (
    "model",
    "harness",
    "prompt",
    "tools",
    "policy",
    "data",
    "repository",
    "environment",
    "grader",
)


class RunManifestValidationError(ValueError):
    """Raised when a run manifest cannot be safely evaluated."""

    def __init__(self, errors: tuple[str, ...]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RunManifestValidationError((f"{field} must be a non-empty string",))
    if any(character.isspace() for character in value):
        raise RunManifestValidationError((f"{field} must not contain whitespace",))
    return value


def _nonempty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RunManifestValidationError((f"{field} must be a non-empty string",))
    return value.strip()


def _digest(value: object, field: str) -> str:
    result = _identifier(value, field)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", result):
        raise RunManifestValidationError(
            (f"{field} must match sha256:<64 lowercase hex characters>",)
        )
    return result


def _non_negative_number(value: object, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise RunManifestValidationError((f"{field} must be a number",))
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise RunManifestValidationError((f"{field} must be finite and non-negative",))
    return result


def _non_negative_integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RunManifestValidationError((f"{field} must be a non-negative integer",))
    return value


def _positive_number(value: object, field: str) -> float:
    result = _non_negative_number(value, field)
    if result <= 0:
        raise RunManifestValidationError((f"{field} must be greater than zero",))
    return result


def _positive_integer(value: object, field: str) -> int:
    result = _non_negative_integer(value, field)
    if result <= 0:
        raise RunManifestValidationError((f"{field} must be greater than zero",))
    return result


def _parse_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RunManifestValidationError(
            (f"{field} must be an ISO-8601 timestamp",)
        ) from error
    if parsed.tzinfo is None:
        raise RunManifestValidationError((f"{field} must include a timezone",))
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class RunBudget:
    """Observed usage, limits, and the explicit stop condition for a run."""

    requests: int
    output_tokens: int
    elapsed_seconds: float
    estimated_cost_usd: float
    max_requests: int
    max_output_tokens: int
    max_elapsed_seconds: float
    max_estimated_cost_usd: float
    stop_condition: str

    @property
    def within_limits(self) -> bool:
        return (
            self.requests <= self.max_requests
            and self.output_tokens <= self.max_output_tokens
            and self.elapsed_seconds <= self.max_elapsed_seconds
            and self.estimated_cost_usd <= self.max_estimated_cost_usd
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "observed": {
                "requests": self.requests,
                "output_tokens": self.output_tokens,
                "elapsed_seconds": self.elapsed_seconds,
                "estimated_cost_usd": self.estimated_cost_usd,
            },
            "limits": {
                "max_requests": self.max_requests,
                "max_output_tokens": self.max_output_tokens,
                "max_elapsed_seconds": self.max_elapsed_seconds,
                "max_estimated_cost_usd": self.max_estimated_cost_usd,
            },
            "stop_condition": self.stop_condition,
            "within_limits": self.within_limits,
        }

    @classmethod
    def from_dict(cls, value: object) -> "RunBudget":
        if not isinstance(value, dict):
            raise RunManifestValidationError(("budget must be an object",))
        observed = value.get("observed")
        limits = value.get("limits")
        if not isinstance(observed, dict) or not isinstance(limits, dict):
            raise RunManifestValidationError(
                ("budget.observed and budget.limits must be objects",)
            )
        return cls(
            requests=_non_negative_integer(
                observed.get("requests"), "budget.observed.requests"
            ),
            output_tokens=_non_negative_integer(
                observed.get("output_tokens"), "budget.observed.output_tokens"
            ),
            elapsed_seconds=_non_negative_number(
                observed.get("elapsed_seconds"), "budget.observed.elapsed_seconds"
            ),
            estimated_cost_usd=_non_negative_number(
                observed.get("estimated_cost_usd"),
                "budget.observed.estimated_cost_usd",
            ),
            max_requests=_positive_integer(
                limits.get("max_requests"), "budget.limits.max_requests"
            ),
            max_output_tokens=_positive_integer(
                limits.get("max_output_tokens"), "budget.limits.max_output_tokens"
            ),
            max_elapsed_seconds=_positive_number(
                limits.get("max_elapsed_seconds"),
                "budget.limits.max_elapsed_seconds",
            ),
            max_estimated_cost_usd=_positive_number(
                limits.get("max_estimated_cost_usd"),
                "budget.limits.max_estimated_cost_usd",
            ),
            stop_condition=_nonempty_text(
                value.get("stop_condition"), "budget.stop_condition"
            ),
        )


@dataclass(frozen=True)
class ResumeCheckpoint:
    """Metadata identifying a safe resume point without storing checkpoint state."""

    checkpoint_id: str | None
    checkpoint_revision: str | None
    resume_supported: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_revision": self.checkpoint_revision,
            "resume_supported": self.resume_supported,
        }

    @classmethod
    def from_dict(cls, value: object) -> "ResumeCheckpoint":
        if not isinstance(value, dict):
            raise RunManifestValidationError(("checkpoint must be an object",))
        checkpoint_id = value.get("checkpoint_id")
        checkpoint_revision = value.get("checkpoint_revision")
        if checkpoint_id is not None:
            checkpoint_id = _identifier(checkpoint_id, "checkpoint.checkpoint_id")
        if checkpoint_revision is not None:
            checkpoint_revision = _identifier(
                checkpoint_revision, "checkpoint.checkpoint_revision"
            )
        resume_supported = value.get("resume_supported")
        if not isinstance(resume_supported, bool):
            raise RunManifestValidationError(
                ("checkpoint.resume_supported must be boolean",)
            )
        if resume_supported and (checkpoint_id is None or checkpoint_revision is None):
            raise RunManifestValidationError(
                (
                    "checkpoint_id and checkpoint_revision are required when "
                    "resume_supported is true",
                )
            )
        return cls(checkpoint_id, checkpoint_revision, resume_supported)


@dataclass(frozen=True)
class Repeatability:
    """Repeated-run metadata used to avoid treating one lucky run as proof."""

    run_count: int
    successful_run_count: int
    variance: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "run_count": self.run_count,
            "successful_run_count": self.successful_run_count,
            "variance": dict(sorted(self.variance.items())),
        }

    @classmethod
    def from_dict(cls, value: object) -> "Repeatability":
        if not isinstance(value, dict):
            raise RunManifestValidationError(("repeatability must be an object",))
        run_count = _positive_integer(value.get("run_count"), "repeatability.run_count")
        successful = _non_negative_integer(
            value.get("successful_run_count"),
            "repeatability.successful_run_count",
        )
        if successful > run_count:
            raise RunManifestValidationError(
                (
                    "repeatability.successful_run_count cannot exceed "
                    "repeatability.run_count",
                )
            )
        variance = value.get("variance")
        if not isinstance(variance, dict):
            raise RunManifestValidationError(("repeatability.variance must be an object",))
        normalized: dict[str, float] = {}
        for key, item in variance.items():
            name = _identifier(key, "repeatability.variance key")
            normalized[name] = _non_negative_number(
                item, f"repeatability.variance.{name}"
            )
        if run_count >= 2 and not normalized:
            raise RunManifestValidationError(
                (
                    "repeatability.variance must contain at least one metric "
                    "when run_count is two or greater",
                )
            )
        return cls(run_count, successful, normalized)


@dataclass(frozen=True)
class RunManifest:
    """The portable, metadata-only evidence binding for one agent run."""

    run_id: str
    decision_target: str
    actor_id: str
    agent_id: str
    provider: str
    model: str
    revisions: dict[str, str]
    tool_scope: tuple[str, ...]
    budget: RunBudget
    checkpoint: ResumeCheckpoint
    repeatability: Repeatability
    grader_version: str
    evidence_scope: tuple[str, ...]
    evidence_digest: str
    evidence_expires_at: str | None
    observed_outcome: str
    created_at: str
    manifest_version: int = RUN_MANIFEST_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_version": self.manifest_version,
            "run_id": self.run_id,
            "decision_target": self.decision_target,
            "actor_id": self.actor_id,
            "agent_id": self.agent_id,
            "provider": self.provider,
            "model": self.model,
            "revisions": dict(sorted(self.revisions.items())),
            "tool_scope": list(self.tool_scope),
            "budget": self.budget.to_dict(),
            "checkpoint": self.checkpoint.to_dict(),
            "repeatability": self.repeatability.to_dict(),
            "grader_version": self.grader_version,
            "evidence": {
                "scope": list(self.evidence_scope),
                "digest": self.evidence_digest,
                "expires_at": self.evidence_expires_at,
                "observed_outcome": self.observed_outcome,
            },
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: object) -> "RunManifest":
        if not isinstance(value, dict):
            raise RunManifestValidationError(("manifest must be an object",))
        if value.get("manifest_version") != RUN_MANIFEST_VERSION:
            raise RunManifestValidationError(
                (f"manifest_version must be {RUN_MANIFEST_VERSION}",)
            )

        revisions = value.get("revisions")
        if not isinstance(revisions, dict):
            raise RunManifestValidationError(("revisions must be an object",))
        missing = sorted(set(REQUIRED_REVISION_KEYS) - set(revisions))
        extra = sorted(set(revisions) - set(REQUIRED_REVISION_KEYS))
        errors = []
        if missing:
            errors.append("revisions missing: " + ", ".join(missing))
        if extra:
            errors.append(
                "revisions contain unsupported keys: " + ", ".join(extra)
            )
        if errors:
            raise RunManifestValidationError(tuple(errors))
        normalized_revisions = {
            key: _identifier(revisions[key], f"revisions.{key}")
            for key in REQUIRED_REVISION_KEYS
        }

        tool_scope = value.get("tool_scope")
        if not isinstance(tool_scope, list) or not tool_scope:
            raise RunManifestValidationError(("tool_scope must be a non-empty array",))
        normalized_tools = tuple(
            _identifier(tool, "tool_scope item") for tool in tool_scope
        )
        if len(set(normalized_tools)) != len(normalized_tools):
            raise RunManifestValidationError(("tool_scope items must be unique",))

        evidence = value.get("evidence")
        if not isinstance(evidence, dict):
            raise RunManifestValidationError(("evidence must be an object",))
        evidence_scope = evidence.get("scope")
        if not isinstance(evidence_scope, list) or not evidence_scope:
            raise RunManifestValidationError(
                ("evidence.scope must be a non-empty array",)
            )
        normalized_scope = tuple(
            _identifier(item, "evidence.scope item") for item in evidence_scope
        )
        evidence_digest = _digest(evidence.get("digest"), "evidence.digest")
        expires_at = evidence.get("expires_at")
        if expires_at is not None:
            expires_at = _identifier(expires_at, "evidence.expires_at")
            _parse_timestamp(expires_at, "evidence.expires_at")

        created_at = _identifier(value.get("created_at"), "created_at")
        _parse_timestamp(created_at, "created_at")
        grader_version = _identifier(
            value.get("grader_version"), "grader_version"
        )
        if grader_version != normalized_revisions["grader"]:
            raise RunManifestValidationError(
                ("grader_version must equal revisions.grader",)
            )
        return cls(
            run_id=_identifier(value.get("run_id"), "run_id"),
            decision_target=_identifier(
                value.get("decision_target"), "decision_target"
            ),
            actor_id=_identifier(value.get("actor_id"), "actor_id"),
            agent_id=_identifier(value.get("agent_id"), "agent_id"),
            provider=_identifier(value.get("provider"), "provider"),
            model=_identifier(value.get("model"), "model"),
            revisions=normalized_revisions,
            tool_scope=normalized_tools,
            budget=RunBudget.from_dict(value.get("budget")),
            checkpoint=ResumeCheckpoint.from_dict(value.get("checkpoint")),
            repeatability=Repeatability.from_dict(value.get("repeatability")),
            grader_version=grader_version,
            evidence_scope=normalized_scope,
            evidence_digest=evidence_digest,
            evidence_expires_at=expires_at,
            observed_outcome=_identifier(
                evidence.get("observed_outcome"), "evidence.observed_outcome"
            ),
            created_at=created_at,
            manifest_version=RUN_MANIFEST_VERSION,
        )


@dataclass(frozen=True)
class ReauthorizationDecision:
    """The decision about whether the manifest still supports its target decision."""

    status: str
    manifest_digest: str
    current_revisions_digest: str
    changed_dependencies: tuple[str, ...]
    reasons: tuple[str, ...]
    required_action: str

    @property
    def supports_decision(self) -> bool:
        return self.status == RUN_MANIFEST_STATUS_REAUTHORIZED

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "supports_decision": self.supports_decision,
            "manifest_digest": self.manifest_digest,
            "current_revisions_digest": self.current_revisions_digest,
            "changed_dependencies": list(self.changed_dependencies),
            "reasons": list(self.reasons),
            "required_action": self.required_action,
        }


def evaluate_reauthorization(
    manifest: RunManifest,
    current_revisions: Mapping[str, str],
    *,
    now: datetime | None = None,
) -> ReauthorizationDecision:
    """Evaluate whether a manifest remains valid against current dependencies."""

    errors: list[str] = []
    if set(current_revisions) != set(REQUIRED_REVISION_KEYS):
        missing = sorted(set(REQUIRED_REVISION_KEYS) - set(current_revisions))
        extra = sorted(set(current_revisions) - set(REQUIRED_REVISION_KEYS))
        if missing:
            errors.append("current revisions missing: " + ", ".join(missing))
        if extra:
            errors.append(
                "current revisions contain unsupported keys: " + ", ".join(extra)
            )
    normalized_current: dict[str, str] = {}
    for key in REQUIRED_REVISION_KEYS:
        if key in current_revisions:
            try:
                normalized_current[key] = _identifier(
                    current_revisions[key], f"current_revisions.{key}"
                )
            except RunManifestValidationError as error:
                errors.extend(error.errors)
    if errors:
        return ReauthorizationDecision(
            status=RUN_MANIFEST_STATUS_BLOCKED,
            manifest_digest=_sha256(manifest.to_dict()),
            current_revisions_digest=_sha256(dict(current_revisions)),
            changed_dependencies=(),
            reasons=tuple(errors),
            required_action="Repair the current revision record before evaluating evidence.",
        )

    changed = tuple(
        key
        for key in REQUIRED_REVISION_KEYS
        if manifest.revisions[key] != normalized_current[key]
    )
    reasons: list[str] = []
    if changed:
        reasons.append("dependency_revision_changed")
    if manifest.evidence_expires_at is not None:
        observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if observed_at >= _parse_timestamp(
            manifest.evidence_expires_at, "evidence.expires_at"
        ):
            reasons.append("evidence_expired")
    if not manifest.budget.within_limits:
        reasons.append("budget_exceeded")
    if manifest.observed_outcome != "success":
        reasons.append("observed_outcome_not_success")
    if manifest.repeatability.run_count < 2:
        reasons.append("insufficient_repeatability")

    hard_blockers = {
        "budget_exceeded",
        "observed_outcome_not_success",
        "insufficient_repeatability",
    }
    if any(reason in hard_blockers for reason in reasons):
        status = RUN_MANIFEST_STATUS_BLOCKED
        action = "Collect bounded, repeatable evidence before using this result."
    elif reasons:
        status = RUN_MANIFEST_STATUS_REAUTHORIZATION_REQUIRED
        action = "Rerun the affected scope and record an explicit reauthorization decision."
    else:
        status = RUN_MANIFEST_STATUS_REAUTHORIZED
        action = "Evidence remains bound to the current dependency revisions."

    return ReauthorizationDecision(
        status=status,
        manifest_digest=_sha256(manifest.to_dict()),
        current_revisions_digest=_sha256(normalized_current),
        changed_dependencies=changed,
        reasons=tuple(reasons),
        required_action=action,
    )


def load_manifest(path: str) -> RunManifest:
    """Load and validate a manifest from a JSON file."""

    with open(path, encoding="utf-8") as handle:
        return RunManifest.from_dict(json.load(handle))


def load_current_revisions(path: str) -> dict[str, str]:
    """Load a current-revision map from a JSON file."""

    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise RunManifestValidationError(("current revisions must be an object",))
    return dict(value)


__all__ = [
    "REQUIRED_REVISION_KEYS",
    "RUN_MANIFEST_STATUS_BLOCKED",
    "RUN_MANIFEST_STATUS_REAUTHORIZED",
    "RUN_MANIFEST_STATUS_REAUTHORIZATION_REQUIRED",
    "RUN_MANIFEST_VERSION",
    "ReauthorizationDecision",
    "Repeatability",
    "ResumeCheckpoint",
    "RunBudget",
    "RunManifest",
    "RunManifestValidationError",
    "evaluate_reauthorization",
    "load_current_revisions",
    "load_manifest",
]
