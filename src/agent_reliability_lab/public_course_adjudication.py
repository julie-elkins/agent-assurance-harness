"""Bind human dispositions to a public-course review packet.

Design rules:

1. A decision must identify the exact safe packet digest it reviewed.
2. Unknown findings, duplicate decisions, and omitted decisions remain blocked
   rather than silently becoming an approval.
3. The output carries dispositions and routing metadata only; it does not carry
   course claims, source quotations, source bytes, or reviewer rationale.
4. Adjudication records a human decision about a queue. It never grants write
   or publication authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Mapping

from .claude_course_adapter import ClaimVerificationState
from .public_course_review import (
    HumanDisposition,
    PublicCourseReviewFinding,
    ReviewPriority,
    _packet_digest_payload,
)


PUBLIC_COURSE_ADJUDICATION_VERSION = 1
_MAX_REVIEWER_ID_LENGTH = 64
_REVIEWER_ID = re.compile(r"[-A-Za-z0-9_.:@/]{1,64}\Z")
_DECISION_KEYS = frozenset({"finding_id", "disposition"})
_MANIFEST_KEYS = frozenset(
    {
        "public_course_adjudication_version",
        "packet_digest",
        "course_id",
        "course_revision",
        "reviewer_id",
        "decisions",
    }
)


@dataclass(frozen=True)
class PublicCourseAdjudication:
    """A bounded human-disposition record for one review packet."""

    course_id: str
    course_revision: str | None
    packet_digest: str | None
    reviewer_id: str | None
    findings: tuple[PublicCourseReviewFinding, ...]
    course_evidence_decision: str
    refusal_code: str | None = None
    human_approval_required: bool = True

    @property
    def open_count(self) -> int:
        """Return the number of findings without a human disposition."""

        return sum(
            finding.disposition is HumanDisposition.OPEN
            for finding in self.findings
        )

    @property
    def deferred_count(self) -> int:
        """Return the number of findings deliberately left for later."""

        return sum(
            finding.disposition is HumanDisposition.DEFERRED
            for finding in self.findings
        )

    @property
    def decision(self) -> str:
        """Return the safe state of the adjudication record."""

        if self.refusal_code is not None:
            return "blocked"
        if self.open_count:
            return "review_required"
        return "adjudicated"

    @property
    def adjudication_complete(self) -> bool:
        """Return whether every known finding has an explicit disposition."""

        return self.decision == "adjudicated"

    @property
    def next_action(self) -> str:
        """Return the next bounded human action."""

        if self.refusal_code is not None:
            return "correct_adjudication_input"
        if self.open_count:
            return "human_review_required"
        if self.deferred_count:
            return "revisit_deferred_findings_before_content_change"
        if self.course_evidence_decision != "verified":
            return "inspect_remaining_unverified_course_rows"
        return "human_approval_required_before_content_change"

    def to_dict(self) -> dict[str, object]:
        """Return the metadata-only adjudication record."""

        return {
            "public_course_adjudication_version": (
                PUBLIC_COURSE_ADJUDICATION_VERSION
            ),
            "course_id": self.course_id,
            "course_revision": self.course_revision,
            "packet_digest": self.packet_digest,
            "reviewer_id": self.reviewer_id,
            "decision": self.decision,
            "adjudication_complete": self.adjudication_complete,
            "course_evidence_decision": self.course_evidence_decision,
            "open_count": self.open_count,
            "deferred_count": self.deferred_count,
            "next_action": self.next_action,
            "findings": [finding.to_dict() for finding in self.findings],
            "refusal_code": self.refusal_code,
            "human_approval_required": self.human_approval_required,
            "diagnostics": {
                "warnings": [
                    "This record contains dispositions and safe locations only.",
                    "Adjudication does not authorise editing or publishing course content.",
                ],
                "what_it_does_not_show": (
                    "It does not prove course correctness, source truth, learner "
                    "outcomes, or publication approval."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Render a reviewer-facing adjudication summary."""

        lines = [
            "# Public Course Review Adjudication",
            "",
            f"Decision: `{self.decision}`",
            "",
            f"- Course: `{self.course_id}`",
            f"- Revision: `{self.course_revision or 'unavailable'}`",
            f"- Packet digest: `{self.packet_digest or 'unavailable'}`",
            f"- Reviewer: `{self.reviewer_id or 'unavailable'}`",
            f"- Course evidence decision: `{self.course_evidence_decision}`",
            f"- Open findings: `{self.open_count}`",
            f"- Deferred findings: `{self.deferred_count}`",
            f"- Next action: `{self.next_action}`",
        ]
        if self.refusal_code is not None:
            lines.extend(["- Refusal: `{}`".format(self.refusal_code)])
        lines.extend(
            [
                "",
                "| Lesson | Claim | State | Priority | Disposition |",
                "| --- | ---: | --- | --- | --- |",
            ]
        )
        for finding in self.findings:
            lines.append(
                f"| `{finding.lesson_id}` | `{finding.claim_index}` | "
                f"`{finding.state.value}` | `{finding.priority.value}` | "
                f"`{finding.disposition.value}` |"
            )
        lines.extend(
            [
                "",
                "A complete adjudication records a disposition for every known "
                "finding; it does not authorise an edit or publication.",
                "",
            ]
        )
        return "\n".join(lines)


