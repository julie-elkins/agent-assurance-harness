import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from agent_reliability_lab.environment import environment_for_scenario
from agent_reliability_lab.claude_tool_loop import anthropic_tool_loop_adapter
from agent_reliability_lab.live import (
    LiveProviderPolicy,
    _NoRedirectHandler,
    live_provider_adapter,
)
from agent_reliability_lab.packs import (
    build_environment_from_pack,
    load_builtin_packs,
    request_from_pack,
)
from agent_reliability_lab.providers import ProviderLimits


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "provider_contracts"


def _policy(
    *,
    provider_id: str = "openai",
    allow_network: bool = True,
) -> LiveProviderPolicy:
    return LiveProviderPolicy(
        provider_id=provider_id,
        model="synthetic-model",
        credential_env_var=(
            "OPENAI_API_KEY"
            if provider_id == "openai"
            else "ANTHROPIC_API_KEY"
        ),
        limits=ProviderLimits(
            max_requests=1,
            max_output_tokens=64,
            max_elapsed_seconds=5.0,
            max_estimated_cost_usd=0.01,
        ),
        estimated_cost_usd_per_request=0.001,
        allow_network=allow_network,
    )


def _request():
    pack = next(
        pack
        for pack in load_builtin_packs()
        if pack.scenario_id == "unauthorized-side-effect"
    )
    return request_from_pack(pack)


def _provider_fixture(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def test_live_adapter_uses_synthetic_request_and_discards_credential(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    observed = {}

    def transport(url, headers, body, timeout_seconds):
        observed["url"] = url
        observed["headers"] = headers
        observed["body"] = body
        observed["timeout_seconds"] = timeout_seconds
        output = {
            "events": [
                {
                    "type": "classification",
                    "kind": "claim",
                    "id": "claim:authorization_required",
                },
                {"type": "classification", "kind": "abstention"},
            ]
        }
        return json.dumps(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(output),
                            }
                        ],
                    }
                ],
                "usage": {"output_tokens": 32},
            }
        ).encode("utf-8")

    result = live_provider_adapter(
        _policy(),
        transport=transport,
    ).run(
        _request(),
        environment_for_scenario("unauthorized-side-effect"),
    )

    assert result.refusal is None
    assert result.trace is not None
    assert result.execution_budget is not None
    assert result.execution_budget.output_tokens == 32
    assert result.execution_budget.max_output_tokens == 64
    assert result.execution_budget.within_limits is True
    assert result.trace.agent_id == "openai-live"
    assert observed["url"] == "https://api.openai.com/v1/responses"
    assert observed["headers"]["Authorization"] == "Bearer test-secret"
    assert b"test-secret" not in observed["body"]
    body = json.loads(observed["body"])
    assert body["store"] is False
    assert body["input"].find("unauthorized-side-effect") >= 0
    assert observed["timeout_seconds"] == 5.0


def test_live_adapter_refuses_before_transport_without_network_opt_in(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    calls = 0

    def transport(*args):
        nonlocal calls
        calls += 1
        return b"{}"

    result = live_provider_adapter(
        _policy(allow_network=False),
        transport=transport,
    ).run(
        _request(),
        environment_for_scenario("unauthorized-side-effect"),
    )

    assert result.trace is None
    assert result.refusal is not None
    assert result.refusal.error == "network_opt_in_required"
    assert calls == 0


def test_live_adapter_refuses_missing_credential_before_transport(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    calls = 0

    def transport(*args):
        nonlocal calls
        calls += 1
        return b"{}"

    result = live_provider_adapter(
        _policy(),
        transport=transport,
    ).run(
        _request(),
        environment_for_scenario("unauthorized-side-effect"),
    )

    assert result.trace is None
    assert result.refusal is not None
    assert result.refusal.error == "provider_credential_missing"
    assert calls == 0


def test_live_adapter_refuses_placeholder_credential_before_transport(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "your-key-here")
    calls = 0

    def transport(*args):
        nonlocal calls
        calls += 1
        return b"{}"

    result = live_provider_adapter(
        _policy(),
        transport=transport,
    ).run(
        _request(),
        environment_for_scenario("unauthorized-side-effect"),
    )

    assert result.trace is None
    assert result.refusal is not None
    assert result.refusal.error == "provider_credential_placeholder"
    assert calls == 0


def test_live_adapter_classifies_http_failure_without_response_body(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    def transport(*args):
        raise urllib.error.HTTPError(
            "https://api.openai.com/v1/responses",
            401,
            "Unauthorized",
            hdrs=None,
            fp=None,
        )

    result = live_provider_adapter(
        _policy(),
        transport=transport,
    ).run(
        _request(),
        environment_for_scenario("unauthorized-side-effect"),
    )

    assert result.trace is None
    assert result.refusal is not None
    assert result.refusal.error == "provider_authentication_failed"
    assert "Unauthorized" not in result.refusal.message
    assert "test-secret" not in result.refusal.message


def test_live_adapter_refuses_raw_model_output_without_echoing_it(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    def transport(*args):
        return json.dumps(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "private model output",
                            }
                        ],
                    }
                ],
                "usage": {"output_tokens": 32},
            }
        ).encode("utf-8")

    result = live_provider_adapter(
        _policy(),
        transport=transport,
    ).run(
        _request(),
        environment_for_scenario("unauthorized-side-effect"),
    )

    assert result.trace is None
    assert result.refusal is not None
    assert result.refusal.error == "provider_response_refused"
    assert "private model output" not in result.refusal.message


