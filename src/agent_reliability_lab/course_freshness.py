"""Bounded course-freshness orchestration over the content-assurance pipeline.

The coordinator assigns one course revision to one worker. Workers run the
existing in-memory content pipeline and return metadata-only results. The
coordinator writes inspectable metadata checkpoints and joins independent
results without writing or publishing course content.

This module is intentionally provider-neutral. A private adapter may construct
the request bytes from an internal course, but the public reference inventory
contains synthetic bytes only.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

from .content_pipeline import (
    ContentPipelineReport,
    ContentPipelineRequest,
    PipelineDecision,
    reference_content_pipeline_cases,
    run_content_assurance_pipeline,
)


COURSE_FRESHNESS_VERSION = 1
DEFAULT_MAX_WORKERS = 4
DEFAULT_MAX_COURSES = 50
DEFAULT_MAX_ELAPSED_SECONDS = 30.0


class WorkerStatus(str, Enum):
    """The orchestration status for one delegated course review."""

    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True)
class CourseReviewRequest:
    """The typed handoff from coordinator to one course worker."""

    course_id: str
    course_revision: str
    pipeline_request: ContentPipelineRequest


@dataclass(frozen=True)
class CourseReviewResult:
    """One metadata-only worker result."""

    course_id: str
    course_revision: str
    worker_status: WorkerStatus
    decision: PipelineDecision | None
    abstention_reasons: tuple[str, ...] = ()
    refusal_code: str | None = None
    source_digest: str | None = None
    claim_evidence_ids: tuple[str, ...] = ()
    failure_code: str | None = None

    @property
    def available(self) -> bool:
        """Return whether this worker returned a usable result."""

        return self.worker_status is WorkerStatus.COMPLETED

    def to_dict(self) -> dict[str, object]:
        """Return a report-safe result without course content or worker errors."""

        return {
            "course_id": self.course_id,
            "course_revision": self.course_revision,
            "worker_status": self.worker_status.value,
            "decision": self.decision.value if self.decision is not None else None,
            "abstention_reasons": list(self.abstention_reasons),
            "refusal_code": self.refusal_code,
            "source_digest": self.source_digest,
            "claim_evidence_ids": list(self.claim_evidence_ids),
            "failure_code": self.failure_code,
        }


@dataclass(frozen=True)
class CourseFreshnessReport:
    """The joined result of one bounded course-freshness sweep."""

    results: tuple[CourseReviewResult, ...]
    max_workers: int
    max_courses: int
    max_elapsed_seconds: float
    stop_condition: str
    refusal_code: str | None = None

    @property
    def passed(self) -> bool:
        """Return true only when every assigned worker returned a result."""

        return self.refusal_code is None and all(
            result.available for result in self.results
        )

    @property
    def unavailable_course_ids(self) -> tuple[str, ...]:
        """Return course IDs whose worker result cannot support a conclusion."""

        return tuple(
            result.course_id for result in self.results if not result.available
        )

    def to_dict(self) -> dict[str, object]:
        """Return metadata-only sweep output."""

        return {
            "course_freshness_version": COURSE_FRESHNESS_VERSION,
            "passed": self.passed,
            "results": [result.to_dict() for result in self.results],
            "counts": {
                "requested": len(self.results),
                "completed": sum(result.available for result in self.results),
                "unavailable": len(self.unavailable_course_ids),
            },
            "limits": {
                "max_workers": self.max_workers,
                "max_courses": self.max_courses,
                "max_elapsed_seconds": self.max_elapsed_seconds,
            },
            "stop_condition": self.stop_condition,
            "unavailable_course_ids": list(self.unavailable_course_ids),
            "refusal_code": self.refusal_code,
            "diagnostics": {
                "warnings": [
                    "The coordinator emits course IDs, revisions, decisions, hashes, "
                    "and reason codes only; it does not emit course text."
                ],
                "what_it_does_not_show": (
                    "It does not prove that a course teaches effectively, that a "
                    "source is semantically correct, or that unavailable workers "
                    "would have reached the same decision."
                ),
            },
        }


@dataclass(frozen=True)
class CourseFreshnessCase:
    """A synthetic course fixture and its expected pipeline outcome."""

    course_id: str
    request: CourseReviewRequest
    expected_decision: PipelineDecision
    expected_reason: str | None = None


@dataclass(frozen=True)
class CourseFreshnessSuiteReport:
    """Reference sweep output with expected-control verification."""

    sweep: CourseFreshnessReport
    controls_caught: tuple[str, ...]
    controls_missed: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """Return true when orchestration and every synthetic control pass."""

        return self.sweep.passed and not self.controls_missed

    def to_dict(self) -> dict[str, object]:
        """Return the metadata-only reference suite report."""

        return {
            **self.sweep.to_dict(),
            "passed": self.passed,
            "controls_caught": list(self.controls_caught),
            "controls_missed": list(self.controls_missed),
            "diagnostics": {
                "warnings": [
                    "The suite uses independent synthetic course workers and "
                    "explicit degraded freshness controls."
                ],
                "what_it_does_not_show": (
                    "It does not establish semantic course quality or live-model "
                    "quality."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Render a reviewer-facing freshness summary."""

        lines = [
            "# Course Freshness Sweep",
            "",
            f"Decision: {'PASS' if self.passed else 'BLOCKED'}",
            "",
            "| Course | Worker | Decision | Reasons |",
            "| --- | --- | --- | --- |",
        ]
        for result in self.sweep.results:
            reasons = ", ".join(result.abstention_reasons) or "none"
            decision = result.decision.value if result.decision else "unavailable"
            lines.append(
                f"| `{result.course_id}` | `{result.worker_status.value}` | "
                f"`{decision}` | `{reasons}` |"
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
                "This report contains metadata only; unavailable workers are not treated "
                "as clean results.",
            ]
        )
        return "\n".join(lines)