def build_public_course_adjudication(
    packet: Mapping[str, object],
    decisions: Mapping[str, object],
) -> PublicCourseAdjudication:
    """Validate and apply a bounded disposition manifest."""

    packet_id = _safe_text(packet.get("course_id"))
    course_id = packet_id or "unavailable"
    course_revision = _optional_text(packet.get("course_revision"))
    packet_digest = _optional_text(packet.get("packet_digest"))
    course_evidence_decision = (
        _safe_text(packet.get("adapter_decision")) or "unavailable"
    )
    try:
        findings = _parse_findings(packet.get("findings"))
    except ValueError as exc:
        return _blocked_adjudication(
            course_id=course_id,
            course_revision=course_revision,
            packet_digest=packet_digest,
            course_evidence_decision=course_evidence_decision,
            refusal_code=str(exc),
        )

    refusal = _validate_packet(packet, findings)
    if refusal is not None:
        return _blocked_adjudication(
            course_id=course_id,
            course_revision=course_revision,
            packet_digest=packet_digest,
            course_evidence_decision=course_evidence_decision,
            refusal_code=refusal,
            findings=findings,
        )
    refusal = _validate_manifest(
        decisions,
        packet=packet,
        packet_digest=packet_digest,
        course_id=course_id,
        course_revision=course_revision,
    )
    if refusal is not None:
        return _blocked_adjudication(
            course_id=course_id,
            course_revision=course_revision,
            packet_digest=packet_digest,
            course_evidence_decision=course_evidence_decision,
            refusal_code=refusal,
            findings=findings,
        )

    decision_rows = decisions["decisions"]
    assert isinstance(decision_rows, list)
    disposition_by_id = {
        str(row["finding_id"]): HumanDisposition(str(row["disposition"]))
        for row in decision_rows
    }
    updated = tuple(
        _with_disposition(
            finding,
            disposition_by_id.get(finding.finding_id, HumanDisposition.OPEN),
        )
        for finding in findings
    )
    if bool(packet.get("truncated")):
        refusal = "packet_truncated"
    elif packet.get("refusal_code") is not None:
        refusal = "packet_refused"
    return PublicCourseAdjudication(
        course_id=course_id,
        course_revision=course_revision,
        packet_digest=packet_digest,
        reviewer_id=str(decisions["reviewer_id"]),
        findings=updated,
        course_evidence_decision=course_evidence_decision,
        refusal_code=refusal,
    )


def _validate_packet(
    packet: Mapping[str, object],
    findings: tuple[PublicCourseReviewFinding, ...],
) -> str | None:
    if packet.get(
        "public_course_review_packet_version"
    ) != _packet_version():
        return "unsupported_packet_version"
    if not _optional_text(packet.get("packet_digest")):
        return "packet_digest_missing"
    try:
        expected_digest = _packet_digest_from_mapping(packet, findings)
    except (KeyError, TypeError, ValueError):
        return "packet_shape_invalid"
    if packet.get("packet_digest") != expected_digest:
        return "packet_digest_mismatch"
    if not isinstance(packet.get("counts"), dict):
        return "packet_counts_missing"
    return None


