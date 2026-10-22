import json

from agent_reliability_lab.claude_course_adapter import (
    ClaimVerificationState,
    VerifierRow,
    adapt_verifier_rows,
)
from agent_reliability_lab.public_course_adjudication import (
    build_public_course_adjudication,
)
from agent_reliability_lab.public_course_review import (
    build_public_course_review_packet,
)


def _packet():
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
                quote="private claim text",
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
    return build_public_course_review_packet(report).to_dict()


def _decisions(packet, *, dispositions=("resolved", "accepted")):
    return {
        "public_course_adjudication_version": 1,
        "packet_digest": packet["packet_digest"],
        "course_id": packet["course_id"],
        "course_revision": packet["course_revision"],
        "reviewer_id": "human-reviewer",
        "decisions": [
            {
                "finding_id": finding["finding_id"],
                "disposition": disposition,
            }
            for finding, disposition in zip(
                packet["findings"],
                dispositions,
                strict=True,
            )
        ],
    }


def test_adjudication_binds_dispositions_to_packet_and_keeps_boundary():
    packet = _packet()
    record = build_public_course_adjudication(
        packet,
        _decisions(packet),
    )

    serialized = json.dumps(record.to_dict(), sort_keys=True)

    assert record.decision == "adjudicated"
    assert record.adjudication_complete is True
    assert record.open_count == 0
    assert record.next_action == "inspect_remaining_unverified_course_rows"
    assert "private claim text" not in serialized
    assert "source_reference" not in serialized


def test_missing_decision_is_blocked_instead_of_becoming_approval():
    packet = _packet()
    decisions = _decisions(packet)
    decisions["decisions"] = decisions["decisions"][:1]

    record = build_public_course_adjudication(packet, decisions)

    assert record.decision == "blocked"
    assert record.refusal_code == "decision_missing"


def test_free_form_reviewer_metadata_is_refused():
    packet = _packet()
    decisions = _decisions(packet)
    decisions["decisions"][0]["rationale"] = "private claim text"

    record = build_public_course_adjudication(packet, decisions)

    assert record.decision == "blocked"
    assert record.refusal_code == "decision_metadata_not_allowed"
    assert "private claim text" not in json.dumps(record.to_dict())
