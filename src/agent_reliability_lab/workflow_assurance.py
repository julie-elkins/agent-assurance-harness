"""Validate metadata-only domain-review workflow manifests.

This module is the public side of a private integration boundary. A domain
reviewer remains authoritative for the subject-matter decision; this validator
checks only whether the declared workflow completed, preserved evidence, and
stayed within its resource limits.

The input is deliberately narrow. It contains identifiers, statuses, counts,
digests, and bounded usage numbers. It must not contain item text, reviewer
identity, prompts, answer keys, traces, or free-form rationale.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping


WORKFLOW_ASSURANCE_VERSION = 1
CONTENT_BOUNDARY = "metadata_only"
HUMAN_DECISION_REQUIRED = "required"
STAGE_STATUSES = frozenset(
    {"completed", "refused", "skipped", "failed", "not_applicable"}
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]+$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REFUSAL_CODE = re.compile(r"^[a-z0-9_.:-]+$")

_REQUIRED_KEYS = frozenset(
    {
        "workflow_assurance_version",
        "run_id",
        "workflow_version",
        "source_revision",
        "stages_expected",
        "stage_statuses",
        "counts",
        "refusals",
        "evidence",
        "artifact_hashes",
        "resources",
        "content_boundary",
        "human_decision",
    }
)
_FORBIDDEN_KEYS = frozenset(
    {
        "answer",
        "answer_key",
        "answer_keys",
        "choice",
        "choices",
        "item",
        "item_text",
        "items",
        "option",
        "options",
        "prompt",
        "rationale",
        "reviewer",
        "reviewer_id",
        "stem",
        "trace",
        "transcript",
        "tool_arguments",
        "tool_payload",
    }
)
_RESOURCE_KEYS = ("tool_calls", "elapsed_seconds", "output_bytes")


class WorkflowAssuranceValidationError(ValueError):
    """Raised when a review manifest cannot safely be interpreted."""

    def __init__(self, errors: tuple[str, ...]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowAssuranceValidationError(
            (f"{field} must be a non-empty identifier",)
        )
    value = value.strip()
    if not _IDENTIFIER.fullmatch(value) or any(
        character.isspace() for character in value
    ):
        raise WorkflowAssuranceValidationError(
            (f"{field} must contain identifier characters only",)
        )
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        raise WorkflowAssuranceValidationError(
            (f"{field} must match sha256:<64 lowercase hex characters>",)
        )
    return value


def _non_negative_number(value: object, field: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WorkflowAssuranceValidationError((f"{field} must be numeric",))
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise WorkflowAssuranceValidationError(
            (f"{field} must be finite and non-negative",)
        )
    return int(value) if value.is_integer() else value


def _non_negative_integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise WorkflowAssuranceValidationError(
            (f"{field} must be a non-negative integer",)
        )
    return value


def _positive_number(value: object, field: str) -> int | float:
    result = _non_negative_number(value, field)
    if result <= 0:
        raise WorkflowAssuranceValidationError(
            (f"{field} must be greater than zero",)
        )
    return result


def _scan_forbidden_keys(value: object, path: str = "manifest") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            allowed_count_field = path == "manifest.counts" and key_text == "items"
            if key_text.lower() in _FORBIDDEN_KEYS and not allowed_count_field:
                findings.append(f"{path}.{key_text}")
            findings.extend(_scan_forbidden_keys(nested, f"{path}.{key_text}"))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            findings.extend(_scan_forbidden_keys(nested, f"{path}[{index}]"))
    return findings


def _object(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkflowAssuranceValidationError((f"{field} must be an object",))
    return dict(value)


def validate_manifest(value: object) -> dict[str, Any]:
    """Validate and return a normalized metadata-only manifest."""

    manifest = _object(value, "manifest")
    forbidden = _scan_forbidden_keys(manifest)
    if forbidden:
        raise WorkflowAssuranceValidationError(
            (
                "manifest contains prohibited content-bearing fields: "
                + ", ".join(forbidden[:8]),
            )
        )

    missing = sorted(_REQUIRED_KEYS - manifest.keys())
    unknown = sorted(set(manifest) - _REQUIRED_KEYS)
    errors: list[str] = []
    if missing:
        errors.append("missing required fields: " + ", ".join(missing))
    if unknown:
        errors.append("unknown fields are not allowed: " + ", ".join(unknown))
    if errors:
        raise WorkflowAssuranceValidationError(tuple(errors))

    if manifest["workflow_assurance_version"] != WORKFLOW_ASSURANCE_VERSION:
        raise WorkflowAssuranceValidationError(
            (
                "workflow_assurance_version must be "
                f"{WORKFLOW_ASSURANCE_VERSION}",
            )
        )
    run_id = _identifier(manifest["run_id"], "run_id")
    workflow_version = _identifier(
        manifest["workflow_version"], "workflow_version"
    )
    source_revision = _digest(manifest["source_revision"], "source_revision")

    stages_expected = manifest["stages_expected"]
    if not isinstance(stages_expected, list) or not stages_expected:
        raise WorkflowAssuranceValidationError(
            ("stages_expected must be a non-empty list",)
        )
    normalized_stages = [_identifier(stage, "stages_expected[]") for stage in stages_expected]
    if len(set(normalized_stages)) != len(normalized_stages):
        raise WorkflowAssuranceValidationError(
            ("stages_expected must contain unique stage identifiers",)
        )

    stage_statuses = _object(manifest["stage_statuses"], "stage_statuses")
    if set(stage_statuses) != set(normalized_stages):
        raise WorkflowAssuranceValidationError(
            ("stage_statuses must contain exactly one status for every expected stage",)
        )
    normalized_statuses: dict[str, str] = {}
    for stage in normalized_stages:
        status = stage_statuses[stage]
        if not isinstance(status, str) or status not in STAGE_STATUSES:
            raise WorkflowAssuranceValidationError(
                (
                    f"stage_statuses.{stage} must be one of "
                    + ", ".join(sorted(STAGE_STATUSES)),
                )
            )
        normalized_statuses[stage] = status

    counts = _object(manifest["counts"], "counts")
    if set(counts) != {"items", "routed", "incomplete"}:
        raise WorkflowAssuranceValidationError(
            ("counts must contain exactly items, routed, and incomplete",)
        )
    normalized_counts = {
        key: _non_negative_integer(counts[key], f"counts.{key}")
        for key in ("items", "routed", "incomplete")
    }
    if normalized_counts["routed"] > normalized_counts["items"]:
        raise WorkflowAssuranceValidationError(
            ("counts.routed cannot exceed counts.items",)
        )
    if normalized_counts["incomplete"] > normalized_counts["items"]:
        raise WorkflowAssuranceValidationError(
            ("counts.incomplete cannot exceed counts.items",)
        )

    refusals = manifest["refusals"]
    if not isinstance(refusals, list):
        raise WorkflowAssuranceValidationError(("refusals must be a list",))
    normalized_refusals = []
    for refusal in refusals:
        if not isinstance(refusal, str) or not _REFUSAL_CODE.fullmatch(refusal):
            raise WorkflowAssuranceValidationError(
                ("refusals must contain reason-code identifiers only",)
            )
        normalized_refusals.append(refusal)

    evidence = _object(manifest["evidence"], "evidence")
    if set(evidence) != {"status", "required", "observed", "missing"}:
        raise WorkflowAssuranceValidationError(
            ("evidence must contain exactly status, required, observed, and missing",)
        )
    evidence_status = evidence["status"]
    if evidence_status not in {"complete", "incomplete", "not_evaluated"}:
        raise WorkflowAssuranceValidationError(
            (
                "evidence.status must be complete, incomplete, or "
                "not_evaluated",
            )
        )
    normalized_evidence = {
        "status": evidence_status,
        "required": _non_negative_integer(
            evidence["required"], "evidence.required"
        ),
        "observed": _non_negative_integer(
            evidence["observed"], "evidence.observed"
        ),
        "missing": _non_negative_integer(evidence["missing"], "evidence.missing"),
    }
    if (
        normalized_evidence["observed"] > normalized_evidence["required"]
        or normalized_evidence["missing"]
        != normalized_evidence["required"] - normalized_evidence["observed"]
    ):
        raise WorkflowAssuranceValidationError(
            ("evidence counts must satisfy required = observed + missing",)
        )

    artifact_hashes = _object(manifest["artifact_hashes"], "artifact_hashes")
    if not artifact_hashes:
        raise WorkflowAssuranceValidationError(
            ("artifact_hashes must contain at least one digest",)
        )
    normalized_hashes = {
        _identifier(key, "artifact_hashes key"): _digest(
            digest, f"artifact_hashes.{key}"
        )
        for key, digest in artifact_hashes.items()
    }

    resources = _object(manifest["resources"], "resources")
    if set(resources) != {"observed", "limits", "within_limits"}:
        raise WorkflowAssuranceValidationError(
            ("resources must contain exactly observed, limits, and within_limits",)
        )
    observed = _object(resources["observed"], "resources.observed")
    limits = _object(resources["limits"], "resources.limits")
    if set(observed) != set(_RESOURCE_KEYS) or set(limits) != set(_RESOURCE_KEYS):
        raise WorkflowAssuranceValidationError(
            "resources.observed and resources.limits must contain exactly "
            + ", ".join(_RESOURCE_KEYS),
        )
    normalized_observed = {
        key: _non_negative_number(observed[key], f"resources.observed.{key}")
        for key in _RESOURCE_KEYS
    }
    normalized_limits = {
        key: _positive_number(limits[key], f"resources.limits.{key}")
        for key in _RESOURCE_KEYS
    }
    within_limits = resources["within_limits"]
    if not isinstance(within_limits, bool):
        raise WorkflowAssuranceValidationError(
            ("resources.within_limits must be boolean",)
        )
    calculated_within_limits = all(
        normalized_observed[key] <= normalized_limits[key] for key in _RESOURCE_KEYS
    )
    if within_limits != calculated_within_limits:
        raise WorkflowAssuranceValidationError(
            ("resources.within_limits does not match observed values and limits",)
        )

    if manifest["content_boundary"] != CONTENT_BOUNDARY:
        raise WorkflowAssuranceValidationError(
            ("content_boundary must be metadata_only",)
        )
    if manifest["human_decision"] != HUMAN_DECISION_REQUIRED:
        raise WorkflowAssuranceValidationError(
            ("human_decision must be required; the harness cannot approve release",)
        )

    return {
        "workflow_assurance_version": WORKFLOW_ASSURANCE_VERSION,
        "run_id": run_id,
        "workflow_version": workflow_version,
        "source_revision": source_revision,
        "stages_expected": normalized_stages,
        "stage_statuses": normalized_statuses,
        "counts": normalized_counts,
        "refusals": normalized_refusals,
        "evidence": normalized_evidence,
        "artifact_hashes": normalized_hashes,
        "resources": {
            "observed": normalized_observed,
            "limits": normalized_limits,
            "within_limits": within_limits,
        },
        "content_boundary": CONTENT_BOUNDARY,
        "human_decision": HUMAN_DECISION_REQUIRED,
    }


def evaluate_manifest(value: object) -> dict[str, Any]:
    """Return a bounded assurance decision for one metadata-only manifest."""

    try:
        manifest = validate_manifest(value)
    except WorkflowAssuranceValidationError as error:
        return {
            "decision": "blocked",
            "supports_human_review": False,
            "release_authorized": False,
            "blocking_reasons": ["manifest_invalid"],
            "required_action": (
                "Repair the metadata-only manifest before interpreting the review."
            ),
            "refusal": {
                "error": "review_workflow_manifest_refused",
                "message": "The review workflow manifest could not be validated.",
                "guidance": str(error),
            },
        }

    blockers: list[str] = []
    if any(
        manifest["stage_statuses"][stage] != "completed"
        for stage in manifest["stages_expected"]
    ):
        blockers.append("expected_stage_not_completed")
    if manifest["refusals"]:
        blockers.append("workflow_refusal_present")
    if (
        manifest["evidence"]["status"] != "complete"
        or manifest["evidence"]["missing"] != 0
    ):
        blockers.append("evidence_incomplete")
    if manifest["counts"]["routed"] != manifest["counts"]["items"]:
        blockers.append("items_not_fully_routed")
    if manifest["counts"]["incomplete"] != 0:
        blockers.append("incomplete_item_review")
    if not manifest["resources"]["within_limits"]:
        blockers.append("resource_limit_exceeded")

    if blockers:
        return {
            "decision": "blocked",
            "supports_human_review": False,
            "release_authorized": False,
            "blocking_reasons": blockers,
            "required_action": (
                "Return the result to the private review workflow. Repair or "
                "adjudicate the blocked conditions before human release review."
            ),
            "manifest": manifest,
            "limitation": (
                "This decision assesses workflow completeness and evidence "
                "integrity; it does not assess subject-matter correctness."
            ),
        }

    return {
        "decision": "pass_for_human_review",
        "supports_human_review": True,
        "release_authorized": False,
        "blocking_reasons": [],
        "required_action": (
            "Return the assurance result to the private review report. An "
            "authorized human must still decide the item disposition and release."
        ),
        "manifest": manifest,
        "limitation": (
            "This decision assesses workflow completeness and evidence "
            "integrity; it does not assess subject-matter correctness."
        ),
    }


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Load one JSON manifest without exposing its contents in an error."""

    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkflowAssuranceValidationError(
            ("manifest could not be read as JSON",)
        ) from error
    if not isinstance(value, dict):
        raise WorkflowAssuranceValidationError(("manifest must contain an object",))
    return value


def sha256_file(path: str | Path) -> str:
    """Hash a private file without returning or persisting its contents."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()
