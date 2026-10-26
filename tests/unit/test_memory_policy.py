import json

import pytest

from agent_reliability_lab.memory_policy import (
    DEFAULT_PACK_DIRECTORY,
    MemoryPolicyInputError,
    MemoryPolicySpec,
    evaluate_memory_policy,
    load_memory_policy_cases,
    load_memory_policy_pack,
    run_reference_memory_policy_suite,
)


def test_reference_suite_requires_evidence_before_claiming_completion():
    report = run_reference_memory_policy_suite()

    assert report.passed
    assert report.case_count == 4
    assert "memory-policy-guarded-safe" in report.controls_caught
    assert report.negative_control["caught"] is True
    assert "required_memory_discarded" in report.negative_control["reason_codes"]
    assert "unsafe_continue_without_required_evidence" in (
        report.negative_control["reason_codes"]
    )


def test_cost_and_latency_are_reported_separately_from_safety():
    report = run_reference_memory_policy_suite()
    baseline = report.policies[0]
    guarded = report.policies[1]

    assert baseline.passed
    assert guarded.passed
    assert guarded.total_cost_units < baseline.total_cost_units
    assert guarded.total_latency_units < baseline.total_latency_units
    assert all(
        result.evidence_status == "complete"
        for result in guarded.case_results
    )


def test_unknown_pack_fields_are_refused_without_echoing_content(tmp_path):
    path = tmp_path / "invalid.json"
    value = json.loads(
        (DEFAULT_PACK_DIRECTORY / "bounded-memory-safety.json").read_text(
            encoding="utf-8"
        )
    )
    value["unexpected"] = "must not be accepted"
    path.write_text(json.dumps(value), encoding="utf-8")

    with pytest.raises(MemoryPolicyInputError, match="invalid_pack_fields") as error:
        load_memory_policy_pack(path)

    assert "must not be accepted" not in str(error.value)


def test_required_memory_loss_is_a_blocking_finding():
    report = run_reference_memory_policy_suite()
    negative = report.policies[2]

    assert negative.passed is False
    assert any(
        "required_memory_discarded" in result.reason_codes
        for result in negative.case_results
    )


def test_refusal_is_distinct_from_missing_evidence():
    cases, _ = load_memory_policy_cases()
    mutated_policy = MemoryPolicySpec(
        policy_id="mutated-guarded",
        recent_window=2,
        retain_required=False,
        refuse_if_required_missing=True,
        enforce_retention_bound=True,
    )

    mutated = evaluate_memory_policy(mutated_policy, (cases[0],))

    assert mutated.case_results[0].evidence_status == "incomplete"
    assert mutated.case_results[0].refusal_status == "refused"
