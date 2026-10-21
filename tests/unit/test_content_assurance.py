from agent_reliability_lab.content_assurance import (
    ContentDecision,
    ContentSource,
    TechnicalContentAssuranceAgent,
    reference_content_assurance_cases,
    run_reference_content_assurance_suite,
)


def test_reference_suite_approves_fresh_source_and_catches_degraded_controls():
    report = run_reference_content_assurance_suite()

    assert report.passed
    assert report.controls_caught == (
        "fresh-approved",
        "stale-approved",
        "fresh-wrong-source",
    )
    assert report.controls_missed == ()
    decisions = {
        case_id: result.decision for case_id, result in report.reports
    }
    assert decisions == {
        "fresh-approved": ContentDecision.APPROVED,
        "stale-approved": ContentDecision.ABSTAIN,
        "fresh-wrong-source": ContentDecision.ABSTAIN,
    }


def test_wrong_source_is_distinguished_from_staleness():
    agent = TechnicalContentAssuranceAgent()
    case = reference_content_assurance_cases()[2]

    report = agent.review(case.request, case.artifact, case.sources)

    assert report.decision is ContentDecision.ABSTAIN
    assert report.abstention_reasons == ("evidence_wrong_source",)
    assert "evidence_stale" not in report.abstention_reasons


def test_unknown_verification_is_not_current():
    agent = TechnicalContentAssuranceAgent()
    case = reference_content_assurance_cases()[0]
    unknown_source = ContentSource(
        source_id="source-approved-docs",
        authority="public-reference-docs",
        source_url="https://docs.aws.amazon.com/",
        source_digest=case.artifact.claims[0].expected_source_digest,
        age_seconds=None,
    )

    report = agent.review(case.request, case.artifact, (unknown_source,))

    assert report.decision is ContentDecision.ABSTAIN
    assert report.abstention_reasons == ("evidence_verification_unknown",)


def test_source_drift_is_reported_without_source_payload():
    agent = TechnicalContentAssuranceAgent()
    case = reference_content_assurance_cases()[0]
    drifted_source = ContentSource(
        source_id="source-approved-docs",
        authority="public-reference-docs",
        source_url="https://docs.aws.amazon.com/",
        source_digest="sha256:" + "0" * 64,
        age_seconds=300,
    )

    report = agent.review(case.request, case.artifact, (drifted_source,))
    data = report.to_dict()

    assert report.decision is ContentDecision.ABSTAIN
    assert report.abstention_reasons == ("source_drift",)
    assert "source_digest" not in data
    assert "source payload" not in json_text(data)


def test_malformed_request_is_refused_not_abstained():
    agent = TechnicalContentAssuranceAgent()
    case = reference_content_assurance_cases()[0]
    request = case.request.__class__(
        artifact_id="different-artifact",
        approved_source_ids=case.request.approved_source_ids,
        max_age_seconds=case.request.max_age_seconds,
    )

    report = agent.review(request, case.artifact, case.sources)

    assert report.decision is ContentDecision.REFUSED
    assert report.refusal_code == "artifact_id_mismatch"


def test_non_official_source_host_is_refused_at_the_boundary():
    agent = TechnicalContentAssuranceAgent()
    case = reference_content_assurance_cases()[0]
    source = ContentSource(
        source_id="source-approved-docs",
        authority="public-reference-docs",
        source_url="https://docs.example.com/",
        source_digest=case.artifact.claims[0].expected_source_digest,
        age_seconds=300,
    )

    report = agent.review(case.request, case.artifact, (source,))

    assert report.decision is ContentDecision.REFUSED
    assert report.refusal_code == "unapproved_source_host"


def test_non_official_source_host_is_refused_at_the_boundary():
    agent = TechnicalContentAssuranceAgent()
    case = reference_content_assurance_cases()[0]
    source = ContentSource(
        source_id="source-approved-docs",
        authority="public-reference-docs",
        source_url="https://docs.example.com/",
        source_digest=case.artifact.claims[0].expected_source_digest,
        age_seconds=300,
    )

    report = agent.review(case.request, case.artifact, (source,))

    assert report.decision is ContentDecision.REFUSED
    assert report.refusal_code == "unapproved_source_host"


def json_text(value: object) -> str:
    """Serialize test data for a simple content-boundary assertion."""

    import json

    return json.dumps(value, sort_keys=True)