def _validate_manifest(
    decisions: Mapping[str, object],
    *,
    packet: Mapping[str, object],
    packet_digest: str | None,
    course_id: str,
    course_revision: str | None,
) -> str | None:
    if set(decisions) - _MANIFEST_KEYS:
        return "decision_metadata_not_allowed"
    if decisions.get("public_course_adjudication_version") != (
        PUBLIC_COURSE_ADJUDICATION_VERSION
    ):
        return "unsupported_adjudication_version"
    if decisions.get("packet_digest") != packet_digest:
        return "decision_packet_digest_mismatch"
    if decisions.get("course_id") != course_id:
        return "decision_course_mismatch"
    if decisions.get("course_revision") != course_revision:
        return "decision_revision_mismatch"
    reviewer_id = _safe_text(decisions.get("reviewer_id"))
    if reviewer_id is None or not _REVIEWER_ID.fullmatch(reviewer_id):
        return "reviewer_id_invalid"
    decision_rows = decisions.get("decisions")
    if not isinstance(decision_rows, list):
        return "decisions_missing"
    seen: set[str] = set()
    known_ids = {
        str(finding["finding_id"])
        for finding in packet.get("findings", [])
        if isinstance(finding, dict)
    }
    for row in decision_rows:
        if not isinstance(row, dict):
            return "decision_row_invalid"
        if set(row) != _DECISION_KEYS:
            return "decision_metadata_not_allowed"
        finding_id = _safe_text(row.get("finding_id"))
        if finding_id is None:
            return "finding_id_invalid"
        if finding_id in seen:
            return "duplicate_finding_decision"
        if finding_id not in known_ids:
            return "unknown_finding_id"
        seen.add(finding_id)
        try:
            HumanDisposition(str(row.get("disposition")))
        except ValueError:
            return "disposition_invalid"
    missing = known_ids - seen
    if missing:
        return "decision_missing"
    if packet.get("truncated"):
        return "packet_truncated"
    if packet.get("refusal_code") is not None:
        return "packet_refused"
    return None


def _parse_findings(value: object) -> tuple[PublicCourseReviewFinding, ...]:
    if not isinstance(value, list):
        raise ValueError("packet_findings_missing")
    findings: list[PublicCourseReviewFinding] = []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError("packet_finding_invalid")
        try:
            findings.append(
                PublicCourseReviewFinding(
                    finding_id=str(row["finding_id"]),
                    lesson_id=str(row["lesson_id"]),
                    claim_index=int(row["claim_index"]),
                    evidence_tier=str(row["evidence_tier"]),
                    state=ClaimVerificationState(str(row["state"])),
                    reason_code=str(row["reason_code"]),
                    source_url=_optional_text(row.get("source_url")),
                    source_read_date=_optional_text(row.get("source_read_date")),
                    priority=ReviewPriority(str(row["priority"])),
                    recommended_action=str(row["recommended_action"]),
                    disposition=HumanDisposition(
                        str(row.get("disposition", HumanDisposition.OPEN.value))
                    ),
                )
            )
        except (KeyError, TypeError, ValueError):
            raise ValueError("packet_finding_invalid") from None
    return tuple(findings)


def _packet_digest_from_mapping(
    packet: Mapping[str, object],
    findings: tuple[PublicCourseReviewFinding, ...],
) -> str:
    payload = _packet_digest_payload(
        version=int(packet["public_course_review_packet_version"]),
        course_id=str(packet["course_id"]),
        course_revision=_optional_text(packet.get("course_revision")),
        adapter_decision=str(packet["adapter_decision"]),
        counts=packet["counts"],
        total_known_findings=int(packet["total_known_findings"]),
        total_unverified_rows=int(packet["total_unverified_rows"]),
        findings=findings,
        max_findings=int(packet["max_findings"]),
        truncated=bool(packet["truncated"]),
        refusal_code=_optional_text(packet.get("refusal_code")),
    )
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _packet_version() -> int:
    from .public_course_review import PUBLIC_COURSE_REVIEW_PACKET_VERSION

    return PUBLIC_COURSE_REVIEW_PACKET_VERSION


def _with_disposition(
    finding: PublicCourseReviewFinding,
    disposition: HumanDisposition,
) -> PublicCourseReviewFinding:
    return PublicCourseReviewFinding(
        finding_id=finding.finding_id,
        lesson_id=finding.lesson_id,
        claim_index=finding.claim_index,
        evidence_tier=finding.evidence_tier,
        state=finding.state,
        reason_code=finding.reason_code,
        source_url=finding.source_url,
        source_read_date=finding.source_read_date,
        priority=finding.priority,
        recommended_action=finding.recommended_action,
        disposition=disposition,
    )


def _blocked_adjudication(
    *,
    course_id: str,
    course_revision: str | None,
    packet_digest: str | None,
    course_evidence_decision: str,
    refusal_code: str,
    findings: tuple[PublicCourseReviewFinding, ...] = (),
) -> PublicCourseAdjudication:
    return PublicCourseAdjudication(
        course_id=course_id,
        course_revision=course_revision,
        packet_digest=packet_digest,
        reviewer_id=None,
        findings=findings,
        course_evidence_decision=course_evidence_decision,
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


def adjudication_json(adjudication: PublicCourseAdjudication) -> str:
    """Serialize an adjudication record for a local file or caller."""

    return json.dumps(adjudication.to_dict(), indent=2, sort_keys=True) + "\n"
