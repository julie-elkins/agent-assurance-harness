from agent_reliability_lab.providers import (
    ProviderLimits,
    ProviderPolicy,
    mock_provider_adapters,
    translate_provider_payload,
)
from agent_reliability_lab.runner import run_adapters_comparison


def test_both_mocked_providers_pass_through_the_shared_assurance_path():
    report = run_adapters_comparison(
        mock_provider_adapters("all"),
        include_mutations=True,
    )

    assert [item.agent_id for item in report.reports] == [
        "anthropic-mock",
        "openai-mock",
    ]
    assert all(item.passed for item in report.reports)
    assert report.mutation_tests
    assert all(item.caught for item in report.mutation_tests)
    for item in report.reports:
        budget = item.execution_budgets["tool-misuse"]
        assert budget.to_dict() == {
            "usage": {
                "requests": 1,
                "output_tokens": 64,
                "elapsed_seconds": 0.01,
                "estimated_cost_usd": 0.001,
            },
            "limits": {
                "max_requests": 1,
                "max_output_tokens": 256,
                "max_elapsed_seconds": 5.0,
                "max_estimated_cost_usd": 0.01,
            },
            "within_limits": True,
        }


def test_openai_raw_content_is_refused_without_echoing_the_value():
    payload = {
        "events": [
            {
                "type": "classification",
                "kind": "claim",
                "id": "claim:safe",
                "text": "private provider output",
            }
        ],
        "usage": {
            "requests": 1,
            "output_tokens": 1,
            "elapsed_seconds": 0.01,
            "estimated_cost_usd": 0.001,
        },
    }

    result = translate_provider_payload(
        "openai",
        payload,
        scenario_id="inappropriate-answer",
        agent_id="openai-mock",
    )

    assert result.trace is None
    assert result.refusal is not None
    assert result.refusal.error == "raw_or_unknown_provider_field"
    assert "private provider output" not in result.refusal.message


def test_anthropic_raw_text_event_is_refused():
    payload = {
        "content": [{"type": "text", "text": "private provider output"}],
        "stop_reason": "end_turn",
        "usage": {
            "requests": 1,
            "output_tokens": 1,
            "elapsed_seconds": 0.01,
            "estimated_cost_usd": 0.001,
        },
    }

    result = translate_provider_payload(
        "anthropic",
        payload,
        scenario_id="inappropriate-answer",
        agent_id="anthropic-mock",
    )

    assert result.trace is None
    assert result.refusal is not None
    assert result.refusal.error == "unknown_provider_event"
    assert "private provider output" not in result.refusal.message


def test_provider_limits_refuse_excess_synthetic_usage():
    adapter = mock_provider_adapters(
        "openai",
        limits=ProviderLimits(
            max_requests=1,
            max_output_tokens=1,
            max_elapsed_seconds=5.0,
            max_estimated_cost_usd=0.01,
        ),
    )[0]
    report = run_adapters_comparison((adapter,))

    finding = report.reports[0].findings[0]
    assert finding.status.value == "refused"
    assert "output_tokens" in finding.message
    budget = report.reports[0].execution_budgets["inappropriate-answer"]
    assert budget.output_tokens == 64
    assert budget.max_output_tokens == 1
    assert budget.within_limits is False


def test_live_policy_is_disabled_without_a_separate_live_gate():
    policy = ProviderPolicy(
        provider_id="openai",
        credential_env_var="OPENAI_API_KEY",
        limits=ProviderLimits(
            max_requests=1,
            max_output_tokens=1,
            max_elapsed_seconds=1.0,
            max_estimated_cost_usd=0.01,
        ),
    )

    refusal = policy.validate(live=True)

    assert refusal is not None
    assert refusal.error == "live_provider_disabled"
