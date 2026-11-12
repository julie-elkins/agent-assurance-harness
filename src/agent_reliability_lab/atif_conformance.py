"""ATIF evidence conformance over identifier-only trajectory summaries.

Design rules:

1. Accept only bounded identifiers, counts, statuses, and digests.
2. Refuse raw-content fields without echoing their values.
3. Keep trajectory evidence completeness separate from task correctness.
4. Return a metadata-only refusal report instead of raising at the trust boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping


ATIF_CONFORMANCE_VERSION = 1
SUPPORTED_ATIF_SCHEMA_VERSIONS = frozenset({"ATIF-v1.2", "ATIF-v1.5"})
METADATA_ONLY_REDACTION_POLICY = "metadata-only-v1"

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_REQUIRED_FIELDS = frozenset(
    {
        "source_id",
        "run_id",
        "schema_version",
        "trajectory_digest",
        "step_count",
        "tool_call_count",
        "terminal_status",
        "artifact_status",
        "artifact_count",
        "redaction_policy",
        "event_linkage_status",
    }
)
_OPTIONAL_FIELDS = frozenset({"semantic_outcome"})
_FORBIDDEN_FIELDS = frozenset(
    {
        "content",
        "output",
        "prompt",
        "provider_request",
        "provider_response",
        "raw_trajectory",
        "tool_arguments",
        "tool_result",
        "trace",
    }
)
_TERMINAL_STATUSES = frozenset(
    {"completed", "failed", "refused", "timed_out", "missing"}
)
_ARTIFACT_STATUSES = frozenset({"observed", "missing", "invalid"})
_LINKAGE_STATUSES = frozenset({"complete", "partial", "missing"})


@dataclass(frozen=True)
class AtifEvidenceSummary:
    """The public, bounded projection of one local trajectory result."""

    source_id: str
    run_id: str
    schema_version: str
    trajectory_digest: str | None
    step_count: int
    tool_call_count: int
    terminal_status: str
    artifact_status: str
    artifact_count: int
    redaction_policy: str
    event_linkage_status: str
    semantic_outcome: str | None = None


@dataclass(frozen=True)
class AtifConformanceCheck:
    """One metadata-only check result."""

    check_id: str
    status: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AtifEvidenceConformanceReport:
    """A bounded result for the ATIF evidence contract."""

    source_id: str
    run_id: str
    schema_version: str
    status: str
    passed: bool
    checks: tuple[AtifConformanceCheck, ...]
    refusal_code: str | None
    semantic_outcome_observed: bool

    @property
    def conformance_passed(self) -> bool:
        """Return whether every evidence check completed successfully."""

        return self.status == "accepted" and self.passed

    def to_dict(self) -> dict[str, object]:
        """Return identifiers, counts, statuses, and no trajectory content."""

        return {
            "report_version": ATIF_CONFORMANCE_VERSION,
            "conformance_id": "atif-evidence-conformance-v1",
            "source_id": self.source_id,
            "run_id": self.run_id,
            "schema_version": self.schema_version,
            "status": self.status,
            "passed": self.passed,
            "conformance_passed": self.conformance_passed,
            "refusal_code": self.refusal_code,
            "semantic_outcome_observed": self.semantic_outcome_observed,
            "checks": [check.to_dict() for check in self.checks],
            "diagnostics": {
                "network": "disabled",
                "data_boundary": "metadata_only",
                "task_correctness": "separate",
                "what_it_does_not_show": (
                    "It does not show prompts, tool arguments, tool results, "
                    "provider responses, hidden reasoning, model quality, or safety."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Render a reviewer-facing summary without raw evidence."""

        decision = "PASS" if self.conformance_passed else "BLOCKED"
        lines = [
            "# ATIF evidence conformance",
            "",
            f"- **Decision:** {decision}",
            f"- **Source:** `{self.source_id}`",
            f"- **Run:** `{self.run_id}`",
            f"- **Schema:** `{self.schema_version}`",
            "- **Content boundary:** metadata only",
            "- **Task correctness:** evaluated separately",
            "",
            "| Check | Status | Reason |",
            "| --- | --- | --- |",
        ]
        lines.extend(
            f"| `{check.check_id}` | `{check.status}` | {check.reason} |"
            for check in self.checks
        )
        lines.extend(
            [
                "",
                "This report validates evidence completeness and privacy boundaries. "
                "It does not establish task correctness or model quality.",
                "",
            ]
        )
        return "\n".join(lines)


