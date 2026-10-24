"""Versioned, metadata-only schemas for the local OpenAI adapter."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .claude_schema import validate_claude_output


OPENAI_SCHEMA_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
_ACTION_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_RELIABILITY_KINDS = (
    "claim",
    "answer",
    "abstention",
    "authorization",
    "side_effect",
    "operation_id",
    "idempotency_key",
    "reconciliation",
    "action_digest",
)


@dataclass(frozen=True)
class OpenAISchemaRefusal:
    """A safe schema refusal without provider content."""

    error: str
    message: str
    guidance: str


def openai_tool_definitions(
    tool_names: tuple[str, ...],
) -> list[dict[str, object]]:
    """Return strict zero-argument function tools for the Responses API."""

    return [
        {
            "type": "function",
            "name": tool_name,
            "description": (
                "Zero-argument synthetic tool. Use only to obtain "
                "identifier-level evidence for this scenario."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        }
        for tool_name in tool_names
    ]


def openai_structured_output_schema() -> dict[str, object]:
    """Return the strict Responses API schema for final classifications."""

    nullable_string = {"type": ["string", "null"]}
    event_properties = {
        "type": {"type": "string", "enum": ["classification"]},
        "kind": {"type": "string", "enum": list(_RELIABILITY_KINDS)},
        "id": nullable_string,
        "status": nullable_string,
        "operation_id": nullable_string,
        "action_digest": nullable_string,
    }
    workflow_properties = {
        "workflow_id": {"type": "string"},
        "transport_status": {"type": "string"},
        "semantic_outcome": {"type": "string"},
        "retry_count": {"type": "integer"},
        "estimated_cost_usd": {"type": "number"},
        "max_retries": {"type": "integer"},
        "max_estimated_cost_usd": {"type": "number"},
        "escalation_status": nullable_string,
        "escalation_id": nullable_string,
    }
    return {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": event_properties,
                    "required": list(event_properties),
                    "additionalProperties": False,
                },
            },
            "workflow": {
                "anyOf": [
                    {
                        "type": "object",
                        "properties": workflow_properties,
                        "required": list(workflow_properties),
                        "additionalProperties": False,
                    },
                    {"type": "null"},
                ]
            },
        },
        "required": ["events", "workflow"],
        "additionalProperties": False,
    }


def validate_openai_output(
    payload: object,
    *,
    available_tools: tuple[str, ...],
) -> OpenAISchemaRefusal | None:
    """Validate final OpenAI classifications through the shared local contract."""

    if not isinstance(payload, dict):
        return _refusal(
            "openai_schema_object_required",
            "The OpenAI payload must be a JSON object.",
            "Return the reviewed object with events and a nullable workflow field.",
        )
    events = payload.get("events")
    if not isinstance(events, list):
        return _refusal(
            "openai_schema_events_invalid",
            "The OpenAI payload events field must be an array.",
            "Return a non-empty array of identifier-only classification events.",
        )
    normalized_events: list[dict[str, object]] = []
    for event in events:
        if not isinstance(event, dict):
            return _refusal(
                "openai_schema_event_invalid",
                "An OpenAI classification event was not an object.",
                "Return classification objects with identifier-only fields.",
            )
        if event.get("type") != "classification":
            return _refusal(
                "openai_schema_event_type_invalid",
                "The OpenAI final response contained a non-classification event.",
                "Return classification events only after the tool loop completes.",
            )
        normalized = {
            key: value
            for key, value in event.items()
            if value is not None
        }
        normalized["type"] = "reliability"
        normalized_events.append(normalized)
    normalized_payload: dict[str, object] = {"content": normalized_events}
    workflow = payload.get("workflow")
    if workflow is not None:
        normalized_payload["workflow"] = _normalize_workflow(workflow)
    refusal = validate_claude_output(
        normalized_payload,
        available_tools=available_tools,
    )
    if refusal is None:
        return None
    return _refusal(
        refusal.error.replace("claude_", "openai_", 1),
        refusal.message.replace("Claude", "OpenAI"),
        refusal.guidance.replace("Claude", "OpenAI"),
    )


def _normalize_workflow(value: object) -> object:
    """Remove strict-schema nulls before shared local validation."""

    if not isinstance(value, dict):
        return value
    return {key: item for key, item in value.items() if item is not None}


def _refusal(
    error: str,
    message: str,
    guidance: str,
) -> OpenAISchemaRefusal:
    return OpenAISchemaRefusal(error=error, message=message, guidance=guidance)
