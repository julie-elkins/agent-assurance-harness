import json
from pathlib import Path

from agent_reliability_lab.pareto import (
    CandidateEvaluation,
    ParetoConstraints,
    compare_candidates,
)


ROOT = Path(__file__).parents[2]


def _fixture_candidates():
    data = json.loads(
        (
            ROOT
            / "examples"
            / "pareto-candidate-comparison"
            / "candidates.json"
        ).read_text(encoding="utf-8")
    )
    return tuple(
        CandidateEvaluation.from_dict(value) for value in data["candidates"]
    )


def test_hard_constraints_run_before_cost_optimization():
    report = compare_candidates(_fixture_candidates())
    decisions = {item.candidate_id: item for item in report.candidates}

    assert report.frontier_ids == ("quality-first-safe", "balanced-safe")
    assert decisions["cheap-but-unsafe"].status == "excluded"
    assert decisions["cheap-but-unsafe"].reasons == ("safety_not_passed",)
    assert decisions["unstable-safe"].status == "excluded"
    assert decisions["unstable-safe"].reasons == (
        "repeated_run_variation_above_limit",
    )


def test_dominated_candidate_is_not_presented_as_a_frontier_choice():
    report = compare_candidates(_fixture_candidates())
    decisions = {item.candidate_id: item for item in report.candidates}

    assert decisions["dominated-safe"].status == "dominated"
    assert decisions["dominated-safe"].reasons == (
        "dominated_by_eligible_candidate",
    )


def test_constraints_can_be_explicitly_relaxed_for_exploration():
    report = compare_candidates(
        _fixture_candidates(),
        constraints=ParetoConstraints(max_quality_spread=0.25),
    )

    assert "unstable-safe" in report.frontier_ids
    assert report.decision == "review_frontier"
    assert report.to_dict()["human_review_required"] is True
