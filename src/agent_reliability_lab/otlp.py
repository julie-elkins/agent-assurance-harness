"""Strict, local normalization of safe OTLP/JSON agent trace exports.

Design rules:

1. The importer reads a constrained OTLP/JSON envelope and emits the existing replay
   protocol; it never returns a copy of the input trace.
2. Known content-bearing GenAI attributes are refused before normalization rather than
   silently dropped.
3. Only scalar identifiers, classifications, and safe reliability events reach the
   TraceRecorder.
4. This module has no network listener, collector, credential path, or OpenTelemetry
   SDK dependency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .replay import (
    REPLAY_VERSION,
    ReplayCase,
    ReplayFile,
    ReplayLoadResult,
    ReplayRefusal,
)
from .recorder import TraceRecorder


# FIELD CONVENTION: These names come from the OpenTelemetry GenAI semantic convention
# and the OTLP/JSON export shape. The importer reads only the fields it can normalize.
# See https://opentelemetry.io/docs/specs/otlp/ and
# https://github.com/open-telemetry/semantic-conventions/blob/main/docs/gen-ai/gen-ai-spans.md.
_SENSITIVE_ATTRIBUTE_KEYS = frozenset(
    {
        "gen_ai.input.messages",
        "gen_ai.output.messages",
        "gen_ai.system_instructions",
        "gen_ai.tool.call.arguments",
        "gen_ai.tool.call.result",
        "gen_ai.tool.definitions",
        "gen_ai.retrieval.query",
        "gen_ai.retrieval.query.text",
        "gen_ai.retrieval.documents",
        "http.request.body",
        "http.response.body",
        "log.body",
        "exception.message",
    }
)
# MODELLING ASSUMPTION: A suffix denylist catches common custom payload keys while the
# explicit set above covers the known GenAI content attributes. A producer using a new
# content key may be refused by the strict scalar parser until it is reviewed.
_SENSITIVE_ATTRIBUTE_SUFFIXES = (
    ".arguments",
    ".messages",
    ".instructions",
    ".payload",
)
# MODELLING ASSUMPTION: These event names are a local extension owned by this repository;
# they are not claimed as OpenTelemetry standard names.
_RELIABILITY_EVENT_IDS = {
    "agent.reliability.claim",
    "agent.reliability.answer",
    "agent.reliability.authorization",
    "agent.reliability.side_effect",
    "agent.reliability.tool_output_flag",
    "agent.reliability.operation_id",
    "agent.reliability.idempotency_key",
    "agent.reliability.reconciliation",
}
_RELIABILITY_EVENT_ABSTENTION = "agent.reliability.abstention"


class OtlpDecodeError(ValueError):
    """Raised internally when the safe OTLP subset cannot be decoded."""

    def __init__(self, error: str, message: str, guidance: str) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.guidance = guidance


@dataclass(frozen=True)
class _Span:
    """The safe subset of one OTLP span retained in process."""

    span_id: str
    attributes: dict[str, tuple[object, ...]]
    events: tuple[dict[str, Any], ...]
    status_code: object
    order: int


def otlp_to_replay(
    value: object,
    *,
    source: str = "otlp",
) -> ReplayLoadResult:
    """Normalize a local OTLP/JSON object into one identifier-only replay file."""

    try:
        resources = _resource_spans(value)
        spans: list[tuple[str, _Span]] = []
        agent_ids: set[str] = set()
        for resource_index, resource_span in enumerate(resources):
            resource = _object(
                resource_span.get("resource", {}),
                f"resourceSpans[{resource_index}].resource",
            )
            resource_attributes = _attributes(
                resource.get("attributes", []),
                f"resourceSpans[{resource_index}].resource.attributes",
            )
            agent_id = _first_string(
                resource_attributes,
                "service.name",
            ) or _first_string(
                resource_attributes,
                "agent.reliability.agent_id",
            )
            if agent_id is None:
                raise OtlpDecodeError(
                    "missing_agent_id",
                    "Each resource must identify the agent with service.name.",
                    "Add a safe service.name or agent.reliability.agent_id attribute.",
                )
            agent_ids.add(agent_id)
            for scope_index, scope_span in enumerate(
                _list(
                    resource_span.get("scopeSpans", []),
                    f"resourceSpans[{resource_index}].scopeSpans",
                )
            ):
                scope_data = _object(
                    scope_span,
                    f"resourceSpans[{resource_index}].scopeSpans[{scope_index}]",
                )
                for span_index, raw_span in enumerate(
                    _list(
                        scope_data.get("spans", []),
                        f"resourceSpans[{resource_index}].scopeSpans[{scope_index}].spans",
                    )
                ):
                    span = _parse_span(
                        raw_span,
                        f"resourceSpans[{resource_index}].scopeSpans[{scope_index}].spans[{span_index}]",
                        order=len(spans),
                    )
                    scenario_id = _first_string(
                        span.attributes,
                        "agent.reliability.scenario_id",
                    )
                    if scenario_id is None:
                        raise OtlpDecodeError(
                            "missing_scenario_id",
                            "Every span must identify its synthetic scenario.",
                            "Add agent.reliability.scenario_id as an identifier-only attribute.",
                        )
                    spans.append((scenario_id, span))

        if not spans:
            raise OtlpDecodeError(
                "empty_otlp_trace",
                "The OTLP export contains no spans.",
                "Provide spans containing safe tool or reliability events.",
            )
        if len(agent_ids) != 1:
            raise OtlpDecodeError(
                "multiple_agent_ids",
                "The OTLP export must contain exactly one agent identifier.",
                "Export one agent run at a time.",
            )
        agent_id = next(iter(agent_ids))
        cases = []
        for scenario_id in sorted({scenario for scenario, _ in spans}):
            recorder = TraceRecorder(
                scenario_id=scenario_id,
                agent_id=agent_id,
            )
            scenario_spans = sorted(
                (span for current_id, span in spans if current_id == scenario_id),
                key=lambda span: (span.order, span.span_id),
            )
            for span in scenario_spans:
                _record_span(recorder, span)
            run = recorder.finish()
            if run.refusal is not None:
                raise OtlpDecodeError(
                    "trace_recording_refused",
                    run.refusal.message,
                    run.refusal.guidance,
                )
            cases.append(ReplayCase(scenario_id=scenario_id, response=run))
        return ReplayLoadResult(
            replay=ReplayFile(
                replay_version=REPLAY_VERSION,
                agent_id=agent_id,
                cases=tuple(cases),
            )
        )
    except OtlpDecodeError as error:
        return ReplayLoadResult(
            refusal=ReplayRefusal(
                error=error.error,
                message=error.message,
                guidance=error.guidance,
                source=source,
            )
        )


def load_otlp_file(path: Path) -> ReplayLoadResult:
    """Read one local UTF-8 OTLP/JSON export without returning its raw contents."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ReplayLoadResult(
            refusal=ReplayRefusal(
                error="unreadable_otlp_file",
                message="The OTLP file could not be read as UTF-8 JSON.",
                guidance="Supply one OTLP/JSON object with resourceSpans.",
                source=str(path),
            )
        )
    return otlp_to_replay(value, source=str(path))


