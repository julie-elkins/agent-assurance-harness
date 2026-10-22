"""Metadata-only review packets for public-course evidence findings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from .claude_course_adapter import (
    ClaimVerificationState,
    ClaudeCourseVerificationReport,
)


PUBLIC_COURSE_REVIEW_PACKET_VERSION = 1
DEFAULT_MAX_FINDINGS = 100


class ReviewPriority(str, Enum):
    """The review queue priority implied by an evidence state."""

    BLOCKING = "blocking"
    REVIEW = "review"
    COVERAGE_GAP = "coverage_gap"


class HumanDisposition(str, Enum):
    """The only initial human-work states emitted by this packet."""

    OPEN = "open"
    RESOLVED = "resolved"
    DEFERRED = "deferred"
    ACCEPTED = "accepted"


@dataclass(frozen=True)
class PublicCourseReviewFinding:
    """One safe, actionable location in a public-course review queue."""

    finding_id: str
    lesson_id: str
    claim_index: int
    evidence_tier: str
    state: ClaimVerificationState
    reason_code: str
    source_url: str | None
    source_read_date: str | None
    priority: ReviewPriority
    recommended_action: str
    disposition: HumanDisposition = HumanDisposition.OPEN

    def to_dict(self) -> dict[str, object]:
        """Return a safe finding without claim or source text."""

        return {
            "finding_id": self.finding_id,
            "lesson_id": self.lesson_id,
            "claim_index": self.claim_index,
            "evidence_tier": self.evidence_tier,
            "state": self.state.value,
            "reason_code": self.reason_code,
            "source_url": self.source_url,
            "source_read_date": self.source_read_date,
            "priority": self.priority.value,
            "recommended_action": self.recommended_action,
            "disposition": self.disposition.value,
            "what_it_does_not_show": (
                "This finding does not reproduce course text, a source quote, "
                "or prove that the lesson is technically incorrect."
            ),
        }


@dataclass(frozen=True)
class PublicCourseReviewPacket:
    """A bounded human review worklist for one course revision."""

    course_id: str
    course_revision: str | None
    adapter_decision: str
    counts: dict[str, int | bool]
    findings: tuple[PublicCourseReviewFinding, ...]
    total_known_findings: int
    total_unverified_rows: int
    max_findings: int
    truncated: bool
    refusal_code: str | None = None
    human_approval_required: bool = True

    @property
    def decision(self) -> str:
        """Return the safe human handoff state."""

        if self.refusal_code is not None:
            return "blocked"
        if self.adapter_decision == "verified" and not self.findings:
            return "ready_for_human_review"
        return "review_required"

    @property
    def passed(self) -> bool:
        """Return true only when no public-course review signal remains."""

        return self.decision == "ready_for_human_review"

    @property
    def open_count(self) -> int:
        """Return the number of findings still awaiting human disposition."""

        return sum(
            finding.disposition is HumanDisposition.OPEN
            for finding in self.findings
        )

    def to_dict(self) -> dict[str, object]:
        """Return the complete metadata-only packet."""

        return {
            "public_course_review_packet_version": (
                PUBLIC_COURSE_REVIEW_PACKET_VERSION
            ),
            "course_id": self.course_id,
            "course_revision": self.course_revision,
            "adapter_decision": self.adapter_decision,
            "decision": self.decision,
            "passed": self.passed,
            "counts": self.counts,
            "total_known_findings": self.total_known_findings,
            "total_unverified_rows": self.total_unverified_rows,
            "findings": [finding.to_dict() for finding in self.findings],
            "open_count": self.open_count,
            "max_findings": self.max_findings,
            "truncated": self.truncated,
            "refusal_code": self.refusal_code,
            "human_approval_required": self.human_approval_required,
            "diagnostics": {
                "warnings": [
                    "This packet contains identifiers, states, dates, URLs, and actions only.",
                    "Initial dispositions are open and require human adjudication.",
                ],
                "what_it_does_not_show": (
                    "It does not prove course correctness, learner outcomes, "
                    "or authorization to edit or publish course content."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Render a reviewer-friendly worklist without course text."""

        lines = [
            "# Public Course Review Packet",
            "",
            f"Decision: `{self.decision}`",
            "",
            f"- Course: `{self.course_id}`",
            f"- Revision: `{self.course_revision or 'unavailable'}`",
            f"- Adapter decision: `{self.adapter_decision}`",
            f"- Rows requiring review: `{self.total_known_findings}`",
            f"- Rows not proven by the strongest check: `{self.total_unverified_rows}`",
            f"- Open findings in this packet: `{self.open_count}`",
            "",
            "| Lesson | Claim | Evidence tier | State | Priority | Action |",
            "| --- | ---: | --- | --- | --- | --- |",
        ]
        if self.refusal_code is not None:
            lines.insert(
                7,
                f"- Refusal: `{self.refusal_code}`",
            )
        for finding in self.findings:
            lines.append(
                f"| `{finding.lesson_id}` | `{finding.claim_index}` | "
                f"`{finding.evidence_tier}` | `{finding.state.value}` | "
                f"`{finding.priority.value}` | `{finding.recommended_action}` |"
            )
        lines.extend(
            [
                "",
                "Every finding starts with disposition `open`.",
                "A human must review the source and decide whether to resolve, "
                "defer, or accept the finding before any content change.",
                "",
                "This packet contains safe locations and evidence states only; "
                "it does not reproduce course claims or source quotations.",
                "",
            ]
        )
        return "\n".join(lines)


