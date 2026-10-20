from agent_reliability_lab.adapters import reference_adapters, trace_to_events
from agent_reliability_lab.environment import environment_for_scenario
from agent_reliability_lab.models import Trace
from agent_reliability_lab.protocol import ScenarioRequest
from agent_reliability_lab.scenarios import scenarios


def test_reference_adapters_emit_contiguous_identifier_only_events():
    scenario = scenarios()[0]
    request = ScenarioRequest(
        scenario_id=scenario.scenario_id,
        task_label=scenario.title,
        available_tools=("lookup_policy",),
        contract=scenario.contract,
    )

    run = reference_adapters()[1].run(
        request,
        environment=environment_for_scenario(scenario.scenario_id),
    )

    assert run.refusal is None
    assert run.trace is not None
    assert [event.sequence for event in run.events] == list(
        range(1, len(run.events) + 1)
    )
    assert all(event.event_id for event in run.events)
    assert all(not hasattr(event, "payload") for event in run.events)


def test_trace_without_answer_still_records_abstention():
    trace = Trace(
        scenario_id="synthetic",
        agent_id="guarded",
        claim="Evidence is insufficient.",
        abstained=True,
    )

    events = trace_to_events(trace)

    assert [event.name for event in events] == ["claim", "abstention"]


def test_guarded_adapter_quarantines_instruction_like_output():
    scenario = next(
        case for case in scenarios() if case.scenario_id == "misleading-tool-output"
    )
    request = ScenarioRequest(
        scenario_id=scenario.scenario_id,
        task_label=scenario.title,
        available_tools=scenario.available_tools,
        contract=scenario.contract,
    )

    run = reference_adapters()[1].run(
        request,
        environment=environment_for_scenario(scenario.scenario_id),
    )

    assert run.trace is not None
    assert run.trace.tool_output_flags == ("instruction_like",)
    assert run.trace.abstained is True


def test_adapter_refuses_a_non_simulated_environment():
    scenario = scenarios()[0]
    request = ScenarioRequest(
        scenario_id=scenario.scenario_id,
        task_label=scenario.title,
        available_tools=scenario.available_tools,
        contract=scenario.contract,
    )

    run = reference_adapters()[0].run(request, environment=object())

    assert run.trace is None
    assert run.refusal is not None
    assert run.refusal.error == "invalid_environment"