def _resource_spans(value: object) -> list[object]:
    data = _object(value, "otlp")
    return _list(data.get("resourceSpans"), "otlp.resourceSpans")


def _parse_span(value: object, context: str, *, order: int) -> _Span:
    data = _object(value, context)
    span_id = _string(data.get("spanId"), f"{context}.spanId")
    attributes = _attributes(
        data.get("attributes", []),
        f"{context}.attributes",
    )
    events = _list(data.get("events", []), f"{context}.events")
    safe_events = []
    for index, event in enumerate(events):
        event_data = _object(event, f"{context}.events[{index}]")
        name = _string(event_data.get("name"), f"{context}.events[{index}].name")
        event_attributes = _attributes(
            event_data.get("attributes", []),
            f"{context}.events[{index}].attributes",
        )
        safe_events.append({"name": name, "attributes": event_attributes})
    status = data.get("status", {})
    status_data = _object(status, f"{context}.status")
    return _Span(
        span_id=span_id,
        attributes=attributes,
        events=tuple(safe_events),
        status_code=status_data.get("code", 0),
        order=order,
    )


def _record_span(recorder: TraceRecorder, span: _Span) -> None:
    operation = _first_string(span.attributes, "gen_ai.operation.name")
    if operation == "execute_tool":
        tool_name = _first_string(span.attributes, "gen_ai.tool.name")
        if tool_name is None:
            raise OtlpDecodeError(
                "missing_tool_name",
                "An execute_tool span has no gen_ai.tool.name.",
                "Add the tool identifier without exporting its arguments or result.",
            )
        result_status = _first_string(
            span.attributes,
            "agent.reliability.result.status",
        ) or _status_from_code(span.status_code)
        result_id = _first_string(
            span.attributes,
            "gen_ai.tool.call.id",
        ) or f"span:{span.span_id}"
        output_flags = _strings(
            span.attributes,
            "agent.reliability.tool_output_flag",
        )
        recorder.record_tool_call(tool_name)
        recorder.record_tool_result(
            tool_name,
            result_status,
            result_id=result_id,
            output_flags=output_flags,
        )
    for event in span.events:
        _record_event(
            recorder,
            event["name"],
            event["attributes"],
        )


