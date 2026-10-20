"""Metadata-only verification of GitHub Actions artifact provenance."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROVENANCE_VERSION = 1
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


def _commit(value: object) -> str:
    if not isinstance(value, str) or _COMMIT.fullmatch(value) is None:
        raise ValueError("source_digest must be a Git commit identifier.")
    return value


@dataclass(frozen=True)
class ProvenanceSubject:
    """One local artifact and the result of its signed verification."""

    name: str
    sha256: str
    verified: bool
    attestation_count: int
    failure_code: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "sha256": self.sha256,
            "verified": self.verified,
            "attestation_count": self.attestation_count,
            "failure_code": self.failure_code,
        }


@dataclass(frozen=True)
class ProvenanceReport:
    """The metadata-only result of verifying all release artifacts."""

    repository: str
    signer_workflow: str
    source_digest: str
    subjects: tuple[ProvenanceSubject, ...]

    @property
    def passed(self) -> bool:
        return bool(self.subjects) and all(item.verified for item in self.subjects)

    def to_dict(self) -> dict[str, object]:
        return {
            "provenance_version": PROVENANCE_VERSION,
            "passed": self.passed,
            "repository": self.repository,
            "signer_workflow": self.signer_workflow,
            "source_digest": self.source_digest,
            "predicate_type": SLSA_PROVENANCE,
            "verification_tool": "gh attestation verify",
            "subjects": [item.to_dict() for item in self.subjects],
            "subject_count": len(self.subjects),
            "network_used": True,
            "credentials_exported": False,
            "diagnostics": {
                "warnings": [
                    "GitHub CLI verification checks a signed attestation and "
                    "the configured repository, workflow, and source commit.",
                    "This report records verification metadata only; the "
                    "attestation bundle and certificate are not copied here.",
                ],
                "what_it_does_not_show": (
                    "It does not show credentials, prompts, provider output, "
                    "artifact contents, or deployment health."
                ),
            },
        }

    def to_markdown(self) -> str:
        status = "PASS" if self.passed else "BLOCKED"
        lines = [
            "# Release provenance verification",
            "",
            f"- **Decision:** {status}",
            f"- **Repository:** `{self.repository}`",
            f"- **Signer workflow:** `{self.signer_workflow}`",
            f"- **Source commit:** `{self.source_digest}`",
            "- **Predicate:** `https://slsa.dev/provenance/v1`",
            "- **Network:** GitHub attestation verification only",
            "",
            "## Subjects",
            "",
            "| Artifact | SHA-256 | Result | Attestations |",
            "| --- | --- | --- | --- |",
        ]
        lines.extend(
            f"| `{item.name}` | `{item.sha256}` | "
            f"{'VERIFIED' if item.verified else 'BLOCKED'} | "
            f"{item.attestation_count} |"
            for item in self.subjects
        )
        lines.extend(
            [
                "",
                "The report excludes attestation bundles, certificates, "
                "credentials, and artifact contents.",
                "",
            ]
        )
        return "\n".join(lines)


def run_provenance_verification(
    artifact_directory: Path,
    *,
    repository: str,
    signer_workflow: str,
    source_digest: str,
) -> ProvenanceReport:
    """Verify each release artifact with the GitHub CLI."""

    repository = _identifier(repository, "repository")
    signer_workflow = _identifier(signer_workflow, "signer_workflow")
    source_digest = _commit(source_digest)
    artifacts = sorted(
        path
        for path in artifact_directory.iterdir()
        if path.is_file() and path.suffix in {".whl", ".gz"}
    )
    if not artifacts:
        raise ValueError("No release artifacts were found.")
    subjects = tuple(
        _verify_subject(
            artifact,
            repository=repository,
            signer_workflow=signer_workflow,
            source_digest=source_digest,
        )
        for artifact in artifacts
    )
    return ProvenanceReport(
        repository=repository,
        signer_workflow=signer_workflow,
        source_digest=source_digest,
        subjects=subjects,
    )


def _verify_subject(
    artifact: Path,
    *,
    repository: str,
    signer_workflow: str,
    source_digest: str,
) -> ProvenanceSubject:
    digest = _file_sha256(artifact)
    command = [
        "gh",
        "attestation",
        "verify",
        str(artifact),
        "--repo",
        repository,
        "--signer-workflow",
        signer_workflow,
        "--source-digest",
        source_digest,
        "--format",
        "json",
    ]
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        attestation_count, predicate_ok, digest_ok = _verification_observations(
            payload,
            digest,
        )
        if not attestation_count:
            failure_code = "attestation_missing"
        elif not predicate_ok:
            failure_code = "predicate_mismatch"
        elif not digest_ok:
            failure_code = "subject_digest_mismatch"
        else:
            failure_code = None
        return ProvenanceSubject(
            name=artifact.name,
            sha256=digest,
            verified=failure_code is None,
            attestation_count=attestation_count,
            failure_code=failure_code,
        )
    except FileNotFoundError:
        failure_code = "github_cli_unavailable"
    except (OSError, subprocess.SubprocessError):
        failure_code = "attestation_verification_failed"
    except (TypeError, ValueError, json.JSONDecodeError):
        failure_code = "verification_output_invalid"
    return ProvenanceSubject(
        name=artifact.name,
        sha256=digest,
        verified=False,
        attestation_count=0,
        failure_code=failure_code,
    )


def _verification_observations(
    payload: object,
    expected_digest: str,
) -> tuple[int, bool, bool]:
    if not isinstance(payload, list):
        raise ValueError("Verification output must be a JSON array.")
    predicate_ok = False
    digest_ok = False
    attestation_count = 0
    for item in payload:
        if not isinstance(item, dict):
            continue
        verification = item.get("verificationResult")
        if not isinstance(verification, dict):
            continue
        statement = verification.get("statement")
        if not isinstance(statement, dict):
            continue
        attestation_count += 1
        predicate_ok = predicate_ok or (
            statement.get("predicateType") == SLSA_PROVENANCE
        )
        subjects = statement.get("subject")
        if not isinstance(subjects, list):
            continue
        for subject in subjects:
            if not isinstance(subject, dict):
                continue
            digest = subject.get("digest")
            if isinstance(digest, dict) and digest.get("sha256") == expected_digest:
                digest_ok = True
    return attestation_count, predicate_ok, digest_ok


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
