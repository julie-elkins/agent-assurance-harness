import json

from agent_reliability_lab.claude_course_adapter import ClaimVerificationState
from agent_reliability_lab.public_course_adjudication import (
    build_public_course_adjudication,
)
from agent_reliability_lab.public_course_change_plan import (
    build_public_course_change_plan,
)
from agent_reliability_lab.public_course_review import (
    PublicCourseReviewFinding,
    PublicCourseReviewPacket,
    ReviewPriority,
)


def _packet() -> dict[str, object]:
    packet = PublicCourseReviewPacket(
        course_id="claude-course",
        course_revision="abc123",
        adapter_decision="review_required",
        counts={"rows_total": 1, "verbatim_not_found": 1, "counts_reconcile": True},
        findings=(
            PublicCourseReviewFinding(
                finding_id="claude-course:lesson-a:claim-1",
                lesson_id="lesson-a",
                claim_index=1,
                evidence_tier="VERBATIM",
                state=ClaimVerificationState.VERBATIM_NOT_FOUND,
                reason_code="verbatim_not_found",
                source_url="https://docs.example.test/guide",
                source_read_date="2026-10-22",
                priority=ReviewPriority.REVIEW,
                recommended_action="inspect_source_alignment",
            ),
        ),
        total_known_findings=1,
        total_unverified_rows=1,
        max_findings=100,
        truncated=False,
    )
    return packet.to_dict()


def _adjudication(packet, disposition="resolved"):
    return build_public_course_adjudication(
        packet,
        {
            "public_course_adjudication_version": 1,
            "packet_digest": packet["packet_digest"],
            "course_id": packet["course_id"],
            "course_revision": packet["course_revision"],
            "reviewer_id": "human-reviewer",
            "decisions": [
                {
                    "finding_id": packet["findings"][0]["finding_id"],
                    "disposition": disposition,
                }
            ],
        },
    ).to_dict()


def test_change_plan_reaches_human_approval_boundary_without_content():
    packet = _packet()
    adjudication = _adjudication(packet)

    plan = build_public_course_change_plan(packet, adjudication)
    serialized = json.dumps(plan.to_dict(), sort_keys=True)

    assert plan.decision == "ready_for_human_approval"
    assert plan.passed is True
    assert plan.items[0].proposed_action == "inspect_source_alignment"
    assert (
        plan.items[0].required_recheck
        == "rerun_public_course_verifier_after_human_change"
    )
    assert "private course text" not in serialized
    assert "source_reference" not in serialized


def test_deferred_finding_blocks_change_plan():
    packet = _packet()
    adjudication = _adjudication(packet, disposition="deferred")

    plan = build_public_course_change_plan(packet, adjudication)

    assert plan.decision == "blocked"
    assert plan.refusal_code == "deferred_finding_present"


def test_adjudication_finding_identity_mismatch_blocks_plan():
    packet = _packet()
    adjudication = _adjudication(packet)
    adjudication["findings"][0]["lesson_id"] = "different-lesson"

    plan = build_public_course_change_plan(packet, adjudication)

    assert plan.decision == "blocked"
    assert plan.refusal_code == "finding_identity_mismatch"
