"""Bounded review packets for technical-course freshness findings.

The course doctor turns one course-freshness result into a metadata-only
review packet and keeps human adjudication separate from automated evidence.
It accepts local source files only through an explicit root directory, reads
their bytes in memory, and never emits source text or source paths.

Design rules:

1. A packet is emitted for every requested course, including failed or
   not-reviewed work.
2. A generated claim is a proposal identifier, not permission to publish.
3. Approval is a separate human decision and cannot approve unresolved findings.
4. Counts reconcile requested, completed, failed, timed-out, and not-reviewed
   work; a capped run says so explicitly.
5. The public reference path uses synthetic fixtures only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping

from .claim_proposals import (
    ClaimProposalRequest,
    ClaimProposalWorker,
    ProposalStatus,
    SyntheticClaimProposalWorker,
    proposed_pipeline_claims,
    validate_claim_proposal_result,
)
from .content_pipeline import (
    DEFAULT_MAX_SOURCE_BYTES,
    ContentPipelineRequest,
    PipelineClaim,
    PipelineDecision,
)
from .course_freshness import (
    CourseFreshnessCoordinator,
    CourseReviewRequest,
    CourseReviewResult,
    WorkerStatus,
    reference_course_freshness_cases,
)


COURSE_DOCTOR_VERSION = 1
DEFAULT_MAX_REVIEW_COURSES = 50


class ReviewDisposition(str, Enum):
    """The automated recommendation or human decision for a packet."""

    APPROVED = "approved"
    NEEDS_REVISION = "needs_revision"
    BLOCKED = "blocked"
    NOT_REVIEWED = "not_reviewed"


@dataclass(frozen=True)
class CourseDoctorRequest:
    """One course request, including any safe preflight refusal."""

    course_id: str
    course_revision: str
    freshness_request: CourseReviewRequest | None = None
    preflight_refusal_code: str | None = None
    source_ref: str | None = None
    proposal_status: ProposalStatus = ProposalStatus.COMPLETED
    proposal_refusal_code: str | None = None
    claim_proposal_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.course_id or not self.course_revision:
            raise ValueError("Course identity is required.")
        if (self.freshness_request is None) == (
            self.preflight_refusal_code is None
        ):
            raise ValueError(
                "Provide exactly one freshness request or preflight refusal."
            )


@dataclass(frozen=True)
class ReviewFinding:
    """One metadata-only finding that a human can adjudicate."""

    finding_id: str
    reason_code: str
    evidence_ids: tuple[str, ...] = ()
    status: str = "open"

    def to_dict(self) -> dict[str, object]:
        """Return the safe finding representation."""

        return {
            "finding_id": self.finding_id,
            "reason_code": self.reason_code,
            "evidence_ids": list(self.evidence_ids),
            "status": self.status,
            "what_it_does_not_show": (
                "This finding does not reproduce course text or prove that "
                "the course teaches effectively."
            ),
        }


@dataclass(frozen=True)
class ReviewPacket:
    """A metadata-only course review packet."""

    packet_id: str
    course_id: str
    course_revision: str
    worker_status: WorkerStatus
    recommended_disposition: ReviewDisposition
    claim_proposal_ids: tuple[str, ...]
    findings: tuple[ReviewFinding, ...] = ()
    source_digest: str | None = None
    claim_evidence_ids: tuple[str, ...] = ()
    failure_code: str | None = None
    proposal_status: ProposalStatus = ProposalStatus.COMPLETED
    proposal_refusal_code: str | None = None
    human_approval_required: bool = True

    @property
    def ready_for_human_review(self) -> bool:
        """Return whether a worker produced enough metadata for review."""

        return self.worker_status is WorkerStatus.COMPLETED

    def to_dict(self) -> dict[str, object]:
        """Return output safe for local files, CI, and pull-request artifacts."""

        return {
            "course_doctor_version": COURSE_DOCTOR_VERSION,
            "packet_id": self.packet_id,
            "course_id": self.course_id,
            "course_revision": self.course_revision,
            "worker_status": self.worker_status.value,
            "recommended_disposition": self.recommended_disposition.value,
            "claim_proposal_ids": list(self.claim_proposal_ids),
            "findings": [finding.to_dict() for finding in self.findings],
            "source_digest": self.source_digest,
            "claim_evidence_ids": list(self.claim_evidence_ids),
            "failure_code": self.failure_code,
            "proposal_status": self.proposal_status.value,
            "proposal_refusal_code": self.proposal_refusal_code,
            "human_approval_required": self.human_approval_required,
            "ready_for_human_review": self.ready_for_human_review,
            "diagnostics": {
                "warnings": [
                    "Claim proposals are unverified identifiers, not publication "
                    "authority.",
                    "The packet contains metadata only; source content and paths "
                    "remain local to the adapter process.",
                ],
                "what_it_does_not_show": (
                    "It does not prove semantic truth, course effectiveness, "
                    "reviewer approval, or permission to publish."
                ),
            },
        }


@dataclass(frozen=True)
class ReviewPacketReport:
    """Reconciled output for one bounded packet-generation run."""

    packets: tuple[ReviewPacket, ...]
    max_courses: int
    stop_condition: str
    refusal_code: str | None = None
    truncated: bool = False
    truncation_limit: int | None = None

    @property
    def passed(self) -> bool:
        """Return true only when every requested course produced a reviewable packet."""

        return (
            self.refusal_code is None
            and not self.truncated
            and all(packet.ready_for_human_review for packet in self.packets)
        )

    @property
    def counts(self) -> dict[str, int | bool]:
        """Return counts whose denominator exposes missing work."""

        completed = sum(
            packet.worker_status is WorkerStatus.COMPLETED
            for packet in self.packets
        )
        failed = sum(packet.worker_status is WorkerStatus.FAILED for packet in self.packets)
        timed_out = sum(
            packet.worker_status is WorkerStatus.TIMED_OUT
            for packet in self.packets
        )
        not_reviewed = sum(
            packet.recommended_disposition is ReviewDisposition.NOT_REVIEWED
            for packet in self.packets
        )
        requested = len(self.packets)
        emitted = len(self.packets)
        return {
            "requested": requested,
            "packets_emitted": emitted,
            "completed": completed,
            "failed": failed,
            "timed_out": timed_out,
            "not_reviewed": not_reviewed,
            "truncated": self.truncated,
            "counts_reconcile": emitted == completed + failed + timed_out,
        }

    def to_dict(self) -> dict[str, object]:
        """Return the metadata-only packet report."""

        return {
            "course_doctor_version": COURSE_DOCTOR_VERSION,
            "passed": self.passed,
            "packets": [packet.to_dict() for packet in self.packets],
            "counts": self.counts,
            "limits": {"max_courses": self.max_courses},
            "stop_condition": self.stop_condition,
            "refusal_code": self.refusal_code,
            "truncated": self.truncated,
            "truncation_limit": self.truncation_limit,
            "diagnostics": {
                "warnings": [
                    "Every requested course receives a packet, including "
                    "not-reviewed results.",
                    "No packet contains source text, source paths, prompts, or "
                    "provider output.",
                ],
                "what_it_does_not_show": (
                    "A generated packet is not human approval and does not "
                    "authorize a content change or publication."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Render a reviewer-facing packet summary without source content."""

        lines = [
            "# Course Doctor Review Packets",
            "",
            f"Workflow: {'PASS' if self.passed else 'BLOCKED'}",
            "",
            "| Course | Worker | Recommendation | Findings |",
            "| --- | --- | --- | --- |",
        ]
        for packet in self.packets:
            lines.append(
                f"| `{packet.course_id}` | `{packet.worker_status.value}` | "
                f"`{packet.recommended_disposition.value}` | "
                f"`{len(packet.findings)}` |"
            )
        lines.extend(
            [
                "",
                f"Counts: `{json.dumps(self.counts, sort_keys=True)}`",
                "",
                "Human approval remains required before any future content change.",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class AdjudicationResult:
    """An append-only human decision attempt for one review packet."""

    packet_id: str
    course_id: str
    course_revision: str
    reviewer_id: str
    requested_disposition: ReviewDisposition
    accepted: bool
    refusal_code: str | None = None
    basis_finding_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a metadata-only adjudication record."""

        return {
            "course_doctor_version": COURSE_DOCTOR_VERSION,
            "packet_id": self.packet_id,
            "course_id": self.course_id,
            "course_revision": self.course_revision,
            "reviewer_id": self.reviewer_id,
            "requested_disposition": self.requested_disposition.value,
            "accepted": self.accepted,
            "refusal_code": self.refusal_code,
            "basis_finding_ids": list(self.basis_finding_ids),
            "diagnostics": {
                "warnings": [
                    "This record identifies a human decision attempt; it contains "
                    "no course content."
                ],
                "what_it_does_not_show": (
                    "It does not prove the reviewer had subject-matter expertise "
                    "or that a publisher executed a later change."
                ),
            },
        }


@dataclass(frozen=True)
class LocalCourseSourceSpec:
    """Metadata needed to construct one local source-backed course request."""

    course_id: str
    course_revision: str
    source_path: str
    case_id: str
    artifact_id: str
    artifact_revision: str
    artifact_digest: str
    reuse_key: str
    source_id: str
    authority: str
    source_url: str
    age_seconds: float | None
    claims: tuple[PipelineClaim, ...]
    approved_source_ids: tuple[str, ...]
    max_age_seconds: float
    expected_source_digest: str | None = None
    max_source_bytes: int = DEFAULT_MAX_SOURCE_BYTES


@dataclass(frozen=True)
class LocalCourseSourceLoad:
    """Safe result of one local source read."""

    course_id: str
    course_revision: str
    request: CourseDoctorRequest | None
    refusal_code: str | None = None


class LocalCourseSourceAdapter:
    """Read one bounded local source under an explicit root directory."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def load(self, spec: LocalCourseSourceSpec) -> LocalCourseSourceLoad:
        """Read bytes in memory and return a typed course request."""

        path = Path(spec.source_path)
        if path.is_absolute():
            return _source_refusal(spec, "source_path_not_relative")
        candidate = (self._root / path).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError:
            return _source_refusal(spec, "source_path_outside_root")
        if not candidate.exists() or not candidate.is_file():
            return _source_refusal(spec, "source_file_missing")
        try:
            source_bytes = candidate.read_bytes()
        except OSError:
            return _source_refusal(spec, "source_read_failed")
        if len(source_bytes) > spec.max_source_bytes:
            return _source_refusal(spec, "source_size_exceeded")

        pipeline_request = ContentPipelineRequest(
            case_id=spec.case_id,
            artifact_id=spec.artifact_id,
            artifact_revision=spec.artifact_revision,
            artifact_digest=spec.artifact_digest,
            reuse_key=spec.reuse_key,
            source_id=spec.source_id,
            authority=spec.authority,
            source_url=spec.source_url,
            source_bytes=source_bytes,
            age_seconds=spec.age_seconds,
            claims=spec.claims,
            approved_source_ids=spec.approved_source_ids,
            max_age_seconds=spec.max_age_seconds,
            expected_source_digest=spec.expected_source_digest,
            max_source_bytes=spec.max_source_bytes,
        )
        freshness_request = CourseReviewRequest(
            course_id=spec.course_id,
            course_revision=spec.course_revision,
            pipeline_request=pipeline_request,
        )
        return LocalCourseSourceLoad(
            course_id=spec.course_id,
            course_revision=spec.course_revision,
            request=CourseDoctorRequest(
                course_id=spec.course_id,
                course_revision=spec.course_revision,
                freshness_request=freshness_request,
            ),
        )


class CourseDoctorCoordinator:
    """Generate review packets around the existing bounded freshness coordinator."""

    def __init__(
        self,
        *,
        freshness_coordinator: CourseFreshnessCoordinator | None = None,
        proposal_worker: ClaimProposalWorker | None = None,
    ) -> None:
        self._freshness_coordinator = (
            freshness_coordinator or CourseFreshnessCoordinator()
        )
        self._proposal_worker = proposal_worker or SyntheticClaimProposalWorker()

    def review(
        self,
        requests: Iterable[CourseDoctorRequest],
        *,
        workspace: Path,
        max_courses: int = DEFAULT_MAX_REVIEW_COURSES,
        max_workers: int = 4,
        max_elapsed_seconds: float = 30.0,
    ) -> ReviewPacketReport:
        """Generate packets and retain every requested outcome."""

        request_tuple = tuple(requests)
        refusal = _validate_doctor_limits(
            request_tuple,
            max_courses=max_courses,
            max_workers=max_workers,
            max_elapsed_seconds=max_elapsed_seconds,
        )
        workspace.mkdir(parents=True, exist_ok=True)
        input_dir = workspace / "inputs"
        intermediate_dir = workspace / "intermediate"
        output_dir = workspace / "outputs"
        events_path = intermediate_dir / "review-events.jsonl"
        input_dir.mkdir(exist_ok=True)
        intermediate_dir.mkdir(exist_ok=True)
        output_dir.mkdir(exist_ok=True)
        for request in request_tuple:
            _write_json(
                input_dir / f"{request.course_id}.json",
                _doctor_request_metadata(request),
            )
        if refusal is not None:
            report = ReviewPacketReport(
                packets=(),
                max_courses=max_courses,
                stop_condition="refused-before-review",
                refusal_code=refusal,
            )
            _write_json(output_dir / "review-packets.json", report.to_dict())
            return report

        prepared_requests, proposal_events = _prepare_proposals(
            request_tuple,
            worker=self._proposal_worker,
        )
        for event in proposal_events:
            _append_event(events_path, event)
        valid_requests = tuple(
            request.freshness_request
            for request in prepared_requests
            if request.freshness_request is not None
        )
        freshness_report = self._freshness_coordinator.sweep(
            valid_requests,
            workspace=workspace / "freshness",
            max_workers=max_workers,
            max_courses=max_courses,
            max_elapsed_seconds=max_elapsed_seconds,
        )
        results = {
            result.course_id: result for result in freshness_report.results
        }
        packets = tuple(
            _packet_for_request(request, results.get(request.course_id))
            for request in prepared_requests
        )
        for packet in packets:
            _append_event(
                events_path,
                {
                    "event": "packet_emitted",
                    "packet_id": packet.packet_id,
                    "course_id": packet.course_id,
                    "course_revision": packet.course_revision,
                    "worker_status": packet.worker_status.value,
                    "recommended_disposition": (
                        packet.recommended_disposition.value
                    ),
                    "finding_ids": [
                        finding.finding_id for finding in packet.findings
                    ],
                },
            )
            _write_json(
                intermediate_dir / f"{packet.course_id}.json",
                packet.to_dict(),
            )
        report = ReviewPacketReport(
            packets=packets,
            max_courses=max_courses,
            stop_condition=(
                "completed-with-not-reviewed-packets"
                if any(
                    packet.recommended_disposition
                    is ReviewDisposition.NOT_REVIEWED
                    for packet in packets
                )
                else "completed"
            ),
        )
        _write_json(output_dir / "review-packets.json", report.to_dict())
        return report


@dataclass(frozen=True)
class CourseDoctorCase:
    """A synthetic packet case and its expected recommendation."""

    course_id: str
    request: CourseDoctorRequest
    expected_disposition: ReviewDisposition
    expected_reason: str | None = None


@dataclass(frozen=True)
class CourseDoctorSuiteReport:
    """Reference packet workflow with deliberate controls."""

    report: ReviewPacketReport
    controls_caught: tuple[str, ...]
    controls_missed: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """Return true when packet generation and all controls pass."""

        return self.report.passed and not self.controls_missed

    def to_dict(self) -> dict[str, object]:
        """Return metadata-only reference output."""

        return {
            **self.report.to_dict(),
            "passed": self.passed,
            "controls_caught": list(self.controls_caught),
            "controls_missed": list(self.controls_missed),
            "diagnostics": {
                "warnings": [
                    "The suite tests evidence-backed review packets, not "
                    "semantic content truth."
                ],
                "what_it_does_not_show": (
                    "It does not authorize publication or establish live-model "
                    "quality."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Render the safe suite summary."""

        lines = [
            "# Course Doctor Review Workflow",
            "",
            f"Decision: {'PASS' if self.passed else 'BLOCKED'}",
            "",
            self.report.to_markdown(),
            "",
            "Controls caught: "
            + (", ".join(f"`{item}`" for item in self.controls_caught) or "none"),
            "",
            "Controls missed: "
            + (", ".join(f"`{item}`" for item in self.controls_missed) or "none"),
        ]
        return "\n".join(lines)


def adjudicate_packet(
    packet: ReviewPacket,
    *,
    reviewer_id: str,
    disposition: ReviewDisposition,
) -> AdjudicationResult:
    """Apply the human gate without changing the packet or course content."""

    if not reviewer_id or not _safe_identifier(reviewer_id):
        return AdjudicationResult(
            packet_id=packet.packet_id,
            course_id=packet.course_id,
            course_revision=packet.course_revision,
            reviewer_id=reviewer_id,
            requested_disposition=disposition,
            accepted=False,
            refusal_code="invalid_reviewer_id",
            basis_finding_ids=tuple(finding.finding_id for finding in packet.findings),
        )
    unresolved = tuple(finding.finding_id for finding in packet.findings)
    if disposition is ReviewDisposition.APPROVED and unresolved:
        return AdjudicationResult(
            packet_id=packet.packet_id,
            course_id=packet.course_id,
            course_revision=packet.course_revision,
            reviewer_id=reviewer_id,
            requested_disposition=disposition,
            accepted=False,
            refusal_code="unresolved_findings",
            basis_finding_ids=unresolved,
        )
    if (
        disposition is ReviewDisposition.APPROVED
        and packet.recommended_disposition is not ReviewDisposition.APPROVED
    ):
        return AdjudicationResult(
            packet_id=packet.packet_id,
            course_id=packet.course_id,
            course_revision=packet.course_revision,
            reviewer_id=reviewer_id,
            requested_disposition=disposition,
            accepted=False,
            refusal_code="packet_not_approvable",
            basis_finding_ids=unresolved,
        )
    return AdjudicationResult(
        packet_id=packet.packet_id,
        course_id=packet.course_id,
        course_revision=packet.course_revision,
        reviewer_id=reviewer_id,
        requested_disposition=disposition,
        accepted=True,
        basis_finding_ids=unresolved,
    )


def append_adjudication(path: Path, result: AdjudicationResult) -> None:
    """Append one metadata-only adjudication attempt without rewriting history."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(result.to_dict(), sort_keys=True) + "\n")


def reference_course_doctor_cases() -> tuple[CourseDoctorCase, ...]:
    """Return five synthetic packet cases with expected dispositions."""

    expected = {
        "course-pipeline-approved": ReviewDisposition.APPROVED,
        "course-pipeline-unsupported-claim": ReviewDisposition.NEEDS_REVISION,
        "course-pipeline-stale-source": ReviewDisposition.NEEDS_REVISION,
        "course-pipeline-source-drift": ReviewDisposition.NEEDS_REVISION,
        "course-pipeline-unapproved-host": ReviewDisposition.BLOCKED,
    }
    return tuple(
        CourseDoctorCase(
            course_id=case.course_id,
            request=CourseDoctorRequest(
                course_id=case.request.course_id,
                course_revision=case.request.course_revision,
                freshness_request=case.request,
            ),
            expected_disposition=expected[case.course_id],
            expected_reason=case.expected_reason,
        )
        for case in reference_course_freshness_cases()
    )


def run_reference_course_doctor_suite(
    *,
    workspace: Path,
    max_courses: int = DEFAULT_MAX_REVIEW_COURSES,
    max_workers: int = 4,
    max_elapsed_seconds: float = 30.0,
) -> CourseDoctorSuiteReport:
    """Run the synthetic course inventory through the review workflow."""

    cases = reference_course_doctor_cases()
    report = CourseDoctorCoordinator().review(
        (case.request for case in cases),
        workspace=workspace,
        max_courses=max_courses,
        max_workers=max_workers,
        max_elapsed_seconds=max_elapsed_seconds,
    )
    by_course = {packet.course_id: packet for packet in report.packets}
    caught: list[str] = []
    missed: list[str] = []
    for case in cases:
        packet = by_course.get(case.course_id)
        expected = (
            packet is not None
            and packet.recommended_disposition is case.expected_disposition
        )
        reason_found = (
            case.expected_reason is None
            or (
                packet is not None
                and any(
                    finding.reason_code == case.expected_reason
                    for finding in packet.findings
                )
            )
        )
        if expected and reason_found:
            caught.append(case.course_id)
        else:
            missed.append(case.course_id)
    return CourseDoctorSuiteReport(
        report=report,
        controls_caught=tuple(caught),
        controls_missed=tuple(missed),
    )


def load_local_course_manifest(
    manifest_path: Path,
    *,
    source_root: Path,
) -> tuple[CourseDoctorRequest, ...]:
    """Load a metadata-only manifest and read no source bytes yet."""

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = payload.get("courses") if isinstance(payload, dict) else payload
    if not isinstance(records, list) or not records:
        raise ValueError("Manifest must contain a non-empty courses list.")
    requests: list[CourseDoctorRequest] = []
    adapter = LocalCourseSourceAdapter(source_root)
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Every manifest course must be an object.")
        spec = _local_spec_from_dict(record)
        loaded = adapter.load(spec)
        if loaded.request is None:
            raise ValueError("Local source adapter returned no request.")
        requests.append(loaded.request)
    return tuple(requests)


def _prepare_proposals(
    requests: tuple[CourseDoctorRequest, ...],
    *,
    worker: ClaimProposalWorker,
) -> tuple[tuple[CourseDoctorRequest, ...], tuple[dict[str, object], ...]]:
    """Run and validate the upstream proposal stage before evidence review."""

    prepared: list[CourseDoctorRequest] = []
    events: list[dict[str, object]] = []
    for request in requests:
        if request.freshness_request is None:
            prepared.append(request)
            continue
        pipeline = request.freshness_request.pipeline_request
        proposal_request = ClaimProposalRequest(
            course_id=request.course_id,
            course_revision=request.course_revision,
            source_id=pipeline.source_id,
            source_bytes=pipeline.source_bytes,
            known_claims=pipeline.claims,
            required_claim_ids=tuple(claim.claim_id for claim in pipeline.claims),
        )
        events.append(
            {
                "direction": "orchestrator_to_proposal_worker",
                "course_id": request.course_id,
                "event": "proposal_requested",
                "required_claim_count": len(proposal_request.required_claim_ids),
            }
        )
        try:
            result = worker.propose(proposal_request)
        except Exception:
            prepared.append(
                replace(
                    request,
                    freshness_request=None,
                    preflight_refusal_code="proposal_worker_failed",
                    proposal_status=ProposalStatus.FAILED,
                    proposal_refusal_code="proposal_worker_failed",
                )
            )
            events.append(
                {
                    "direction": "proposal_worker_to_orchestrator",
                    "course_id": request.course_id,
                    "event": "proposal_worker_failed",
                }
            )
            continue
        validated = validate_claim_proposal_result(proposal_request, result)
        proposal_ids = tuple(
            proposal.proposal_id for proposal in validated.proposals
        )
        events.append(
            {
                "direction": "proposal_worker_to_orchestrator",
                "course_id": request.course_id,
                "event": validated.status.value,
                "proposal_count": len(validated.proposals),
                "refusal_code": validated.refusal_code,
            }
        )
        if not validated.usable:
            code = validated.refusal_code or validated.failure_code
            prepared.append(
                replace(
                    request,
                    freshness_request=None,
                    preflight_refusal_code=f"proposal_{code or 'failed'}",
                    proposal_status=validated.status,
                    proposal_refusal_code=code or "proposal_failed",
                    claim_proposal_ids=proposal_ids,
                )
            )
            continue
        proposed_claims = proposed_pipeline_claims(proposal_request, validated)
        prepared.append(
            replace(
                request,
                freshness_request=replace(
                    request.freshness_request,
                    pipeline_request=replace(
                        pipeline,
                        claims=proposed_claims,
                    ),
                ),
                claim_proposal_ids=proposal_ids,
                proposal_status=validated.status,
                proposal_refusal_code=None,
            )
        )
    return tuple(prepared), tuple(events)


def _packet_for_request(
    request: CourseDoctorRequest,
    result: CourseReviewResult | None,
) -> ReviewPacket:
    proposal_ids = _proposal_ids(request)
    packet_id = _packet_id(request.course_id, request.course_revision)
    if request.preflight_refusal_code is not None:
        proposal_refusal = request.proposal_status is ProposalStatus.REFUSED
        disposition = (
            ReviewDisposition.BLOCKED
            if proposal_refusal
            else ReviewDisposition.NOT_REVIEWED
        )
        return ReviewPacket(
            packet_id=packet_id,
            course_id=request.course_id,
            course_revision=request.course_revision,
            worker_status=WorkerStatus.FAILED,
            recommended_disposition=disposition,
            claim_proposal_ids=proposal_ids,
            findings=(
                ReviewFinding(
                    finding_id=f"{packet_id}:source-preflight",
                    reason_code=request.preflight_refusal_code,
                ),
            ),
            failure_code=request.preflight_refusal_code,
            proposal_status=request.proposal_status,
            proposal_refusal_code=request.proposal_refusal_code,
        )
    if result is None:
        return ReviewPacket(
            packet_id=packet_id,
            course_id=request.course_id,
            course_revision=request.course_revision,
            worker_status=WorkerStatus.FAILED,
            recommended_disposition=ReviewDisposition.NOT_REVIEWED,
            claim_proposal_ids=proposal_ids,
            findings=(
                ReviewFinding(
                    finding_id=f"{packet_id}:worker-result-missing",
                    reason_code="worker_result_missing",
                ),
            ),
            failure_code="worker_result_missing",
            proposal_status=request.proposal_status,
            proposal_refusal_code=request.proposal_refusal_code,
        )
    if result.worker_status is not WorkerStatus.COMPLETED:
        return ReviewPacket(
            packet_id=packet_id,
            course_id=request.course_id,
            course_revision=request.course_revision,
            worker_status=result.worker_status,
            recommended_disposition=ReviewDisposition.NOT_REVIEWED,
            claim_proposal_ids=proposal_ids,
            findings=(
                ReviewFinding(
                    finding_id=f"{packet_id}:worker-unavailable",
                    reason_code=result.failure_code or "worker_unavailable",
                ),
            ),
            failure_code=result.failure_code or "worker_unavailable",
            proposal_status=request.proposal_status,
            proposal_refusal_code=request.proposal_refusal_code,
        )
    findings = tuple(
        ReviewFinding(
            finding_id=f"{packet_id}:{reason}",
            reason_code=reason,
            evidence_ids=result.claim_evidence_ids,
        )
        for reason in result.abstention_reasons
    )
    if result.refusal_code is not None:
        findings += (
            ReviewFinding(
                finding_id=f"{packet_id}:{result.refusal_code}",
                reason_code=result.refusal_code,
                evidence_ids=result.claim_evidence_ids,
            ),
        )
    if result.decision is PipelineDecision.APPROVED:
        disposition = ReviewDisposition.APPROVED
    elif result.decision is PipelineDecision.ABSTAIN:
        disposition = ReviewDisposition.NEEDS_REVISION
    else:
        disposition = ReviewDisposition.BLOCKED
    return ReviewPacket(
        packet_id=packet_id,
        course_id=request.course_id,
        course_revision=request.course_revision,
        worker_status=result.worker_status,
        recommended_disposition=disposition,
        claim_proposal_ids=proposal_ids,
        findings=findings,
        source_digest=result.source_digest,
        claim_evidence_ids=result.claim_evidence_ids,
        failure_code=result.refusal_code,
        proposal_status=request.proposal_status,
        proposal_refusal_code=request.proposal_refusal_code,
    )


def _proposal_ids(request: CourseDoctorRequest) -> tuple[str, ...]:
    if request.claim_proposal_ids:
        return request.claim_proposal_ids
    if request.freshness_request is None:
        return ()
    return tuple(
        f"{request.course_id}:{claim.claim_id}"
        for claim in request.freshness_request.pipeline_request.claims
    )


def _packet_id(course_id: str, course_revision: str) -> str:
    digest = hashlib.sha256(
        f"{course_id}:{course_revision}".encode("utf-8")
    ).hexdigest()[:16]
    return f"packet:{course_id}:{digest}"


def _source_refusal(
    spec: LocalCourseSourceSpec,
    refusal_code: str,
) -> LocalCourseSourceLoad:
    return LocalCourseSourceLoad(
        course_id=spec.course_id,
        course_revision=spec.course_revision,
        request=CourseDoctorRequest(
            course_id=spec.course_id,
            course_revision=spec.course_revision,
            preflight_refusal_code=refusal_code,
        ),
        refusal_code=refusal_code,
    )


def _local_spec_from_dict(record: Mapping[str, object]) -> LocalCourseSourceSpec:
    claims_value = record.get("claims")
    if not isinstance(claims_value, list):
        raise ValueError("Manifest claims must be a list.")
    claims: list[PipelineClaim] = []
    for claim in claims_value:
        if not isinstance(claim, dict):
            raise ValueError("Manifest claim must be an object.")
        claims.append(
            PipelineClaim(
                claim_id=_required_string(claim, "claim_id"),
                section_id=_required_string(claim, "section_id"),
                support_status=_required_string(claim, "support_status"),
            )
        )
    approved = record.get("approved_source_ids")
    if not isinstance(approved, list) or not all(
        isinstance(value, str) for value in approved
    ):
        raise ValueError("Manifest approved_source_ids must be a string list.")
    return LocalCourseSourceSpec(
        course_id=_required_string(record, "course_id"),
        course_revision=_required_string(record, "course_revision"),
        source_path=_required_string(record, "source_path"),
        case_id=_required_string(record, "case_id"),
        artifact_id=_required_string(record, "artifact_id"),
        artifact_revision=_required_string(record, "artifact_revision"),
        artifact_digest=_required_string(record, "artifact_digest"),
        reuse_key=_required_string(record, "reuse_key"),
        source_id=_required_string(record, "source_id"),
        authority=_required_string(record, "authority"),
        source_url=_required_string(record, "source_url"),
        age_seconds=_optional_float(record.get("age_seconds")),
        claims=tuple(claims),
        approved_source_ids=tuple(approved),
        max_age_seconds=_required_float(record, "max_age_seconds"),
        expected_source_digest=_optional_string(
            record.get("expected_source_digest")
        ),
        max_source_bytes=int(
            record.get("max_source_bytes", DEFAULT_MAX_SOURCE_BYTES)
        ),
    )


def _required_string(record: Mapping[str, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Manifest field {key} must be a non-empty string.")
    return value


def _required_float(record: Mapping[str, object], key: str) -> float:
    value = record.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"Manifest field {key} must be numeric.")
    return float(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError("Manifest optional age_seconds must be numeric.")
    return float(value)


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Manifest optional expected_source_digest must be a string.")
    return value


def _validate_doctor_limits(
    requests: tuple[CourseDoctorRequest, ...],
    *,
    max_courses: int,
    max_workers: int,
    max_elapsed_seconds: float,
) -> str | None:
    if not requests:
        return "empty_course_inventory"
    if max_courses < 1:
        return "invalid_course_limit"
    if len(requests) > max_courses:
        return "course_limit_exceeded"
    if max_workers < 1:
        return "invalid_worker_limit"
    if max_elapsed_seconds <= 0:
        return "invalid_elapsed_limit"
    course_ids = [request.course_id for request in requests]
    if len(course_ids) != len(set(course_ids)):
        return "duplicate_course_id"
    return None


def _doctor_request_metadata(request: CourseDoctorRequest) -> dict[str, object]:
    """Return an input checkpoint without source paths or source bytes."""

    if request.freshness_request is None:
        return {
            "course_id": request.course_id,
            "course_revision": request.course_revision,
            "preflight_refusal_code": request.preflight_refusal_code,
            "proposal_status": request.proposal_status.value,
            "claim_proposal_ids": list(request.claim_proposal_ids),
        }
    pipeline = request.freshness_request.pipeline_request
    return {
        "course_id": request.course_id,
        "course_revision": request.course_revision,
        "pipeline_case_id": pipeline.case_id,
        "source_id": pipeline.source_id,
        "claim_ids": [claim.claim_id for claim in pipeline.claims],
        "section_ids": [claim.section_id for claim in pipeline.claims],
        "proposal_only": True,
        "proposal_status": request.proposal_status.value,
        "claim_proposal_ids": list(request.claim_proposal_ids),
    }


def _safe_identifier(value: str) -> bool:
    return all(character.isalnum() or character in "._:-/" for character in value)


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_event(path: Path, value: Mapping[str, object]) -> None:
    """Append a metadata-only packet event; do not rewrite prior history."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")
