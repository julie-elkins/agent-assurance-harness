from agent_reliability_lab.models import Trace
from agent_reliability_lab.protocol import (
    AdapterRefusal,
    AdapterRun,
    EventType,
    ObservableEvent,
    validate_adapter_run,
)


def _valid_run() -> AdapterRun:
    return AdapterRun(
        trace=Trace(scenario_id="synthetic", agent_id="reference"),
        events=(
            ObservableEvent(
                sequence=1,
                event_id="event-001",
                event_type=EventType.CLAIM,
                name="claim",
            ),
        ),
    )


def test_valid_adapter_run_has_no_refusal():
    assert validate_adapter_run(_valid_run()) is None


def test_adapter_refuses_when_event_sequence_is_not_contiguous():
    run = AdapterRun(
        trace=Trace(scenario_id="synthetic", agent_id="reference"),
        events=(
            ObservableEvent(
                sequence=2,
                event_id="event-001",
                event_type=EventType.CLAIM,
                name="claim",
            ),
        ),
    )

    refusal = validate_adapter_run(run)

    assert isinstance(refusal, AdapterRefusal)
    assert refusal.error == "invalid_event_sequence"


def test_adapter_refuses_when_trace_and_refusal_are_both_present():
    run = AdapterRun(
        trace=Trace(scenario_id="synthetic", agent_id="reference"),
        refusal=AdapterRefusal(
            error="sample",
            message="Sample refusal.",
            guidance="Fix the sample.",
        ),
        events=(
            ObservableEvent(
                sequence=1,
                event_id="event-001",
                event_type=EventType.CLAIM,
                name="claim",
            ),
        ),
    )

    refusal = validate_adapter_run(run)

    assert refusal is not None
    assert refusal.error == "invalid_adapter_run"
