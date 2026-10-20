from agent_reliability_lab.external import adapter_run_from_dict, adapter_run_to_dict
from agent_reliability_lab.protocol import EventType
from agent_reliability_lab.recorder import TraceRecorder
from agent_reliability_lab.replay import REPLAY_VERSION, ReplayFile


def test_recorder_builds_an_identifier_only_replay_case():
    recorder = TraceRecorder(
        scenario_id="misleading-tool-output",
        agent_id="synthetic-agent",
    )

    assert recorder.record_tool_call("lookup_catalog").accepted is True
    result = recorder.record_tool_result(
        "lookup_catalog",
        "ok",
        result_id="tool-result-007",
        output_flags=("instruction_like",),
    )
    assert result.accepted is True
    assert recorder.record_claim("claim:data_only").accepted is True
    assert recorder.record_authorization("authorization:approval").accepted is True
    assert recorder.record_side_effect("side-effect-001").accepted is True
    assert recorder.record_abstention().accepted is True

    run = recorder.finish()

    assert run.refusal is None
    assert run.trace is not None
    assert run.trace.tool_calls[0].arguments == {}
    assert run.trace.evidence_ids == ("tool-result-007",)
    assert run.trace.tool_output_flags == ("instruction_like",)
    assert run.trace.authorization_ids == ("authorization:approval",)
    assert [event.event_type for event in run.events] == [
        EventType.TOOL_CALL,
        EventType.TOOL_RESULT,
        EventType.CLAIM,
        EventType.AUTHORIZATION,
        EventType.SIDE_EFFECT,
        EventType.ABSTENTION,
    ]
    serialized = adapter_run_to_dict(run)
    assert "arguments" not in str(serialized)
    assert "payload" not in str(serialized)
    assert adapter_run_from_dict(serialized) == run


def test_recorder_refuses_raw_payloads_and_keeps_the_refusal():
    recorder = TraceRecorder(
        scenario_id="tool-misuse",
        agent_id="synthetic-agent",
    )

    result = recorder.record_tool_call(
        "lookup_policy",
        arguments={"record_id": "synthetic-policy-404"},
    )

    assert result.accepted is False
    assert result.refusal is not None
    assert result.refusal.error == "raw_tool_arguments_rejected"
    finished = recorder.finish()
    assert finished.trace is None
    assert finished.refusal == result.refusal


def test_recorder_refuses_raw_result_payloads():
    recorder = TraceRecorder(
        scenario_id="tool-misuse",
        agent_id="synthetic-agent",
    )
    recorder.record_tool_call("lookup_policy")

    result = recorder.record_tool_result(
        "lookup_policy",
        "ok",
        payload={"secret": "not stored"},
    )

    assert result.accepted is False
    assert result.refusal is not None
    assert result.refusal.error == "raw_tool_payload_rejected"
    assert recorder.finish().refusal == result.refusal


def test_recorder_refuses_unresolved_tool_calls():
    recorder = TraceRecorder(
        scenario_id="false-completion",
        agent_id="synthetic-agent",
    )

    recorder.record_tool_call("check_inventory")
    run = recorder.finish()

    assert run.trace is None
    assert run.refusal is not None
    assert run.refusal.error == "unresolved_tool_call"


def test_recorder_refuses_free_form_claims_and_answers():
    recorder = TraceRecorder(
        scenario_id="inappropriate-answer",
        agent_id="synthetic-agent",
    )

    claim = recorder.record_claim("The answer is known.")
    answer = recorder.record_answer("answer:ready")

    assert claim.accepted is False
    assert claim.refusal is not None
    assert claim.refusal.error == "invalid_identifier"
    assert answer.accepted is False
    assert answer.refusal == claim.refusal


def test_recorder_produces_a_replay_case():
    recorder = TraceRecorder(
        scenario_id="unauthorized-side-effect",
        agent_id="synthetic-agent",
    )
    recorder.record_claim("claim:authorization_required")
    recorder.record_abstention()

    case = recorder.finish_replay_case()

    assert case.scenario_id == "unauthorized-side-effect"
    assert case.response.trace is not None
    assert case.response.trace.abstained is True
    replay = ReplayFile(
        replay_version=REPLAY_VERSION,
        agent_id="synthetic-agent",
        cases=(case,),
    )
    assert replay.to_dict()["runs"][0]["scenario_id"] == "unauthorized-side-effect"
