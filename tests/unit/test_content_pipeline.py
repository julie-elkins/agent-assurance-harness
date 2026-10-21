import json
from dataclasses import replace

from agent_reliability_lab.content_pipeline import (
    PipelineDecision,
    reference_content_pipeline_cases,
    run_content_assurance_pipeline,
    run_reference_content_pipeline_suite,
)


def test_pipeline_suite_catches_source_and_claim_controls():
    report = run_reference_content_pipeline_suite()

    assert report.passed
    assert report.controls_caught == (
        "pipeline-approved",
        "pipeline-unsupported-claim",
        "pipeline-stale-source",
        "pipeline-source-drift",
        "pipeline-unapproved-host",
    )
    assert report.controls_missed == ()


def test_pipeline_emits_only_metadata():
    case = reference_content_pipeline_cases()[0]

    report = run_content_assurance_pipeline(case.request)
    data = report.to_dict()
    serialized = json.dumps(data, sort_keys=True)

    assert report.decision is PipelineDecision.APPROVED
    assert report.claim_evidence_ids == (
        "evidence:source-approved-docs:claim-pipeline-supported:"
        "section-synthetic-guidance",
    )
    assert report.finding_locators == ()
    assert "Approved technical guidance fixture" not in serialized
    assert "source_bytes" not in serialized
    assert "normalized_text" not in serialized
    assert "line_start" not in serialized


def test_pipeline_refuses_oversized_source_before_normalization():
    case = reference_content_pipeline_cases()[0]
    request = replace(case.request, max_source_bytes=1)

    report = run_content_assurance_pipeline(request)

    assert report.decision is PipelineDecision.REFUSED
    assert report.refusal_code == "source_too_large"
    assert report.source_digest is None
    assert report.normalized_digest is None


def test_pipeline_locator_identifies_stale_claim_without_source_text():
    case = next(
        case
        for case in reference_content_pipeline_cases()
        if case.case_id == "pipeline-stale-source"
    )

    report = run_content_assurance_pipeline(case.request)

    assert report.finding_locators[0].reason_code == "evidence_stale"
    assert report.finding_locators[0].claim_id == "claim-pipeline-supported"
    assert report.finding_locators[0].section_id == "section-synthetic-guidance"
    assert report.finding_locators[0].age_seconds == 7200
    assert report.finding_locators[0].max_age_seconds == 3600
    assert "Approved technical guidance fixture" not in json.dumps(
        report.to_dict()
    )
