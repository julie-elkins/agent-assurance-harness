from agent_reliability_lab.evaluators import (
    all_evaluator_failures_caught,
    run_evaluator_validity,
)
from agent_reliability_lab.models import FindingStatus


def test_weak_evaluator_false_pass_is_exposed():
    results = run_evaluator_validity()

    assert all_evaluator_failures_caught(results)
    assert len(results) == 1
    assert results[0].false_pass_detected is True
    assert results[0].weak_result.status is FindingStatus.COMPLETED
    assert results[0].robust_result.status is FindingStatus.FAILED
