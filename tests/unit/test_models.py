from agent_reliability_lab.models import (
    AgentReport,
    Finding,
    FindingStatus,
)


def test_finding_serialization_names_what_was_not_shown():
    finding = Finding(
        check_id="sample",
        status=FindingStatus.COMPLETED,
        message="A synthetic check ran.",
        evidence=("scenario:sample",),
        does_not_show="It does not show live-provider behaviour.",
    )

    assert finding.to_dict() == {
        "check_id": "sample",
        "status": "completed",
        "message": "A synthetic check ran.",
        "dimension": "evidence_completeness",
        "required_evidence": [],
        "evidence": ["scenario:sample"],
        "missing_evidence": [],
        "what_it_does_not_show": "It does not show live-provider behaviour.",
    }


def test_refused_check_is_not_reported_as_passed():
    report = AgentReport(
        agent_id="malformed-adapter",
        findings=(
            Finding(
                check_id="adapter-run",
                status=FindingStatus.REFUSED,
                message="The adapter was refused.",
            ),
        ),
    )

    assert report.passed is False
