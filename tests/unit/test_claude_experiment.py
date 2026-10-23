import json

from agent_reliability_lab.claude_experiment import (
    CLAUDE_SONNET_MODEL,
    ClaudeExperimentPolicy,
    run_claude_experiment,
)


def _anthropic_response() -> bytes:
    return json.dumps(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "content": [
                                {
                                    "type": "reliability",
                                    "kind": "abstention",
                                }
                            ]
                        }
                    ),
                }
            ],
            "stop_reason": "end_turn",
            "usage": {"output_tokens": 32},
        }
    ).encode("utf-8")


def _policy(**overrides) -> ClaudeExperimentPolicy:
    values = {
        "model": CLAUDE_SONNET_MODEL,
        "case_count": 10,
        "max_total_cost_usd": 5.0,
        "estimated_cost_usd_per_request": 0.05,
        "max_output_tokens": 64,
        "max_elapsed_seconds": 5.0,
        "allow_network": True,
    }
    values.update(overrides)
    return ClaudeExperimentPolicy(**values)


def test_policy_refuses_network_without_explicit_opt_in():
    report = run_claude_experiment(_policy(allow_network=False))

    assert report.decision == "refused"
    assert report.refusal_error == "experiment_policy_refused"
    assert report.attempted_case_count == 0


def test_policy_refuses_unbounded_pilot_before_transport():
    calls = 0

    def transport(*args):
        nonlocal calls
        calls += 1
        return _anthropic_response()

    report = run_claude_experiment(
        _policy(case_count=30, max_total_cost_usd=2.0),
        transport=transport,
    )

    assert report.decision == "refused"
    assert calls == 0


def test_smoke_run_is_bounded_and_metadata_only(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-secret")
    observed = []

    def transport(url, headers, body, timeout_seconds):
        observed.append((url, headers, body, timeout_seconds))
        return _anthropic_response()

    report = run_claude_experiment(
        _policy(),
        transport=transport,
    )

    assert report.decision == "complete"
    assert report.requested_case_count == 10
    assert report.attempted_case_count == 10
    assert len(observed) == 10
    serialized = json.dumps(report.to_dict())
    assert "synthetic-secret" not in serialized
    assert "Return only a JSON object" not in serialized
    assert "claude-sonnet-5-5" in serialized


def test_pilot_repeats_fixed_scenarios_without_exceeding_total_cap(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-secret")

    report = run_claude_experiment(
        _policy(case_count=20),
        transport=lambda *args: _anthropic_response(),
    )

    assert report.decision == "complete"
    assert report.attempted_case_count == 20
    assert report.completed_case_count == 20
    assert report.total_estimated_cost_usd == 1.0
    assert report.within_total_cost_limit is True
    assert report.cases[0].replicate == 1
    assert report.cases[-1].replicate == 2
