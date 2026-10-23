import json

from agent_reliability_lab.benchmark import run_synthetic_benchmark


def test_public_synthetic_benchmark_reports_guarded_paths_and_controls():
    report = run_synthetic_benchmark()
    data = report.to_dict()

    assert report.gate_passed
    assert data["synthetic_only"] is True
    assert data["scenario_ids"] == [
        "tool-misuse",
        "false-completion",
        "inappropriate-answer",
        "unauthorized-side-effect",
        "misleading-tool-output",
        "ambiguous-side-effect-retry",
        "http-200-empty-context-retry",
        "evidence-freshness-source",
        "evidence-stale-approved-source",
        "evidence-fresh-wrong-source",
    ]
    assert [agent["agent_id"] for agent in data["agents"]] == [
        "naive",
        "guarded",
        "anthropic-mock",
        "openai-mock",
    ]
    assert data["evaluator_controls"] == {
        "mutation_count": 3,
        "mutations_caught": 3,
        "evaluator_case_count": 2,
        "evaluator_failures_caught": 2,
    }
    assert "findings" not in json.dumps(data)
