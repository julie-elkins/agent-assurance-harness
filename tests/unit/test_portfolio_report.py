import json

from agent_reliability_lab.portfolio_report import (
    REQUIRED_LANES,
    PortfolioLaneResult,
    PortfolioLaneStatus,
    assemble_portfolio_lanes,
    run_reference_portfolio_report,
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
