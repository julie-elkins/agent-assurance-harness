import json

from agent_reliability_lab.portfolio_report import (
    PUBLIC_COURSE_LANE_ID,
    REQUIRED_LANES,
    PortfolioLaneResult,
    PortfolioLaneStatus,
    assemble_portfolio_lanes,
    build_public_course_lane,
    run_reference_portfolio_report,
)
from agent_reliability_lab.claude_course_adapter import (
    ClaimVerificationState,
    VerifierRow,
    adapt_verifier_rows,
)


def test_reference_portfolio_report_joins_all_lanes_and_catches_missing_lane(
    tmp_path,
):
    report = run_reference_portfolio_report(workspace=tmp_path)

    assert report.passed
    assert tuple(lane.lane_id for lane in report.lanes) == REQUIRED_LANES
    assert report.controls_missed == ()
    assert report.negative_control.caught
    assert report.negative_control.reason_code == (
        "missing_lane:instructor_calibration"
    )
    assert (tmp_path / "intermediate" / "course_doctor.json").exists()


def test_missing_lane_cannot_be_presented_as_ready():
    lane = PortfolioLaneResult(
        lane_id="agent_assurance",
        title="Agent reliability assurance",
        status=PortfolioLaneStatus.PASSED,
        controls_caught=("guarded-agent",),
        controls_missed=(),
        degraded_controls_caught=(),
        evidence_ids=("scenario_count:9",),
        human_gate="human review",
    )

    result = assemble_portfolio_lanes((lane,))

    assert result["passed"] is False
    assert result["decision"] == "blocked"
    assert "course_doctor" in result["missing_lanes"]


def test_portfolio_intermediates_are_metadata_only(tmp_path):
    run_reference_portfolio_report(workspace=tmp_path)

    serialized = []
    for path in (tmp_path / "intermediate").glob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(value, dict)
        serialized.append(path.read_text(encoding="utf-8"))
    joined = "\n".join(serialized)
    assert "source_bytes" not in joined
    assert "provider_output" not in joined
    assert "classroom_notes" not in joined


def test_public_course_lane_preserves_review_signals_without_course_text():
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
                quote="course text must not escape",
            ),
        ),
        course_id="claude-course",
        course_revision="abc123",
        outcomes={
            "lesson-a:claim-1": ClaimVerificationState.VERBATIM_NOT_FOUND,
        },
        pages_fetched=1,
    )

    lane = build_public_course_lane(report)
    serialized = json.dumps(lane.to_dict(), sort_keys=True)

    assert lane.lane_id == PUBLIC_COURSE_LANE_ID
    assert lane.status is PortfolioLaneStatus.REVIEW_REQUIRED
    assert lane.summary["course_revision"] == "abc123"
    assert lane.summary["known_finding_count"] == 1
    assert "course text must not escape" not in serialized