def build_public_course_review_packet(
    report: ClaudeCourseVerificationReport,
    *,
    max_findings: int = DEFAULT_MAX_FINDINGS,
) -> PublicCourseReviewPacket:
    """Convert adapter findings into a bounded human worklist."""

    if max_findings <= 0:
        raise ValueError("max_findings must be positive")
    findings = tuple(
        _finding_from_result(report.course_id, result)
        for result in report.known_findings[:max_findings]
    )
    total_unverified = sum(
        result.state is not ClaimVerificationState.VERBATIM_VERIFIED
        for result in report.results
    )
    return PublicCourseReviewPacket(
        course_id=report.course_id,
        course_revision=report.course_revision,
        adapter_decision=report.decision,
        counts=report.counts,
        findings=findings,
        total_known_findings=len(report.known_findings),
        total_unverified_rows=total_unverified,
        max_findings=max_findings,
        truncated=len(report.known_findings) > max_findings,
        refusal_code=report.refusal_code,
    )


def _finding_from_result(
    course_id: str,
    result: object,
) -> PublicCourseReviewFinding:
    """Map one adapter result to a stable review action."""

    state = result.state
    priority, action = _review_action(state)
    return PublicCourseReviewFinding(
        finding_id=f"{course_id}:{result.row_id}",
        lesson_id=result.locator.lesson_id,
        claim_index=result.locator.claim_index,
        evidence_tier=result.locator.tier,
        state=state,
        reason_code=result.reason_code,
        source_url=result.locator.source_url,
        source_read_date=result.locator.source_read_date,
        priority=priority,
        recommended_action=action,
    )


def _review_action(
    state: ClaimVerificationState,
) -> tuple[ReviewPriority, str]:
    return {
        ClaimVerificationState.IDENTIFIER_MISSING: (
            ReviewPriority.BLOCKING,
            "verify_identifier_against_current_docs",
        ),
        ClaimVerificationState.UNABLE_TO_CHECK: (
            ReviewPriority.BLOCKING,
            "rerun_bounded_source_check",
        ),
        ClaimVerificationState.VERBATIM_NOT_FOUND: (
            ReviewPriority.REVIEW,
            "inspect_source_alignment",
        ),
        ClaimVerificationState.UNCOVERED: (
            ReviewPriority.COVERAGE_GAP,
            "add_claim_evidence_contract",
        ),
    }.get(
        state,
        (ReviewPriority.REVIEW, "human_review_required"),
    )


def packet_json(packet: PublicCourseReviewPacket) -> str:
    """Serialize a packet for a local file or caller."""

    return json.dumps(packet.to_dict(), indent=2, sort_keys=True) + "\n"
