"""Create a metadata-only change plan after public-course adjudication.

Design rules:

1. A plan must match both the packet digest and the adjudication's course
   revision before it can be created.
2. Open, deferred, blocked, truncated, or evidence-incomplete reviews cannot
   become a proposed change plan.
3. A plan contains locations, actions, dispositions, and re-checks only; it
   never contains course text, source quotations, or a content diff.
4. The plan stops at human approval. It has no file-writing or publishing
   capability.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping

from .claude_course_adapter import ClaimVerificationState
from .public_course_adjudication import PUBLIC_COURSE_ADJUDICATION_VERSION
from .public_course_review import (
    HumanDisposition,
    PUBLIC_COURSE_REVIEW_PACKET_VERSION,
    PublicCourseReviewFinding,
    ReviewPriority,
)


PUBLIC_COURSE_CHANGE_PLAN_VERSION = 1


@dataclass(frozen=True)
class PublicCourseChangePlanItem:
    """One safe, human-approval-required change-plan item."""

    finding_id: str
    lesson_id: str
    claim_index: int
    state: ClaimVerificationState
    priority: ReviewPriority
    disposition: HumanDisposition
    proposed_action: str
    required_recheck: str
    status: str = "human_approval_required"

    def to_dict(self) -> dict[str, object]:
        """Return a metadata-only plan item."""

        return {
            "finding_id": self.finding_id,
            "lesson_id": self.lesson_id,
            "claim_index": self.claim_index,
            "state": self.state.value,
            "priority": self.priority.value,
            "disposition": self.disposition.value,
            "proposed_action": self.proposed_action,
            "required_recheck": self.required_recheck,
            "status": self.status,
            "what_it_does_not_show": (
                "This item does not reproduce course text or prescribe exact "
                "replacement wording."
            ),
        }


@dataclass(frozen=True)
class PublicCourseChangePlan:
    """A bounded proposal for human-approved course maintenance."""

    course_id: str
    course_revision: str | None
    packet_digest: str | None
    adjudication_decision: str
    course_evidence_decision: str
    items: tuple[PublicCourseChangePlanItem, ...]
    refusal_code: str | None = None
    human_approval_required: bool = True

    @property
    def decision(self) -> str:
        """Return the safe plan state."""

        if self.refusal_code is not None:
            return "blocked"
        if not self.items:
            return "no_change_required"
        return "ready_for_human_approval"

    @property
    def passed(self) -> bool:
        """Return whether the plan reached the approval boundary."""

        return self.decision in {"no_change_required", "ready_for_human_approval"}

    @property
    def next_action(self) -> str:
        """Return the next bounded human action."""

        if self.refusal_code is not None:
            return "correct_change_plan_input"
        if not self.items:
            return "no_content_change_proposed"
        return "human_approval_required_before_content_change"

    @property
    def plan_digest(self) -> str:
        """Return a stable fingerprint of the safe plan metadata."""

        payload = {
            "public_course_change_plan_version": (
                PUBLIC_COURSE_CHANGE_PLAN_VERSION
            ),
            "course_id": self.course_id,
            "course_revision": self.course_revision,
            "packet_digest": self.packet_digest,
            "adjudication_decision": self.adjudication_decision,
            "course_evidence_decision": self.course_evidence_decision,
            "items": [
                {
                    key: value
                    for key, value in item.to_dict().items()
                    if key != "what_it_does_not_show"
                }
                for item in self.items
            ],
            "refusal_code": self.refusal_code,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    def to_dict(self) -> dict[str, object]:
        """Return the complete metadata-only change plan."""

        return {
            "public_course_change_plan_version": (
                PUBLIC_COURSE_CHANGE_PLAN_VERSION
            ),
            "course_id": self.course_id,
            "course_revision": self.course_revision,
            "packet_digest": self.packet_digest,
            "plan_digest": self.plan_digest,
            "adjudication_decision": self.adjudication_decision,
            "course_evidence_decision": self.course_evidence_decision,
            "decision": self.decision,
            "passed": self.passed,
            "next_action": self.next_action,
            "items": [item.to_dict() for item in self.items],
            "refusal_code": self.refusal_code,
            "human_approval_required": self.human_approval_required,
            "diagnostics": {
                "warnings": [
                    "This plan contains safe locations, actions, and re-checks only.",
                    "Human approval remains required before any content change.",
                ],
                "what_it_does_not_show": (
                    "It does not prove course correctness, source truth, learner "
                    "outcomes, or authorise editing or publishing."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Render a reviewer-facing change-plan summary."""

        lines = [
            "# Public Course Change Plan",
            "",
            f"Decision: `{self.decision}`",
            "",
            f"- Course: `{self.course_id}`",
            f"- Revision: `{self.course_revision or 'unavailable'}`",
            f"- Packet digest: `{self.packet_digest or 'unavailable'}`",
            f"- Plan digest: `{self.plan_digest}`",
            f"- Course evidence decision: `{self.course_evidence_decision}`",
            f"- Next action: `{self.next_action}`",
        ]
        if self.refusal_code is not None:
            lines.append(f"- Refusal: `{self.refusal_code}`")
        lines.extend(
            [
                "",
                "| Lesson | Claim | Priority | Disposition | Proposed action | Re-check |",
                "| --- | ---: | --- | --- | --- | --- |",
            ]
        )
        for item in self.items:
            lines.append(
                f"| `{item.lesson_id}` | `{item.claim_index}` | "
                f"`{item.priority.value}` | `{item.disposition.value}` | "
                f"`{item.proposed_action}` | `{item.required_recheck}` |"
            )
        lines.extend(
            [
                "",
                "This is a proposal for human approval, not an automatic edit or publish.",
                "",
            ]
        )
        return "\n".join(lines)


