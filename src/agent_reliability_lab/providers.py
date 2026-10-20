"""Provider-shaped adapters that preserve the local identifier-only boundary.

Design rules:

1. Mock provider payloads contain classifications and identifiers, never provider text.
2. Both provider shapes translate through TraceRecorder before evaluation.
3. Credential configuration names are validated without reading credential values.
4. Usage limits and live-execution policy refuse unsafe inputs instead of defaulting open.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .adapters import ScenarioAdapter
from .environment import SimulatedToolEnvironment
from .protocol import (
    AdapterRefusal,
    AdapterRun,
    ScenarioRequest,
)
from .recorder import TraceRecorder
from .scenarios import scenarios


_ENVIRONMENT_VARIABLE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_PROVIDERS = frozenset({"openai", "anthropic"})
_USAGE_FIELDS = {
    "requests",
    "output_tokens",
    "elapsed_seconds",
    "estimated_cost_usd",
}

# MODELLING ASSUMPTION: these limits are intentionally small synthetic defaults. They
# exercise refusal paths without pretending to estimate a live provider bill.
DEFAULT_PROVIDER_LIMITS = {
    "max_requests": 1,
    "max_output_tokens": 256,
    "max_elapsed_seconds": 5.0,
    "max_estimated_cost_usd": 0.01,
}


@dataclass(frozen=True)
class ProviderLimits:
    """Caller-supplied ceilings for one provider execution."""

    max_requests: int
    max_output_tokens: int
    max_elapsed_seconds: float
    max_estimated_cost_usd: float

    def validate(self) -> AdapterRefusal | None:
        """Return a refusal when a limit is missing or non-positive."""

        if self.max_requests < 1:
            return _refusal(
                "invalid_provider_limits",
                "max_requests must be at least 1.",
                "Set a positive request ceiling before running a provider.",
            )
        if self.max_output_tokens < 1:
            return _refusal(
                "invalid_provider_limits",
                "max_output_tokens must be at least 1.",
                "Set a positive output-token ceiling before running a provider.",
            )
        if self.max_elapsed_seconds <= 0:
            return _refusal(
                "invalid_provider_limits",
                "max_elapsed_seconds must be greater than zero.",
                "Set a positive time ceiling before running a provider.",
            )
        if self.max_estimated_cost_usd <= 0:
            return _refusal(
                "invalid_provider_limits",
                "max_estimated_cost_usd must be greater than zero.",
                "Set a positive spend ceiling before running a provider.",
            )
        return None

    def check_usage(self, usage: dict[str, int | float]) -> AdapterRefusal | None:
        """Return a refusal when synthetic usage exceeds a caller ceiling."""

        refusal = self.validate()
        if refusal is not None:
            return refusal
        if usage["requests"] > self.max_requests:
            return _refusal(
                "provider_request_limit_exceeded",
                "The provider response exceeded max_requests.",
                "Lower the requested work or raise the limit deliberately.",
            )
        if usage["output_tokens"] > self.max_output_tokens:
            return _refusal(
                "provider_token_limit_exceeded",
                "The provider response exceeded max_output_tokens.",
                "Lower the requested output or raise the limit deliberately.",
            )
        if usage["elapsed_seconds"] > self.max_elapsed_seconds:
            return _refusal(
                "provider_timeout_budget_exceeded",
                "The provider response exceeded max_elapsed_seconds.",
                "Fix the slow path or raise the time limit deliberately.",
            )
        if usage["estimated_cost_usd"] > self.max_estimated_cost_usd:
            return _refusal(
                "provider_spend_limit_exceeded",
                "The provider response exceeded max_estimated_cost_usd.",
                "Reduce the run or raise the spend limit deliberately.",
            )
        return None


@dataclass(frozen=True)
class ProviderPolicy:
    """The non-secret policy required before a provider can run."""

    provider_id: str
    credential_env_var: str
    limits: ProviderLimits
    live_enabled: bool = False

    def validate(self, *, live: bool = False) -> AdapterRefusal | None:
        """Validate policy without reading the named environment variable."""

        if self.provider_id not in _PROVIDERS:
            return _refusal(
                "unsupported_provider",
                "The provider is not supported by this adapter contract.",
                "Use openai or anthropic.",
            )
        if _ENVIRONMENT_VARIABLE.fullmatch(self.credential_env_var) is None:
            return _refusal(
                "invalid_credential_environment_variable",
                "credential_env_var must be an uppercase environment-variable name.",
                "Provide a name such as OPENAI_API_KEY; do not provide its value.",
            )
        refusal = self.limits.validate()
        if refusal is not None:
            return refusal
        if live and not self.live_enabled:
            return _refusal(
                "live_provider_disabled",
                "Live provider execution is disabled in the mocked adapter phase.",
                "Use the mocked adapter or complete the separate live-integration gate.",
            )
        return None


class ProviderPayloadError(ValueError):
    """Raised internally when a provider-shaped payload is not in the safe subset."""

    def __init__(self, error: str, message: str, guidance: str) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.guidance = guidance


@dataclass(frozen=True)
class MockProviderAdapter:
    """Translate one synthetic provider shape through TraceRecorder."""

    provider_id: str
    policy: ProviderPolicy
    agent_id: str

    def run(
        self,
        request: ScenarioRequest,
        environment: object,
    ) -> AdapterRun:
        """Generate and translate one safe provider-shaped synthetic response."""

        refusal = self.policy.validate()
        if refusal is not None:
            return AdapterRun(refusal=refusal)
        if not isinstance(environment, SimulatedToolEnvironment):
            return AdapterRun(
                refusal=_refusal(
                    "invalid_environment",
                    "Mock provider adapters require the synthetic tool environment.",
                    "Pass environment_for_scenario(request.scenario_id).",
                )
            )
        reference = ScenarioAdapter(
            agent_id=self.agent_id,
            guarded=True,
            scenario_cases=scenarios(),
        )
        reference_run = reference.run(request, environment)
        if reference_run.refusal is not None:
            return reference_run
        assert reference_run.trace is not None
        payload = _provider_payload(
            self.provider_id,
            reference_run.trace,
        )
        try:
            usage = _parse_usage(payload.get("usage"))
            refusal = self.policy.limits.check_usage(usage)
            if refusal is not None:
                return AdapterRun(refusal=refusal)
            return translate_provider_payload(
                self.provider_id,
                payload,
                scenario_id=request.scenario_id,
                agent_id=self.agent_id,
            )
        except ProviderPayloadError as error:
            return AdapterRun(
                refusal=AdapterRefusal(
                    error=error.error,
                    message=error.message,
                    guidance=error.guidance,
                )
            )


def mock_provider_adapters(
    provider: str = "all",
    *,
    limits: ProviderLimits | None = None,
) -> tuple[MockProviderAdapter, ...]:
    """Return the requested credential-free provider adapters."""

    if provider not in {*_PROVIDERS, "all"}:
        raise ValueError("provider must be openai, anthropic, or all.")
    selected = tuple(_PROVIDERS) if provider == "all" else (provider,)
    selected = tuple(sorted(selected))
    configured_limits = limits or ProviderLimits(**DEFAULT_PROVIDER_LIMITS)
    return tuple(
        MockProviderAdapter(
            provider_id=item,
            policy=ProviderPolicy(
                provider_id=item,
                credential_env_var=(
                    "OPENAI_API_KEY"
                    if item == "openai"
                    else "ANTHROPIC_API_KEY"
                ),
                limits=configured_limits,
            ),
            agent_id=f"{item}-mock",
        )
        for item in selected
    )


def translate_provider_payload(
    provider_id: str,
    payload: object,
    *,
    scenario_id: str,
    agent_id: str,
) -> AdapterRun:
    """Translate one reviewed provider-shaped payload through TraceRecorder."""

    try:
        data = _object(payload, "provider response")
        _parse_usage(data.get("usage"))
        if provider_id == "openai":
            return _translate_openai(
                data,
                scenario_id=scenario_id,
                agent_id=agent_id,
            )
        if provider_id == "anthropic":
            return _translate_anthropic(
                data,
                scenario_id=scenario_id,
                agent_id=agent_id,
            )
        raise ProviderPayloadError(
            "unsupported_provider",
            "The provider is not supported by this adapter contract.",
            "Use openai or anthropic.",
        )
    except ProviderPayloadError as error:
        return AdapterRun(
            refusal=AdapterRefusal(
                error=error.error,
                message=error.message,
                guidance=error.guidance,
            )
        )


def _provider_payload(
    provider_id: str,
    trace,
) -> dict[str, object]:
    usage = {
        "requests": 1,
        "output_tokens": 64,
        "elapsed_seconds": 0.01,
        "estimated_cost_usd": 0.001,
    }
    if provider_id == "openai":
        return {
            "events": _openai_events(trace),
            "usage": usage,
        }
    if provider_id == "anthropic":
        return {
            "content": _anthropic_events(trace),
            "stop_reason": "end_turn",
            "usage": usage,
        }
    raise ProviderPayloadError(
        "unsupported_provider",
        f"Provider {provider_id} is not supported.",
        "Use openai or anthropic.",
    )


def _openai_events(trace) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for index, call in enumerate(trace.tool_calls, start=1):
        call_id = call.result_id or f"call-{index:03d}"
        events.append(
            {
                "type": "function_call",
                "name": call.name,
                "call_id": call_id,
            }
        )
        events.append(
            {
                "type": "function_result",
                "call_id": call_id,
                "status": call.result_status,
                "evidence_id": call.result_id,
                "output_flags": (
                    list(trace.tool_output_flags) if index == 1 else []
                ),
            }
        )
    if trace.claim is not None:
        events.append(
            {
                "type": "classification",
                "kind": "claim",
                "id": "claim:provider_safe",
            }
        )
    if trace.answer is not None:
        events.append(
            {
                "type": "classification",
                "kind": "answer",
                "id": "answer:provider_safe",
            }
        )
    if trace.abstained:
        events.append({"type": "classification", "kind": "abstention"})
    events.extend(
        {
            "type": "authorization",
            "id": item,
            **(
                {"operation_id": trace.authorization_operation_ids[index]}
                if index < len(trace.authorization_operation_ids)
                else {}
            ),
            **(
                {"action_digest": trace.authorization_action_digests[index]}
                if index < len(trace.authorization_action_digests)
                else {}
            ),
        }
        for index, item in enumerate(trace.authorization_ids)
    )
    events.extend(
        {"type": "side_effect", "id": item}
        for item in trace.side_effects
    )
    events.extend(
        {"type": "classification", "kind": "operation_id", "id": item}
        for item in trace.operation_ids
    )
    events.extend(
        {"type": "classification", "kind": "idempotency_key", "id": item}
        for item in trace.idempotency_keys
    )
    events.extend(
        {
            "type": "classification",
            "kind": "reconciliation",
            "id": reconciliation_id,
            "status": trace.reconciliation_statuses[index],
        }
        for index, reconciliation_id in enumerate(trace.reconciliation_ids)
        if index < len(trace.reconciliation_statuses)
    )
    events.extend(
        {
            "type": "classification",
            "kind": "action_digest",
            "id": action_digest,
        }
        for action_digest in trace.action_digests
    )
    return events


def _anthropic_events(trace) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for index, call in enumerate(trace.tool_calls, start=1):
        call_id = call.result_id or f"tool-use-{index:03d}"
        events.append(
            {
                "type": "tool_use",
                "name": call.name,
                "id": call_id,
            }
        )
        events.append(
            {
                "type": "tool_result",
                "tool_use_id": call_id,
                "status": call.result_status,
                "evidence_id": call.result_id,
                "output_flags": (
                    list(trace.tool_output_flags) if index == 1 else []
                ),
            }
        )
    if trace.claim is not None:
        events.append(
            {
                "type": "reliability",
                "kind": "claim",
                "id": "claim:provider_safe",
            }
        )
    if trace.answer is not None:
        events.append(
            {
                "type": "reliability",
                "kind": "answer",
                "id": "answer:provider_safe",
            }
        )
    if trace.abstained:
        events.append({"type": "reliability", "kind": "abstention"})
    events.extend(
        {
            "type": "reliability",
            "kind": "authorization",
            "id": item,
            **(
                {"operation_id": trace.authorization_operation_ids[index]}
                if index < len(trace.authorization_operation_ids)
                else {}
            ),
            **(
                {"action_digest": trace.authorization_action_digests[index]}
                if index < len(trace.authorization_action_digests)
                else {}
            ),
        }
        for index, item in enumerate(trace.authorization_ids)
    )
    events.extend(
        {"type": "reliability", "kind": "side_effect", "id": item}
        for item in trace.side_effects
    )
    events.extend(
        {"type": "reliability", "kind": "operation_id", "id": item}
        for item in trace.operation_ids
    )
    events.extend(
        {"type": "reliability", "kind": "idempotency_key", "id": item}
        for item in trace.idempotency_keys
    )
    events.extend(
        {
            "type": "reliability",
            "kind": "reconciliation",
            "id": reconciliation_id,
            "status": trace.reconciliation_statuses[index],
        }
        for index, reconciliation_id in enumerate(trace.reconciliation_ids)
        if index < len(trace.reconciliation_statuses)
    )
    events.extend(
        {
            "type": "reliability",
            "kind": "action_digest",
            "id": action_digest,
        }
        for action_digest in trace.action_digests
    )
    return events


def _translate_openai(
    payload: dict[str, object],
    *,
    scenario_id: str,
    agent_id: str,
) -> AdapterRun:
    _keys(payload, {"events", "usage"}, "openai response")
    events = _list_of_objects(payload.get("events"), "openai response.events")
    recorder = TraceRecorder(scenario_id=scenario_id, agent_id=agent_id)
    call_names: dict[str, str] = {}
    for index, event in enumerate(events):
        event_type = _identifier(event.get("type"), f"openai events[{index}].type")
        if event_type == "function_call":
            _keys(
                event,
                {"type", "name", "call_id"},
                f"openai events[{index}]",
            )
            name = _identifier(event.get("name"), "openai function name")
            call_id = _identifier(event.get("call_id"), "openai call_id")
            call_names[call_id] = name
            recorder.record_tool_call(name)
        elif event_type == "function_result":
            _keys(
                event,
                {"type", "call_id", "status", "evidence_id", "output_flags"},
                f"openai events[{index}]",
            )
            call_id = _identifier(event.get("call_id"), "openai call_id")
            name = call_names.get(call_id)
            if name is None:
                raise ProviderPayloadError(
                    "provider_event_mismatch",
                    "OpenAI function result did not match a function call.",
                    "Emit one matching function call before each function result.",
                )
            recorder.record_tool_result(
                name,
                _identifier(event.get("status"), "openai result status"),
                result_id=_optional_identifier(
                    event.get("evidence_id"),
                    "openai evidence_id",
                ),
                output_flags=_identifier_list(
                    event.get("output_flags"),
                    "openai output_flags",
                ),
            )
        elif event_type == "classification":
            _keys(
                event,
                {"type", "kind", "id", "status", "operation_id", "action_digest"},
                f"openai events[{index}]",
            )
            _record_classification(
                recorder,
                _identifier(event.get("kind"), "openai classification kind"),
                _optional_identifier(event.get("id"), "openai classification id"),
                status=_optional_identifier(
                    event.get("status"),
                    "openai classification status",
                ),
                operation_id=_optional_identifier(
                    event.get("operation_id"),
                    "openai classification operation_id",
                ),
                action_digest=_optional_action_digest(
                    event.get("action_digest"),
                    "openai classification action_digest",
                ),
            )
        elif event_type in {"authorization", "side_effect"}:
            _keys(
                event,
                {"type", "id", "operation_id", "action_digest"},
                f"openai events[{index}]",
            )
            identifier = _identifier(event.get("id"), f"openai {event_type} id")
            if event_type == "authorization":
                operation_id = _optional_identifier(
                    event.get("operation_id"),
                    "openai authorization operation_id",
                )
                action_digest = event.get("action_digest")
                if action_digest is not None:
                    action_digest = _required_action_digest(
                        action_digest,
                        "openai authorization action_digest",
                    )
                recorder.record_authorization(
                    identifier,
                    operation_id=operation_id,
                    action_digest=action_digest,
                )
            else:
                recorder.record_side_effect(identifier)
        else:
            raise ProviderPayloadError(
                "unknown_provider_event",
                "OpenAI response contained an unsupported event type.",
                "Map the provider event to the reviewed safe subset before accepting it.",
            )
    return recorder.finish()


def _translate_anthropic(
    payload: dict[str, object],
    *,
    scenario_id: str,
    agent_id: str,
) -> AdapterRun:
    _keys(
        payload,
        {"content", "stop_reason", "usage"},
        "anthropic response",
    )
    _identifier(payload.get("stop_reason"), "anthropic stop_reason")
    events = _list_of_objects(payload.get("content"), "anthropic response.content")
    recorder = TraceRecorder(scenario_id=scenario_id, agent_id=agent_id)
    call_names: dict[str, str] = {}
    for index, event in enumerate(events):
        event_type = _identifier(event.get("type"), f"anthropic content[{index}].type")
        if event_type == "tool_use":
            _keys(
                event,
                {"type", "name", "id"},
                f"anthropic content[{index}]",
            )
            name = _identifier(event.get("name"), "anthropic tool name")
            call_id = _identifier(event.get("id"), "anthropic tool id")
            call_names[call_id] = name
            recorder.record_tool_call(name)
        elif event_type == "tool_result":
            _keys(
                event,
                {
                    "type",
                    "tool_use_id",
                    "status",
                    "evidence_id",
                    "output_flags",
                },
                f"anthropic content[{index}]",
            )
            call_id = _identifier(
                event.get("tool_use_id"),
                "anthropic tool_use_id",
            )
            name = call_names.get(call_id)
            if name is None:
                raise ProviderPayloadError(
                    "provider_event_mismatch",
                    "Anthropic tool result did not match a tool use event.",
                    "Emit one matching tool use before each tool result.",
                )
            recorder.record_tool_result(
                name,
                _identifier(event.get("status"), "anthropic result status"),
                result_id=_optional_identifier(
                    event.get("evidence_id"),
                    "anthropic evidence_id",
                ),
                output_flags=_identifier_list(
                    event.get("output_flags"),
                    "anthropic output_flags",
                ),
            )
        elif event_type == "reliability":
            _keys(
                event,
                {"type", "kind", "id", "status", "operation_id", "action_digest"},
                f"anthropic content[{index}]",
            )
            _record_classification(
                recorder,
                _identifier(event.get("kind"), "anthropic reliability kind"),
                _optional_identifier(event.get("id"), "anthropic reliability id"),
                status=_optional_identifier(
                    event.get("status"),
                    "anthropic reliability status",
                ),
                operation_id=_optional_identifier(
                    event.get("operation_id"),
                    "anthropic reliability operation_id",
                ),
                action_digest=_optional_action_digest(
                    event.get("action_digest"),
                    "anthropic reliability action_digest",
                ),
            )
        else:
            raise ProviderPayloadError(
                "unknown_provider_event",
                "Anthropic response contained an unsupported content type.",
                "Map the provider event to the reviewed safe subset before accepting it.",
            )
    return recorder.finish()


def _record_classification(
    recorder: TraceRecorder,
    kind: str,
    identifier: str | None,
    *,
    status: str | None = None,
    operation_id: str | None = None,
    action_digest: str | None = None,
) -> None:
    if kind == "claim":
        if identifier is None:
            raise ProviderPayloadError(
                "missing_classification_id",
                "A claim classification requires an identifier.",
                "Emit an identifier-only claim classification.",
            )
        recorder.record_claim(identifier)
    elif kind == "answer":
        if identifier is None:
            raise ProviderPayloadError(
                "missing_classification_id",
                "An answer classification requires an identifier.",
                "Emit an identifier-only answer classification.",
            )
        recorder.record_answer(identifier)
    elif kind == "abstention":
        recorder.record_abstention()
    elif kind == "authorization":
        if identifier is None:
            raise ProviderPayloadError(
                "missing_classification_id",
                "An authorization classification requires an identifier.",
                "Emit an identifier-only authorization classification.",
            )
        recorder.record_authorization(
            identifier,
            operation_id=operation_id,
            action_digest=action_digest,
        )
    elif kind == "side_effect":
        if identifier is None:
            raise ProviderPayloadError(
                "missing_classification_id",
                "A side-effect classification requires an identifier.",
                "Emit an identifier-only side-effect classification.",
            )
        recorder.record_side_effect(identifier)
    elif kind == "operation_id":
        if identifier is None:
            raise ProviderPayloadError(
                "missing_classification_id",
                "An operation-id classification requires an identifier.",
                "Emit an identifier-only operation-id classification.",
            )
        recorder.record_operation_id(identifier)
    elif kind == "idempotency_key":
        if identifier is None:
            raise ProviderPayloadError(
                "missing_classification_id",
                "An idempotency-key classification requires an identifier.",
                "Emit an identifier-only idempotency-key classification.",
            )
        recorder.record_idempotency_key(identifier)
    elif kind == "reconciliation":
        if identifier is None or status is None:
            raise ProviderPayloadError(
                "missing_classification_id",
                "A reconciliation classification requires an identifier and status.",
                "Emit an identifier-only reconciliation classification with its status.",
            )
        recorder.record_reconciliation(identifier, status)
    elif kind == "action_digest":
        if identifier is None:
            raise ProviderPayloadError(
                "missing_classification_id",
                "An action-digest classification requires an identifier.",
                "Emit an identifier-only sha256 action digest.",
            )
        recorder.record_action_digest(identifier)
    else:
        raise ProviderPayloadError(
            "unknown_reliability_classification",
            "The provider response contained an unsupported reliability classification.",
            "Map the classification to the reviewed safe subset before accepting it.",
        )


def _parse_usage(value: object) -> dict[str, int | float]:
    data = _object(value, "provider usage")
    _keys(data, _USAGE_FIELDS, "provider usage")
    result: dict[str, int | float] = {}
    for field in _USAGE_FIELDS:
        item = data.get(field)
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ProviderPayloadError(
                "invalid_provider_usage",
                "Provider usage must contain numeric measurements.",
                "Emit requests, output_tokens, elapsed_seconds, and estimated_cost_usd.",
            )
        if item < 0:
            raise ProviderPayloadError(
                "invalid_provider_usage",
                "Provider usage measurements cannot be negative.",
                "Emit non-negative synthetic usage measurements.",
            )
        result[field] = item
    return result


def _object(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderPayloadError(
            "invalid_provider_payload",
            f"{context} must be an object.",
            "Supply the reviewed provider-shaped object.",
        )
    return value


def _keys(value: dict[str, Any], allowed: set[str], context: str) -> None:
    if set(value) - allowed:
        raise ProviderPayloadError(
            "raw_or_unknown_provider_field",
            f"{context} contains a field outside the reviewed safe subset.",
            "Remove raw provider content and map only allowlisted fields.",
        )


def _list_of_objects(value: object, context: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ProviderPayloadError(
            "invalid_provider_payload",
            f"{context} must be a list.",
            "Supply a list of safe provider event objects.",
        )
    return [_object(item, f"{context}[{index}]") for index, item in enumerate(value)]


def _identifier(value: object, context: str) -> str:
    if not isinstance(value, str) or re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.:/-]*",
        value,
    ) is None:
        raise ProviderPayloadError(
            "invalid_provider_identifier",
            f"{context} must be an identifier.",
            "Use an identifier rather than free-form provider text.",
        )
    return value


def _optional_identifier(value: object, context: str) -> str | None:
    if value is None:
        return None
    return _identifier(value, context)


def _required_action_digest(value: object, context: str) -> str:
    if not isinstance(value, str) or re.fullmatch(
        r"sha256:[0-9a-f]{64}",
        value,
    ) is None:
        raise ProviderPayloadError(
            "invalid_provider_action_digest",
            f"{context} must be a lowercase sha256 digest identifier.",
            "Use the form sha256:<64 lowercase hexadecimal characters>.",
        )
    return value


def _optional_action_digest(value: object, context: str) -> str | None:
    if value is None:
        return None
    return _required_action_digest(value, context)


def _identifier_list(value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ProviderPayloadError(
            "invalid_provider_identifier_list",
            f"{context} must be a list of identifiers.",
            "Supply only classification identifiers.",
        )
    return tuple(_identifier(item, context) for item in value)


def _refusal(error: str, message: str, guidance: str) -> AdapterRefusal:
    return AdapterRefusal(error=error, message=message, guidance=guidance)
