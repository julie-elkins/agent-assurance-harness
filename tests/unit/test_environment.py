from agent_reliability_lab.environment import (
    FaultInjection,
    FaultMode,
    SimulatedToolEnvironment,
    ToolSpec,
)


def test_simulator_applies_named_faults_without_returning_payloads():
    environment = SimulatedToolEnvironment(
        tools=(
            ToolSpec(
                name="lookup",
                result_status="ok",
                result_id="result-001",
            ),
        ),
        faults=(
            FaultInjection(
                fault_id="fault-stale",
                tool_name="lookup",
                mode=FaultMode.STALE_RESULT,
            ),
        ),
    )

    observation = environment.invoke("lookup")

    assert observation.result_status == "stale"
    assert observation.output_flags == ("stale",)
    assert observation.fault_id == "fault-stale"
    assert not hasattr(observation, "payload")


def test_simulator_marks_unauthorized_side_effect_attempts():
    environment = SimulatedToolEnvironment(
        tools=(
            ToolSpec(
                name="cancel_order",
                result_status="ok",
                result_id="result-002",
                side_effect_id="side-effect-001",
                requires_authorization=True,
            ),
        )
    )

    observation = environment.invoke("cancel_order")

    assert observation.result_status == "unauthorized"
    assert observation.side_effect_attempted == "side-effect-001"
    assert observation.authorization_required is True
    assert observation.authorization_present is False


def test_unknown_tool_is_an_observation_not_an_exception():
    environment = SimulatedToolEnvironment(tools=())

    observation = environment.invoke("missing_tool")

    assert observation.result_status == "not_found"
    assert observation.result_id is None


def test_simulator_supports_missing_and_misleading_faults():
    environment = SimulatedToolEnvironment(
        tools=(
            ToolSpec(name="missing", result_status="ok", result_id="result-003"),
            ToolSpec(name="misleading", result_status="ok", result_id="result-004"),
        ),
        faults=(
            FaultInjection(
                fault_id="fault-missing",
                tool_name="missing",
                mode=FaultMode.MISSING_RESULT,
            ),
            FaultInjection(
                fault_id="fault-misleading",
                tool_name="misleading",
                mode=FaultMode.MISLEADING_OUTPUT,
            ),
        ),
    )

    missing = environment.invoke("missing")
    misleading = environment.invoke("misleading")

    assert missing.result_status == "missing"
    assert missing.result_id is None
    assert misleading.output_flags == ("instruction_like",)


def test_simulator_supports_stale_fault():
    environment = SimulatedToolEnvironment(
        tools=(ToolSpec(name="lookup", result_status="ok", result_id="result-005"),),
        faults=(
            FaultInjection(
                fault_id="fault-stale",
                tool_name="lookup",
                mode=FaultMode.STALE_RESULT,
            ),
        ),
    )

    observation = environment.invoke("lookup")

    assert observation.result_status == "stale"
    assert observation.result_id == "result-005"


def test_simulator_models_timeout_after_commit_as_an_ambiguous_retry():
    environment = SimulatedToolEnvironment(
        tools=(
            ToolSpec(
                name="charge_order",
                result_status="ok",
                result_id="result-006",
                side_effect_id="side-effect-002",
                requires_authorization=True,
            ),
        ),
        faults=(
            FaultInjection(
                fault_id="fault-timeout-after-commit",
                tool_name="charge_order",
                mode=FaultMode.TIMEOUT_AFTER_COMMIT,
            ),
        ),
    )

    first = environment.invoke("charge_order", authorized=True)
    second = environment.invoke("charge_order", authorized=True)

    assert first.result_status == "timeout"
    assert second.result_status == "ok"
    assert first.side_effect_attempted == second.side_effect_attempted
    assert second.result_id == "result-006-retry"
