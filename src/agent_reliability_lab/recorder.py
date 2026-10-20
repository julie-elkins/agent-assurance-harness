"""Provider-neutral recording of safe, observable agent events.

Design rules:

1. The recorder accepts identifiers and classifications, never raw arguments,
   result payloads, prompts, or hidden reasoning.
2. Tool calls must be paired with results before a run can be accepted.
3. Invalid input becomes a structured refusal rather than a partial trace.
4. The recorder emits the existing AdapterRun and ReplayCase protocols so callers
   do not need a provider-specific integration or a second serializer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .models import ToolCall, Trace
from .protocol import (
    AdapterRefusal,
    AdapterRun,
    EventType,
    ObservableEvent,
    validate_adapter_run,
)
from .replay import ReplayCase


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")


@dataclass(frozen=True)
class RecorderResult:
    """The outcome of one recording operation."""

    accepted: bool
    event: ObservableEvent | None = None
    refusal: AdapterRefusal | None = None


class TraceRecorder:
    """Build one identifier-only adapter run from observable agent callbacks.

    A recorder is stateful by design: create one instance for one scenario execution
    and do not share it across concurrent runs. This keeps event order and tool
    call/result pairing explicit.
    """

    def __init__(self, *, scenario_id: str, agent_id: str) -> None:
        self._scenario_id = scenario_id
        self._agent_id = agent_id
        self._events: list[ObservableEvent] = []
        self._pending_tool_calls: list[str] = []
        self._tool_calls: list[ToolCall] = []
        self._evidence_ids: list[str] = []
        self._side_effects: list[str] = []
        self._authorization_ids: list[str] = []
        self._tool_output_flags: list[str] = []
        self._claim: str | None = None
        self._answer: str | None = None
        self._abstained = False
        self._refusal: AdapterRefusal | None = None

        invalid = _identifier_refusal(scenario_id, "scenario_id")
        if invalid is None:
            invalid = _identifier_refusal(agent_id, "agent_id")
        if invalid is not None:
            self._refusal = invalid

    @property
    def scenario_id(self) -> str:
        """Return the scenario identifier assigned to this recorder."""

        return self._scenario_id

    @property
    def agent_id(self) -> str:
        """Return the agent identifier assigned to this recorder."""

        return self._agent_id

    def record_tool_call(
        self,
        tool_name: str,
        *,
        arguments: object | None = None,
    ) -> RecorderResult:
        """Record a tool name without accepting its raw argument payload."""

        blocked = self._blocked()
        if blocked is not None:
            return blocked
        if arguments is not None:
            return self._refuse(
                error="raw_tool_arguments_rejected",
                message="Raw tool arguments are not accepted by TraceRecorder.",
                guidance="Record only the tool identifier; classify the result with record_tool_result.",
            )
        invalid = _identifier_refusal(tool_name, "tool_name")
        if invalid is not None:
            return self._set_refusal(invalid)
        self._pending_tool_calls.append(tool_name)
        return self._event(EventType.TOOL_CALL, tool_name)

    def record_tool_result(
        self,
        tool_name: str,
        result_status: str,
        *,
        result_id: str | None = None,
        output_flags: Iterable[str] = (),
        payload: object | None = None,
    ) -> RecorderResult:
        """Record a classified tool result without storing its raw payload."""

        blocked = self._blocked()
        if blocked is not None:
            return blocked
        if payload is not None:
            return self._refuse(
                error="raw_tool_payload_rejected",
                message="Raw tool-result payloads are not accepted by TraceRecorder.",
                guidance="Record result_status, result_id, and output_flags only.",
            )
        invalid = _identifier_refusal(tool_name, "tool_name")
        if invalid is None:
            invalid = _identifier_refusal(result_status, "result_status")
        if invalid is None and result_id is not None:
            invalid = _identifier_refusal(result_id, "result_id")
        flags, flags_refusal = _identifier_values(output_flags, "output_flags")
        if invalid is None:
            invalid = flags_refusal
        if invalid is not None:
            return self._set_refusal(invalid)
        if tool_name not in self._pending_tool_calls:
            return self._refuse(
                error="tool_result_without_call",
                message=f"No pending tool call was recorded for {tool_name}.",
                guidance="Record the matching tool call before recording its result.",
            )
        self._pending_tool_calls.remove(tool_name)
        self._tool_calls.append(
            ToolCall(
                name=tool_name,
                arguments={},
                result_status=result_status,
                result_id=result_id,
            )
        )
        if result_id is not None:
            _append_unique(self._evidence_ids, result_id)
        for flag in flags:
            _append_unique(self._tool_output_flags, flag)
        return self._event(
            EventType.TOOL_RESULT,
            tool_name,
            status=result_status,
            evidence_id=result_id,
        )

    def record_claim(self, claim_id: str) -> RecorderResult:
        """Record a claim identifier, not the claim's free-form text."""

        blocked = self._blocked()
        if blocked is not None:
            return blocked
        invalid = _identifier_refusal(claim_id, "claim_id")
        if invalid is not None:
            return self._set_refusal(invalid)
        if self._claim is not None:
            return self._refuse(
                error="duplicate_claim",
                message="TraceRecorder accepts one claim identifier per run.",
                guidance="Create a new recorder for a separate scenario run.",
            )
        self._claim = claim_id
        return self._event(EventType.CLAIM, "claim")

    def record_answer(self, answer_id: str) -> RecorderResult:
        """Record an answer classification, not the answer's free-form text."""

        blocked = self._blocked()
        if blocked is not None:
            return blocked
        invalid = _identifier_refusal(answer_id, "answer_id")
        if invalid is not None:
            return self._set_refusal(invalid)
        if self._answer is not None:
            return self._refuse(
                error="duplicate_answer",
                message="TraceRecorder accepts one answer identifier per run.",
                guidance="Create a new recorder for a separate scenario run.",
            )
        self._answer = answer_id
        return self._event(EventType.ANSWER, "answer")

    def record_abstention(self) -> RecorderResult:
        """Record that the agent deliberately abstained."""

        blocked = self._blocked()
        if blocked is not None:
            return blocked
        if self._abstained:
            return self._refuse(
                error="duplicate_abstention",
                message="TraceRecorder accepts one abstention event per run.",
                guidance="Create a new recorder for a separate scenario run.",
            )
        self._abstained = True
        return self._event(EventType.ABSTENTION, "abstention")

    def record_authorization(self, authorization_id: str) -> RecorderResult:
        """Record an authorization identifier without recording its contents."""

        blocked = self._blocked()
        if blocked is not None:
            return blocked
        invalid = _identifier_refusal(authorization_id, "authorization_id")
        if invalid is not None:
            return self._set_refusal(invalid)
        if authorization_id in self._authorization_ids:
            return self._refuse(
                error="duplicate_authorization",
                message=f"Authorization identifier {authorization_id} was already recorded.",
                guidance="Record each authorization identifier once per run.",
            )
        self._authorization_ids.append(authorization_id)
        return self._event(EventType.AUTHORIZATION, authorization_id)

    def record_side_effect(self, side_effect_id: str) -> RecorderResult:
        """Record a synthetic side-effect identifier."""

        blocked = self._blocked()
        if blocked is not None:
            return blocked
        invalid = _identifier_refusal(side_effect_id, "side_effect_id")
        if invalid is not None:
            return self._set_refusal(invalid)
        if side_effect_id in self._side_effects:
            return self._refuse(
                error="duplicate_side_effect",
                message=f"Side-effect identifier {side_effect_id} was already recorded.",
                guidance="Record each side-effect identifier once per run.",
            )
        self._side_effects.append(side_effect_id)
        return self._event(EventType.SIDE_EFFECT, side_effect_id)

    def record_tool_output_flag(self, flag_id: str) -> RecorderResult:
        """Record a classified tool-output flag without recording output content."""

        blocked = self._blocked()
        if blocked is not None:
            return blocked
        invalid = _identifier_refusal(flag_id, "tool_output_flag")
        if invalid is not None:
            return self._set_refusal(invalid)
        _append_unique(self._tool_output_flags, flag_id)
        return self._event(EventType.TOOL_OUTPUT_FLAG, flag_id)

    def finish(self) -> AdapterRun:
        """Return the accepted run or a structured refusal."""

        if self._refusal is not None:
            return AdapterRun(refusal=self._refusal)
        if self._pending_tool_calls:
            return AdapterRun(
                refusal=AdapterRefusal(
                    error="unresolved_tool_call",
                    message=(
                        "The run ended with tool calls that have no recorded result: "
                        + ", ".join(self._pending_tool_calls)
                        + "."
                    ),
                    guidance="Record every tool result before finishing the run.",
                )
            )
        run = AdapterRun(
            trace=Trace(
                scenario_id=self._scenario_id,
                agent_id=self._agent_id,
                tool_calls=tuple(self._tool_calls),
                claim=self._claim,
                answer=self._answer,
                abstained=self._abstained,
                evidence_ids=tuple(self._evidence_ids),
                side_effects=tuple(self._side_effects),
                authorization_ids=tuple(self._authorization_ids),
                tool_output_flags=tuple(self._tool_output_flags),
            ),
            events=tuple(self._events),
        )
        refusal = validate_adapter_run(run)
        return AdapterRun(refusal=refusal) if refusal is not None else run

    def finish_replay_case(self) -> ReplayCase:
        """Return this run in the replay-file case shape."""

        return ReplayCase(scenario_id=self._scenario_id, response=self.finish())

    def _event(
        self,
        event_type: EventType,
        name: str,
        *,
        status: str | None = None,
        evidence_id: str | None = None,
    ) -> RecorderResult:
        event = ObservableEvent(
            sequence=len(self._events) + 1,
            event_id=f"event-{len(self._events) + 1:03d}",
            event_type=event_type,
            name=name,
            status=status,
            evidence_id=evidence_id,
        )
        self._events.append(event)
        return RecorderResult(accepted=True, event=event)

    def _refuse(
        self,
        *,
        error: str,
        message: str,
        guidance: str,
    ) -> RecorderResult:
        return self._set_refusal(
            AdapterRefusal(error=error, message=message, guidance=guidance)
        )

    def _blocked(self) -> RecorderResult | None:
        if self._refusal is None:
            return None
        return RecorderResult(accepted=False, refusal=self._refusal)

    def _set_refusal(self, refusal: AdapterRefusal) -> RecorderResult:
        if self._refusal is None:
            self._refusal = refusal
        return RecorderResult(accepted=False, refusal=self._refusal)


def _identifier_refusal(value: object, context: str) -> AdapterRefusal | None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        return AdapterRefusal(
            error="invalid_identifier",
            message=f"{context} must be a non-empty identifier.",
            guidance=(
                "Use letters, numbers, dots, underscores, colons, slashes, or hyphens; "
                "do not send free-form text."
            ),
        )
    return None


def _identifier_values(
    values: Iterable[str],
    context: str,
) -> tuple[tuple[str, ...], AdapterRefusal | None]:
    if isinstance(values, (str, bytes)):
        return (), AdapterRefusal(
            error="invalid_identifier_list",
            message=f"{context} must be an iterable of identifiers, not text.",
            guidance="Supply a list or tuple of classification identifiers.",
        )
    try:
        values_tuple = tuple(values)
    except TypeError:
        return (), AdapterRefusal(
            error="invalid_identifier_list",
            message=f"{context} must be an iterable of identifiers.",
            guidance="Supply only classification identifiers.",
        )
    for value in values_tuple:
        refusal = _identifier_refusal(value, context)
        if refusal is not None:
            return (), refusal
    return values_tuple, None


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
