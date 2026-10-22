"""Reviewer-facing orchestration of the public assurance portfolio.

The portfolio report joins existing bounded workflows. It does not replace their
decisions or copy their underlying content. Each worker returns metadata, the
orchestrator keeps lane failures visible, and the join refuses to call an
incomplete portfolio ready for review.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Sequence

from .claude_course_adapter import (
    ClaudeCourseVerificationReport,
    DEFAULT_MAX_REQUESTS,
    DEFAULT_MAX_ROWS,
    run_claude_course_adapter,
)
from .course_doctor import run_reference_course_doctor_suite
from .enablement_pack import run_reference_launch_to_field_suite
from .instructor_calibration import run_reference_instructor_calibration_suite
from .public_course_review import build_public_course_review_packet
from .runner import run_comparison


PORTFOLIO_ASSURANCE_VERSION = 2
REQUIRED_LANES = (
    "agent_assurance",
    "course_doctor",
    "launch_to_field",
    "instructor_calibration",
    "delivery_path",
)
PUBLIC_COURSE_LANE_ID = "public_course"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class PortfolioLaneStatus(str, Enum):
    """The safe state of one independently executed portfolio lane."""

    PASSED = "passed"
    BLOCKED = "blocked"
    REVIEW_REQUIRED = "review_required"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class PortfolioLaneResult:
    """Metadata returned by one portfolio worker."""

    lane_id: str
    title: str
    status: PortfolioLaneStatus
    controls_caught: tuple[str, ...]
    controls_missed: tuple[str, ...]
    degraded_controls_caught: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    human_gate: str
    reason_code: str | None = None
    summary: dict[str, object] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Return true only when the lane completed without missed controls."""

        return (
            self.status is PortfolioLaneStatus.PASSED
            and not self.controls_missed
        )

    def to_dict(self) -> dict[str, object]:
        """Return the safe lane contract."""

        return {
            "lane_id": self.lane_id,
            "title": self.title,
            "status": self.status.value,
            "passed": self.passed,
            "controls_caught": list(self.controls_caught),
            "controls_missed": list(self.controls_missed),
            "degraded_controls_caught": list(self.degraded_controls_caught),
            "evidence_ids": list(self.evidence_ids),
            "human_gate": self.human_gate,
            "reason_code": self.reason_code,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class PortfolioNegativeControl:
    """A deliberate incomplete-join case."""

    control_id: str
    caught: bool
    removed_lane: str
    observed_decision: str
    reason_code: str

    def to_dict(self) -> dict[str, object]:
        """Return the negative-control result."""

        return {
            "control_id": self.control_id,
            "caught": self.caught,
            "removed_lane": self.removed_lane,
            "observed_decision": self.observed_decision,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class PortfolioAssuranceReport:
    """The joined reviewer-facing assurance result."""

    lanes: tuple[PortfolioLaneResult, ...]
    controls_caught: tuple[str, ...]
    controls_missed: tuple[str, ...]
    negative_control: PortfolioNegativeControl
    required_lanes: tuple[str, ...] = REQUIRED_LANES

    @property
    def blocking_lanes(self) -> tuple[str, ...]:
        """Return lanes that prevent a complete portfolio decision."""

        return tuple(
            lane.lane_id
            for lane in self.lanes
            if lane.status
            in {
                PortfolioLaneStatus.BLOCKED,
                PortfolioLaneStatus.UNAVAILABLE,
            }
        )

    @property
    def review_required_lanes(self) -> tuple[str, ...]:
        """Return lanes that need human review but are not unavailable."""

        return tuple(
            lane.lane_id
            for lane in self.lanes
            if lane.status is PortfolioLaneStatus.REVIEW_REQUIRED
        )

    @property
    def missing_lanes(self) -> tuple[str, ...]:
        """Return required lane identifiers absent from the join."""

        present = {lane.lane_id for lane in self.lanes}
        return tuple(lane for lane in REQUIRED_LANES if lane not in present)

    @property
    def passed(self) -> bool:
        """Return true only when every lane and orchestration control passes."""

        return (
            not self.missing_lanes
            and not self.blocking_lanes
            and not self.review_required_lanes
            and not self.controls_missed
            and self.negative_control.caught
        )

    @property
    def decision(self) -> str:
        """Return the explicit reviewer handoff state."""

        if self.blocking_lanes or self.missing_lanes:
            return "blocked"
        if self.review_required_lanes:
            return "review_required"
        return "ready_for_human_review"

    def to_dict(self) -> dict[str, object]:
        """Return metadata-only portfolio evidence."""

        return {
            "portfolio_assurance_version": PORTFOLIO_ASSURANCE_VERSION,
            "passed": self.passed,
            "decision": self.decision,
            "required_lanes": list(self.required_lanes),
            "lanes": [lane.to_dict() for lane in self.lanes],
            "blocking_lanes": list(self.blocking_lanes),
            "review_required_lanes": list(self.review_required_lanes),
            "missing_lanes": list(self.missing_lanes),
            "controls_caught": list(self.controls_caught),
            "controls_missed": list(self.controls_missed),
            "negative_control": self.negative_control.to_dict(),
            "diagnostics": {
                "warnings": [
                    "The lanes use synthetic, offline, metadata-only evidence.",
                    "A ready result is a reviewer handoff, not employment evidence.",
                    "Human approval remains required for content, release, and instructor decisions.",
                ],
                "what_it_does_not_show": (
                    "It does not prove live learner outcomes, production adoption, "
                    "semantic source truth, or general live-model reliability."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Render the concise reviewer-facing report."""

        lines = [
            "# Portfolio Assurance Report",
            "",
            f"Decision: `{self.decision}`",
            "",
            "| Lane | Status | Degraded controls | Human gate |",
            "| --- | --- | ---: | --- |",
        ]
        for lane in self.lanes:
            lines.append(
                f"| `{lane.lane_id}` | `{lane.status.value}` | "
                f"`{len(lane.degraded_controls_caught)}` | {lane.human_gate} |"
            )
        lines.extend(
            [
                "",
                f"Blocking lanes: "
                f"{', '.join(f'`{item}`' for item in self.blocking_lanes) or 'none'}",
                f"Missing lanes: "
                f"{', '.join(f'`{item}`' for item in self.missing_lanes) or 'none'}",
                f"Review-required lanes: "
                f"{', '.join(f'`{item}`' for item in self.review_required_lanes) or 'none'}",
                "",
                "Orchestration controls caught: "
                + (
                    ", ".join(f"`{item}`" for item in self.controls_caught)
                    or "none"
                ),
                "",
                "Orchestration controls missed: "
                + (
                    ", ".join(f"`{item}`" for item in self.controls_missed)
                    or "none"
                ),
                "",
                "The report joins inspectable evidence; it does not replace "
                "human review, release approval, or instructor certification.",
                "",
            ]
        )
        public_course = next(
            (
                lane
                for lane in self.lanes
                if lane.lane_id == PUBLIC_COURSE_LANE_ID
            ),
            None,
        )
        if public_course is not None:
            summary = public_course.summary
            lines.extend(
                [
                    "## Public course evidence",
                    "",
                    f"- Course: `{summary.get('course_id', 'unavailable')}`",
                    f"- Revision: `{summary.get('course_revision', 'unavailable')}`",
                    f"- Course decision: `{summary.get('decision', 'unavailable')}`",
                    f"- Rows checked: `{summary.get('counts', {}).get('rows_total', 0)}`",
                    f"- Known findings: `{summary.get('known_finding_count', 0)}`",
                    "",
                    "Finding locations:",
                ]
            )
            for finding in summary.get("findings", []):
                if not isinstance(finding, dict):
                    continue
                lines.append(
                    f"- `{finding.get('lesson_id', 'unknown')}` claim "
                    f"`{finding.get('claim_index', 'unknown')}`: "
                    f"`{finding.get('state', 'unknown')}`; "
                    f"{finding.get('source_url') or 'source URL unavailable'}"
                )
            lines.extend(
                [
                    "",
                    "These are safe locators and evidence states; they do not "
                    "reproduce course claims or source quotations.",
                    "",
                ]
            )
        return "\n".join(lines)


def run_reference_portfolio_report(
    *,
    workspace: Path,
    course_root: Path | None = None,
    course_id: str = "claude-architect-lab",
    offline: bool = False,
    max_rows: int = DEFAULT_MAX_ROWS,
    max_requests: int = DEFAULT_MAX_REQUESTS,
    max_workers: int = len(REQUIRED_LANES) + 1,
) -> PortfolioAssuranceReport:
    """Run the independent public lanes and join their metadata contracts."""

    intermediate = workspace / "intermediate"
    intermediate.mkdir(parents=True, exist_ok=True)
    workers: dict[str, Callable[[], PortfolioLaneResult]] = {
        "agent_assurance": _run_agent_assurance_lane,
        "course_doctor": lambda: _run_course_doctor_lane(
            intermediate / "course-doctor"
        ),
        "launch_to_field": _run_launch_to_field_lane,
        "instructor_calibration": _run_instructor_calibration_lane,
        "delivery_path": _run_delivery_path_lane,
    }
    required_lanes = REQUIRED_LANES
    if course_root is not None:
        required_lanes += (PUBLIC_COURSE_LANE_ID,)
        workers[PUBLIC_COURSE_LANE_ID] = lambda: _run_public_course_lane(
            course_root,
            course_id=course_id,
            offline=offline,
            max_rows=max_rows,
            max_requests=max_requests,
        )
    results: dict[str, PortfolioLaneResult] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(worker): lane_id
            for lane_id, worker in workers.items()
        }
        for future in as_completed(futures):
            lane_id = futures[future]
            try:
                result = future.result()
            except Exception:
                result = _unavailable_lane(lane_id)
            results[lane_id] = result
            _write_json(intermediate / f"{lane_id}.json", result.to_dict())

    ordered = tuple(results[lane_id] for lane_id in required_lanes)
    ready_join = _assemble_lanes(ordered, required_lanes)
    incomplete_join = _assemble_lanes(
        tuple(
            lane
            for lane in ordered
            if lane.lane_id != "instructor_calibration"
        ),
        required_lanes,
    )
    negative_control = PortfolioNegativeControl(
        control_id="portfolio-missing-instructor-lane",
        caught=(
            not incomplete_join["passed"]
            and "instructor_calibration" in incomplete_join["missing_lanes"]
        ),
        removed_lane="instructor_calibration",
        observed_decision=incomplete_join["decision"],
        reason_code="missing_lane:instructor_calibration",
    )
    controls_caught: list[str] = []
    controls_missed: list[str] = []
    if ready_join["passed"]:
        controls_caught.append("portfolio-ready")
    else:
        controls_missed.append("portfolio-ready")
    if negative_control.caught:
        controls_caught.append(negative_control.control_id)
    else:
        controls_missed.append(negative_control.control_id)
    controls_missed.extend(
        f"lane:{lane_id}"
        for lane_id in ready_join["blocking_lanes"]
        if f"lane:{lane_id}" not in controls_missed
    )
    controls_missed.extend(
        f"review_required:{lane_id}"
        for lane_id in ready_join["review_required_lanes"]
        if f"review_required:{lane_id}" not in controls_missed
    )
    return PortfolioAssuranceReport(
        lanes=ordered,
        controls_caught=tuple(controls_caught),
        controls_missed=tuple(controls_missed),
        negative_control=negative_control,
        required_lanes=required_lanes,
    )


def assemble_portfolio_lanes(
    lanes: tuple[PortfolioLaneResult, ...],
    *,
    required_lanes: tuple[str, ...] = REQUIRED_LANES,
) -> dict[str, object]:
    """Evaluate a lane join for orchestration tests and diagnostics."""

    return _assemble_lanes(lanes, required_lanes)


def _assemble_lanes(
    lanes: Sequence[PortfolioLaneResult],
    required_lanes: tuple[str, ...],
) -> dict[str, object]:
    present = {lane.lane_id for lane in lanes}
    missing = tuple(
        lane_id for lane_id in required_lanes if lane_id not in present
    )
    blocking = tuple(
        lane.lane_id
        for lane in lanes
        if lane.status
        in {
            PortfolioLaneStatus.BLOCKED,
            PortfolioLaneStatus.UNAVAILABLE,
        }
    )
    review_required = tuple(
        lane.lane_id
        for lane in lanes
        if lane.status is PortfolioLaneStatus.REVIEW_REQUIRED
    )
    passed = not missing and not blocking
    return {
        "passed": passed and not review_required,
        "decision": (
            "blocked"
            if missing or blocking
            else (
                "review_required"
                if review_required
                else "ready_for_human_review"
            )
        ),
        "missing_lanes": missing,
        "blocking_lanes": blocking,
        "review_required_lanes": review_required,
    }


def _run_agent_assurance_lane() -> PortfolioLaneResult:
    comparison = run_comparison(include_mutations=True)
    guarded = next(
        report for report in comparison.reports if report.agent_id == "guarded"
    )
    evaluator_controls = tuple(
        result.case_id
        for result in comparison.evaluator_validity
        if result.caught
    )
    mutation_controls = tuple(
        result.mutation_id
        for result in comparison.mutation_tests
        if result.caught
    )
    missed: list[str] = []
    if not guarded.passed:
        missed.append("guarded-agent")
    if not evaluator_controls:
        missed.append("evaluator-controls")
    if not mutation_controls:
        missed.append("mutation-controls")
    return PortfolioLaneResult(
        lane_id="agent_assurance",
        title="Agent reliability assurance",
        status=(
            PortfolioLaneStatus.PASSED
            if not missed
            else PortfolioLaneStatus.BLOCKED
        ),
        controls_caught=evaluator_controls + mutation_controls,
        controls_missed=tuple(missed),
        degraded_controls_caught=evaluator_controls + mutation_controls,
        evidence_ids=(
            f"scenario_count:{comparison.scenario_count}",
            f"evaluator_controls:{len(evaluator_controls)}",
            f"mutation_controls:{len(mutation_controls)}",
        ),
        human_gate="CI and human merge approval remain required.",
    )


def _run_course_doctor_lane(workspace: Path) -> PortfolioLaneResult:
    suite = run_reference_course_doctor_suite(workspace=workspace)
    degraded = tuple(
        case_id
        for case_id in suite.controls_caught
        if case_id != "course-pipeline-approved"
    )
    return PortfolioLaneResult(
        lane_id="course_doctor",
        title="Course Doctor content assurance",
        status=(
            PortfolioLaneStatus.PASSED
            if suite.passed
            else PortfolioLaneStatus.BLOCKED
        ),
        controls_caught=suite.controls_caught,
        controls_missed=suite.controls_missed,
        degraded_controls_caught=degraded,
        evidence_ids=(
            f"review_packets:{len(suite.report.packets)}",
            f"completed:{suite.report.counts['completed']}",
            f"counts_reconcile:{suite.report.counts['counts_reconcile']}",
        ),
        human_gate="Human adjudication remains required before content changes.",
    )


def _run_launch_to_field_lane() -> PortfolioLaneResult:
    suite = run_reference_launch_to_field_suite()
    degraded = tuple(
        case_id
        for case_id in suite.controls_caught
        if case_id != "launch-pack-ready"
    )
    return PortfolioLaneResult(
        lane_id="launch_to_field",
        title="Launch-to-field enablement",
        status=(
            PortfolioLaneStatus.PASSED
            if suite.passed
            else PortfolioLaneStatus.BLOCKED
        ),
        controls_caught=suite.controls_caught,
        controls_missed=suite.controls_missed,
        degraded_controls_caught=degraded,
        evidence_ids=(
            f"declared_cases:{len(suite.reports)}",
            f"degraded_controls:{len(degraded)}",
        ),
        human_gate="Human approval remains required before publication.",
    )


def _run_instructor_calibration_lane() -> PortfolioLaneResult:
    suite = run_reference_instructor_calibration_suite()
    degraded = tuple(
        case_id
        for case_id in suite.controls_caught
        if case_id != "instructor-ready"
    )
    return PortfolioLaneResult(
        lane_id="instructor_calibration",
        title="Instructor calibration",
        status=(
            PortfolioLaneStatus.PASSED
            if suite.passed
            else PortfolioLaneStatus.BLOCKED
        ),
        controls_caught=suite.controls_caught,
        controls_missed=suite.controls_missed,
        degraded_controls_caught=degraded,
        evidence_ids=(
            f"declared_cases:{len(suite.reports)}",
            f"degraded_controls:{len(degraded)}",
        ),
        human_gate="Qualified observer sign-off remains required.",
    )


def _run_public_course_lane(
    course_root: Path,
    *,
    course_id: str,
    offline: bool,
    max_rows: int,
    max_requests: int,
) -> PortfolioLaneResult:
    report = run_claude_course_adapter(
        course_root,
        course_id=course_id,
        offline=offline,
        max_rows=max_rows,
        max_requests=max_requests,
    )
    return build_public_course_lane(report)


def build_public_course_lane(
    report: ClaudeCourseVerificationReport,
    *,
    max_findings: int = 10,
) -> PortfolioLaneResult:
    """Convert a course adapter report into a safe portfolio lane."""

    finding_summaries = tuple(
        {
            "row_id": result.row_id,
            "state": result.state.value,
            "reason_code": result.reason_code,
            "lesson_id": result.locator.lesson_id,
            "claim_index": result.locator.claim_index,
            "evidence_tier": result.locator.tier,
            "source_url": result.locator.source_url,
            "source_read_date": result.locator.source_read_date,
        }
        for result in report.known_findings[:max_findings]
    )
    summary = {
        "course_id": report.course_id,
        "course_revision": report.course_revision,
        "decision": report.decision,
        "pages_fetched": report.pages_fetched,
        "offline": report.offline,
        "counts": report.counts,
        "known_finding_count": len(report.known_findings),
        "findings": list(finding_summaries),
    }
    review_packet = build_public_course_review_packet(report)
    summary["review_packet"] = review_packet.to_dict()
    if report.refusal_code is not None:
        status = PortfolioLaneStatus.BLOCKED
        controls_caught: tuple[str, ...] = ()
        controls_missed = (report.refusal_code,)
    elif report.passed:
        status = PortfolioLaneStatus.PASSED
        controls_caught = (
            "public-course-adapter-completed",
            "public-course-metadata-boundary",
        )
        controls_missed = ()
    else:
        status = PortfolioLaneStatus.REVIEW_REQUIRED
        controls_caught = (
            "public-course-adapter-completed",
            "public-course-metadata-boundary",
        )
        controls_missed = ()
    return PortfolioLaneResult(
        lane_id=PUBLIC_COURSE_LANE_ID,
        title="Public Claude course evidence",
        status=status,
        controls_caught=controls_caught,
        controls_missed=controls_missed,
        degraded_controls_caught=tuple(
            f"{key}:{value}"
            for key, value in report.counts.items()
            if key
            in {
                "verbatim_not_found",
                "identifier_missing",
                "uncovered",
                "unable_to_check",
            }
            and isinstance(value, int)
            and value > 0
        ),
        evidence_ids=(
            f"course_revision:{report.course_revision or 'unavailable'}",
            f"rows_total:{report.counts['rows_total']}",
            f"pages_fetched:{report.pages_fetched}",
        ),
        human_gate=(
            "Human review is required for unresolved rows before course claims change."
        ),
        reason_code=report.refusal_code,
        summary=summary,
    )


def _run_delivery_path_lane() -> PortfolioLaneResult:
    required_files = {
        "delivery_standard": _REPOSITORY_ROOT / "PRODUCTION_DELIVERY_STANDARD.md",
        "reliability_workflow": _REPOSITORY_ROOT / ".github" / "workflows" / "reliability.yml",
        "security_policy": _REPOSITORY_ROOT / "SECURITY.md",
        "rollback_contract": _REPOSITORY_ROOT / "examples" / "rollback-plan.json",
        "test_suite": _REPOSITORY_ROOT / "tests",
    }
    missing = tuple(
        evidence_id
        for evidence_id, path in required_files.items()
        if not path.exists()
    )
    workflow = required_files["reliability_workflow"]
    if workflow.exists() and "Agent reliability gate" not in workflow.read_text(
        encoding="utf-8"
    ):
        missing += ("workflow_gate",)
    return PortfolioLaneResult(
        lane_id="delivery_path",
        title="Production delivery evidence",
        status=(
            PortfolioLaneStatus.PASSED
            if not missing
            else PortfolioLaneStatus.BLOCKED
        ),
        controls_caught=(
            ("delivery-contract-present",) if not missing else ()
        ),
        controls_missed=missing,
        degraded_controls_caught=(),
        evidence_ids=tuple(required_files),
        human_gate="Release approval, deployment controls, and monitoring remain external.",
    )


def _unavailable_lane(lane_id: str) -> PortfolioLaneResult:
    return PortfolioLaneResult(
        lane_id=lane_id,
        title=lane_id.replace("_", " ").title(),
        status=PortfolioLaneStatus.UNAVAILABLE,
        controls_caught=(),
        controls_missed=("worker_unavailable",),
        degraded_controls_caught=(),
        evidence_ids=(),
        human_gate="No handoff until this lane is rerun successfully.",
        reason_code="worker_unavailable",
    )


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
