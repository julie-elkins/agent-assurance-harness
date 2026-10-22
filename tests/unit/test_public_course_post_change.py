import json

from agent_reliability_lab.claude_course_adapter import ClaimVerificationState
from agent_reliability_lab.public_course_change_plan import (
    PublicCourseChangePlan,
    PublicCourseChangePlanItem,
)
from agent_reliability_lab.public_course_post_change import (
    build_public_course_post_change_verification,
)
from agent_reliability_lab.public_course_review import (
    HumanDisposition,
    ReviewPriority,
)


def _plan() -> dict[str, object]:
    return PublicCourseChangePlan(
        course_id="claude-course",
        course_revision="before-revision",
        packet_digest="sha256:packet",
        adjudication_decision="adjudicated",
        course_evidence_decision="review_required",
        items=(
            PublicCourseChangePlanItem(
                finding_id="claude-course:lesson-a:claim-1",
                lesson_id="lesson-a",
                claim_index=1,
                state=ClaimVerificationState.VERBATIM_NOT_FOUND,
                priority=ReviewPriority.REVIEW,
                disposition=HumanDisposition.RESOLVED,
                proposed_action="inspect_source_alignment",
                required_recheck="rerun_public_course_verifier_after_human_change",
            ),
        ),
    ).to_dict()


def _report(*, new_blocking=False, revision="after-revision"):
    results = [
        {
            "row_id": "lesson-a:claim-1",
            "state": ClaimVerificationState.VERBATIM_VERIFIED.value,
            "reason_code": "verbatim_verified",
            "locator": {"lesson_id": "lesson-a", "claim_index": 1},
        }
    ]
    if new_blocking:
        results.append(
            {
                "row_id": "lesson-new:claim-1",
                "state": ClaimVerificationState.IDENTIFIER_MISSING.value,
                "reason_code": "identifier_missing",
                "locator": {"lesson_id": "lesson-new", "claim_index": 1},
            }
        )
    return {
        "claude_course_adapter_version": 1,
        "course_id": "claude-course",
        "course_revision": revision,
        "decision": "review_required",
        "offline": False,
        "refusal_code": None,
        "counts": {"rows_total": len(results), "counts_reconcile": True},
        "results": results,
    }


def test_post_change_verification_closes_targeted_scope_only():
    verification = build_public_course_post_change_verification(
        _plan(),
        _report(),
    )
    serialized = json.dumps(verification.to_dict(), sort_keys=True)

    assert verification.decision == "verified_targeted_scope"
    assert verification.passed is True
    assert verification.targets[0].outcome == "target_recovered"
    assert verification.next_action == "human_approval_required_before_publication"
    assert "private course text" not in serialized
    assert "source_reference" not in serialized


def test_new_blocking_finding_blocks_targeted_verification():
    verification = build_public_course_post_change_verification(
        _plan(),
        _report(new_blocking=True),
    )

    assert verification.decision == "blocked"
    assert verification.refusal_code == "new_blocking_finding"
    assert verification.new_blocking_findings == (
        "claude-course:lesson-new:claim-1",
    )


def test_unchanged_revision_blocks_post_change_claim():
    verification = build_public_course_post_change_verification(
        _plan(),
        _report(revision="before-revision"),
    )

    assert verification.decision == "blocked"
    assert verification.refusal_code == "course_revision_unchanged"


def test_accepted_risk_that_becomes_blocking_is_not_silently_accepted():
    plan = _plan()
    plan["items"][0]["disposition"] = HumanDisposition.ACCEPTED.value
    report = _report()
    report["results"][0]["state"] = ClaimVerificationState.IDENTIFIER_MISSING.value

    verification = build_public_course_post_change_verification(plan, report)

    assert verification.decision == "blocked"
    assert verification.refusal_code == "accepted_risk_regressed"
    assert verification.targets[0].outcome == "accepted_risk_regressed"
