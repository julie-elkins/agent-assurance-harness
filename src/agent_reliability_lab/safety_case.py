"""Metadata-only safety-case packaging for monitorability results.

Design rules:

1. A safety case states a bounded claim and its limitations; it never becomes
   deployment approval automatically.
2. The case includes the monitorability report and reauthorization state rather than
   repeating or weakening either decision.
3. Signed attestations remain future work; the current case is a digestable report,
   not a cryptographic producer statement.
"""

from __future__ import annotations

from dataclasses import dataclass

from .monitorability import (
    MONITORABILITY_BLOCKED,
    MONITORABILITY_READY,
    MonitorabilityReport,
)


SAFETY_CASE_VERSION = 1
SAFETY_CASE_READY = "supports_human_review"
SAFETY_CASE_REVIEW = "review_required"
SAFETY_CASE_BLOCKED = "blocked"


@dataclass(frozen=True)
class SafetyCase:
    """A bounded claim supported by one monitorability report."""

    case_id: str
    claim_id: str
    decision_target: str
    status: str
    report_id: str
    report_status: str
    reauthorization_status: str
    evidence_scope: str
    limitations: tuple[str, ...]
    required_human_review: bool
    monitorability_report: MonitorabilityReport

    def to_dict(self) -> dict[str, object]:
        return {
            "safety_case_version": SAFETY_CASE_VERSION,
            "case_id": self.case_id,
            "claim_id": self.claim_id,
            "decision_target": self.decision_target,
            "status": self.status,
            "report_id": self.report_id,
            "report_status": self.report_status,
            "reauthorization_status": self.reauthorization_status,
            "evidence_scope": self.evidence_scope,
            "limitations": list(self.limitations),
            "required_human_review": self.required_human_review,
            "monitorability_report": self.monitorability_report.to_dict(),
        }

    def to_markdown(self) -> str:
        """Return a reviewer-facing summary without raw case content."""

        limitations = "\n".join(f"- {item}" for item in self.limitations)
        return "\n".join(
            [
                "# Synthetic agent safety case",
                "",
                f"- **Status:** `{self.status}`",
                f"- **Claim:** `{self.claim_id}`",
                f"- **Decision target:** `{self.decision_target}`",
                f"- **Monitorability report:** `{self.report_id}`",
                f"- **Report status:** `{self.report_status}`",
                f"- **Reauthorization:** `{self.reauthorization_status}`",
                f"- **Human review required:** `{self.required_human_review}`",
                "",
                "**Scope**",
                "",
                self.evidence_scope,
                "",
                "**Limitations**",
                "",
                limitations,
                "",
                "This is synthetic metadata for human review; it is not a signed "
                "attestation, deployment approval, or proof of live model safety.",
                "",
            ]
        )


def build_safety_case(
    report: MonitorabilityReport,
    *,
    decision_target: str,
    claim_id: str = "monitor-and-evaluator-controls-support-review",
) -> SafetyCase:
    """Package one monitorability report without changing its decisions."""

    if report.status == MONITORABILITY_BLOCKED:
        status = SAFETY_CASE_BLOCKED
    elif report.status == MONITORABILITY_READY:
        status = SAFETY_CASE_READY
    else:
        status = SAFETY_CASE_REVIEW
    return SafetyCase(
        case_id=f"safety-case:{report.report_id.removeprefix('monitorability:')}",
        claim_id=claim_id,
        decision_target=decision_target,
        status=status,
        report_id=report.report_id,
        report_status=report.status,
        reauthorization_status=report.reauthorization.status,
        evidence_scope=(
            "Synthetic monitor and evaluator labels across calibration, held-out, "
            "benign-control, and evaluation-awareness cases."
        ),
        limitations=report.limitations,
        required_human_review=True,
        monitorability_report=report,
    )


__all__ = [
    "SAFETY_CASE_BLOCKED",
    "SAFETY_CASE_READY",
    "SAFETY_CASE_REVIEW",
    "SAFETY_CASE_VERSION",
    "SafetyCase",
    "build_safety_case",
]
