from agent_reliability_lab.models import FindingStatus
from agent_reliability_lab.scenarios import scenarios


def test_scenarios_are_public_synthetic_cases():
    cases = scenarios()

    assert [case.scenario_id for case in cases] == [
        "tool-misuse",
        "false-completion",
        "inappropriate-answer",
        "unauthorized-side-effect",
        "misleading-tool-output",
        "ambiguous-side-effect-retry",
        "evidence-freshness-source",
        "evidence-stale-approved-source",
        "evidence-fresh-wrong-source",
    ]
    assert all("synthetic" in case.description.lower() or case.scenario_id for case in cases)


def test_naive_and_guarded_agents_diverge_in_expected_direction():
    for case in scenarios():
        naive_finding = case.evaluate(case.run_naive(), case.contract)
        guarded_finding = case.evaluate(case.run_guarded(), case.contract)

        assert naive_finding.status is FindingStatus.FAILED
        assert guarded_finding.status is FindingStatus.COMPLETED
        assert guarded_finding.required_evidence


def test_freshness_scenario_carries_source_and_age_metadata():
    case = next(
        case for case in scenarios() if case.scenario_id == "evidence-freshness-source"
    )

    guarded = case.run_guarded().tool_calls[0]
    naive = case.run_naive().tool_calls[0]

    assert guarded.source == "authoritative-catalog"
    assert guarded.age_seconds == 60.0
    assert naive.source == "cache"
    assert naive.age_seconds == 7200.0


def test_stale_evidence_requires_abstention_and_records_reason():
    scenario = next(
        case
        for case in scenarios()
        if case.scenario_id == "evidence-stale-approved-source"
    )

    naive = scenario.evaluate(scenario.run_naive(), scenario.contract)
    guarded = scenario.evaluate(scenario.run_guarded(), scenario.contract)

    assert naive.status is FindingStatus.FAILED
    assert naive.failure_reason == "evidence_stale"
    assert "abstain:when-evidence-untrusted" in naive.missing_evidence
    assert guarded.status is FindingStatus.COMPLETED
    assert guarded.failure_reason == "evidence_stale"
    assert "abstain:when-evidence-untrusted" in guarded.evidence


def test_fresh_wrong_source_requires_abstention_and_records_reason():
    scenario = next(
        case
        for case in scenarios()
        if case.scenario_id == "evidence-fresh-wrong-source"
    )

    naive = scenario.evaluate(scenario.run_naive(), scenario.contract)
    guarded = scenario.evaluate(scenario.run_guarded(), scenario.contract)

    assert naive.status is FindingStatus.FAILED
    assert naive.failure_reason == "evidence_wrong_source"
    assert "abstain:when-evidence-untrusted" in naive.missing_evidence
    assert guarded.status is FindingStatus.COMPLETED
    assert guarded.failure_reason == "evidence_wrong_source"
    assert "abstain:when-evidence-untrusted" in guarded.evidence
