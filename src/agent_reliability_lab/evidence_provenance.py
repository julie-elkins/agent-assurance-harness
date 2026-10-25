"""Metadata-only provenance checks for one run-manifest evidence record.

Design rules:

1. Bind the producer record to the canonical run-manifest digest.
2. Record only bounded metadata; never read or accept artifact content.
3. Keep missing, invalid, and observed evidence as distinct decisions.
4. Make the negative control fail closed so an unobserved artifact cannot support reuse.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from .run_manifest import RunManifest


EVIDENCE_PROVENANCE_VERSION = 1
EVIDENCE_PROVENANCE_ID = "run-evidence-provenance-v1"
EVIDENCE_PROVENANCE_OBSERVED = "evidence_observed"
EVIDENCE_PROVENANCE_MISSING = "evidence_missing"
EVIDENCE_PROVENANCE_BLOCKED = "blocked"
# MODELLING ASSUMPTION: v1 is a public metadata-only contract; changing these
# identifiers requires a new version so existing consumers do not misread a record.
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER_PATTERN = re.compile(r"^[^\s]{1,128}$")
_RETENTION_STATUSES = {"retained", "expired", "not_observed"}
_CALIBRATION_STATUSES = {"calibrated", "not_calibrated", "not_applicable"}


def manifest_digest(manifest: RunManifest) -> str:
    """Return the canonical digest used to bind provenance to one manifest."""

    encoded = (
        json.dumps(
            manifest.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class EvidenceValidityMetadata:
    """Bounded receipt, grader, and synthetic deployment-context metadata."""

    artifact_type: str
    producer_version: str
    observed_at: str | None
    capture_scope: str
    retention_status: str
    retention_expires_at: str | None
    grader_type: str
    grader_calibration_status: str
    independent_breaker_id: str
    sample_count: int
    scenario_source: str
    trajectory_horizon: str
    tool_risk_tier: str
    coverage_profile: str

    def to_dict(self) -> dict[str, object]:
        """Return bounded validity metadata without evidence content."""

        record = {
            "artifact_type": self.artifact_type,
            "producer_version": self.producer_version,
            "observed_at": self.observed_at,
            "capture_scope": self.capture_scope,
            "retention_status": self.retention_status,
            "retention_expires_at": self.retention_expires_at,
            "grader_type": self.grader_type,
            "grader_calibration_status": self.grader_calibration_status,
            "independent_breaker_id": self.independent_breaker_id,
            "sample_count": self.sample_count,
            "scenario_source": self.scenario_source,
            "trajectory_horizon": self.trajectory_horizon,
            "tool_risk_tier": self.tool_risk_tier,
            "coverage_profile": self.coverage_profile,
        }
        return record

    @classmethod
    def from_dict(cls, value: object) -> "EvidenceValidityMetadata":
        """Validate receipt, grader, and synthetic deployment metadata."""

        if not isinstance(value, dict):
            raise ValueError("validity_metadata must be a JSON object.")
        observed_at = _optional_timestamp(value.get("observed_at"), "observed_at")
        retention_expires_at = _optional_timestamp(
            value.get("retention_expires_at"),
            "retention_expires_at",
        )
        retention_status = _identifier(
            value.get("retention_status"),
            "retention_status",
        )
        if retention_status not in _RETENTION_STATUSES:
            raise ValueError(
                "retention_status must be retained, expired, or not_observed."
            )
        if retention_status == "not_observed" and observed_at is not None:
            raise ValueError(
                "not_observed retention_status requires a null observed_at."
            )
        if retention_status != "not_observed" and observed_at is None:
            raise ValueError(
                "Observed retention status requires an observed_at timestamp."
            )
        calibration_status = _identifier(
            value.get("grader_calibration_status"),
            "grader_calibration_status",
        )
        if calibration_status not in _CALIBRATION_STATUSES:
            raise ValueError(
                "grader_calibration_status is not a supported calibration state."
            )
        sample_count = value.get("sample_count")
        if (
            not isinstance(sample_count, int)
            or isinstance(sample_count, bool)
            or sample_count < 1
        ):
            raise ValueError("sample_count must be a positive integer.")
        return cls(
            artifact_type=_identifier(value.get("artifact_type"), "artifact_type"),
            producer_version=_identifier(
                value.get("producer_version"),
                "producer_version",
            ),
            observed_at=observed_at,
            capture_scope=_identifier(
                value.get("capture_scope"),
                "capture_scope",
            ),
            retention_status=retention_status,
            retention_expires_at=retention_expires_at,
            grader_type=_identifier(value.get("grader_type"), "grader_type"),
            grader_calibration_status=calibration_status,
            independent_breaker_id=_identifier(
                value.get("independent_breaker_id"),
                "independent_breaker_id",
            ),
            sample_count=sample_count,
            scenario_source=_identifier(
                value.get("scenario_source"),
                "scenario_source",
            ),
            trajectory_horizon=_identifier(
                value.get("trajectory_horizon"),
                "trajectory_horizon",
            ),
            tool_risk_tier=_identifier(
                value.get("tool_risk_tier"),
                "tool_risk_tier",
            ),
            coverage_profile=_identifier(
                value.get("coverage_profile"),
                "coverage_profile",
            ),
        )


@dataclass(frozen=True)
class EvidenceProvenance:
    """A producer's metadata-only statement about one evidence artifact."""

    manifest_digest: str
    producer_id: str
    artifact_digest: str | None
    artifact_count: int
    observed: bool
    redaction_policy: str
    provenance_version: int = EVIDENCE_PROVENANCE_VERSION
    provenance_id: str = EVIDENCE_PROVENANCE_ID
    validity_metadata: EvidenceValidityMetadata | None = None

    def to_dict(self) -> dict[str, object]:
        """Return only the bounded provenance metadata."""

        record = {
            "provenance_version": self.provenance_version,
            "provenance_id": self.provenance_id,
            "manifest_digest": self.manifest_digest,
            "producer_id": self.producer_id,
            "artifact_digest": self.artifact_digest,
            "artifact_count": self.artifact_count,
            "observed": self.observed,
            "redaction_policy": self.redaction_policy,
            "diagnostics": {
                "warnings": [
                    "This is a metadata-only producer record, not a cryptographic signature.",
                    "The gate does not inspect or export the evidence artifact.",
                ],
                "what_it_does_not_show": (
                    "It does not prove the semantic quality of the trace, transcript, "
                    "grader result, or provider response."
                ),
            },
        }
        if self.validity_metadata is not None:
            record["validity_metadata"] = self.validity_metadata.to_dict()
        return record

    @classmethod
    def from_dict(cls, value: object) -> "EvidenceProvenance":
        """Validate one producer record without reading any artifact."""

        if not isinstance(value, dict):
            raise ValueError("Evidence provenance must be a JSON object.")
        if value.get("provenance_version") != EVIDENCE_PROVENANCE_VERSION:
            raise ValueError(
                f"provenance_version must be {EVIDENCE_PROVENANCE_VERSION}."
            )
        if value.get("provenance_id") != EVIDENCE_PROVENANCE_ID:
            raise ValueError("Unsupported evidence provenance identifier.")
        manifest_value = value.get("manifest_digest")
        if not isinstance(manifest_value, str) or not _DIGEST_PATTERN.fullmatch(
            manifest_value
        ):
            raise ValueError("manifest_digest must match sha256:<64 lowercase hex>.")
        producer_id = _identifier(value.get("producer_id"), "producer_id")
        artifact_digest = value.get("artifact_digest")
        if artifact_digest is not None and (
            not isinstance(artifact_digest, str)
            or not _DIGEST_PATTERN.fullmatch(artifact_digest)
        ):
            raise ValueError(
                "artifact_digest must be null or sha256:<64 lowercase hex>."
            )
        artifact_count = value.get("artifact_count")
        if (
            not isinstance(artifact_count, int)
            or isinstance(artifact_count, bool)
            or artifact_count < 0
        ):
            raise ValueError("artifact_count must be a non-negative integer.")
        observed = value.get("observed")
        if not isinstance(observed, bool):
            raise ValueError("observed must be boolean.")
        redaction_policy = _identifier(
            value.get("redaction_policy"),
            "redaction_policy",
        )
        validity_value = value.get("validity_metadata")
        validity_metadata = (
            EvidenceValidityMetadata.from_dict(validity_value)
            if validity_value is not None
            else None
        )
        if observed and (artifact_digest is None or artifact_count < 1):
            raise ValueError(
                "Observed evidence requires an artifact digest and positive artifact_count."
            )
        if not observed and (artifact_digest is not None or artifact_count != 0):
            raise ValueError(
                "Unobserved evidence requires a null artifact_digest and zero artifact_count."
            )
        return cls(
            manifest_digest=manifest_value,
            producer_id=producer_id,
            artifact_digest=artifact_digest,
            artifact_count=artifact_count,
            observed=observed,
            redaction_policy=redaction_policy,
            validity_metadata=validity_metadata,
        )


