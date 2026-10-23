"""Bounded Anthropic tool-loop adapter for the synthetic assurance harness.

The adapter models the minimum useful agent sequence: Claude requests a synthetic
tool, the local environment returns identifier-only evidence, and Claude emits a
final identifier-only classification. It is deliberately not a production runtime.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
from dataclasses import dataclass, replace

from .environment import SimulatedToolEnvironment
from .live import (
    HttpTransport,
    LiveProviderPolicy,
    _ENDPOINTS,
    _LIVE_INSTRUCTIONS,
    _MAX_RESPONSE_BYTES,
    _default_transport,
    _extract_model_payload,
    _headers,
    _http_refusal,
    _live_usage,
    _refusal,
)
from .models import ExecutionBudget
from .packs import build_environment_from_pack
from .protocol import AdapterRun, ScenarioRequest
from .providers import ProviderLimits, ProviderPayloadError, translate_provider_payload


MAX_TOOL_LOOP_TURNS = 3
_PLACEHOLDER_CREDENTIALS = frozenset(
    {"your-key-here", "replace-me", "replace-with-your-key"}
)


@dataclass(frozen=True)
class AnthropicToolLoopAdapter:
    """Run a bounded Anthropic conversation against a synthetic environment."""

    policy: LiveProviderPolicy
    max_turns: int = MAX_TOOL_LOOP_TURNS
    transport: HttpTransport | None = None

    @property
    def agent_id(self) -> str:
        """Return a stable identifier for the bounded tool-loop adapter."""

        return "anthropic-tool-loop-live"

    def run(
        self,
        request: ScenarioRequest,
        environment: object,
    ) -> AdapterRun:
        """Run model decision, synthetic tool results, and final classification."""

        refusal = self.policy.validate()
        if refusal is not None:
            return AdapterRun(refusal=refusal)
        if self.policy.provider_id != "anthropic":
            return AdapterRun(
                refusal=_refusal(
                    "tool_loop_provider_required",
                    "The synthetic tool loop supports Anthropic only.",
                    "Use the direct live adapter for another supported provider.",
                )
            )
        if not 2 <= self.max_turns <= MAX_TOOL_LOOP_TURNS:
            return AdapterRun(
                refusal=_refusal(
                    "invalid_tool_loop_turn_limit",
                    "The synthetic tool loop must allow two or three turns.",
                    "Use two turns for a simple exchange or three for a final classification.",
                )
            )
        if not isinstance(environment, SimulatedToolEnvironment):
            return AdapterRun(
                refusal=_refusal(
                    "invalid_environment",
                    "The live tool loop requires the local synthetic environment.",
                    "Use a built-in scenario through the local experiment runner.",
                )
            )

        credential = os.environ.get(self.policy.credential_env_var)
        if not credential:
            return AdapterRun(
                refusal=_refusal(
                    "provider_credential_missing",
                    "The required provider credential is not present.",
                    f"Set {self.policy.credential_env_var} in the local process environment.",
                )
            )
        if credential.strip().lower() in _PLACEHOLDER_CREDENTIALS:
            return AdapterRun(
                refusal=_refusal(
                    "provider_credential_placeholder",
                    "The provider credential is still the command example placeholder.",
                    f"Replace the placeholder with the local {self.policy.credential_env_var} value; do not paste the credential into a report or chat.",
                )
            )

        messages: list[dict[str, str]] = [
            {
                "role": "user",
                "content": json.dumps(_safe_request(request), sort_keys=True),
            }
        ]
        all_events: list[dict[str, object]] = []
        total_output_tokens = 0
        total_elapsed_seconds = 0.0
        total_estimated_cost_usd = 0.0

        for turn in range(1, self.max_turns + 1):
            response = self._request(messages)
            if isinstance(response, AdapterRun):
                return replace(
                    response,
                    execution_budget=_loop_budget(
                        self.policy,
                        requests=turn - 1,
                        output_tokens=total_output_tokens,
                        elapsed_seconds=total_elapsed_seconds,
                        estimated_cost_usd=total_estimated_cost_usd,
                        max_turns=self.max_turns,
                    )
                    if turn > 1
                    else None,
                )
            provider_response, elapsed_seconds = response
            try:
                model_payload = _extract_model_payload(
                    "anthropic",
                    provider_response,
                )
                usage = _live_usage(
                    provider_response,
                    elapsed_seconds=elapsed_seconds,
                    estimated_cost_usd=(
                        self.policy.estimated_cost_usd_per_request
                    ),
                )
                turn_budget = self.policy.limits.check_usage(usage)
                if turn_budget is not None:
                    return AdapterRun(refusal=turn_budget)
                content = model_payload["content"]
                if not isinstance(content, list) or not all(
                    isinstance(item, dict) for item in content
                ):
                    raise ProviderPayloadError(
                        "provider_response_refused",
                        "The Anthropic safe content field was not an event list.",
                        "Return one content array containing identifier-only events.",
                    )
                events = [item for item in content if isinstance(item, dict)]
                if any(event.get("type") == "tool_result" for event in events):
                    raise ProviderPayloadError(
                        "provider_tool_result_forbidden",
                        "The model returned a tool result that must come from the harness.",
                        "Return tool_use only; the harness supplies synthetic tool results.",
                    )
                total_output_tokens += int(usage["output_tokens"])
                total_elapsed_seconds += float(usage["elapsed_seconds"])
                total_estimated_cost_usd += float(
                    usage["estimated_cost_usd"]
                )
            except ProviderPayloadError as error:
                return AdapterRun(
                    refusal=_refusal(
                        error.error,
                        error.message,
                        error.guidance,
                    )
                )
            except (UnicodeDecodeError, json.JSONDecodeError):
                return AdapterRun(
                    refusal=_refusal(
                        "provider_response_refused",
                        "The provider response was not valid UTF-8 JSON.",
                        "Return the requested safe JSON object without surrounding prose.",
                    )
                )

            tool_events = [
                event for event in events if event.get("type") == "tool_use"
            ]
            if not tool_events:
                all_events.extend(events)
                combined = {
                    "content": all_events,
                    "stop_reason": "end_turn",
                    "usage": {
                        "requests": turn,
                        "output_tokens": total_output_tokens,
                        "elapsed_seconds": total_elapsed_seconds,
                        "estimated_cost_usd": total_estimated_cost_usd,
                    },
                }
                translated = translate_provider_payload(
                    "anthropic",
                    combined,
                    scenario_id=request.scenario_id,
                    agent_id=self.agent_id,
                )
                return replace(
                    translated,
                    execution_budget=_loop_budget(
                        self.policy,
                        requests=turn,
                        output_tokens=total_output_tokens,
                        elapsed_seconds=total_elapsed_seconds,
                        estimated_cost_usd=total_estimated_cost_usd,
                        max_turns=self.max_turns,
                    ),
                )

            if any(event.get("type") != "tool_use" for event in events):
                return AdapterRun(
                    refusal=_refusal(
                        "provider_tool_turn_mixed_events",
                        "A tool-request turn contained final classification events.",
                        "Return only tool_use events before the harness supplies tool results.",
                    )
                )
            if turn == self.max_turns:
                return AdapterRun(
                    refusal=_refusal(
                        "tool_loop_turn_limit_exceeded",
                        "The model requested another tool after the local turn ceiling.",
                        "Reduce tool steps or raise the bounded turn limit deliberately.",
                    ),
                    execution_budget=_loop_budget(
                        self.policy,
                        requests=turn,
                        output_tokens=total_output_tokens,
                        elapsed_seconds=total_elapsed_seconds,
                        estimated_cost_usd=total_estimated_cost_usd,
                        max_turns=self.max_turns,
                    ),
                )

            all_events.extend(events)
            tool_results: list[dict[str, object]] = []
            for event in tool_events:
                name = event.get("name")
                call_id = event.get("id")
                if not isinstance(name, str) or name not in request.available_tools:
                    return AdapterRun(
                        refusal=_refusal(
                            "provider_tool_not_allowed",
                            "The model requested a tool outside the scenario contract.",
                            "Request only one of the synthetic tools listed in the scenario.",
                        )
                    )
                if not isinstance(call_id, str):
                    return AdapterRun(
                        refusal=_refusal(
                            "provider_tool_identifier_invalid",
                            "The model tool request did not contain a valid identifier.",
                            "Return a stable identifier for each synthetic tool request.",
                        )
                    )
                observation = environment.invoke(name)
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
                all_events.append(result)
                tool_results.append(result)

            messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(
                        {"content": events},
                        separators=(",", ":"),
                    ),
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {"tool_results": tool_results},
                        separators=(",", ":"),
                    ),
                }
            )
        raise RuntimeError("Tool loop exited without a result.")

    def _request(
        self,
        messages: list[dict[str, str]],
    ) -> tuple[dict[str, object], float] | AdapterRun:
        """Send one safe text-only conversation turn and parse it in memory."""

        body = _anthropic_conversation_body(self.policy, messages)
        credential = os.environ[self.policy.credential_env_var]
        started = time.monotonic()
        try:
            transport = self.transport or _default_transport
            response_bytes = transport(
                _ENDPOINTS["anthropic"],
                _headers("anthropic", credential),
                body,
                self.policy.limits.max_elapsed_seconds,
            )
        except urllib.error.HTTPError as error:
            return AdapterRun(refusal=_http_refusal(error.code))
        except (OSError, urllib.error.URLError, TimeoutError):
            return AdapterRun(
                refusal=_refusal(
                    "provider_transport_failed",
                    "The provider request did not complete.",
                    "Check the local network and provider availability; no retry was attempted.",
                )
            )
        elapsed_seconds = time.monotonic() - started
        if not isinstance(response_bytes, bytes):
            return AdapterRun(
                refusal=_refusal(
                    "provider_transport_invalid_response",
                    "The provider transport did not return bytes.",
                    "Use a bytes response and keep provider parsing inside the adapter.",
                )
            )
        if len(response_bytes) > _MAX_RESPONSE_BYTES:
            return AdapterRun(
                refusal=_refusal(
                    "provider_response_too_large",
                    "The provider response exceeded the local response-size ceiling.",
                    "Reduce the provider output before retrying.",
                )
            )
        try:
            decoded = json.loads(response_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return AdapterRun(
                refusal=_refusal(
                    "provider_response_refused",
                    "The provider response was not valid UTF-8 JSON.",
                    "Return the requested safe JSON object without surrounding prose.",
                )
            )
        if not isinstance(decoded, dict):
            return AdapterRun(
                refusal=_refusal(
                    "provider_response_refused",
                    "The provider response was not a JSON object.",
                    "Return one provider response object containing the safe content.",
                )
            )
        return decoded, elapsed_seconds


def anthropic_tool_loop_adapter(
    policy: LiveProviderPolicy,
    *,
    max_turns: int = MAX_TOOL_LOOP_TURNS,
    transport: HttpTransport | None = None,
) -> AnthropicToolLoopAdapter:
    """Construct a bounded Anthropic tool-loop adapter."""

    return AnthropicToolLoopAdapter(
        policy=policy,
        max_turns=max_turns,
        transport=transport,
    )


def _safe_request(request: ScenarioRequest) -> dict[str, object]:
    """Return the fixed synthetic request shape shared by loop turns."""

    return {
        "scenario_id": request.scenario_id,
        "available_tools": list(request.available_tools),
        "requirement_ids": [
            requirement.requirement_id
            for requirement in request.contract.requirements
        ],
    }


def _anthropic_conversation_body(
    policy: LiveProviderPolicy,
    messages: list[dict[str, str]],
) -> bytes:
    """Build a text-only Anthropic request from safe event summaries."""

    return json.dumps(
        {
            "model": policy.model,
            "max_tokens": policy.limits.max_output_tokens,
            "system": (
                _LIVE_INSTRUCTIONS
                + " If you request a tool, return only tool_use events. "
                + "After tool results appear in the next user message, return "
                + "only reliability classification events."
            ),
            "messages": messages,
        },
        separators=(",", ":"),
    ).encode("utf-8")


def _loop_budget(
    policy: LiveProviderPolicy,
    *,
    requests: int,
    output_tokens: int,
    elapsed_seconds: float,
    estimated_cost_usd: float,
    max_turns: int,
) -> ExecutionBudget:
    """Return aggregate metadata for a bounded multi-turn case."""

    limits = ProviderLimits(
        max_requests=max_turns,
        max_output_tokens=policy.limits.max_output_tokens * max_turns,
        max_elapsed_seconds=policy.limits.max_elapsed_seconds * max_turns,
        max_estimated_cost_usd=policy.limits.max_estimated_cost_usd * max_turns,
    )
    return limits.execution_budget(
        {
            "requests": requests,
            "output_tokens": output_tokens,
            "elapsed_seconds": elapsed_seconds,
            "estimated_cost_usd": estimated_cost_usd,
        }
    )
