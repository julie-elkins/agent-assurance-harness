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
    ]
    assert all("synthetic" in case.description.lower() or case.scenario_id for case in cases)


def test_naive_and_guarded_agents_diverge_in_expected_direction():
    for case in scenarios():
        naive_finding = case.evaluate(case.run_naive(), case.contract)
        guarded_finding = case.evaluate(case.run_guarded(), case.contract)

        assert naive_finding.status is FindingStatus.FAILED
        assert guarded_finding.status is FindingStatus.COMPLETED
        assert guarded_finding.required_evidence
