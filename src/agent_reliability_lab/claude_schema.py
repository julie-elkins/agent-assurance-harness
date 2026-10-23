"""Versioned, metadata-only schemas for the local Claude adapter."""

from __future__ import annotations

import re
from dataclasses import dataclass


CLAUDE_SCHEMA_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
_ACTION_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_RELIABILITY_KINDS = frozenset(
    {
        "claim",
        "answer",
        "abstention",
        "authorization",
        "side_effect",
        "operation_id",
        "idempotency_key",
        "reconciliation",
        "action_digest",
    }
)
_EVENT_KEYS = {"type", "kind", "id", "status", "operation_id", "action_digest"}
_WORKFLOW_KEYS = {
    "workflow_id",
    "transport_status",
    "semantic_outcome",
    "retry_count",
    "estimated_cost_usd",
    "max_retries",
    "max_estimated_cost_usd",
    "escalation_status",
    "escalation_id",
}


@dataclass(frozen=True)
class ClaudeSchemaRefusal:
    """A safe schema refusal without provider content."""

    error: str
    message: str
    guidance: str


def synthetic_tool_definitions(
    tool_names: tuple[str, ...],
) -> list[dict[str, object]]:
    """Return explicit zero-argument tool definitions for the provider request."""

    return [
        {
            "name": tool_name,
            "description": (
                "Zero-argument synthetic tool. Use only to obtain "
                "identifier-level evidence for this scenario."
            ),
            "input_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        }
        for tool_name in tool_names
    ]


def claude_output_schema() -> dict[str, object]:
    """Return the reviewed JSON contract embedded in the local request."""

    return {
        "schema_version": CLAUDE_SCHEMA_VERSION,
        "object": {
            "required": ["content"],
            "optional": ["workflow"],
            "content_event_types": ["tool_use", "reliability"],
            "tool_use": {
                "required": ["type", "name", "id", "input"],
                "input": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
            "reliability": {
                "required": ["type", "kind"],
                "identifier_required_for": [
                    "claim",
                    "answer",
                    "authorization",
                    "side_effect",
                    "operation_id",
                    "idempotency_key",
                    "reconciliation",
                    "action_digest",
                ],
                "status_required_for": ["reconciliation"],
            },
            "workflow": {
                "required": [
                    "workflow_id",
                    "transport_status",
                    "semantic_outcome",
                    "retry_count",
                    "estimated_cost_usd",
                    "max_retries",
                    "max_estimated_cost_usd",
                ],
                "optional": ["escalation_status", "escalation_id"],
            },
        },
    }


def validate_claude_output(
    payload: object,
    *,
    available_tools: tuple[str, ...],
) -> ClaudeSchemaRefusal | None:
    """Validate the safe Claude payload before passing it to the translator."""

    if not isinstance(payload, dict):
        return _refusal(
            "claude_schema_object_required",
            "The Claude payload must be a JSON object.",
            "Return the versioned object with content and optional workflow fields.",
        )
    if set(payload) not in ({"content"}, {"content", "workflow"}):
        return _refusal(
            "claude_schema_top_level_invalid",
            "The Claude payload contains fields outside the reviewed schema.",
            "Return only content and, for workflow scenarios, workflow.",
        )
    content = payload.get("content")
    if not isinstance(content, list) or not content:
        return _refusal(
            "claude_schema_content_invalid",
            "The Claude payload content must be a non-empty event list.",
            "Return identifier-only tool_use or reliability events.",
        )
    for index, event in enumerate(content):
        refusal = _validate_event(event, index, available_tools)
        if refusal is not None:
            return refusal
    if "workflow" in payload:
        refusal = _validate_workflow(payload["workflow"])
        if refusal is not None:
            return refusal
    return None


def _validate_event(
    event: object,
    index: int,
    available_tools: tuple[str, ...],
) -> ClaudeSchemaRefusal | None:
    if not isinstance(event, dict):
        return _refusal(
            "claude_schema_event_invalid",
            f"Claude content event {index} was not an object.",
            "Return objects using the reviewed tool_use or reliability event shape.",
        )
    event_type = event.get("type")
    if event_type == "tool_use":
        if set(event) != {"type", "name", "id", "input"}:
            return _refusal(
                "claude_schema_tool_use_invalid",
                "The Claude tool_use event contains unsupported fields.",
                "Return type, name, id, and an empty input object only.",
            )
        name = event.get("name")
        call_id = event.get("id")
        tool_input = event.get("input")
        if (
            not isinstance(name, str)
            or name not in available_tools
            or not isinstance(call_id, str)
            or _IDENTIFIER.fullmatch(call_id) is None
            or not isinstance(tool_input, dict)
            or tool_input
        ):
            return _refusal(
                "claude_schema_tool_use_arguments_invalid",
                "The Claude tool_use event was not a listed zero-argument synthetic call.",
                "Use one listed tool, a stable identifier, and an empty input object.",
            )
        return None
    if event_type != "reliability":
        return _refusal(
            "claude_schema_event_type_invalid",
            "Claude returned an unsupported event type.",
            "Use tool_use or reliability events only.",
        )
    if set(event) - _EVENT_KEYS:
        return _refusal(
            "claude_schema_reliability_fields_invalid",
            "The reliability event contains unsupported fields.",
            "Use only the reviewed reliability fields.",
        )
    kind = event.get("kind")
    if (
        not isinstance(kind, str)
        or _IDENTIFIER.fullmatch(kind) is None
        or kind not in _RELIABILITY_KINDS
    ):
        return _refusal(
            "claude_schema_reliability_kind_invalid",
            "The reliability event kind was not a valid identifier.",
            "Use one reviewed reliability classification kind.",
        )
    if kind != "abstention":
        identifier = event.get("id")
        if (
            not isinstance(identifier, str)
            or _IDENTIFIER.fullmatch(identifier) is None
        ):
            return _refusal(
                "claude_schema_reliability_id_required",
                "The reliability classification requires an identifier.",
                "Emit an identifier-only classification with an id field.",
            )
    if kind == "reconciliation" and (
        not isinstance(event.get("status"), str)
        or _IDENTIFIER.fullmatch(event["status"]) is None
    ):
        return _refusal(
            "claude_schema_reconciliation_status_required",
            "The reconciliation classification requires an identifier and status.",
            "Emit both id and status for reconciliation.",
        )
    if kind == "action_digest":
        identifier = event.get("id")
        if not isinstance(identifier, str) or _ACTION_DIGEST.fullmatch(identifier) is None:
            return _refusal(
                "claude_schema_action_digest_invalid",
                "The action-digest classification requires a sha256 identifier.",
                "Emit an identifier in the reviewed sha256 format.",
            )
    return None


def _validate_workflow(value: object) -> ClaudeSchemaRefusal | None:
    if not isinstance(value, dict):
        return _refusal(
            "claude_schema_workflow_invalid",
            "The workflow field must be an object.",
            "Return only the bounded identifier-and-number workflow object.",
        )
    required = {
        "workflow_id",
        "transport_status",
        "semantic_outcome",
        "retry_count",
        "estimated_cost_usd",
        "max_retries",
        "max_estimated_cost_usd",
    }
    if set(value) - _WORKFLOW_KEYS or not required.issubset(value):
        return _refusal(
            "claude_schema_workflow_fields_invalid",
            "The workflow object does not match the reviewed field set.",
            "Include all required workflow fields and no unsupported fields.",
        )
    for field in ("workflow_id", "transport_status", "semantic_outcome"):
        if (
            not isinstance(value[field], str)
            or _IDENTIFIER.fullmatch(value[field]) is None
        ):
            return _refusal(
                "claude_schema_workflow_identifier_invalid",
                "A workflow identifier field was invalid.",
                "Use identifier-only workflow values.",
            )
    for field in (
        "retry_count",
        "estimated_cost_usd",
        "max_retries",
        "max_estimated_cost_usd",
    ):
        number = value[field]
        if (
            isinstance(number, bool)
            or not isinstance(number, (int, float))
            or number < 0
        ):
            return _refusal(
                "claude_schema_workflow_number_invalid",
                "A workflow numeric field was invalid.",
                "Use non-negative numeric workflow values.",
            )
    for field in ("escalation_status", "escalation_id"):
        if field in value and (
            not isinstance(value[field], str)
            or _IDENTIFIER.fullmatch(value[field]) is None
        ):
            return _refusal(
                "claude_schema_escalation_invalid",
                "An escalation field was invalid.",
                "Use identifier-only escalation values.",
            )
    return None


def _refusal(
    error: str,
    message: str,
    guidance: str,
) -> ClaudeSchemaRefusal:
    return ClaudeSchemaRefusal(error=error, message=message, guidance=guidance)
