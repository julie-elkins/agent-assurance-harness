"""Metadata-only promotion decision for a verified release evidence bundle."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROMOTION_VERSION = 1
SLSA_PROVENANCE = "https://slsa.dev/provenance/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]*$")


def _identifier(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or _IDENTIFIER.fullmatch(value) is None
    ):
        raise ValueError(f"{field} must be a non-empty identifier.")
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be a SHA-256 fingerprint.")
    return value


def _commit(value: object, field: str = "source_digest") -> str:
    if not isinstance(value, str) or _COMMIT.fullmatch(value) is None:
        raise ValueError(f"{field} must be a Git commit identifier.")
    return value


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Evidence report must contain a JSON object.")
    return value


@dataclass(frozen=True)
class PromotionArtifact:
    """The safe identity and local hash of one promotion subject."""

    name: str
    sha256: str
    local_match: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "sha256": self.sha256,
            "local_match": self.local_match,
        }


@dataclass(frozen=True)
class ReleasePromotionReport:
    """A metadata-only decision at the release promotion boundary."""

    decision: str
    repository: str
    signer_workflow: str
    source_digest: str
    approved_by: str
    approval_id: str
    environment: str
    package_version: str | None
    artifacts: tuple[PromotionArtifact, ...]
    blocking_reasons: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.decision == "promote"

    def to_dict(self) -> dict[str, object]:
        return {
            "promotion_version": PROMOTION_VERSION,
            "passed": self.passed,
            "decision": self.decision,
            "repository": self.repository,
            "signer_workflow": self.signer_workflow,
            "source_digest": self.source_digest,
            "package_version": self.package_version,
            "approval": {
                "approved_by": self.approved_by,
                "approval_id": self.approval_id,
                "environment": self.environment,
            },
            "artifacts": [item.to_dict() for item in self.artifacts],
            "blocking_reasons": list(self.blocking_reasons),
            "evidence": {
                "provenance_verified": not any(
                    reason.startswith("provenance-")
                    for reason in self.blocking_reasons
                ),
                "release_manifest_verified": not any(
                    reason.startswith("release-manifest-")
                    for reason in self.blocking_reasons
                ),
                "rollback_verified": not any(
                    reason.startswith("rollback-")
                    for reason in self.blocking_reasons
                ),
                "approval_verified": not any(
                    reason.startswith("approval-")
                    for reason in self.blocking_reasons
                ),
            },
            "diagnostics": {
                "warnings": [
                    "This is a metadata-only promotion decision; it does "
                    "not publish or deploy an artifact.",
                    "The protected GitHub environment is an external approval "
                    "control and must be configured by repository administrators.",
                ],
                "what_it_does_not_show": (
                    "It does not show credentials, prompts, provider output, "
                    "artifact contents, deployment health, or target state."
                ),
            },
        }

    def to_markdown(self) -> str:
        status = "PROMOTE" if self.passed else "BLOCKED"
        lines = [
            "# Release promotion decision",
            "",
            f"- **Decision:** {status}",
            f"- **Repository:** `{self.repository}`",
            f"- **Source commit:** `{self.source_digest}`",
            f"- **Package version:** `{self.package_version or 'unknown'}`",
            f"- **Approved by:** `{self.approved_by}`",
            f"- **Approval ID:** `{self.approval_id}`",
            f"- **Environment:** `{self.environment}`",
            "",
            "## Artifact evidence",
            "",
            "| Artifact | SHA-256 | Local bytes match |",
            "| --- | --- | --- |",
        ]
        lines.extend(
            f"| `{item.name}` | `{item.sha256}` | "
            f"{'PASS' if item.local_match else 'BLOCKED'} |"
            for item in self.artifacts
        )
        lines.extend(["", "## Blocking reasons", ""])
        if self.blocking_reasons:
            lines.extend(f"- `{reason}`" for reason in self.blocking_reasons)
        else:
            lines.append("- none")
        lines.extend(
            [
                "",
                "This decision contains identifiers and hashes only; it does "
                "not publish or deploy the artifact.",
                "",
            ]
        )
        return "\n".join(lines)


def evaluate_release_promotion(
    *,
    artifact_directory: Path,
    provenance_path: Path,
    release_manifest_path: Path,
    rollback_path: Path,
    repository: str,
    signer_workflow: str,
    source_digest: str,
    approved_by: str,
    approval_id: str,
    environment: str,
) -> ReleasePromotionReport:
    """Evaluate whether one exact, approved evidence bundle may proceed."""

    repository = _identifier(repository, "repository")
    signer_workflow = _identifier(signer_workflow, "signer_workflow")
    source_digest = _commit(source_digest)
    approved_by = _identifier(approved_by, "approved_by")
    approval_id = _identifier(approval_id, "approval_id")
    environment = _identifier(environment, "environment")

    provenance = _read_object(provenance_path)
    release_manifest = _read_object(release_manifest_path)
    rollback = _read_object(rollback_path)
    reasons: list[str] = []
    package_version = _safe_identifier(release_manifest.get("package_version"))

    if environment != "release":
        reasons.append("approval-environment-not-release")
    if not approved_by:
        reasons.append("approval-approved-by-missing")
    if not approval_id:
        reasons.append("approval-id-missing")

    provenance_subjects = _provenance_observation(
        provenance,
        repository=repository,
        signer_workflow=signer_workflow,
        source_digest=source_digest,
        reasons=reasons,
    )
    expected_artifacts = _release_manifest_observation(
        release_manifest,
        source_digest=source_digest,
        reasons=reasons,
    )
    rollback_ok = _rollback_observation(
        rollback,
        source_digest=source_digest,
        reasons=reasons,
    )
    if not rollback_ok:
        reasons.append("rollback-evidence-not-ready")

    artifacts: list[PromotionArtifact] = []
    artifact_names = tuple(sorted(expected_artifacts))
    for name in artifact_names:
        expected_digest = expected_artifacts[name]
        artifact = artifact_directory / name
        if not artifact.is_file():
            reasons.append(f"artifact-missing:{name}")
            artifacts.append(
                PromotionArtifact(name, expected_digest, False)
            )
            continue
        local_digest = _file_sha256(artifact)
        local_match = local_digest == expected_digest
        if not local_match:
            reasons.append(f"artifact-hash-mismatch:{name}")
        artifacts.append(
            PromotionArtifact(name, local_digest, local_match)
        )

    for name, digest in provenance_subjects.items():
        if name not in expected_artifacts:
            reasons.append(f"provenance-unexpected-artifact:{name}")
        elif digest != expected_artifacts[name]:
            reasons.append(f"provenance-manifest-hash-mismatch:{name}")
    for name in expected_artifacts:
        if name not in provenance_subjects:
            reasons.append(f"provenance-missing-artifact:{name}")

    return ReleasePromotionReport(
        decision="promote" if not reasons else "blocked",
        repository=repository,
        signer_workflow=signer_workflow,
        source_digest=source_digest,
        approved_by=approved_by,
        approval_id=approval_id,
        environment=environment,
        package_version=package_version,
        artifacts=tuple(artifacts),
        blocking_reasons=tuple(dict.fromkeys(reasons)),
    )


def _provenance_observation(
    report: dict[str, Any],
    *,
    repository: str,
    signer_workflow: str,
    source_digest: str,
    reasons: list[str],
) -> dict[str, str]:
    subjects = report.get("subjects")
    if (
        report.get("provenance_version") != 1
        or report.get("passed") is not True
        or report.get("repository") != repository
        or report.get("signer_workflow") != signer_workflow
        or report.get("source_digest") != source_digest
        or report.get("predicate_type") != SLSA_PROVENANCE
    ):
        reasons.append("provenance-report-invalid")
    if not isinstance(subjects, list) or not subjects:
        reasons.append("provenance-subjects-missing")
        return {}
    observed: dict[str, str] = {}
    for subject in subjects:
        if not isinstance(subject, dict):
            reasons.append("provenance-subject-invalid")
            continue
        name = _safe_artifact_name(subject.get("name"))
        digest = _safe_sha256(subject.get("sha256"))
        if not name or not digest:
            reasons.append("provenance-subject-identity-invalid")
            continue
        if subject.get("verified") is not True:
            reasons.append(f"provenance-subject-not-verified:{name}")
        observed[name] = digest
    return observed


def _release_manifest_observation(
    report: dict[str, Any],
    *,
    source_digest: str,
    reasons: list[str],
) -> dict[str, str]:
    if (
        report.get("release_artifact_version") != 1
        or report.get("passed") is not True
        or report.get("git_commit") != source_digest
        or report.get("artifact_output_persisted") is not True
        or report.get("sbom_persisted") is not True
    ):
        reasons.append("release-manifest-invalid")
    artifacts = report.get("artifacts")
    names = report.get("artifact_names")
    if not isinstance(artifacts, dict) or not isinstance(names, list):
        reasons.append("release-manifest-artifacts-missing")
        return {}
    package_version = _safe_identifier(report.get("package_version"))
    expected_names = (
        {
            f"agent_reliability_lab-{package_version}.tar.gz",
            f"agent_reliability_lab-{package_version}-py3-none-any.whl",
        }
        if package_version
        else set()
    )
    safe_names = [_safe_artifact_name(name) for name in names]
    if (
        len(names) != 2
        or any(name is None for name in safe_names)
        or set(safe_names) != expected_names
    ):
        reasons.append("release-manifest-artifact-names-invalid")
    source_digest = _safe_sha256(
        artifacts.get("source_distribution_sha256")
    )
    wheel_digest = _safe_sha256(artifacts.get("wheel_sha256"))
    if not source_digest:
        reasons.append("release-manifest-source-hash-invalid")
    if not wheel_digest:
        reasons.append("release-manifest-wheel-hash-invalid")
    if not package_version:
        reasons.append("release-manifest-package-version-invalid")
        return {}
    return {
        f"agent_reliability_lab-{package_version}.tar.gz": source_digest or "",
        f"agent_reliability_lab-{package_version}-py3-none-any.whl": wheel_digest or "",
    }


def _rollback_observation(
    report: dict[str, Any],
    *,
    source_digest: str,
    reasons: list[str],
) -> bool:
    recovery = report.get("recovery")
    injection = report.get("failure_injection")
    side_effects = report.get("side_effects")
    passed = (
        report.get("rollback_rehearsal_version") == 1
        and report.get("passed") is True
        and report.get("git_commit") == source_digest
        and isinstance(recovery, dict)
        and recovery.get("restored_match") is True
        and isinstance(injection, dict)
        and injection.get("applied") is True
        and injection.get("detected") is True
        and isinstance(side_effects, dict)
        and side_effects.get("external_writes_attempted") is False
        and side_effects.get("network_used") is False
    )
    if not passed:
        reasons.append("rollback-evidence-invalid")
    return passed


def _safe_identifier(value: object) -> str | None:
    return (
        value
        if isinstance(value, str)
        and value
        and _IDENTIFIER.fullmatch(value) is not None
        else None
    )


def _safe_sha256(value: object) -> str | None:
    return value if isinstance(value, str) and _SHA256.fullmatch(value) else None


def _safe_artifact_name(value: object) -> str | None:
    name = _safe_identifier(value)
    if (
        name is None
        or Path(name).name != name
        or not (name.endswith(".tar.gz") or name.endswith(".whl"))
    ):
        return None
    return name


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
