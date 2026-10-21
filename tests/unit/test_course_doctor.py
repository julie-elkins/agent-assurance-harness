import json
from dataclasses import replace

from agent_reliability_lab.course_doctor import (
    CourseDoctorCoordinator,
    LocalCourseSourceAdapter,
    LocalCourseSourceSpec,
    ReviewDisposition,
    adjudicate_packet,
    append_adjudication,
    reference_course_doctor_cases,
    run_reference_course_doctor_suite,
)
from agent_reliability_lab.course_freshness import (
    CourseFreshnessCoordinator,
    CourseFreshnessWorker,
)


def _spec_from_case(case, source_path):
    request = case.request.freshness_request
    pipeline = request.pipeline_request
    return LocalCourseSourceSpec(
        course_id=case.course_id,
        course_revision=case.request.course_revision,
        source_path=source_path,
        case_id=pipeline.case_id,
        artifact_id=pipeline.artifact_id,
        artifact_revision=pipeline.artifact_revision,
        artifact_digest=pipeline.artifact_digest,
        reuse_key=pipeline.reuse_key,
        source_id=pipeline.source_id,
        authority=pipeline.authority,
        source_url=pipeline.source_url,
        age_seconds=pipeline.age_seconds,
        claims=pipeline.claims,
        approved_source_ids=pipeline.approved_source_ids,
        max_age_seconds=pipeline.max_age_seconds,
        expected_source_digest=pipeline.expected_source_digest,
        max_source_bytes=pipeline.max_source_bytes,
    )


def test_reference_course_doctor_emits_review_packets_without_source_text(tmp_path):
    suite = run_reference_course_doctor_suite(workspace=tmp_path)

    assert suite.passed
    assert suite.controls_missed == ()
    assert len(suite.controls_caught) == 5
    assert suite.report.counts == {
        "requested": 5,
        "packets_emitted": 5,
        "completed": 5,
        "failed": 0,
        "timed_out": 0,
        "not_reviewed": 0,
        "truncated": False,
        "counts_reconcile": True,
    }
    packets = {packet.course_id: packet for packet in suite.report.packets}
    assert (
        packets["course-pipeline-approved"].recommended_disposition
        is ReviewDisposition.APPROVED
    )
    assert (
        packets["course-pipeline-stale-source"].recommended_disposition
        is ReviewDisposition.NEEDS_REVISION
    )
    stale_finding = packets["course-pipeline-stale-source"].findings[0]
    assert stale_finding.locators[0].to_dict()["claim_id"] == (
        "claim-pipeline-supported"
    )
    assert stale_finding.locators[0].age_seconds == 7200
    assert stale_finding.locators[0].max_age_seconds == 3600
    assert stale_finding.locators[0].section_id == "section-synthetic-guidance"
    serialized = json.dumps(suite.to_dict())
    assert "Approved technical guidance fixture" not in serialized
    assert (tmp_path / "outputs" / "review-packets.json").exists()
    events = (
        tmp_path / "intermediate" / "review-events.jsonl"
    ).read_text(encoding="utf-8")
    assert events.count('"event": "packet_emitted"') == 5
    assert "Approved technical guidance fixture" not in events


def test_local_review_index_is_opt_in_and_contains_navigation_only(tmp_path):
    case = reference_course_doctor_cases()[2]
    pipeline = case.request.freshness_request.pipeline_request
    source = tmp_path / "course.md"
    source.write_bytes(pipeline.source_bytes)
    spec = _spec_from_case(case, "course.md")
    claim = replace(pipeline.claims[0], line_start=12, line_end=18)
    spec = replace(spec, claims=(claim,))
    loaded = LocalCourseSourceAdapter(tmp_path).load(spec)

    assert loaded.request is not None
    report = CourseDoctorCoordinator().review(
        (loaded.request,),
        workspace=tmp_path / "workspace",
    )
    from agent_reliability_lab.course_doctor import write_local_review_index

    index_path = tmp_path / "local-review-index.json"
    write_local_review_index(index_path, report, (spec,))

    public_report = json.dumps(report.to_dict())
    local_index = json.loads(index_path.read_text(encoding="utf-8"))
    assert "course.md" not in public_report
    assert local_index["local_review_index_version"] == 1
    entry = local_index["entries"][0]
    assert entry["source_path"] == "course.md"
    assert entry["line_start"] == 12
    assert entry["line_end"] == 18
    assert "Approved technical guidance fixture" not in index_path.read_text(
        encoding="utf-8"
    )


