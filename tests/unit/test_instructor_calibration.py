import json
from dataclasses import replace

from agent_reliability_lab.instructor_calibration import (
    CalibrationDecision,
    InstructorCalibrationRequest,
    reference_instructor_calibration_cases,
    run_instructor_calibration,
    run_reference_instructor_calibration_suite,
)


def test_reference_calibration_suite_has_ready_and_coaching_paths():
    report = run_reference_instructor_calibration_suite()

    assert report.passed
    assert report.controls_missed == ()
    assert report.controls_caught == (
        "instructor-ready",
        "instructor-missing-lab",
        "instructor-missing-adaptation",
        "instructor-no-feedback",
        "instructor-missing-criterion",
    )
    decisions = {
        case_id: result.decision for case_id, result in report.reports
    }
    assert decisions == {
        "instructor-ready": CalibrationDecision.READY_FOR_HUMAN_SIGNOFF,
        "instructor-missing-lab": CalibrationDecision.COACHING_REQUIRED,
        "instructor-missing-adaptation": CalibrationDecision.COACHING_REQUIRED,
        "instructor-no-feedback": CalibrationDecision.REFUSED,
        "instructor-missing-criterion": CalibrationDecision.REFUSED,
    }


def test_ready_calibration_contains_feedback_and_is_not_certification():
    case = reference_instructor_calibration_cases()[0]

    report = run_instructor_calibration(case.request)
    serialized = json.dumps(report.to_dict())

    assert report.passed
    assert report.rubric_version == 1
    assert report.feedback_signal_count == 2
    assert "ready_for_human_signoff" in serialized
    assert "certification" in serialized
    assert "learner_confusion" not in serialized


def test_missing_lab_emits_coaching_recommendation():
    case = reference_instructor_calibration_cases()[1]

    report = run_instructor_calibration(case.request)

    assert report.decision is CalibrationDecision.COACHING_REQUIRED
    assert report.missing_criteria == ("hands_on_execution",)
    assert report.coaching_recommendations == ("coach:hands_on_execution",)


def test_missing_feedback_is_refused_before_readiness():
    case = reference_instructor_calibration_cases()[3]

    report = run_instructor_calibration(case.request)

    assert report.decision is CalibrationDecision.REFUSED
    assert report.refusal_code == "missing_feedback_signals"


def test_not_observed_criterion_requires_coaching():
    case = reference_instructor_calibration_cases()[0]
    observation = case.request.observations[0]
    request = replace(
        case.request,
        observations=(
            replace(observation, status="not_observed"),
            *case.request.observations[1:],
        ),
    )

    report = run_instructor_calibration(request)

    assert report.decision is CalibrationDecision.COACHING_REQUIRED
    assert report.missing_criteria == ("technical_accuracy",)


def test_unknown_observer_state_is_refused():
    case = reference_instructor_calibration_cases()[0]
    observation = case.request.observations[0]
    request = replace(
        case.request,
        observations=(
            replace(observation, status="unknown"),
            *case.request.observations[1:],
        ),
    )

    report = run_instructor_calibration(request)

    assert report.decision is CalibrationDecision.REFUSED
    assert report.refusal_code == "invalid_observation_status"