def build_public_course_change_plan(
    packet: Mapping[str, object],
    adjudication: Mapping[str, object],
) -> PublicCourseChangePlan:
    """Create a safe change plan only after complete adjudication."""

    course_id = _safe_text(packet.get("course_id")) or "unavailable"
    course_revision = _optional_text(packet.get("course_revision"))
    packet_digest = _optional_text(packet.get("packet_digest"))
    adjudication_decision = (
        _safe_text(adjudication.get("decision")) or "unavailable"
    )
    course_evidence_decision = (
        _safe_text(adjudication.get("course_evidence_decision")) or "unavailable"
    )

    refusal = _validate_inputs(
        packet=packet,
        adjudication=adjudication,
        course_id=course_id,
        course_revision=course_revision,
        packet_digest=packet_digest,
    )
    if refusal is not None:
        return _blocked_plan(
            course_id=course_id,
            course_revision=course_revision,
            packet_digest=packet_digest,
            adjudication_decision=adjudication_decision,
            course_evidence_decision=course_evidence_decision,
            refusal_code=refusal,
        )

    try:
        findings = _parse_findings(adjudication.get("findings"))
    except ValueError as exc:
        return _blocked_plan(
            course_id=course_id,
            course_revision=course_revision,
            packet_digest=packet_digest,
            adjudication_decision=adjudication_decision,
            course_evidence_decision=course_evidence_decision,
            refusal_code=str(exc),
        )

    if any(
        finding.disposition is HumanDisposition.OPEN for finding in findings
    ):
        refusal = "open_finding_present"
    elif any(
        finding.disposition is HumanDisposition.DEFERRED for finding in findings
    ):
        refusal = "deferred_finding_present"
    elif not findings and course_evidence_decision != "verified":
        refusal = "course_evidence_incomplete"
    if refusal is not None:
        return _blocked_plan(
            course_id=course_id,
            course_revision=course_revision,
            packet_digest=packet_digest,
            adjudication_decision=adjudication_decision,
            course_evidence_decision=course_evidence_decision,
            refusal_code=refusal,
        )

    items = tuple(_plan_item(finding) for finding in findings)
    return PublicCourseChangePlan(
        course_id=course_id,
        course_revision=course_revision,
        packet_digest=packet_digest,
        adjudication_decision=adjudication_decision,
        course_evidence_decision=course_evidence_decision,
        items=items,
    )