class CourseFreshnessWorker:
    """Review exactly one course revision through the existing pipeline."""

    def review(self, request: CourseReviewRequest) -> CourseReviewResult:
        """Run one idempotent course review."""

        report = run_content_assurance_pipeline(request.pipeline_request)
        return _worker_result(request, report)


class CourseFreshnessCoordinator:
    """Fan out bounded course workers and join inspectable metadata results."""

    def __init__(
        self,
        *,
        worker: CourseFreshnessWorker | None = None,
        worker_factory: Callable[[], CourseFreshnessWorker] | None = None,
    ) -> None:
        if worker is not None and worker_factory is not None:
            raise ValueError("Provide worker or worker_factory, not both.")
        self._worker = worker
        self._worker_factory = worker_factory or CourseFreshnessWorker

    def sweep(
        self,
        requests: Iterable[CourseReviewRequest],
        *,
        workspace: Path,
        max_workers: int = DEFAULT_MAX_WORKERS,
        max_courses: int = DEFAULT_MAX_COURSES,
        max_elapsed_seconds: float = DEFAULT_MAX_ELAPSED_SECONDS,
    ) -> CourseFreshnessReport:
        """Run the bounded fan-out/join workflow and persist metadata checkpoints."""

        request_tuple = tuple(requests)
        refusal = _validate_limits(
            request_tuple,
            max_workers=max_workers,
            max_courses=max_courses,
            max_elapsed_seconds=max_elapsed_seconds,
        )
        workspace.mkdir(parents=True, exist_ok=True)
        input_dir = workspace / "inputs"
        intermediate_dir = workspace / "intermediate"
        output_dir = workspace / "outputs"
        input_dir.mkdir(exist_ok=True)
        intermediate_dir.mkdir(exist_ok=True)
        output_dir.mkdir(exist_ok=True)
        if refusal is not None:
            report = CourseFreshnessReport(
                results=(),
                max_workers=max_workers,
                max_courses=max_courses,
                max_elapsed_seconds=max_elapsed_seconds,
                stop_condition="refused-before-fanout",
                refusal_code=refusal,
            )
            _write_json(output_dir / "sweep.json", report.to_dict())
            return report

        for request in request_tuple:
            _write_json(
                input_dir / f"{request.course_id}.json",
                _request_metadata(request),
            )
        events_path = intermediate_dir / "orchestration-events.jsonl"
        started = time.monotonic()
        futures: dict[str, Future[CourseReviewResult]] = {}
        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            for request in request_tuple:
                _append_event(
                    events_path,
                    {
                        "direction": "orchestrator_to_worker",
                        "course_id": request.course_id,
                        "event": "dispatched",
                    },
                )
                futures[request.course_id] = executor.submit(
                    self._run_worker,
                    request,
                )

            results: list[CourseReviewResult] = []
            deadline = started + max_elapsed_seconds
            for request in request_tuple:
                future = futures[request.course_id]
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    result = _unavailable_result(request, "worker_timeout")
                else:
                    try:
                        result = future.result(timeout=remaining)
                    except TimeoutError:
                        result = _unavailable_result(request, "worker_timeout")
                    except Exception:
                        result = _unavailable_result(request, "worker_failed")
                results.append(result)
                _append_event(
                    events_path,
                    {
                        "direction": "worker_to_orchestrator",
                        "course_id": request.course_id,
                        "event": result.worker_status.value,
                        "decision": (
                            result.decision.value
                            if result.decision is not None
                            else None
                        ),
                    },
                )
                _write_json(
                    intermediate_dir / f"{request.course_id}.json",
                    result.to_dict(),
                )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        report = CourseFreshnessReport(
            results=tuple(results),
            max_workers=max_workers,
            max_courses=max_courses,
            max_elapsed_seconds=max_elapsed_seconds,
            stop_condition=(
                "completed-with-unavailable-workers"
                if any(not result.available for result in results)
                else "completed"
            ),
        )
        _write_json(output_dir / "sweep.json", report.to_dict())
        return report

    def _run_worker(self, request: CourseReviewRequest) -> CourseReviewResult:
        worker = self._worker or self._worker_factory()
        return worker.review(request)


