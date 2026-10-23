from agent_reliability_lab.claude_hooks import (
    after_response_hook,
    after_tool_hook,
    before_request_hook,
    before_tool_hook,
    stop_hook,
)
from agent_reliability_lab.environment import ToolObservation, environment_for_scenario
from agent_reliability_lab.live import LiveProviderPolicy
from agent_reliability_lab.packs import load_builtin_packs, request_from_pack
from agent_reliability_lab.providers import ProviderLimits


def _policy() -> LiveProviderPolicy:
    return LiveProviderPolicy(
        provider_id="anthropic",
        model="synthetic-model",
        credential_env_var="ANTHROPIC_API_KEY",
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


def test_before_request_hook_reports_stage_for_missing_credential(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    result = before_request_hook(
        _policy(),
        environment=environment_for_scenario("unauthorized-side-effect"),
        turn=1,
        max_turns=3,
    )

    assert result.allowed is False
    assert result.refusal is not None
    assert result.refusal.error == "provider_credential_missing"
    assert result.refusal.stage == "before_request"


def test_after_response_hook_reports_schema_stage():
    result = after_response_hook(
        {"content": [{"type": "tool_use", "name": "cancel_order", "id": "call"}]},
        available_tools=("cancel_order",),
    )

    assert result.allowed is False
    assert result.refusal is not None
    assert result.refusal.error == "claude_schema_tool_use_invalid"
    assert result.refusal.stage == "after_response"


def test_before_tool_hook_rejects_nonempty_arguments_without_echoing_them():
    result = before_tool_hook(
        {
            "type": "tool_use",
            "name": "cancel_order",
            "id": "call-001",
            "input": {"private": "do-not-retain"},
        },
        available_tools=("cancel_order",),
    )

    assert result.allowed is False
    assert result.refusal is not None
    assert result.refusal.error == "provider_raw_tool_arguments_rejected"
    assert result.refusal.stage == "before_tool"
    assert "do-not-retain" not in result.refusal.message


def test_after_tool_hook_returns_identifier_level_result_only():
    result = after_tool_hook(
        ToolObservation(
            tool_name="cancel_order",
            result_status="ok",
            result_id="tool-result-006",
            output_flags=("synthetic",),
            source="approved-source",
            age_seconds=4.0,
        ),
        call_id="call-001",
    )

    assert result.allowed is True
    assert result.value == {
        "type": "tool_result",
        "tool_use_id": "call-001",
        "status": "ok",
        "evidence_id": "tool-result-006",
        "output_flags": ["synthetic"],
        "source": "approved-source",
        "age_seconds": 4.0,
    }


def test_stop_hook_reports_bounded_stop_stage():
    result = stop_hook(
        turn=3,
        max_turns=3,
        estimated_cost_usd=0.03,
        max_estimated_cost_usd=0.09,
    )

    assert result.allowed is False
    assert result.refusal is not None
    assert result.refusal.error == "tool_loop_turn_limit_exceeded"
    assert result.refusal.stage == "stop"