def test_worker_failure_still_emits_not_reviewed_packet(tmp_path):
    cases = reference_course_doctor_cases()

    class SelectiveFailureWorker(CourseFreshnessWorker):
        def review(self, request):
            if request.course_id == "course-pipeline-stale-source":
                raise RuntimeError("synthetic worker failure")
            return super().review(request)

    report = CourseDoctorCoordinator(
        freshness_coordinator=CourseFreshnessCoordinator(
            worker_factory=SelectiveFailureWorker,
        )
    ).review(
        (case.request for case in cases),
        workspace=tmp_path,
    )

    packets = {packet.course_id: packet for packet in report.packets}
    assert not report.passed
    assert (
        packets["course-pipeline-stale-source"].recommended_disposition
        is ReviewDisposition.NOT_REVIEWED
    )
    assert packets["course-pipeline-stale-source"].findings[0].reason_code == (
        "worker_failed"
    )
    assert (
        packets["course-pipeline-approved"].recommended_disposition
        is ReviewDisposition.APPROVED
    )


def test_local_adapter_reads_under_root_and_never_reports_source_path(tmp_path):
    case = reference_course_doctor_cases()[0]
    pipeline = case.request.freshness_request.pipeline_request
    source = tmp_path / "course.html"
    source.write_bytes(pipeline.source_bytes)

    loaded = LocalCourseSourceAdapter(tmp_path).load(
        _spec_from_case(case, "course.html")
    )

    assert loaded.request is not None
    report = CourseDoctorCoordinator().review(
        (loaded.request,),
        workspace=tmp_path / "workspace",
    )
    serialized = json.dumps(report.to_dict())
    assert "course.html" not in serialized
    assert "Approved technical guidance fixture" not in serialized

    refused = LocalCourseSourceAdapter(tmp_path).load(
        _spec_from_case(case, "../course.html")
    )
    assert refused.refusal_code == "source_path_outside_root"
    refused_report = CourseDoctorCoordinator().review(
        (refused.request,),
        workspace=tmp_path / "refused-workspace",
    )
    assert refused_report.counts["packets_emitted"] == 1
    assert refused_report.counts["not_reviewed"] == 1
    assert refused_report.packets[0].failure_code == "source_path_outside_root"


def test_human_approval_cannot_override_unresolved_findings(tmp_path):
    suite = run_reference_course_doctor_suite(workspace=tmp_path)
    packets = {packet.course_id: packet for packet in suite.report.packets}
    clean = packets["course-pipeline-approved"]
    stale = packets["course-pipeline-stale-source"]

    approved = adjudicate_packet(
        clean,
        reviewer_id="synthetic-reviewer",
        disposition=ReviewDisposition.APPROVED,
    )
    assert approved.accepted

    blocked = adjudicate_packet(
        stale,
        reviewer_id="synthetic-reviewer",
        disposition=ReviewDisposition.APPROVED,
    )
    assert not blocked.accepted
    assert blocked.refusal_code == "unresolved_findings"

    ledger = tmp_path / "adjudications.jsonl"
    append_adjudication(ledger, approved)
    append_adjudication(ledger, blocked)
    assert len(ledger.read_text(encoding="utf-8").splitlines()) == 2
    assert "Approved technical guidance fixture" not in ledger.read_text(
        encoding="utf-8"
    )