def _validate_inputs(
    *,
    packet: Mapping[str, object],
    adjudication: Mapping[str, object],
    course_id: str,
    course_revision: str | None,
    packet_digest: str | None,
) -> str | None:
    if packet.get("public_course_review_packet_version") != (
        PUBLIC_COURSE_REVIEW_PACKET_VERSION
    ):
        return "unsupported_packet_version"
    if adjudication.get("public_course_adjudication_version") != (
        PUBLIC_COURSE_ADJUDICATION_VERSION
    ):
        return "unsupported_adjudication_version"
    if not packet_digest:
        return "packet_digest_missing"
    if adjudication.get("packet_digest") != packet_digest:
        return "packet_digest_mismatch"
    if adjudication.get("course_id") != course_id:
        return "course_id_mismatch"
    if adjudication.get("course_revision") != course_revision:
        return "course_revision_mismatch"
    if adjudication.get("course_evidence_decision") != packet.get(
        "adapter_decision"
    ):
        return "course_evidence_decision_mismatch"
    if adjudication.get("decision") != "adjudicated":
        return "adjudication_incomplete"
    finding_refusal = _validate_finding_identity(packet, adjudication)
    if finding_refusal is not None:
        return finding_refusal
    if packet.get("truncated"):
        return "packet_truncated"
    if packet.get("refusal_code") is not None:
        return "packet_refused"
    return None


def _validate_finding_identity(
    packet: Mapping[str, object],
    adjudication: Mapping[str, object],
) -> str | None:
    packet_rows = packet.get("findings")
    adjudication_rows = adjudication.get("findings")
    if not isinstance(packet_rows, list) or not isinstance(adjudication_rows, list):
        return "finding_identity_unavailable"
    packet_by_id = {
        str(row["finding_id"]): row
        for row in packet_rows
        if isinstance(row, dict) and "finding_id" in row
    }
    adjudication_by_id = {
        str(row["finding_id"]): row
        for row in adjudication_rows
        if isinstance(row, dict) and "finding_id" in row
    }
    if set(packet_by_id) != set(adjudication_by_id):
        return "finding_identity_mismatch"
    for finding_id, packet_row in packet_by_id.items():
        adjudication_row = adjudication_by_id[finding_id]
        for key in ("lesson_id", "claim_index", "state", "priority"):
            if packet_row.get(key) != adjudication_row.get(key):
                return "finding_identity_mismatch"
    return None


def _parse_findings(value: object) -> tuple[PublicCourseReviewFinding, ...]:
    if not isinstance(value, list):
        raise ValueError("adjudication_findings_missing")
    findings: list[PublicCourseReviewFinding] = []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError("adjudication_finding_invalid")
        try:
            findings.append(
                PublicCourseReviewFinding(
                    finding_id=str(row["finding_id"]),
                    lesson_id=str(row["lesson_id"]),
                    claim_index=int(row["claim_index"]),
                    evidence_tier="metadata-only",
                    state=ClaimVerificationState(str(row["state"])),
                    reason_code="adjudicated",
                    source_url=None,
                    source_read_date=None,
                    priority=ReviewPriority(str(row["priority"])),
                    recommended_action=str(row["recommended_action"]),
                    disposition=HumanDisposition(str(row["disposition"])),
                )
            )
        except (KeyError, TypeError, ValueError):
            raise ValueError("adjudication_finding_invalid") from None
    return tuple(findings)


def _plan_item(finding: PublicCourseReviewFinding) -> PublicCourseChangePlanItem:
    if finding.disposition is HumanDisposition.ACCEPTED:
        action = "retain_current_content_with_accepted_risk"
        recheck = "revisit_acceptance_at_next_course_revision"
    else:
        action = finding.recommended_action
        recheck = "rerun_public_course_verifier_after_human_change"
    return PublicCourseChangePlanItem(
        finding_id=finding.finding_id,
        lesson_id=finding.lesson_id,
        claim_index=finding.claim_index,
        state=finding.state,
        priority=finding.priority,
        disposition=finding.disposition,
        proposed_action=action,
        required_recheck=recheck,
    )


def _blocked_plan(
    *,
    course_id: str,
    course_revision: str | None,
    packet_digest: str | None,
    adjudication_decision: str,
    course_evidence_decision: str,
    refusal_code: str,
) -> PublicCourseChangePlan:
    return PublicCourseChangePlan(
        course_id=course_id,
        course_revision=course_revision,
        packet_digest=packet_digest,
        adjudication_decision=adjudication_decision,
        course_evidence_decision=course_evidence_decision,
        items=(),
        refusal_code=refusal_code,
    )


def _safe_text(value: object) -> str | None:
    if not isinstance(value, str) or not value or "\n" in value:
        return None
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _safe_text(value)


def change_plan_json(plan: PublicCourseChangePlan) -> str:
    """Serialize a change plan for a local file or caller."""

    return json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n"
