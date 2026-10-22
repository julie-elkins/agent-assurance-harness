import json

from agent_reliability_lab.enablement_pack import (
    EnablementDecision,
    LaunchToFieldPackRequest,
    reference_launch_to_field_cases,
    run_launch_to_field_pack,
    run_reference_launch_to_field_suite,
)


def test_reference_enablement_suite_has_ready_path_and_controls():
    report = run_reference_launch_to_field_suite()

    assert report.passed
    assert report.controls_missed == ()
    assert report.controls_caught == (
        "launch-pack-ready",
        "launch-pack-stale-source",
        "launch-pack-unsupported-claim",
        "launch-pack-wrong-source",
        "launch-pack-incomplete-assets",
    )
    decisions = {
        case_id: result.decision for case_id, result in report.reports
    }
    assert decisions == {
        "launch-pack-ready": EnablementDecision.READY_FOR_HUMAN_APPROVAL,
        "launch-pack-stale-source": EnablementDecision.BLOCKED,
        "launch-pack-unsupported-claim": EnablementDecision.BLOCKED,
        "launch-pack-wrong-source": EnablementDecision.BLOCKED,
        "launch-pack-incomplete-assets": EnablementDecision.REFUSED,
    }


def test_ready_pack_contains_assets_feedback_and_no_content():
    case = reference_launch_to_field_cases()[0]

    report = run_launch_to_field_pack(case.request)
    data = report.to_dict()

    assert report.passed
    assert data["asset_types"] == ["demo", "lab", "quick_reference"]
    assert data["feedback_signal_count"] == 2
    assert "Approved launch guidance fixture" not in json.dumps(data)
    assert "source_bytes" not in json.dumps(data)


def test_stale_source_is_blocked_with_locator():
    case = reference_launch_to_field_cases()[1]

    report = run_launch_to_field_pack(case.request)

    assert report.decision is EnablementDecision.BLOCKED
    assert report.blocked_reasons == ("evidence_stale",)
    assert report.finding_locators
    assert report.finding_locators[0].source_id == "source-approved-docs"


def test_missing_required_asset_is_refused_before_source_evaluation():
    case = reference_launch_to_field_cases()[-1]

    report = run_launch_to_field_pack(case.request)

    assert report.decision is EnablementDecision.REFUSED
    assert report.refusal_code == "missing_asset_type:quick_reference"


def test_missing_feedback_is_refused():
    case = reference_launch_to_field_cases()[0]
    request = LaunchToFieldPackRequest(
        **{**case.request.__dict__, "feedback": ()}
    )

    report = run_launch_to_field_pack(request)

    assert report.decision is EnablementDecision.REFUSED
    assert report.refusal_code == "missing_feedback_signals"