def run_atif_conformance(value: object) -> AtifEvidenceConformanceReport:
    """Validate one identifier-only ATIF evidence summary."""

    if not isinstance(value, Mapping):
        return _refusal("summary_not_object")

    keys = set(value)
    if keys & _FORBIDDEN_FIELDS:
        return _refusal("raw_content_refused")
    if keys != _REQUIRED_FIELDS | (keys & _OPTIONAL_FIELDS):
        return _refusal("unsupported_or_missing_fields")

    summary, refusal_code = _parse_summary(value)
    if summary is None:
        return _refusal(refusal_code or "invalid_summary")

    checks = (
        _check_schema(summary),
        _check_artifact(summary),
        _check_event_linkage(summary),
        _check_terminal_consistency(summary),
        _check_privacy(summary),
    )
    failures = tuple(check for check in checks if check.status != "completed")
    return AtifEvidenceConformanceReport(
        source_id=summary.source_id,
        run_id=summary.run_id,
        schema_version=summary.schema_version,
        status="accepted" if not failures else "refused",
        passed=not failures,
        checks=checks,
        refusal_code=failures[0].reason if failures else None,
        semantic_outcome_observed=summary.semantic_outcome is not None,
    )


def _parse_summary(
    value: Mapping[object, object],
) -> tuple[AtifEvidenceSummary | None, str | None]:
    """Parse without returning caller-supplied content in a refusal."""

    try:
        source_id = _identifier(value["source_id"])
        run_id = _identifier(value["run_id"])
        schema_version = _identifier(value["schema_version"])
        trajectory_digest = _optional_digest(value["trajectory_digest"])
        step_count = _non_negative_int(value["step_count"])
        tool_call_count = _non_negative_int(value["tool_call_count"])
        terminal_status = _enum(value["terminal_status"], _TERMINAL_STATUSES)
        artifact_status = _enum(value["artifact_status"], _ARTIFACT_STATUSES)
        artifact_count = _non_negative_int(value["artifact_count"])
        redaction_policy = _identifier(value["redaction_policy"])
        event_linkage_status = _enum(
            value["event_linkage_status"], _LINKAGE_STATUSES
        )
        semantic_outcome = _optional_identifier(value.get("semantic_outcome"))
    except (KeyError, TypeError, ValueError):
        return None, "invalid_summary"
    return (
        AtifEvidenceSummary(
            source_id=source_id,
            run_id=run_id,
            schema_version=schema_version,
            trajectory_digest=trajectory_digest,
            step_count=step_count,
            tool_call_count=tool_call_count,
            terminal_status=terminal_status,
            artifact_status=artifact_status,
            artifact_count=artifact_count,
            redaction_policy=redaction_policy,
            event_linkage_status=event_linkage_status,
            semantic_outcome=semantic_outcome,
        ),
        None,
    )


def _check_schema(summary: AtifEvidenceSummary) -> AtifConformanceCheck:
    if summary.schema_version not in SUPPORTED_ATIF_SCHEMA_VERSIONS:
        return _blocked("schema_version_unsupported")
    return _completed("schema_supported")


def _check_artifact(summary: AtifEvidenceSummary) -> AtifConformanceCheck:
    if summary.artifact_status != "observed":
        return _blocked("trajectory_artifact_not_observed")
    if summary.artifact_count < 1:
        return _blocked("trajectory_artifact_count_invalid")
    if summary.step_count < 1:
        return _blocked("trajectory_step_count_invalid")
    if summary.trajectory_digest is None:
        return _blocked("trajectory_digest_missing")
    return _completed("trajectory_artifact_observed")


def _check_event_linkage(summary: AtifEvidenceSummary) -> AtifConformanceCheck:
    if summary.tool_call_count > 0 and summary.event_linkage_status != "complete":
        return _blocked("event_linkage_incomplete")
    return _completed("event_linkage_sufficient")


def _check_terminal_consistency(
    summary: AtifEvidenceSummary,
) -> AtifConformanceCheck:
    if (
        summary.terminal_status == "completed"
        and summary.artifact_status != "observed"
    ):
        return _blocked("completed_without_observed_artifact")
    return _completed("terminal_status_consistent")


def _check_privacy(summary: AtifEvidenceSummary) -> AtifConformanceCheck:
    if summary.redaction_policy != METADATA_ONLY_REDACTION_POLICY:
        return _blocked("redaction_policy_unsupported")
    return _completed("metadata_only_boundary")


def _refusal(code: str) -> AtifEvidenceConformanceReport:
    return AtifEvidenceConformanceReport(
        source_id="unavailable",
        run_id="unavailable",
        schema_version="unavailable",
        status="refused",
        passed=False,
        checks=(_blocked(code, check_id="input_boundary"),),
        refusal_code=code,
        semantic_outcome_observed=False,
    )


def _completed(check_id: str) -> AtifConformanceCheck:
    return AtifConformanceCheck(check_id, "completed", "completed")


def _blocked(
    reason: str,
    *,
    check_id: str = "evidence_boundary",
) -> AtifConformanceCheck:
    return AtifConformanceCheck(check_id, "refused", reason)


def _identifier(value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError
    return value


def _optional_identifier(value: object) -> str | None:
    if value is None:
        return None
    return _identifier(value)


def _optional_digest(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError
    return value


def _non_negative_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError
    return value


def _enum(value: object, allowed: frozenset[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError
    return value
