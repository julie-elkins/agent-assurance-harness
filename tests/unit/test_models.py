from agent_reliability_lab.models import Finding, FindingStatus


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
        "required_evidence": [],
        "evidence": ["scenario:sample"],
        "missing_evidence": [],
        "what_it_does_not_show": "It does not show live-provider behaviour.",
    }
