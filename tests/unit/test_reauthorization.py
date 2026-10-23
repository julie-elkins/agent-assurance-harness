from agent_reliability_lab.reauthorization import (
    CaseVariant,
    PilotCondition,
    PilotDecision,
    held_out_cases,
    load_reference_decisions,
    run_pilot,
    synthetic_cases,
)


def test_pilot_has_the_prespecified_case_matrix():
    cases = synthetic_cases()

    assert len(cases) == 18
    assert {
        case.variant for case in cases
    } == {
        CaseVariant.CURRENT,
        CaseVariant.REEVALUATION_REQUIRED,
        CaseVariant.NEGATIVE_CONTROL,
    }
    assert len({case.change_family for case in cases}) == 6


def test_pilot_conditions_have_full_coverage_and_control_results():
    report = run_pilot()

    assert report["decision"] == "pass"
    assert all(report["controls"].values())
    assert len(report["results"]) == 18 * len(PilotCondition)

    summaries = {
        item["condition"]: item for item in report["conditions"]
    }
    assert summaries[PilotCondition.PASS_FAIL.value]["false_ready_count"] == 12
    assert summaries[PilotCondition.REVISION_AWARE.value]["false_ready_count"] == 0
    assert summaries[PilotCondition.REAUTHORIZATION.value]["false_ready_count"] == 0
    assert summaries[PilotCondition.REAUTHORIZATION.value][
        "correct_escalation_count"
    ] == 18


def test_reference_manifest_is_independent_and_covers_both_matrices():
    cases = synthetic_cases() + held_out_cases()
    reference = load_reference_decisions()

    assert set(reference) == {case.case_id for case in cases}
    assert all(
        reference[case.case_id] is case.expected_decision
        for case in cases
        if not case.case_id.startswith("reauth-heldout-")
    )


def test_robustness_matrix_uses_held_out_cases_and_preserves_controls():
    report = run_pilot(include_held_out=True)

    assert report["report_kind"] == "agent-reauthorization-robustness-v1"
    assert report["case_count"] == 30
    assert len(report["results"]) == 30 * len(PilotCondition)
    assert all(report["controls"].values())

    reauthorization = next(
        item
        for item in report["conditions"]
        if item["condition"] == PilotCondition.REAUTHORIZATION.value
    )
    assert reauthorization["false_ready_count"] == 0
    assert reauthorization["correct_escalation_count"] == 30


def test_negative_control_is_blocked_only_by_full_reauthorization_condition():
    report = run_pilot()
    negative = [
        result
        for result in report["results"]
        if result["variant"] == CaseVariant.NEGATIVE_CONTROL.value
    ]

    decisions = {
        result["condition"]: result["decision"] for result in negative
    }
    assert decisions[PilotCondition.PASS_FAIL.value] == PilotDecision.REAUTHORIZED.value
    assert (
        decisions[PilotCondition.REVISION_AWARE.value]
        == PilotDecision.REVIEW_REQUIRED.value
    )
    assert (
        decisions[PilotCondition.REAUTHORIZATION.value]
        == PilotDecision.BLOCKED.value
    )