def reference_course_freshness_cases() -> tuple[CourseFreshnessCase, ...]:
    """Build synthetic course revisions from the bounded pipeline controls."""

    pipeline_cases = reference_content_pipeline_cases()
    return tuple(
        CourseFreshnessCase(
            course_id=f"course-{case.case_id}",
            request=CourseReviewRequest(
                course_id=f"course-{case.case_id}",
                course_revision=case.request.artifact_revision,
                pipeline_request=case.request,
            ),
            expected_decision=case.expected_decision,
            expected_reason=case.expected_reason,
        )
        for case in pipeline_cases
    )


def run_reference_course_freshness_suite(
    *,
    workspace: Path,
    max_workers: int = DEFAULT_MAX_WORKERS,
    max_courses: int = DEFAULT_MAX_COURSES,
    max_elapsed_seconds: float = DEFAULT_MAX_ELAPSED_SECONDS,
) -> CourseFreshnessSuiteReport:
    """Run the synthetic course inventory through the coordinator."""

    cases = reference_course_freshness_cases()
    sweep = CourseFreshnessCoordinator().sweep(
        (case.request for case in cases),
        workspace=workspace,
        max_workers=max_workers,
        max_courses=max_courses,
        max_elapsed_seconds=max_elapsed_seconds,
    )
    by_course = {result.course_id: result for result in sweep.results}
    caught: list[str] = []
    missed: list[str] = []
    for case in cases:
        result = by_course.get(case.course_id)
        expected = (
            result is not None
            and result.decision is case.expected_decision
        )
        reason_found = (
            case.expected_reason is None
            or (
                result is not None
                and (
                    case.expected_reason in result.abstention_reasons
                    or case.expected_reason == result.refusal_code
                )
            )
        )
        if expected and reason_found:
            caught.append(case.course_id)
        else:
            missed.append(case.course_id)
    return CourseFreshnessSuiteReport(
        sweep=sweep,
        controls_caught=tuple(caught),
        controls_missed=tuple(missed),
    )


def _worker_result(
    request: CourseReviewRequest,
    report: ContentPipelineReport,
) -> CourseReviewResult:
    return CourseReviewResult(
        course_id=request.course_id,
        course_revision=request.course_revision,
        worker_status=WorkerStatus.COMPLETED,
        decision=PipelineDecision(report.decision.value),
        abstention_reasons=report.abstention_reasons,
        refusal_code=report.refusal_code,
        source_digest=report.source_digest,
        claim_evidence_ids=report.claim_evidence_ids,
    )


def _unavailable_result(
    request: CourseReviewRequest,
    failure_code: str,
) -> CourseReviewResult:
    return CourseReviewResult(
        course_id=request.course_id,
        course_revision=request.course_revision,
        worker_status=(
            WorkerStatus.TIMED_OUT
            if failure_code == "worker_timeout"
            else WorkerStatus.FAILED
        ),
        decision=None,
        failure_code=failure_code,
    )


def _validate_limits(
    requests: tuple[CourseReviewRequest, ...],
    *,
    max_workers: int,
    max_courses: int,
    max_elapsed_seconds: float,
) -> str | None:
    if not requests:
        return "empty_course_inventory"
    if len(requests) > max_courses:
        return "course_limit_exceeded"
    if max_workers < 1:
        return "invalid_worker_limit"
    if max_elapsed_seconds <= 0:
        return "invalid_elapsed_limit"
    course_ids = [request.course_id for request in requests]
    if len(course_ids) != len(set(course_ids)):
        return "duplicate_course_id"
    if any(not request.course_id or not request.course_revision for request in requests):
        return "invalid_course_identity"
    return None


def _request_metadata(request: CourseReviewRequest) -> dict[str, object]:
    """Return the safe input checkpoint without source bytes."""

    pipeline = request.pipeline_request
    return {
        "course_id": request.course_id,
        "course_revision": request.course_revision,
        "pipeline_case_id": pipeline.case_id,
        "source_id": pipeline.source_id,
        "claim_ids": [claim.claim_id for claim in pipeline.claims],
        "section_ids": [claim.section_id for claim in pipeline.claims],
    }


def _append_event(path: Path, value: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
