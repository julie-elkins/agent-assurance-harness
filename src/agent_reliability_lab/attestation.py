"""Metadata-only assurance attestations for reproducible local evaluations.

Design rules:

1. An attestation records evaluation identity and counts, never traces, prompts,
   commands, credentials, or provider output.
2. Pack identity comes from the canonical validated pack definitions and their
   sorted set hash, not from a caller path.
3. A hash-based attestation identifies what was checked; it is not a signed
   provenance statement and does not establish live-provider quality.
4. Refusals remain visible as failed attestations rather than being presented as
   a clean or incomplete success.
"""

from __future__ import annotations

from dataclasses import dataclass

from .packs import ScenarioPack
from .pack_provenance import pack_manifest, pack_set_sha256
from .regression import RegressionReport


ATTESTATION_VERSION = 1
ATTESTATION_ID = "adapter-regression-attestation-v1"


@dataclass(frozen=True)
class AssuranceAttestation:
    """Identifier-only evidence of one regression evaluation state."""

    package: str
    package_version: str
    git_commit: str
    pack_set_sha256: str
    pack_manifests: tuple[dict[str, object], ...]
    baseline_harness_change: dict[str, object] | None
    candidate_harness_change: dict[str, object] | None
    scenario_count: int
    passed: bool
    blocking_finding_count: int
    observation_count: int
    refusal_code: str | None
    attestation_version: int = ATTESTATION_VERSION
    attestation_id: str = ATTESTATION_ID

    def to_dict(self) -> dict[str, object]:
        """Return metadata without evaluation content."""

        return {
            "attestation_version": self.attestation_version,
            "attestation_id": self.attestation_id,
            "package": self.package,
            "package_version": self.package_version,
            "git_commit": self.git_commit,
            "pack_set_sha256": self.pack_set_sha256,
            "pack_manifests": [dict(manifest) for manifest in self.pack_manifests],
            "baseline_harness_change": (
                dict(self.baseline_harness_change)
                if self.baseline_harness_change is not None
                else None
            ),
            "candidate_harness_change": (
                dict(self.candidate_harness_change)
                if self.candidate_harness_change is not None
                else None
            ),
            "scenario_count": self.scenario_count,
            "passed": self.passed,
            "blocking_finding_count": self.blocking_finding_count,
            "observation_count": self.observation_count,
            "refusal_code": self.refusal_code,
            "diagnostics": {
                "warnings": [
                    "This is a hash-based metadata attestation, not a cryptographic signature.",
                    "The attestation identifies the evaluated synthetic state; it does not establish live-provider quality or causality.",
                ],
                "what_it_does_not_show": (
                    "It does not contain traces, prompts, commands, credentials, "
                    "tool payloads, provider output, or raw finding messages."
                ),
            },
        }


def build_regression_attestation(
    report: RegressionReport,
    packs: tuple[ScenarioPack, ...],
    *,
    package_version: str,
    git_commit: str,
) -> AssuranceAttestation:
    """Build a reproducibility record from one regression report and pack set."""

    if not package_version:
        raise ValueError("package_version must be non-empty.")
    if not git_commit:
        raise ValueError("git_commit must be non-empty.")
    if not packs:
        raise ValueError("At least one scenario pack is required.")

    return AssuranceAttestation(
        package="agent-reliability-lab",
        package_version=package_version,
        git_commit=git_commit,
        pack_set_sha256=pack_set_sha256(packs),
        pack_manifests=tuple(
            pack_manifest(pack).to_dict()
            for pack in sorted(packs, key=lambda item: item.scenario_id)
        ),
        baseline_harness_change=(
            report.baseline_change.to_dict()
            if report.baseline_change is not None
            else None
        ),
        candidate_harness_change=(
            report.candidate_change.to_dict()
            if report.candidate_change is not None
            else None
        ),
        scenario_count=report.expected_scenario_count,
        passed=not report.failed,
        blocking_finding_count=sum(
            finding.blocking for finding in report.findings
        ),
        observation_count=sum(
            not finding.blocking for finding in report.findings
        ),
        refusal_code=report.refusal.error if report.refusal is not None else None,
    )


__all__ = [
    "ATTESTATION_ID",
    "ATTESTATION_VERSION",
    "AssuranceAttestation",
    "build_regression_attestation",
]