def _record_event(
    recorder: TraceRecorder,
    name: str,
    attributes: dict[str, tuple[object, ...]],
) -> None:
    if name == _RELIABILITY_EVENT_ABSTENTION:
        recorder.record_abstention()
        return
    if name not in _RELIABILITY_EVENT_IDS:
        return
    event_id = _first_string(attributes, "agent.reliability.id")
    if event_id is None:
        raise OtlpDecodeError(
            "missing_reliability_event_id",
            f"{name} has no agent.reliability.id.",
            "Add an identifier-only event id; do not include event content.",
        )
    if name == "agent.reliability.claim":
        recorder.record_claim(event_id)
    elif name == "agent.reliability.answer":
        recorder.record_answer(event_id)
    elif name == "agent.reliability.authorization":
        recorder.record_authorization(event_id)
    elif name == "agent.reliability.side_effect":
        recorder.record_side_effect(event_id)
    elif name == "agent.reliability.operation_id":
        recorder.record_operation_id(event_id)
    elif name == "agent.reliability.idempotency_key":
        recorder.record_idempotency_key(event_id)
    elif name == "agent.reliability.reconciliation":
        status = _first_string(attributes, "agent.reliability.status")
        if status is None:
            raise OtlpDecodeError(
                "missing_reconciliation_status",
                "A reconciliation event has no status classification.",
                "Add an identifier-only agent.reliability.status value.",
            )
        recorder.record_reconciliation(event_id, status)
    else:
        recorder.record_tool_output_flag(event_id)


def _status_from_code(value: object) -> str:
    if value in (1, "1", "STATUS_CODE_OK", "OK"):
        return "ok"
    if value in (2, "2", "STATUS_CODE_ERROR", "ERROR"):
        return "error"
    return "unknown"


def _attributes(value: object, context: str) -> dict[str, tuple[object, ...]]:
    values = _list(value, context)
    result: dict[str, list[object]] = {}
    for index, raw_attribute in enumerate(values):
        attribute = _object(raw_attribute, f"{context}[{index}]")
        key = _string(attribute.get("key"), f"{context}[{index}].key")
        if _is_sensitive(key):
            raise OtlpDecodeError(
                "sensitive_attribute_rejected",
                f"OTLP attribute {key} is not accepted by the local privacy boundary.",
                "Export identifiers or classifications only; omit content-bearing attributes.",
            )
        attribute_value = _object(
            attribute.get("value"),
            f"{context}[{index}].value",
        )
        result.setdefault(key, []).extend(
            _scalar_values(attribute_value, f"{context}[{index}].value")
        )
    return {key: tuple(values) for key, values in result.items()}


def _scalar_values(value: dict[str, Any], context: str) -> list[object]:
    for field in ("stringValue", "boolValue", "intValue", "doubleValue"):
        if field in value:
            scalar = value[field]
            if field == "stringValue" and isinstance(scalar, str):
                return [scalar]
            if field == "boolValue" and isinstance(scalar, bool):
                return [scalar]
            if field in {"intValue", "doubleValue"} and isinstance(
                scalar,
                (int, float, str),
            ):
                return [scalar]
            raise OtlpDecodeError(
                "invalid_attribute_value",
                f"{context}.{field} has an invalid scalar value.",
                "Use a scalar OTLP value for safe identifiers and classifications.",
            )
    array_value = value.get("arrayValue")
    if array_value is not None:
        array_data = _object(array_value, f"{context}.arrayValue")
        values = _list(array_data.get("values"), f"{context}.arrayValue.values")
        result = []
        for index, item in enumerate(values):
            item_data = _object(item, f"{context}.arrayValue.values[{index}]")
            item_values = _scalar_values(
                item_data,
                f"{context}.arrayValue.values[{index}]",
            )
            if len(item_values) != 1 or not isinstance(item_values[0], str):
                raise OtlpDecodeError(
                    "invalid_attribute_value",
                    f"{context}.arrayValue must contain strings.",
                    "Use string classifications for repeated safe attributes.",
                )
            result.extend(item_values)
        return result
    raise OtlpDecodeError(
        "invalid_attribute_value",
        f"{context} must contain one scalar OTLP value.",
        "Use a scalar value for safe identifiers and classifications.",
    )


def _is_sensitive(key: str) -> bool:
    return key in _SENSITIVE_ATTRIBUTE_KEYS or key.endswith(
        _SENSITIVE_ATTRIBUTE_SUFFIXES
    )


def _first_string(
    attributes: dict[str, tuple[object, ...]],
    key: str,
) -> str | None:
    values = attributes.get(key, ())
    return next((value for value in values if isinstance(value, str)), None)


def _strings(
    attributes: dict[str, tuple[object, ...]],
    key: str,
) -> tuple[str, ...]:
    return tuple(value for value in attributes.get(key, ()) if isinstance(value, str))


def _object(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OtlpDecodeError(
            "invalid_otlp_shape",
            f"{context} must be an object.",
            "Supply the OTLP/JSON object shape documented for this importer.",
        )
    return value


def _list(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise OtlpDecodeError(
            "invalid_otlp_shape",
            f"{context} must be a list.",
            "Supply the OTLP/JSON list shape documented for this importer.",
        )
    return value


def _string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise OtlpDecodeError(
            "invalid_otlp_identifier",
            f"{context} must be a non-empty string.",
            "Provide the required OTLP identifier.",
        )
    return value
