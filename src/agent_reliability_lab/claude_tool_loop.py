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

from .claude_schema import (
    claude_output_schema,
    synthetic_tool_definitions,
)
from .claude_hooks import (
    after_response_hook,
    after_tool_hook,
    before_request_hook,
    before_tool_hook,
    stop_hook,
)
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
from .protocol import AdapterRun, ScenarioRequest
from .providers import ProviderLimits, ProviderPayloadError, translate_provider_payload


MAX_TOOL_LOOP_TURNS = 3


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

        messages: list[dict[str, str]] = [
            {
                "role": "user",
                "content": json.dumps(_safe_request(request), sort_keys=True),
            }
        ]
        all_events: list[dict[str, object]] = []
        workflow_metadata: dict[str, object] | None = None
        total_output_tokens = 0
        total_elapsed_seconds = 0.0
        total_estimated_cost_usd = 0.0

        for turn in range(1, self.max_turns + 1):
            before_request = before_request_hook(
                self.policy,
                environment=environment,
                turn=turn,
                max_turns=self.max_turns,
            )
            if not before_request.allowed:
                return AdapterRun(
                    refusal=before_request.refusal,
                    execution_budget=(
                        _loop_budget(
                            self.policy,
                            requests=turn - 1,
                            output_tokens=total_output_tokens,
                            elapsed_seconds=total_elapsed_seconds,
                            estimated_cost_usd=total_estimated_cost_usd,
                            max_turns=self.max_turns,
                        )
                        if turn > 1
                        else None
                    ),
                )
            response = self._request(messages, request.available_tools)
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
                model_payload = _extract_loop_payload(
                    provider_response,
                    available_tools=request.available_tools,
                )
                response_hook = after_response_hook(
                    model_payload,
                    available_tools=request.available_tools,
                )
                if not response_hook.allowed:
                    raise ProviderPayloadError(
                        response_hook.refusal.error,
                        response_hook.refusal.message,
                        response_hook.refusal.guidance,
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
                if "workflow" in model_payload:
                    workflow = model_payload["workflow"]
                    if not isinstance(workflow, dict):
                        raise ProviderPayloadError(
                            "provider_workflow_invalid",
                            "The workflow field was not an object.",
                            "Return only the bounded identifier-and-number workflow object.",
                        )
                    workflow_metadata = workflow
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
                        stage="after_response",
                    ),
                    execution_budget=_loop_budget(
                        self.policy,
                        requests=turn,
                        output_tokens=total_output_tokens,
                        elapsed_seconds=total_elapsed_seconds,
                        estimated_cost_usd=(
                            total_estimated_cost_usd
                            + self.policy.estimated_cost_usd_per_request
                        ),
                        max_turns=self.max_turns,
                    ),
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
            normalized_events = [
                (
                    {
                        key: value
                        for key, value in event.items()
                        if key != "input"
                    }
                    if event.get("type") == "tool_use"
                    else event
                )
                for event in events
            ]
            if not tool_events:
                all_events.extend(normalized_events)
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
                if workflow_metadata is not None:
                    combined["workflow"] = workflow_metadata
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
            stop = stop_hook(
                turn=turn,
                max_turns=self.max_turns,
                estimated_cost_usd=total_estimated_cost_usd,
                max_estimated_cost_usd=(
                    self.policy.limits.max_estimated_cost_usd * self.max_turns
                ),
            )
            if not stop.allowed:
                return AdapterRun(
                    refusal=stop.refusal,
                    execution_budget=_loop_budget(
                        self.policy,
                        requests=turn,
                        output_tokens=total_output_tokens,
                        elapsed_seconds=total_elapsed_seconds,
                        estimated_cost_usd=total_estimated_cost_usd,
                        max_turns=self.max_turns,
                    ),
                )

            all_events.extend(normalized_events)
            tool_results: list[dict[str, object]] = []
            for event in tool_events:
                tool_hook = before_tool_hook(
                    event,
                    available_tools=request.available_tools,
                )
                if not tool_hook.allowed:
                    return AdapterRun(
                        refusal=tool_hook.refusal,
                        execution_budget=_loop_budget(
                            self.policy,
                            requests=turn,
                            output_tokens=total_output_tokens,
                            elapsed_seconds=total_elapsed_seconds,
                            estimated_cost_usd=total_estimated_cost_usd,
                            max_turns=self.max_turns,
                        ),
                    )
                name, call_id = tool_hook.value
                observation = environment.invoke(name)
                tool_result_hook = after_tool_hook(
                    observation,
                    call_id=call_id,
                )
                result = tool_result_hook.value
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
        available_tools: tuple[str, ...],
    ) -> tuple[dict[str, object], float] | AdapterRun:
        """Send one safe text-only conversation turn and parse it in memory."""

        body = _anthropic_conversation_body(
            self.policy,
            messages,
            available_tools,
        )
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
            return AdapterRun(
                refusal=replace(_http_refusal(error.code), stage="request_transport")
            )
        except (OSError, urllib.error.URLError, TimeoutError):
            return AdapterRun(
                refusal=_refusal(
                    "provider_transport_failed",
                    "The provider request did not complete.",
                    "Check the local network and provider availability; no retry was attempted.",
                    stage="request_transport",
                )
            )
        elapsed_seconds = time.monotonic() - started
        if not isinstance(response_bytes, bytes):
            return AdapterRun(
                refusal=_refusal(
                    "provider_transport_invalid_response",
                    "The provider transport did not return bytes.",
                    "Use a bytes response and keep provider parsing inside the adapter.",
                    stage="request_transport",
                )
            )
        if len(response_bytes) > _MAX_RESPONSE_BYTES:
            return AdapterRun(
                refusal=_refusal(
                    "provider_response_too_large",
                    "The provider response exceeded the local response-size ceiling.",
                    "Reduce the provider output before retrying.",
                    stage="request_transport",
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
                    stage="request_transport",
                )
            )
        if not isinstance(decoded, dict):
            return AdapterRun(
                refusal=_refusal(
                    "provider_response_refused",
                    "The provider response was not a JSON object.",
                    "Return one provider response object containing the safe content.",
                    stage="request_transport",
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
    available_tools: tuple[str, ...],
) -> bytes:
    """Build an Anthropic request from safe summaries and synthetic tools."""

    return json.dumps(
        {
            "model": policy.model,
            "max_tokens": policy.limits.max_output_tokens,
            "system": (
                _LIVE_INSTRUCTIONS
                + f" Output schema version is {claude_output_schema()['schema_version']}. "
                + "The reviewed output schema is "
                + json.dumps(claude_output_schema(), sort_keys=True)
                + " If you request a tool, return only tool_use events. "
                + "After tool results appear in the next user message, return "
                + "only reliability classification events."
            ),
            "messages": messages,
            "tools": synthetic_tool_definitions(available_tools),
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


def _extract_loop_payload(
    response: dict[str, object],
    *,
    available_tools: tuple[str, ...],
) -> dict[str, object]:
    """Accept safe text JSON or native zero-argument Anthropic tool blocks."""

    try:
        return _extract_model_payload("anthropic", response)
    except ProviderPayloadError:
        content = response.get("content")
        if not isinstance(content, list) or not content:
            raise
        native_events: list[dict[str, object]] = []
        for block in content:
            if not isinstance(block, dict):
                raise
            if block.get("type") == "text":
                if not isinstance(block.get("text"), str):
                    raise ProviderPayloadError(
                        "provider_native_text_block_refused",
                        "The native text block was not a string.",
                        "Return a valid text block or a zero-argument synthetic tool_use block.",
                    )
                continue
            if block.get("type") != "tool_use":
                raise
            if set(block) != {"type", "id", "name", "input"}:
                raise ProviderPayloadError(
                    "provider_native_tool_block_refused",
                    "The native tool block contained fields outside the reviewed shape.",
                    "Return a zero-argument synthetic tool_use block.",
                )
            name = block.get("name")
            call_id = block.get("id")
            tool_input = block.get("input")
            if (
                not isinstance(name, str)
                or name not in available_tools
                or not isinstance(call_id, str)
                or not isinstance(tool_input, dict)
                or tool_input
            ):
                raise ProviderPayloadError(
                    "provider_raw_tool_arguments_rejected",
                    "The native tool block was not a permitted zero-argument synthetic call.",
                    "Use one listed synthetic tool with an empty input object.",
                )
            native_events.append(
                {
                    "type": "tool_use",
                    "name": name,
                    "id": call_id,
                    "input": {},
                }
            )
        if not native_events:
            raise
        return {"content": native_events}
