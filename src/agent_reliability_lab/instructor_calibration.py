"""Deterministic instructor-calibration assurance for technical enablement.

This module models the smallest public contract needed to show instructor
development: an observer records whether a technical instructor demonstrated
the required behaviors, and the workflow returns a readiness or coaching
decision without storing classroom notes or learner content.

The result is a recommendation for human sign-off. It is not an instructor
certification system and it does not replace a qualified observer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


INSTRUCTOR_CALIBRATION_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
_OBSERVATION_STATES = frozenset({"observed", "not_observed"})
_DELIVERY_MODES = frozenset({"live_in_person", "live_remote"})
REQUIRED_CRITERIA = (
    "technical_accuracy",
    "hands_on_execution",
    "live_debugging",
    "audience_adaptation",
    "safety_boundary",
)


class CalibrationDecision(str, Enum):
    """The safe result of one instructor observation."""

    READY_FOR_HUMAN_SIGNOFF = "ready_for_human_signoff"
    COACHING_REQUIRED = "coaching_required"
    REFUSED = "refused"


@dataclass(frozen=True)
class CalibrationObservation:
    """One rubric criterion and its identifier-only observation evidence."""

    criterion_id: str
    status: str
    evidence_id: str


@dataclass(frozen=True)
class InstructorFeedbackSignal:
    """A bounded feedback signal without classroom prose."""

    signal_id: str
    signal_type: str
    count: int
    recommended_action: str


@dataclass(frozen=True)
class InstructorCalibrationRequest:
    """One observer's bounded review request."""

    session_id: str
    instructor_id: str
    observer_id: str
    content_pack_id: str
    delivery_mode: str
    audience_size: int
    observations: tuple[CalibrationObservation, ...]
    feedback: tuple[InstructorFeedbackSignal, ...]


@dataclass(frozen=True)
class InstructorCalibrationReport:
    """A metadata-only readiness and coaching recommendation."""

    session_id: str
    instructor_id: str
    observer_id: str
    content_pack_id: str
    delivery_mode: str
    audience_size: int
    decision: CalibrationDecision
    rubric_version: int
    observed_criteria: tuple[str, ...]
    missing_criteria: tuple[str, ...]
    feedback_signal_ids: tuple[str, ...]
    feedback_signal_count: int
    coaching_recommendations: tuple[str, ...] = ()
    refusal_code: str | None = None

    @property
    def passed(self) -> bool:
        """Return true only when a human sign-off may proceed."""

        return self.decision is CalibrationDecision.READY_FOR_HUMAN_SIGNOFF

    def to_dict(self) -> dict[str, object]:
        """Return the safe report representation."""

        return {
            "instructor_calibration_version": INSTRUCTOR_CALIBRATION_VERSION,
            "session_id": self.session_id,
            "instructor_id": self.instructor_id,
            "observer_id": self.observer_id,
            "content_pack_id": self.content_pack_id,
            "delivery_mode": self.delivery_mode,
            "audience_size": self.audience_size,
            "decision": self.decision.value,
            "passed": self.passed,
            "rubric_version": self.rubric_version,
            "observed_criteria": list(self.observed_criteria),
            "missing_criteria": list(self.missing_criteria),
            "feedback_signal_ids": list(self.feedback_signal_ids),
            "feedback_signal_count": self.feedback_signal_count,
            "coaching_recommendations": list(self.coaching_recommendations),
            "refusal_code": self.refusal_code,
            "diagnostics": {
                "warnings": [
                    "This report contains rubric identifiers, states, counts, and recommendations only.",
                    "Ready means ready for human sign-off; it is not instructor certification.",
                ],
                "what_it_does_not_show": (
                    "It does not prove classroom effectiveness, learner mastery, "
                    "technical correctness beyond the observed rubric, or readiness "
                    "to teach content outside this session."
                ),
            },
        }


@dataclass(frozen=True)
class InstructorCalibrationCase:
    """A deterministic positive or degraded observation case."""

    case_id: str
    request: InstructorCalibrationRequest
    expected_decision: CalibrationDecision
    expected_reason: str | None = None


