import json

from agent_reliability_lab.environment import environment_for_scenario
from agent_reliability_lab.openai_experiment import (
    OPENAI_DEFAULT_MODEL,
    OpenAIExperimentPolicy,
    run_openai_experiment,
)
from agent_reliability_lab.openai_schema import (
    openai_structured_output_schema,
    openai_tool_definitions,
    validate_openai_output,
)
from agent_reliability_lab.openai_tool_loop import openai_tool_loop_adapter
from agent_reliability_lab.live import LiveProviderPolicy
from agent_reliability_lab.packs import load_builtin_packs, request_from_pack
from agent_reliability_lab.providers import ProviderLimits


def _policy() -> LiveProviderPolicy:
    return LiveProviderPolicy(
        provider_id="openai",
        model=OPENAI_DEFAULT_MODEL,
        credential_env_var="OPENAI_API_KEY",
        limits=ProviderLimits(
            max_requests=1,
            max_output_tokens=64,
            max_elapsed_seconds=5.0,
            max_estimated_cost_usd=0.01,
        ),
        estimated_cost_usd_per_request=0.001,
        allow_network=True,
    )


def _request():
    pack = next(
        pack
        for pack in load_builtin_packs()
        if pack.scenario_id == "unauthorized-side-effect"
    )
    return request_from_pack(pack)


def _final_response() -> bytes:
    return json.dumps(
        {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "events": [
                                        {
                                            "type": "classification",
                                            "kind": "abstention",
                                        }
                                    ]
                                }
                            ),
                        }
                    ],
                }
            ],
            "usage": {"output_tokens": 16},
        }
    ).encode("utf-8")


def test_openai_tool_loop_pairs_function_result_before_final_classification(
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    responses = iter(
        (
            json.dumps(
                {
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": "call-001",
                            "name": "cancel_order",
                            "arguments": "{}",
                        }
                    ],
                    "usage": {"output_tokens": 24},
                }
            ).encode("utf-8"),
            _final_response(),
        )
    )
    observed = []

    def transport(url, headers, body, timeout_seconds):
        observed.append(json.loads(body))
        return next(responses)

    result = openai_tool_loop_adapter(
        _policy(),
        transport=transport,
    ).run(
        _request(),
        environment=environment_for_scenario("unauthorized-side-effect"),
    )

    assert result.refusal is None
    assert result.trace is not None
    assert result.trace.tool_calls[0].result_status == "ok"
    assert result.trace.abstained is True
    assert result.execution_budget is not None
    assert result.execution_budget.requests == 2
    assert observed[0]["parallel_tool_calls"] is False
    assert observed[0]["tools"][0]["type"] == "function"
    assert observed[0]["tools"][0]["parameters"]["additionalProperties"] is False
    assert observed[1]["input"][-2]["type"] == "function_call"
    assert observed[1]["input"][-1]["type"] == "function_call_output"
    assert observed[1]["input"][-1]["call_id"] == "call-001"
    assert "test-secret" not in json.dumps(observed)


def test_openai_structured_condition_sends_strict_schema(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    observed = []

    def transport(url, headers, body, timeout_seconds):
        observed.append(json.loads(body))
        return _final_response()

    result = openai_tool_loop_adapter(
        _policy(),
        structured_output=True,
        transport=transport,
    ).run(
        _request(),
        environment=environment_for_scenario("unauthorized-side-effect"),
    )

    assert result.refusal is None
    assert result.trace is not None
    assert observed[0]["text"]["format"]["type"] == "json_schema"
    assert observed[0]["text"]["format"]["strict"] is True
    assert observed[0]["text"]["format"]["schema"]["additionalProperties"] is False
    assert '"type":"classification"' in observed[0]["instructions"]


def test_openai_tool_schema_and_final_schema_are_closed():
    tools = openai_tool_definitions(("lookup_policy",))
    assert tools[0]["type"] == "function"
    assert tools[0]["strict"] is True
    assert tools[0]["parameters"]["required"] == []
    assert tools[0]["parameters"]["additionalProperties"] is False

    schema = openai_structured_output_schema()
    assert schema["required"] == ["events", "workflow"]
    assert schema["additionalProperties"] is False

    assert (
        validate_openai_output(
            {
                "events": [
                    {
                        "type": "classification",
                        "kind": "abstention",
                        "id": None,
                        "status": None,
                        "operation_id": None,
                        "action_digest": None,
                    }
                ],
                "workflow": None,
            },
            available_tools=("lookup_policy",),
        )
        is None
    )


def test_openai_tool_loop_refuses_nonempty_arguments_without_echoing_them(
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    def transport(url, headers, body, timeout_seconds):
        return json.dumps(
            {
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call-001",
                        "name": "cancel_order",
                        "arguments": '{"private":"do-not-retain"}',
                    }
                ],
                "usage": {"output_tokens": 24},
            }
        ).encode("utf-8")

    result = openai_tool_loop_adapter(
        _policy(),
        transport=transport,
    ).run(
        _request(),
        environment=environment_for_scenario("unauthorized-side-effect"),
    )

    assert result.trace is None
    assert result.refusal is not None
    assert result.refusal.error == "provider_native_tool_arguments_rejected"
    assert "do-not-retain" not in result.refusal.message


def test_openai_experiment_reports_metadata_only(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-secret")
    report = run_openai_experiment(
        OpenAIExperimentPolicy(
            model=OPENAI_DEFAULT_MODEL,
            case_count=10,
            max_output_tokens=64,
            max_elapsed_seconds=5.0,
            allow_network=True,
        ),
        transport=lambda *args: _final_response(),
    )

    assert report.decision == "complete"
    assert report.attempted_case_count == 10
    assert report.completed_case_count == 10
    assert "synthetic-secret" not in json.dumps(report.to_dict())
