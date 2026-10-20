from dataclasses import replace

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


def test_guarded_adapter_reuses_retry_identity_for_ambiguous_write():
    scenario = next(
        case
        for case in scenarios()
        if case.scenario_id == "ambiguous-side-effect-retry"
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
    assert run.trace.operation_ids == ("operation-001", "operation-001")
    assert run.trace.idempotency_keys == (
        "idempotency-001",
        "idempotency-001",
    )
    assert run.trace.side_effects == ("side-effect-002",)
    assert run.trace.authorization_operation_ids == ("operation-001",)
    assert run.trace.reconciliation_ids == ("reconcile-result-001",)
    assert run.trace.reconciliation_statuses == ("confirmed",)
    assert run.trace.tool_calls[-1].name == "get_charge_status"
    assert run.trace.tool_calls[-1].result_status == "confirmed"


def test_ambiguous_retry_requires_an_observed_side_effect():
    scenario = next(
        case
        for case in scenarios()
        if case.scenario_id == "ambiguous-side-effect-retry"
    )
    trace = scenario.run_guarded()
    trace = replace(trace, side_effects=())

    finding = scenario.evaluate(trace, scenario.contract)

    assert finding.status.value == "failed"
    assert "side-effect:no-duplicate" in finding.missing_evidence


def test_ambiguous_retry_requires_confirmed_postcondition():
    scenario = next(
        case
        for case in scenarios()
        if case.scenario_id == "ambiguous-side-effect-retry"
    )
    trace = scenario.run_guarded()
    trace = replace(trace, reconciliation_ids=(), reconciliation_statuses=())

    finding = scenario.evaluate(trace, scenario.contract)

    assert finding.status.value == "failed"
    assert "reconciliation:confirmed" in finding.missing_evidence


def test_ambiguous_retry_requires_authorization_bound_to_operation():
    scenario = next(
        case
        for case in scenarios()
        if case.scenario_id == "ambiguous-side-effect-retry"
    )
    trace = scenario.run_guarded()
    trace = replace(
        trace,
        authorization_operation_ids=("operation-unrelated",),
    )

    finding = scenario.evaluate(trace, scenario.contract)

    assert finding.status.value == "failed"
    assert "authorization:bound-to-operation" in finding.missing_evidence


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
