import json

from agent_reliability_lab.claude_course_adapter import (
    ClaimVerificationState,
    VerifierRow,
    adapt_verifier_rows,
)
from agent_reliability_lab.public_course_review import (
    HumanDisposition,
    ReviewPriority,
    build_public_course_review_packet,
)


def test_review_packet_turns_findings_into_safe_actions():
    report = adapt_verifier_rows(
        (
            VerifierRow(
                row_id="lesson-a:claim-1",
                lesson_id="lesson-a",
                claim_index=1,
                tier="VERBATIM",
                source_url="https://docs.example.test/guide",
                source_reference="official docs read 2026-10-22",
                source_read_date="2026-10-22",
                quote="course claim must not escape",
            ),
            VerifierRow(
                row_id="lesson-b:claim-2",
                lesson_id="lesson-b",
                claim_index=2,
                tier="IDENTIFIER",
                source_url="https://docs.example.test/tools",
                source_reference="official docs read 2026-10-22",
                source_read_date="2026-10-22",
                identifiers=("--removed-flag",),
            ),
        ),
        course_id="claude-course",
        course_revision="abc123",
        outcomes={
            "lesson-a:claim-1": ClaimVerificationState.VERBATIM_NOT_FOUND,
            "lesson-b:claim-2": ClaimVerificationState.IDENTIFIER_MISSING,
        },
        pages_fetched=2,
    )

    packet = build_public_course_review_packet(report)
    serialized = json.dumps(packet.to_dict(), sort_keys=True)

    assert packet.decision == "review_required"
    assert packet.open_count == 2
    assert packet.findings[0].priority is ReviewPriority.REVIEW
    assert packet.findings[0].recommended_action == "inspect_source_alignment"
    assert packet.findings[1].priority is ReviewPriority.BLOCKING
    assert packet.findings[1].disposition is HumanDisposition.OPEN
    assert "course claim must not escape" not in serialized
    assert "source_reference" not in serialized


def test_review_packet_is_bounded_and_marks_truncation():
    rows = tuple(
        VerifierRow(
            row_id=f"lesson-{index}:claim-1",
            lesson_id=f"lesson-{index}",
            claim_index=1,
            tier="VERBATIM",
            source_url="https://docs.example.test/guide",
            source_reference="official docs read 2026-10-22",
            source_read_date="2026-10-22",
            quote="must not escape",
        )
        for index in range(3)
    )
    report = adapt_verifier_rows(
        rows,
        course_id="claude-course",
        course_revision="abc123",
        outcomes={
            row.row_id: ClaimVerificationState.VERBATIM_NOT_FOUND
            for row in rows
        },
        pages_fetched=1,
    )

    packet = build_public_course_review_packet(report, max_findings=2)

    assert packet.total_known_findings == 3
    assert len(packet.findings) == 2
    assert packet.truncated is True