@dataclass(frozen=True)
class InstructorCalibrationSuiteReport:
    """The ready path and deliberate instructor-development controls."""

    reports: tuple[tuple[str, InstructorCalibrationReport], ...]
    controls_caught: tuple[str, ...]
    controls_missed: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """Return true only when every declared control behaves as expected."""

        return not self.controls_missed

    def to_dict(self) -> dict[str, object]:
        """Return metadata-only suite output."""

        return {
            "instructor_calibration_version": INSTRUCTOR_CALIBRATION_VERSION,
            "passed": self.passed,
            "cases": [
                {
                    "case_id": case_id,
                    **report.to_dict(),
                }
                for case_id, report in self.reports
            ],
            "controls_caught": list(self.controls_caught),
            "controls_missed": list(self.controls_missed),
            "diagnostics": {
                "warnings": [
                    "The suite uses synthetic observation and feedback signals.",
                    "Coaching recommendations require human interpretation.",
                ],
                "what_it_does_not_show": (
                    "It does not replace an observer, certify an instructor, "
                    "or publish training content."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Render a reviewer-facing calibration summary."""

        lines = [
            "# Instructor Calibration Report",
            "",
            f"Decision: {'PASS' if self.passed else 'BLOCKED'}",
            "",
            "| Case | Decision | Observed criteria | Feedback signals | Coaching |",
            "| --- | --- | ---: | ---: | --- |",
        ]
        for case_id, report in self.reports:
            coaching = ", ".join(report.coaching_recommendations)
            if not coaching and report.refusal_code is not None:
                coaching = report.refusal_code
            coaching = coaching or "none"
            lines.append(
                f"| `{case_id}` | `{report.decision.value}` | "
                f"`{len(report.observed_criteria)}` | "
                f"`{report.feedback_signal_count}` | {coaching} |"
            )
        lines.extend(
            [
                "",
                "Controls caught: "
                + (", ".join(f"`{item}`" for item in self.controls_caught) or "none"),
                "",
                "Controls missed: "
                + (", ".join(f"`{item}`" for item in self.controls_missed) or "none"),
                "",
                "This report contains rubric identifiers, states, counts, and recommendations only.",
                "A ready result still requires human sign-off.",
                "",
            ]
        )
        return "\n".join(lines)


def run_instructor_calibration(
    request: InstructorCalibrationRequest,
) -> InstructorCalibrationReport:
    """Evaluate one observation against the fixed synthetic rubric."""

    refusal = _validate_request(request)
    if refusal is not None:
        return _refused_report(request, refusal)

    state_by_criterion = {
        observation.criterion_id: observation.status
        for observation in request.observations
    }
    observed = tuple(
        criterion
        for criterion in REQUIRED_CRITERIA
        if state_by_criterion[criterion] == "observed"
    )
    missing = tuple(
        criterion
        for criterion in REQUIRED_CRITERIA
        if state_by_criterion[criterion] == "not_observed"
    )
    recommendations = tuple(
        _coaching_code(criterion) for criterion in missing
    )
    decision = (
        CalibrationDecision.COACHING_REQUIRED
        if missing
        else CalibrationDecision.READY_FOR_HUMAN_SIGNOFF
    )
    return InstructorCalibrationReport(
        session_id=request.session_id,
        instructor_id=request.instructor_id,
        observer_id=request.observer_id,
        content_pack_id=request.content_pack_id,
        delivery_mode=request.delivery_mode,
        audience_size=request.audience_size,
        decision=decision,
        rubric_version=INSTRUCTOR_CALIBRATION_VERSION,
        observed_criteria=observed,
        missing_criteria=missing,
        feedback_signal_ids=tuple(
            signal.signal_id for signal in request.feedback
        ),
        feedback_signal_count=len(request.feedback),
        coaching_recommendations=recommendations,
    )


def reference_instructor_calibration_cases() -> tuple[
    InstructorCalibrationCase, ...
]:
    """Return the public synthetic positive path and degraded controls."""

    observations = tuple(
        CalibrationObservation(
            criterion_id=criterion,
            status="observed",
            evidence_id=f"observation:{criterion}",
        )
        for criterion in REQUIRED_CRITERIA
    )
    feedback = (
        InstructorFeedbackSignal(
            signal_id="feedback-learner-confusion",
            signal_type="learner_confusion",
            count=2,
            recommended_action="clarify",
        ),
        InstructorFeedbackSignal(
            signal_id="feedback-lab-completion",
            signal_type="lab_completion",
            count=18,
            recommended_action="retain",
        ),
    )
    base = {
        "session_id": "session-platform-training-001",
        "instructor_id": "instructor-synthetic-001",
        "observer_id": "observer-synthetic-001",
        "content_pack_id": "pack-platform-launch",
        "delivery_mode": "live_remote",
        "audience_size": 24,
        "observations": observations,
        "feedback": feedback,
    }
    missing_lab = tuple(
        CalibrationObservation(
            criterion_id=observation.criterion_id,
            status=(
                "not_observed"
                if observation.criterion_id == "hands_on_execution"
                else observation.status
            ),
            evidence_id=observation.evidence_id,
        )
        for observation in observations
    )
    missing_adaptation = tuple(
        CalibrationObservation(
            criterion_id=observation.criterion_id,
            status=(
                "not_observed"
                if observation.criterion_id == "audience_adaptation"
                else observation.status
            ),
            evidence_id=observation.evidence_id,
        )
        for observation in observations
    )
    return (
        InstructorCalibrationCase(
            case_id="instructor-ready",
            request=InstructorCalibrationRequest(**base),
            expected_decision=CalibrationDecision.READY_FOR_HUMAN_SIGNOFF,
        ),
        InstructorCalibrationCase(
            case_id="instructor-missing-lab",
            request=InstructorCalibrationRequest(
                **{**base, "observations": missing_lab}
            ),
            expected_decision=CalibrationDecision.COACHING_REQUIRED,
            expected_reason="coach:hands_on_execution",
        ),
        InstructorCalibrationCase(
            case_id="instructor-missing-adaptation",
            request=InstructorCalibrationRequest(
                **{**base, "observations": missing_adaptation}
            ),
            expected_decision=CalibrationDecision.COACHING_REQUIRED,
            expected_reason="coach:audience_adaptation",
        ),
        InstructorCalibrationCase(
            case_id="instructor-no-feedback",
            request=InstructorCalibrationRequest(
                **{**base, "feedback": ()}
            ),
            expected_decision=CalibrationDecision.REFUSED,
            expected_reason="missing_feedback_signals",
        ),
        InstructorCalibrationCase(
            case_id="instructor-missing-criterion",
            request=InstructorCalibrationRequest(
                **{**base, "observations": observations[:-1]}
            ),
            expected_decision=CalibrationDecision.REFUSED,
            expected_reason="missing_criterion:safety_boundary",
        ),
    )


def run_reference_instructor_calibration_suite() -> (
    InstructorCalibrationSuiteReport
):
    """Run the ready path and verify all calibration controls."""

    reports: list[tuple[str, InstructorCalibrationReport]] = []
    caught: list[str] = []
    missed: list[str] = []
    for case in reference_instructor_calibration_cases():
        report = run_instructor_calibration(case.request)
        reports.append((case.case_id, report))
        expected_decision = report.decision is case.expected_decision
        expected_reason = (
            case.expected_reason is None
            or case.expected_reason in report.coaching_recommendations
            or case.expected_reason == report.refusal_code
        )
        if expected_decision and expected_reason:
            caught.append(case.case_id)
        else:
            missed.append(case.case_id)
    return InstructorCalibrationSuiteReport(
        reports=tuple(reports),
        controls_caught=tuple(caught),
        controls_missed=tuple(missed),
    )


def _validate_request(
    request: InstructorCalibrationRequest,
) -> str | None:
    for value, code in (
        (request.session_id, "invalid_session_id"),
        (request.instructor_id, "invalid_instructor_id"),
        (request.observer_id, "invalid_observer_id"),
        (request.content_pack_id, "invalid_content_pack_id"),
    ):
        if not _valid_identifier(value):
            return code
    if request.delivery_mode not in _DELIVERY_MODES:
        return "invalid_delivery_mode"
    if (
        isinstance(request.audience_size, bool)
        or not isinstance(request.audience_size, int)
        or request.audience_size < 1
        or request.audience_size > 1000
    ):
        return "invalid_audience_size"
    if not request.observations:
        return "missing_observations"
    observation_ids = [
        observation.criterion_id for observation in request.observations
    ]
    if len(observation_ids) != len(set(observation_ids)):
        return "duplicate_criterion"
    for observation in request.observations:
        if observation.criterion_id not in REQUIRED_CRITERIA:
            return "unknown_criterion"
        if observation.status not in _OBSERVATION_STATES:
            return "invalid_observation_status"
        if not _valid_identifier(observation.evidence_id):
            return "invalid_observation_evidence"
    missing_criteria = [
        criterion
        for criterion in REQUIRED_CRITERIA
        if criterion not in observation_ids
    ]
    if missing_criteria:
        return f"missing_criterion:{missing_criteria[0]}"
    feedback_ids = [signal.signal_id for signal in request.feedback]
    if len(feedback_ids) != len(set(feedback_ids)):
        return "duplicate_feedback_id"
    if not request.feedback:
        return "missing_feedback_signals"
    for signal in request.feedback:
        if not _valid_identifier(signal.signal_id):
            return "invalid_feedback_id"
        if not _valid_identifier(signal.signal_type):
            return "invalid_feedback_type"
        if (
            isinstance(signal.count, bool)
            or not isinstance(signal.count, int)
            or signal.count < 0
        ):
            return "invalid_feedback_count"
        if not _valid_identifier(signal.recommended_action):
            return "invalid_feedback_action"
    return None


def _refused_report(
    request: InstructorCalibrationRequest,
    refusal_code: str,
) -> InstructorCalibrationReport:
    return InstructorCalibrationReport(
        session_id=request.session_id,
        instructor_id=request.instructor_id,
        observer_id=request.observer_id,
        content_pack_id=request.content_pack_id,
        delivery_mode=request.delivery_mode,
        audience_size=request.audience_size,
        decision=CalibrationDecision.REFUSED,
        rubric_version=INSTRUCTOR_CALIBRATION_VERSION,
        observed_criteria=(),
        missing_criteria=(),
        feedback_signal_ids=tuple(
            signal.signal_id for signal in request.feedback
        ),
        feedback_signal_count=len(request.feedback),
        refusal_code=refusal_code,
    )


def _coaching_code(criterion_id: str) -> str:
    return f"coach:{criterion_id}"


def _valid_identifier(value: object) -> bool:
    return isinstance(value, str) and _IDENTIFIER.fullmatch(value) is not None


