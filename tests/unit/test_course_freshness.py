import json

from agent_reliability_lab.course_freshness import (
    CourseFreshnessCoordinator,
    CourseFreshnessWorker,
    WorkerStatus,
    reference_course_freshness_cases,
    run_reference_course_freshness_suite,
)


def test_reference_course_sweep_catches_controls_and_writes_checkpoints(tmp_path):
    report = run_reference_course_freshness_suite(workspace=tmp_path)

    assert report.passed
    assert report.controls_missed == ()
    assert len(report.controls_caught) == 5
    assert (tmp_path / "inputs").is_dir()
    assert (tmp_path / "intermediate" / "orchestration-events.jsonl").exists()
    assert (tmp_path / "outputs" / "sweep.json").exists()
    assert "Approved technical guidance fixture" not in (
        tmp_path / "inputs" / "course-pipeline-approved.json"
    ).read_text(encoding="utf-8")


def test_lateral_worker_failure_is_unavailable_but_other_courses_complete(tmp_path):
    cases = reference_course_freshness_cases()
    requests = tuple(case.request for case in cases)

    class SelectiveFailureWorker(CourseFreshnessWorker):
        def review(self, request):
            if request.course_id == "course-pipeline-stale-source":
                raise RuntimeError("synthetic worker failure")
            return super().review(request)

    report = CourseFreshnessCoordinator(
        worker_factory=SelectiveFailureWorker,
    ).sweep(
        requests,
        workspace=tmp_path,
    )

    results = {result.course_id: result for result in report.results}
    assert not report.passed
    assert results["course-pipeline-stale-source"].worker_status is WorkerStatus.FAILED
    assert results["course-pipeline-stale-source"].failure_code == "worker_failed"
    assert results["course-pipeline-approved"].worker_status is WorkerStatus.COMPLETED
    events = (
        tmp_path / "intermediate" / "orchestration-events.jsonl"
    ).read_text(encoding="utf-8")
    assert "synthetic worker failure" not in events
    assert '"event": "failed"' in events


def test_course_limit_refuses_before_fanout(tmp_path):
    requests = tuple(
        case.request for case in reference_course_freshness_cases()
    )

    report = CourseFreshnessCoordinator().sweep(
        requests,
        workspace=tmp_path,
        max_courses=1,
    )

    assert not report.passed
    assert report.refusal_code == "course_limit_exceeded"
    assert report.stop_condition == "refused-before-fanout"
    assert json.loads(
        (tmp_path / "outputs" / "sweep.json").read_text(encoding="utf-8")
    )["refusal_code"] == "course_limit_exceeded"