@dataclass(frozen=True)
class EvidenceProvenanceDecision:
    """The bounded result of comparing a producer record with a manifest."""

    status: str
    supports_evidence: bool
    manifest_digest: str
    producer_id: str | None
    artifact_digest: str | None
    reasons: tuple[str, ...]
    required_action: str
    validity_metadata: EvidenceValidityMetadata | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a safe decision record."""

        result = {
            "status": self.status,
            "supports_evidence": self.supports_evidence,
            "manifest_digest": self.manifest_digest,
            "producer_id": self.producer_id,
            "artifact_digest": self.artifact_digest,
            "reasons": list(self.reasons),
            "required_action": self.required_action,
        }
        if self.validity_metadata is not None:
            result["validity_metadata"] = self.validity_metadata.to_dict()
        return result


def evaluate_evidence_provenance(
    manifest: RunManifest,
    provenance: Mapping[str, object] | EvidenceProvenance,
) -> EvidenceProvenanceDecision:
    """Check whether metadata says an evidence artifact was observed for a manifest."""

    expected_digest = manifest_digest(manifest)
    try:
        record = (
            provenance
            if isinstance(provenance, EvidenceProvenance)
            else EvidenceProvenance.from_dict(provenance)
        )
    except ValueError as error:
        return EvidenceProvenanceDecision(
            status=EVIDENCE_PROVENANCE_BLOCKED,
            supports_evidence=False,
            manifest_digest=expected_digest,
            producer_id=None,
            artifact_digest=None,
            reasons=("provenance_record_invalid", str(error)),
            required_action="Repair the producer record before reusing the evidence.",
        )

    if record.manifest_digest != expected_digest:
        return EvidenceProvenanceDecision(
            status=EVIDENCE_PROVENANCE_BLOCKED,
            supports_evidence=False,
            manifest_digest=expected_digest,
            producer_id=record.producer_id,
            artifact_digest=record.artifact_digest,
            reasons=("manifest_digest_mismatch",),
            required_action=(
                "Regenerate provenance from the exact run manifest before reusing "
                "the evidence."
            ),
            validity_metadata=record.validity_metadata,
        )

    if not record.observed or record.artifact_count < 1:
        return EvidenceProvenanceDecision(
            status=EVIDENCE_PROVENANCE_MISSING,
            supports_evidence=False,
            manifest_digest=expected_digest,
            producer_id=record.producer_id,
            artifact_digest=record.artifact_digest,
            reasons=("evidence_artifact_not_observed",),
            required_action=(
                "Collect and record the bounded evidence artifact before reusing "
                "the manifest result."
            ),
            validity_metadata=record.validity_metadata,
        )

    return EvidenceProvenanceDecision(
        status=EVIDENCE_PROVENANCE_OBSERVED,
        supports_evidence=True,
        manifest_digest=expected_digest,
        producer_id=record.producer_id,
        artifact_digest=record.artifact_digest,
        reasons=(),
        required_action="The producer record is bound to an observed evidence artifact.",
        validity_metadata=record.validity_metadata,
    )


def build_evidence_provenance(
    manifest: RunManifest,
    *,
    producer_id: str,
    artifact_digest: str | None,
    artifact_count: int,
    observed: bool,
    redaction_policy: str,
    validity_metadata: EvidenceValidityMetadata | None = None,
) -> EvidenceProvenance:
    """Build a producer record from metadata supplied by a local adapter."""

    record = EvidenceProvenance(
        manifest_digest=manifest_digest(manifest),
        producer_id=_identifier(producer_id, "producer_id"),
        artifact_digest=artifact_digest,
        artifact_count=artifact_count,
        observed=observed,
        redaction_policy=_identifier(redaction_policy, "redaction_policy"),
        validity_metadata=validity_metadata,
    )
    # Validate builder output through the same boundary as JSON input. Otherwise a
    # local adapter could create an impossible "observed" record that the file gate
    # would correctly refuse, making in-process and file-based behaviour disagree.
    EvidenceProvenance.from_dict(record.to_dict())
    return record


def build_evidence_validity_metadata(
    *,
    artifact_type: str,
    producer_version: str,
    observed_at: str | None,
    capture_scope: str,
    retention_status: str,
    retention_expires_at: str | None,
    grader_type: str,
    grader_calibration_status: str,
    independent_breaker_id: str,
    sample_count: int,
    scenario_source: str,
    trajectory_horizon: str,
    tool_risk_tier: str,
    coverage_profile: str,
) -> EvidenceValidityMetadata:
    """Build and validate bounded validity metadata for a local adapter."""

    return EvidenceValidityMetadata.from_dict(
        {
            "artifact_type": artifact_type,
            "producer_version": producer_version,
            "observed_at": observed_at,
            "capture_scope": capture_scope,
            "retention_status": retention_status,
            "retention_expires_at": retention_expires_at,
            "grader_type": grader_type,
            "grader_calibration_status": grader_calibration_status,
            "independent_breaker_id": independent_breaker_id,
            "sample_count": sample_count,
            "scenario_source": scenario_source,
            "trajectory_horizon": trajectory_horizon,
            "tool_risk_tier": tool_risk_tier,
            "coverage_profile": coverage_profile,
        }
    )


def _optional_timestamp(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be null or an ISO 8601 timestamp.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field} must be null or an ISO 8601 timestamp.") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone.")
    return value


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} must be a non-empty identifier without whitespace.")
    return value


__all__ = [
    "EVIDENCE_PROVENANCE_BLOCKED",
    "EVIDENCE_PROVENANCE_ID",
    "EVIDENCE_PROVENANCE_MISSING",
    "EVIDENCE_PROVENANCE_OBSERVED",
    "EVIDENCE_PROVENANCE_VERSION",
    "EvidenceProvenance",
    "EvidenceProvenanceDecision",
    "EvidenceValidityMetadata",
    "build_evidence_provenance",
    "build_evidence_validity_metadata",
    "evaluate_evidence_provenance",
    "manifest_digest",
]
