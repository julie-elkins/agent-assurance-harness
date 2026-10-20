"""Local adapter and observable-event protocol.

Design rules:

1. Adapters return structured refusals instead of raising for malformed runs.
2. Events contain identifiers and classifications, never raw tool payloads or hidden
   reasoning.
3. A run must contain exactly one of a valid trace or a structured refusal.
4. Event sequence and identifier checks happen before scenario evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from .models import EvidenceContract, Trace


class EventType(str, Enum):
    """Observable event categories accepted by the local adapter boundary."""

    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    CLAIM = "claim"
    ANSWER = "answer"
    ABSTENTION = "abstention"
    SIDE_EFFECT = "side_effect"
    AUTHORIZATION = "authorization"


@dataclass(frozen=True)
class ObservableEvent:
    """A safe event summary emitted by an adapter."""

    sequence: int
    event_id: str
    event_type: EventType
    name: str
    status: str | None = None
    evidence_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return an identifier-only event representation."""

        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "name": self.name,
            "status": self.status,
            "evidence_id": self.evidence_id,
        }


@dataclass(frozen=True)
class ScenarioRequest:
    """The public input an adapter receives for one synthetic scenario."""

    scenario_id: str
    task_label: str
    available_tools: tuple[str, ...]
    contract: EvidenceContract


@dataclass(frozen=True)
class AdapterRefusal:
    """A structured refusal returned when an adapter cannot provide a valid run."""

    error: str
    message: str
    guidance: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-safe refusal."""

        return {
            "error": self.error,
            "message": self.message,
            "guidance": self.guidance,
        }


@dataclass(frozen=True)
class AdapterRun:
    """Exactly one accepted trace or one structured adapter refusal."""

    trace: Trace | None = None
    refusal: AdapterRefusal | None = None
    events: tuple[ObservableEvent, ...] = ()


class AgentAdapter(Protocol):
    """The local boundary an agent implementation must satisfy."""

    agent_id: str

    def run(
        self,
        request: ScenarioRequest,
        environment: object,
    ) -> AdapterRun:
        """Run one scenario against a supplied tool environment."""


def validate_adapter_run(run: AdapterRun) -> AdapterRefusal | None:
    """Return a refusal when an adapter result violates the local protocol."""

    if (run.trace is None) == (run.refusal is None):
        return AdapterRefusal(
            error="invalid_adapter_run",
            message="Adapter must return exactly one trace or one refusal.",
            guidance="Return AdapterRun(trace=...) for a valid run or AdapterRun(refusal=...) for a refusal.",
        )
    if run.refusal is not None:
        return None
    if not run.events:
        return AdapterRefusal(
            error="missing_observable_events",
            message="Accepted adapter runs must include observable events.",
            guidance="Emit identifier-only events for each observable tool or outcome event.",
        )
    event_ids = [event.event_id for event in run.events]
    if any(not event_id for event_id in event_ids):
        return AdapterRefusal(
            error="invalid_event_id",
            message="Every observable event must have an event identifier.",
            guidance="Assign a stable non-empty event_id to every emitted event.",
        )
    if len(event_ids) != len(set(event_ids)):
        return AdapterRefusal(
            error="duplicate_event_id",
            message="Observable event identifiers must be unique within a run.",
            guidance="Generate one identifier per event before returning the adapter result.",
        )
    sequences = [event.sequence for event in run.events]
    if sequences != list(range(1, len(sequences) + 1)):
        return AdapterRefusal(
            error="invalid_event_sequence",
            message="Observable event sequences must start at 1 and increase by one.",
            guidance="Re-number the emitted events before returning the adapter result.",
        )
    return None