def test_anthropic_live_adapter_uses_approved_endpoint_and_headers(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    observed = {}

    def transport(url, headers, body, timeout_seconds):
        observed["url"] = url
        observed["headers"] = headers
        observed["body"] = body
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
                                        "kind": "claim",
                                        "id": "claim:authorization_required",
                                    },
                                    {
                                        "type": "reliability",
                                        "kind": "abstention",
                                    },
                                ]
                            }
                        ),
                    }
                ],
                "usage": {"output_tokens": 32},
            }
        ).encode("utf-8")

    result = live_provider_adapter(
        _policy(provider_id="anthropic"),
        transport=transport,
    ).run(
        _request(),
        environment_for_scenario("unauthorized-side-effect"),
    )

    assert result.refusal is None
    assert result.trace is not None
    assert observed["url"] == "https://api.anthropic.com/v1/messages"
    assert observed["headers"]["x-api-key"] == "test-secret"
    assert observed["headers"]["anthropic-version"] == "2023-06-01"
    assert b"test-secret" not in observed["body"]


def test_anthropic_tool_loop_pairs_synthetic_result_before_final_classification(
    monkeypatch,
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-secret")
    pack = next(
        pack
        for pack in load_builtin_packs()
        if pack.scenario_id == "unauthorized-side-effect"
    )
    request = request_from_pack(pack)
    responses = iter(
        (
            json.dumps(
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "content": [
                                        {
                                            "type": "tool_use",
                                            "name": "cancel_order",
                                            "id": "call-001",
                                        }
                                    ]
                                }
                            ),
                        }
                    ],
                    "stop_reason": "end_turn",
                    "usage": {"output_tokens": 24},
                }
            ).encode("utf-8"),
            json.dumps(
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
                    "usage": {"output_tokens": 16},
                }
            ).encode("utf-8"),
        )
    )
    observed = []

    def transport(url, headers, body, timeout_seconds):
        observed.append(json.loads(body))
        return next(responses)

    result = anthropic_tool_loop_adapter(
        _policy(provider_id="anthropic"),
        max_turns=3,
        transport=transport,
    ).run(
        request,
        environment=build_environment_from_pack(pack),
    )

    assert result.refusal is None
    assert result.trace is not None
    assert len(result.trace.tool_calls) == 1
    assert result.trace.tool_calls[0].result_status == "ok"
    assert result.trace.abstained is True
    assert result.execution_budget is not None
    assert result.execution_budget.requests == 2
    assert len(observed) == 2
    assert observed[1]["messages"][-1]["content"].find("tool_results") >= 0
    assert b"test-secret" not in json.dumps(observed).encode("utf-8")


def test_provider_contract_fixtures_remain_accepted(monkeypatch):
    for provider_id, credential_name, fixture_name in (
        ("openai", "OPENAI_API_KEY", "openai-responses-safe.json"),
        ("anthropic", "ANTHROPIC_API_KEY", "anthropic-messages-safe.json"),
    ):
        monkeypatch.setenv(credential_name, "test-secret")
        result = live_provider_adapter(
            _policy(provider_id=provider_id),
            transport=lambda *args, fixture_name=fixture_name: _provider_fixture(
                fixture_name
            ),
        ).run(
            _request(),
            environment_for_scenario("unauthorized-side-effect"),
        )

        assert result.refusal is None
        assert result.trace is not None
        assert result.execution_budget is not None
        assert result.execution_budget.within_limits is True


def test_live_adapter_refuses_non_bytes_transport_output(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")

    result = live_provider_adapter(
        _policy(),
        transport=lambda *args: "not-bytes",
    ).run(
        _request(),
        environment_for_scenario("unauthorized-side-effect"),
    )

    assert result.trace is None
    assert result.refusal is not None
    assert result.refusal.error == "provider_transport_invalid_response"


def test_live_transport_redirect_handler_refuses_redirects():
    request = urllib.request.Request("https://api.openai.com/v1/responses")

    with pytest.raises(urllib.error.HTTPError):
        _NoRedirectHandler().redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://example.invalid/redirect",
        )
