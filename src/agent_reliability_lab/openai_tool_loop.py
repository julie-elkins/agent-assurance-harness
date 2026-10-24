"""Bounded OpenAI Responses tool-loop adapter for synthetic assurance cases.

The adapter uses native Responses API function calls, supplies identifier-only
synthetic results locally, and accepts a final identifier-only classification.
It is a research adapter, not a production agent runtime.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
from dataclasses import dataclass, replace

from .claude_hooks import (
    after_response_hook,
    before_request_hook,
    before_tool_hook,
    stop_hook,
)
from .environment import ToolObservation
from .live import (
    HttpTransport,
    LiveProviderPolicy,
    _ENDPOINTS,
    _LIVE_INSTRUCTIONS,
    _MAX_RESPONSE_BYTES,
    _default_transport,
    _headers,
    _http_refusal,
    _live_usage,
    _refusal,
)
from .models import ExecutionBudget
from .openai_schema import (
    openai_structured_output_schema,
    openai_tool_definitions,
    validate_openai_output,
)
from .protocol import AdapterRun, ScenarioRequest
from .providers import ProviderLimits, ProviderPayloadError, translate_provider_payload


MAX_OPENAI_TOOL_LOOP_TURNS = 3


@dataclass(frozen=True)
class OpenAIToolLoopAdapter:
    """Run a bounded OpenAI Responses conversation over a synthetic environment."""

    policy: LiveProviderPolicy
    max_turns: int = MAX_OPENAI_TOOL_LOOP_TURNS
    transport: HttpTransport | None = None
    structured_output: bool = False

    @property
    def agent_id(self) -> str:
        """Return a stable identifier for the bounded tool-loop adapter."""

        return "openai-tool-loop-live"

    def run(
        self,
        request: ScenarioRequest,
        environment: object,
    ) -> AdapterRun:
        """Run bounded function calls, local results, and final classification."""

        input_items: list[object] = [
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

            response = self._request(input_items, request.available_tools)
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
                usage = _live_usage(
                    provider_response,
                    elapsed_seconds=elapsed_seconds,
                    estimated_cost_usd=self.policy.estimated_cost_usd_per_request,
                )
                turn_budget = self.policy.limits.check_usage(usage)
                if turn_budget is not None:
                    return AdapterRun(refusal=turn_budget)
                total_output_tokens += int(usage["output_tokens"])
                total_elapsed_seconds += float(usage["elapsed_seconds"])
                total_estimated_cost_usd += float(usage["estimated_cost_usd"])

                tool_calls = _extract_function_calls(
                    provider_response,
                    available_tools=request.available_tools,
                )
                if tool_calls:
                    if _has_message_output(provider_response):
                        return AdapterRun(
                            refusal=_refusal(
                                "provider_tool_turn_mixed_events",
                                "An OpenAI tool-request turn also contained final text.",
                                "Return only synthetic function calls before the harness supplies results.",
                                stage="after_response",
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
                    stop = stop_hook(
                        turn=turn,
                        max_turns=self.max_turns,
                        estimated_cost_usd=total_estimated_cost_usd,
                        max_estimated_cost_usd=(
                            self.policy.limits.max_estimated_cost_usd
                            * self.max_turns
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
                    sanitized_output_items: list[dict[str, object]] = []
                    function_results: list[dict[str, object]] = []
                    for call in tool_calls:
                        tool_event = {
                            "type": "tool_use",
                            "name": call["name"],
                            "id": call["call_id"],
                            "input": {},
                        }
                        tool_hook = before_tool_hook(
                            tool_event,
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
                        result = _openai_function_result(
                            observation,
                            call_id=call_id,
                        )
                        all_events.append(
                            {
                                "type": "function_call",
                                "name": name,
                                "call_id": call_id,
                            }
                        )
                        all_events.append(result)
                        sanitized_output_items.append(
                            {
                                "type": "function_call",
                                "name": name,
                                "call_id": call_id,
                                "arguments": "{}",
                            }
                        )
                        function_results.append(
                            {
                                "type": "function_call_output",
                                "call_id": call_id,
                                "output": json.dumps(
                                    {
                                        key: value
                                        for key, value in result.items()
                                        if key not in {"type", "call_id"}
                                    },
                                    separators=(",", ":"),
                                ),
                            }
                        )
                    input_items.extend(sanitized_output_items)
                    input_items.extend(function_results)
                    continue

                payload = _extract_final_payload(provider_response)
                response_hook = _validate_final_payload(
                    payload,
                    available_tools=request.available_tools,
                )
                if response_hook is not None:
                    return AdapterRun(
                        refusal=response_hook,
                        execution_budget=_loop_budget(
                            self.policy,
                            requests=turn,
                            output_tokens=total_output_tokens,
                            elapsed_seconds=total_elapsed_seconds,
                            estimated_cost_usd=total_estimated_cost_usd,
                            max_turns=self.max_turns,
                        ),
                    )
                final_events = payload["events"]
                if not isinstance(final_events, list) or not all(
                    isinstance(event, dict) for event in final_events
                ):
                    raise ProviderPayloadError(
                        "provider_response_refused",
                        "The OpenAI events field was not an event list.",
                        "Return one events array containing identifier-only classifications.",
                    )
                all_events.extend(final_events)
                if payload.get("workflow") is not None:
                    workflow = payload["workflow"]
                    if not isinstance(workflow, dict):
                        raise ProviderPayloadError(
                            "provider_workflow_invalid",
                            "The workflow field was not an object.",
                            "Return only the bounded workflow object or null.",
                        )
                    workflow_metadata = workflow
                combined = {
                    "events": all_events,
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
                    "openai",
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
                        estimated_cost_usd=total_estimated_cost_usd,
                        max_turns=self.max_turns,
                    ),
                )
            except (UnicodeDecodeError, json.JSONDecodeError):
                return AdapterRun(
                    refusal=_refusal(
                        "provider_response_refused",
                        "The provider response was not valid UTF-8 JSON.",
                        "Return the requested safe JSON object without surrounding prose.",
                        stage="after_response",
                    )
                )
        raise RuntimeError("OpenAI tool loop exited without a result.")

    def _request(
        self,
        input_items: list[object],
        available_tools: tuple[str, ...],
    ) -> tuple[dict[str, object], float] | AdapterRun:
        """Send one Responses API turn and parse it in memory."""

        body = _openai_conversation_body(
            self.policy,
            input_items,
            available_tools,
            structured_output=self.structured_output,
        )
        credential = os.environ[self.policy.credential_env_var]
        started = time.monotonic()
        try:
            transport = self.transport or _default_transport
            response_bytes = transport(
                _ENDPOINTS["openai"],
                _headers("openai", credential),
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
                    "Return one provider response object containing the safe output.",
                    stage="request_transport",
                )
            )
        return decoded, elapsed_seconds


def openai_tool_loop_adapter(
    policy: LiveProviderPolicy,
    *,
    max_turns: int = MAX_OPENAI_TOOL_LOOP_TURNS,
    transport: HttpTransport | None = None,
    structured_output: bool = False,
) -> OpenAIToolLoopAdapter:
    """Construct a bounded OpenAI Responses tool-loop adapter."""

    return OpenAIToolLoopAdapter(
        policy=policy,
        max_turns=max_turns,
        transport=transport,
        structured_output=structured_output,
    )


def _safe_request(request: ScenarioRequest) -> dict[str, object]:
    """Return only fixed synthetic identifiers in the provider input."""

    return {
        "scenario_id": request.scenario_id,
        "available_tools": list(request.available_tools),
        "requirement_ids": [
            requirement.requirement_id
            for requirement in request.contract.requirements
        ],
    }


def _openai_conversation_body(
    policy: LiveProviderPolicy,
    input_items: list[object],
    available_tools: tuple[str, ...],
    *,
    structured_output: bool,
) -> bytes:
    """Build one native Responses API request."""

    body: dict[str, object] = {
        "model": policy.model,
        "store": False,
        "instructions": (
            _LIVE_INSTRUCTIONS
            + " The final response must contain an events array of OpenAI "
            "classification objects. Tool calls must be zero-argument native "
            "function calls; after tool results, emit classifications only. "
            "For this OpenAI adapter, every final event must use "
            "\"type\":\"classification\"; do not use the Anthropic "
            "\"type\":\"reliability\" event type, and do not include "
            "function_call or function_result items in final events."
        ),
        "input": input_items,
        "max_output_tokens": policy.limits.max_output_tokens,
        "tools": openai_tool_definitions(available_tools),
        "tool_choice": "auto",
        "parallel_tool_calls": False,
    }
    if structured_output:
        body["text"] = {
            "format": {
                "type": "json_schema",
                "name": "agent_reliability_output",
                "strict": True,
                "schema": openai_structured_output_schema(),
            }
        }
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def _extract_function_calls(
    response: dict[str, object],
    *,
    available_tools: tuple[str, ...],
) -> list[dict[str, str]]:
    """Extract and validate native zero-argument Responses function calls."""

    output = response.get("output")
    if not isinstance(output, list):
        return []
    calls: list[dict[str, str]] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "function_call":
            continue
        name = item.get("name")
        call_id = item.get("call_id")
        arguments = item.get("arguments")
        if not isinstance(name, str) or name not in available_tools:
            raise ProviderPayloadError(
                "provider_native_tool_name_invalid",
                "The OpenAI function call named a tool outside the scenario contract.",
                "Use one listed synthetic function name.",
            )
        if not isinstance(call_id, str) or not call_id:
            raise ProviderPayloadError(
                "provider_native_tool_identifier_invalid",
                "The OpenAI function call did not contain a valid call identifier.",
                "Return a stable call_id for each synthetic function call.",
            )
        if arguments != "{}":
            raise ProviderPayloadError(
                "provider_native_tool_arguments_rejected",
                "The OpenAI function call contained arguments outside the synthetic contract.",
                "Use an empty JSON object for the zero-argument synthetic function.",
            )
        calls.append({"name": name, "call_id": call_id})
    return calls


def _has_message_output(response: dict[str, object]) -> bool:
    """Return whether a tool-request response also contains model message text."""

    output = response.get("output")
    return isinstance(output, list) and any(
        isinstance(item, dict) and item.get("type") == "message"
        for item in output
    )


def _extract_final_payload(response: dict[str, object]) -> dict[str, object]:
    """Parse the single final output_text JSON object."""

    output = response.get("output")
    if not isinstance(output, list):
        raise ProviderPayloadError(
            "provider_response_refused",
            "The OpenAI response did not contain an output list.",
            "Return one message containing the safe JSON object.",
        )
    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if (
                isinstance(part, dict)
                and part.get("type") == "output_text"
                and isinstance(part.get("text"), str)
            ):
                texts.append(part["text"])
    if len(texts) != 1:
        raise ProviderPayloadError(
            "provider_response_refused",
            "The OpenAI response did not contain exactly one final structured output.",
            "Return exactly one output_text JSON object after tool results.",
        )
    payload = json.loads(texts[0])
    if not isinstance(payload, dict):
        raise ProviderPayloadError(
            "provider_response_refused",
            "The OpenAI final output was not a JSON object.",
            "Return an object containing events and workflow.",
        )
    return payload


def _validate_final_payload(
    payload: dict[str, object],
    *,
    available_tools: tuple[str, ...],
) -> object:
    """Return a local refusal or None after final schema validation."""

    refusal = validate_openai_output(
        payload,
        available_tools=available_tools,
    )
    if refusal is None:
        return None
    return _refusal(refusal.error, refusal.message, refusal.guidance, stage="after_response")


def _openai_function_result(
    observation: ToolObservation,
    *,
    call_id: str,
) -> dict[str, object]:
    """Convert a synthetic observation to a safe OpenAI event."""

    result: dict[str, object] = {
        "type": "function_result",
        "call_id": call_id,
        "status": observation.result_status,
        "evidence_id": observation.result_id,
        "output_flags": list(observation.output_flags),
    }
    if observation.source is not None:
        result["source"] = observation.source
    if observation.age_seconds is not None:
        result["age_seconds"] = observation.age_seconds
    return result


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
