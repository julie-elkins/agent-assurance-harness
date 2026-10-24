"""Deterministic lifecycle hooks for local provider tool loops.

Hooks are small checks that run at named boundaries.  They keep provider formatting,
tool permission, and stop-budget failures distinguishable without retaining model text
or tool payloads.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from .claude_schema import validate_claude_output
from .environment import SimulatedToolEnvironment, ToolObservation
from .live import (
    LiveProviderPolicy,
    _PLACEHOLDER_CREDENTIALS,
    _refusal,
)
from .protocol import AdapterRefusal


@dataclass(frozen=True)
class HookResult:
    """The safe outcome of one lifecycle hook."""

    stage: str
    refusal: AdapterRefusal | None = None
    value: object | None = None

    @property
    def allowed(self) -> bool:
        """Return whether the hook allowed the lifecycle transition."""

        return self.refusal is None


def before_request_hook(
    policy: LiveProviderPolicy,
    *,
    environment: object,
    turn: int,
    max_turns: int,
) -> HookResult:
    """Check policy, credential, environment, and turn bounds before a request."""

    stage = "before_request"
    refusal = policy.validate()
    if refusal is not None:
        return _blocked(stage, refusal)
    if policy.provider_id not in {"anthropic", "openai"}:
        return _blocked(
            stage,
            _refusal(
                "tool_loop_provider_required",
                "The synthetic tool loop supports Anthropic and OpenAI only.",
                "Use one of the supported provider tool-loop adapters.",
            ),
        )
    if not 2 <= max_turns <= 3:
        return _blocked(
            stage,
            _refusal(
                "invalid_tool_loop_turn_limit",
                "The synthetic tool loop must allow two or three turns.",
                "Use two turns for a simple exchange or three for a final classification.",
            ),
        )
    if turn < 1 or turn > max_turns:
        return _blocked(
            stage,
            _refusal(
                "invalid_tool_loop_turn",
                "The requested tool-loop turn is outside the bounded range.",
                "Start at turn one and keep requests within the configured turn ceiling.",
            ),
        )
    if not isinstance(environment, SimulatedToolEnvironment):
        return _blocked(
            stage,
            _refusal(
                "invalid_environment",
                "The live tool loop requires the local synthetic environment.",
                "Use a built-in scenario through the local experiment runner.",
            ),
        )
    credential = os.environ.get(policy.credential_env_var)
    if not credential:
        return _blocked(
            stage,
            _refusal(
                "provider_credential_missing",
                "The required provider credential is not present.",
                f"Set {policy.credential_env_var} in the local process environment.",
            ),
        )
    if credential.strip().lower() in _PLACEHOLDER_CREDENTIALS:
        return _blocked(
            stage,
            _refusal(
                "provider_credential_placeholder",
                "The provider credential is still the command example placeholder.",
                f"Replace the placeholder with the local {policy.credential_env_var} value; do not paste the credential into a report or chat.",
            ),
        )
    return HookResult(stage=stage)


def after_response_hook(
    payload: object,
    *,
    available_tools: tuple[str, ...],
) -> HookResult:
    """Validate one model payload before the harness accepts its events."""

    stage = "after_response"
    refusal = validate_claude_output(payload, available_tools=available_tools)
    if refusal is not None:
        return _blocked(
            stage,
            _refusal(refusal.error, refusal.message, refusal.guidance),
        )
    return HookResult(stage=stage, value=payload)


def before_tool_hook(
    event: dict[str, object],
    *,
    available_tools: tuple[str, ...],
) -> HookResult:
    """Allow only listed, zero-argument synthetic tool calls."""

    stage = "before_tool"
    name = event.get("name")
    call_id = event.get("id")
    tool_input = event.get("input")
    if not isinstance(name, str) or name not in available_tools:
        return _blocked(
            stage,
            _refusal(
                "provider_tool_not_allowed",
                "The model requested a tool outside the scenario contract.",
                "Request only one of the synthetic tools listed in the scenario.",
            ),
        )
    if not isinstance(call_id, str):
        return _blocked(
            stage,
            _refusal(
                "provider_tool_identifier_invalid",
                "The model tool request did not contain a valid identifier.",
                "Return a stable identifier for each synthetic tool request.",
            ),
        )
    if not isinstance(tool_input, dict) or tool_input:
        return _blocked(
            stage,
            _refusal(
                "provider_raw_tool_arguments_rejected",
                "The model tool request contained arguments outside the synthetic contract.",
                "Use a listed synthetic tool with an empty input object.",
            ),
        )
    return HookResult(stage=stage, value=(name, call_id))


def after_tool_hook(
    observation: ToolObservation,
    *,
    call_id: str,
) -> HookResult:
    """Convert one local observation into a safe synthetic tool-result event."""

    result: dict[str, object] = {
        "type": "tool_result",
        "tool_use_id": call_id,
        "status": observation.result_status,
        "evidence_id": observation.result_id,
        "output_flags": list(observation.output_flags),
    }
    if observation.source is not None:
        result["source"] = observation.source
    if observation.age_seconds is not None:
        result["age_seconds"] = observation.age_seconds
    return HookResult(stage="after_tool", value=result)


def stop_hook(
    *,
    turn: int,
    max_turns: int,
    estimated_cost_usd: float,
    max_estimated_cost_usd: float,
) -> HookResult:
    """Block another tool transition when a bounded stop condition is reached."""

    stage = "stop"
    if turn >= max_turns:
        return _blocked(
            stage,
            _refusal(
                "tool_loop_turn_limit_exceeded",
                "The model requested another tool after the local turn ceiling.",
                "Reduce tool steps or raise the bounded turn limit deliberately.",
            ),
        )
    if estimated_cost_usd >= max_estimated_cost_usd:
        return _blocked(
            stage,
            _refusal(
                "tool_loop_spend_limit_exceeded",
                "The bounded tool loop reached its estimated spend ceiling.",
                "Reduce request cost or raise the local ceiling deliberately.",
            ),
        )
    return HookResult(stage=stage)


def _blocked(stage: str, refusal: AdapterRefusal) -> HookResult:
    """Attach a lifecycle stage without changing the refusal's safe content."""

    return HookResult(stage=stage, refusal=replace(refusal, stage=stage))
