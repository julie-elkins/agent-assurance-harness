"""Strict metadata-only import for external evaluator results.

Design rules:

1. The adapter accepts bounded case labels and measurements, not prompts, transcripts,
   tool payloads, model output, credentials, or provider traces.
2. Inspect- and Petri-shaped results use the same internal monitorability contract;
   source-system identity is provenance, not a second scoring rule.
3. A result bound to the wrong manifest revision or harness revision is blocked before
   it can support a safety case.
4. A current result remains review-required when the current revision map changes; the
   adapter must not silently treat an old external result as current.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .change_impact import revisions_digest
from .monitorability import (
    MONITORABILITY_BLOCKED,
    MONITORABILITY_READY,
    MonitorabilityFixture,
    MonitorabilityInputError,
    MonitorabilityReport,
    TrajectoryCase,
    build_monitorability_report,
)
from .run_manifest import RunManifest, load_current_revisions, load_manifest
from .safety_case import SafetyCase, build_safety_case


EXTERNAL_EVALUATOR_VERSION = 1
EXTERNAL_IMPORT_ACCEPTED = "accepted"
EXTERNAL_IMPORT_REVIEW = "review_required"
EXTERNAL_IMPORT_BLOCKED = "blocked"
SUPPORTED_SOURCE_SYSTEMS = frozenset({"inspect", "petri", "local"})


@dataclass(frozen=True)
class ExternalEvaluatorResult:
    """A validated external evaluator result with no content-bearing fields."""

    source_system: str
    source_result_id: str
    harness_revision: str
    revision_digest: str
    fixture: MonitorabilityFixture

    def to_dict(self) -> dict[str, object]:
        return {
            "external_evaluator_version": EXTERNAL_EVALUATOR_VERSION,
            "source_system": self.source_system,
            "source_result_id": self.source_result_id,
            "harness_revision": self.harness_revision,
            "revision_digest": self.revision_digest,
            "scenario_pack_id": self.fixture.scenario_pack_id,
            "monitor_id": self.fixture.monitor_id,
            "evaluator_id": self.fixture.evaluator_id,
            "cases": [case.to_dict() for case in self.fixture.cases],
        }


@dataclass(frozen=True)
class ExternalEvaluatorImportReport:
    """The bounded result of importing and evaluating one external result."""

    source_system: str
    source_result_id: str
    import_status: str
    reasons: tuple[str, ...]
    revision_digest: str
    expected_revision_digest: str
    monitorability_report: MonitorabilityReport | None
    safety_case: SafetyCase | None

    def to_dict(self) -> dict[str, object]:
        return {
            "external_evaluator_version": EXTERNAL_EVALUATOR_VERSION,
            "source_system": self.source_system,
            "source_result_id": self.source_result_id,
            "import_status": self.import_status,
            "reasons": list(self.reasons),
            "revision_digest": self.revision_digest,
            "expected_revision_digest": self.expected_revision_digest,
            "monitorability_report": (
                self.monitorability_report.to_dict()
                if self.monitorability_report is not None
                else None
            ),
            "safety_case": (
                self.safety_case.to_dict()
                if self.safety_case is not None
                else None
            ),
            "limitations": [
                "The imported result contains bounded metadata only.",
                "Source-system provenance does not prove source evaluator quality.",
                "The safety case remains a human-review input, not deployment approval.",
            ],
        }

    def to_markdown(self) -> str:
        """Return a reviewer-facing import summary without raw evidence."""

        return "\n".join(
            [
                "## External evaluator import",
                "",
                f"- **Source:** `{self.source_system}`",
                f"- **Result:** `{self.source_result_id}`",
                f"- **Import:** `{self.import_status}`",
                f"- **Reasons:** {', '.join(self.reasons) or 'none'}",
                f"- **Revision binding:** `{self.revision_digest}`",
                f"- **Expected revision:** `{self.expected_revision_digest}`",
                "",
                "The adapter imported labels, counts, statuses, and revision metadata "
                "only. It did not import prompts, transcripts, tool payloads, model "
                "output, credentials, or private traces.",
                "",
            ]
        )


def _identifier(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MonitorabilityInputError(f"{field} must be a non-empty identifier")
    if any(character.isspace() for character in value):
        raise MonitorabilityInputError(f"{field} must not contain whitespace")
    return value


def _digest(value: object, field: str) -> str:
    result = _identifier(value, field)
    if len(result) != 71 or not result.startswith("sha256:"):
        raise MonitorabilityInputError(
            f"{field} must match sha256:<64 lowercase hex characters>"
        )
    if any(character not in "0123456789abcdef" for character in result[7:]):
        raise MonitorabilityInputError(
            f"{field} must match sha256:<64 lowercase hex characters>"
        )
    return result


def load_external_evaluator_result(
    path: str | Path,
) -> ExternalEvaluatorResult:
    """Load and validate an Inspect-, Petri-, or local-shaped result."""

    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise MonitorabilityInputError("external evaluator result must be an object")
    allowed = {
        "external_evaluator_version",
        "source_system",
        "source_result_id",
        "harness_revision",
        "revision_digest",
        "scenario_pack_id",
        "monitor_id",
        "evaluator_id",
        "cases",
    }
    extra = sorted(set(value) - allowed)
    if extra:
        raise MonitorabilityInputError(
            "external evaluator result contains unsupported fields: "
            + ", ".join(extra)
        )
    if value.get("external_evaluator_version") != EXTERNAL_EVALUATOR_VERSION:
        raise MonitorabilityInputError(
            f"external_evaluator_version must be {EXTERNAL_EVALUATOR_VERSION}"
        )
    source_system = _identifier(value.get("source_system"), "source_system")
    if source_system not in SUPPORTED_SOURCE_SYSTEMS:
        raise MonitorabilityInputError(
            "source_system must be inspect, petri, or local"
        )
    raw_cases = value.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise MonitorabilityInputError("external evaluator cases must be non-empty")
    cases = tuple(
        TrajectoryCase.from_dict(item, index)
        for index, item in enumerate(raw_cases)
    )
    case_ids = [case.case_id for case in cases]
    if len(set(case_ids)) != len(case_ids):
        raise MonitorabilityInputError("external evaluator case IDs must be unique")
    fixture = MonitorabilityFixture(
        scenario_pack_id=_identifier(
            value.get("scenario_pack_id"), "scenario_pack_id"
        ),
        monitor_id=_identifier(value.get("monitor_id"), "monitor_id"),
        evaluator_id=_identifier(value.get("evaluator_id"), "evaluator_id"),
        cases=cases,
    )
    return ExternalEvaluatorResult(
        source_system=source_system,
        source_result_id=_identifier(
            value.get("source_result_id"), "source_result_id"
        ),
        harness_revision=_identifier(
            value.get("harness_revision"), "harness_revision"
        ),
        revision_digest=_digest(value.get("revision_digest"), "revision_digest"),
        fixture=fixture,
    )


def import_external_evaluator_result(
    result: ExternalEvaluatorResult,
    manifest: RunManifest,
    current_revisions: Mapping[str, str],
) -> ExternalEvaluatorImportReport:
    """Validate source binding, then reuse the canonical monitorability evaluator."""

    expected_digest = revisions_digest(manifest.revisions)
    reasons: list[str] = []
    if result.revision_digest != expected_digest:
        reasons.append("external_evaluator_revision_mismatch")
    if result.harness_revision != manifest.revisions["harness"]:
        reasons.append("external_evaluator_harness_mismatch")
    if reasons:
        return ExternalEvaluatorImportReport(
            source_system=result.source_system,
            source_result_id=result.source_result_id,
            import_status=EXTERNAL_IMPORT_BLOCKED,
            reasons=tuple(reasons),
            revision_digest=result.revision_digest,
            expected_revision_digest=expected_digest,
            monitorability_report=None,
            safety_case=None,
        )
    report = build_monitorability_report(
        result.fixture,
        manifest,
        current_revisions,
    )
    import_status = (
        EXTERNAL_IMPORT_ACCEPTED
        if report.status == MONITORABILITY_READY
        else EXTERNAL_IMPORT_REVIEW
        if report.status != MONITORABILITY_BLOCKED
        else EXTERNAL_IMPORT_BLOCKED
    )
    safety_case = build_safety_case(
        report,
        decision_target=manifest.decision_target,
    )
    return ExternalEvaluatorImportReport(
        source_system=result.source_system,
        source_result_id=result.source_result_id,
        import_status=import_status,
        reasons=report.reasons,
        revision_digest=result.revision_digest,
        expected_revision_digest=expected_digest,
        monitorability_report=report,
        safety_case=safety_case,
    )


def import_external_evaluator_files(
    result_path: str | Path,
    manifest_path: str | Path,
    current_revisions_path: str | Path,
) -> ExternalEvaluatorImportReport:
    """Load the three bounded inputs used by the CLI."""

    result = load_external_evaluator_result(result_path)
    manifest = load_manifest(str(manifest_path))
    current_revisions = load_current_revisions(str(current_revisions_path))
    return import_external_evaluator_result(result, manifest, current_revisions)


__all__ = [
    "EXTERNAL_EVALUATOR_VERSION",
    "EXTERNAL_IMPORT_ACCEPTED",
    "EXTERNAL_IMPORT_BLOCKED",
    "EXTERNAL_IMPORT_REVIEW",
    "SUPPORTED_SOURCE_SYSTEMS",
    "ExternalEvaluatorImportReport",
    "ExternalEvaluatorResult",
    "import_external_evaluator_files",
    "import_external_evaluator_result",
    "load_external_evaluator_result",
]
