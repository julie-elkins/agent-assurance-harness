import json
from pathlib import Path

from agent_reliability_lab.environment import environment_for_scenario
from agent_reliability_lab.live import LiveProviderPolicy, live_provider_adapter
from agent_reliability_lab.packs import load_builtin_packs, request_from_pack
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
