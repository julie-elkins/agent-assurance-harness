from agent_reliability_lab.evaluators import (
    all_evaluator_failures_caught,
    run_evaluator_validity,
)
from agent_reliability_lab.models import FindingStatus


def test_weak_evaluator_false_pass_is_exposed():
    results = run_evaluator_validity()

    assert all_evaluator_failures_caught(results)
    assert len(results) == 2
    assert all(result.false_pass_detected for result in results)
    assert all(
        result.weak_result.status is FindingStatus.COMPLETED
        and result.robust_result.status is FindingStatus.FAILED
        for result in results
    )
