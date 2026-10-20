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
