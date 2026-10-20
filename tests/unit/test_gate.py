import pytest

from agent_reliability_lab.gate import (
    EvidenceGate,
    GateAction,
    GateDecision,
    run_gated_scenario,
)
from agent_reliability_lab.models import Trace
from agent_reliability_lab.packs import load_builtin_packs
from agent_reliability_lab.scenarios import AMBIGUOUS_ACTION_DIGEST, scenarios


SCENARIO_IDS = (
    "tool-misuse",
    "false-completion",
    "inappropriate-answer",
    "unauthorized-side-effect",
    "misleading-tool-output",
    "ambiguous-side-effect-retry",
    "evidence-stale-approved-source",
    "evidence-fresh-wrong-source",
)


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_naive_profile_is_blocked_before_action(scenario_id):
    result = run_gated_scenario(scenario_id, "naive")

    assert result.result.decision is GateDecision.BLOCKED
    assert result.executed is False


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_guarded_profile_is_allowed_after_required_evidence(scenario_id):
    result = run_gated_scenario(scenario_id, "guarded")

    assert result.result.decision is GateDecision.ALLOWED
    assert result.executed is True


def test_unauthorized_side_effect_is_blocked_before_environment_invoke():
    result = run_gated_scenario("unauthorized-side-effect", "naive")

    assert result.result.missing_evidence == ("authorization:approval",)
    assert result.tool_events == ()
    assert result.side_effects == ()


def test_authorized_synthetic_side_effect_is_invoked_after_gate_allows():
    result = run_gated_scenario("unauthorized-side-effect", "guarded")

    assert result.result.observed_evidence == ("authorization:approval",)
    assert len(result.tool_events) == 1
    assert result.side_effects == ("side-effect-001",)


def test_unrecognised_authorization_label_does_not_unlock_side_effect():
    scenario = next(
        item for item in scenarios() if item.scenario_id == "unauthorized-side-effect"
    )
    pack = next(
        item
        for item in load_builtin_packs()
        if item.scenario_id == "unauthorized-side-effect"
    )
    result = EvidenceGate(scenario, pack).decide(
        Trace(
            scenario_id=scenario.scenario_id,
            agent_id="synthetic-agent",
            authorization_ids=("authorization:maybe",),
        ),
        action=GateAction.PROTECTED_SIDE_EFFECT,
    )

    assert result.decision is GateDecision.BLOCKED
    assert result.missing_evidence == ("authorization:approval",)


def test_unrelated_authorization_does_not_unlock_ambiguous_write():
    scenario = next(
        case
        for case in scenarios()
        if case.scenario_id == "ambiguous-side-effect-retry"
    )
    pack = next(
        pack
        for pack in load_builtin_packs()
        if pack.scenario_id == scenario.scenario_id
    )
    result = EvidenceGate(scenario, pack).decide(
        Trace(
            scenario_id=scenario.scenario_id,
            agent_id="synthetic-agent",
            authorization_ids=("authorization:approval",),
            authorization_operation_ids=("operation-unrelated",),
            operation_ids=("operation-001", "operation-001"),
        ),
        action=GateAction.PROTECTED_SIDE_EFFECT,
    )

    assert result.decision is GateDecision.BLOCKED
    assert result.missing_evidence == ("authorization:bound-to-operation",)


def test_wrong_action_digest_does_not_unlock_ambiguous_write():
    scenario = next(
        case
        for case in scenarios()
        if case.scenario_id == "ambiguous-side-effect-retry"
    )
    pack = next(
        pack
        for pack in load_builtin_packs()
        if pack.scenario_id == scenario.scenario_id
    )
    wrong_digest = "sha256:" + "0" * 64
    result = EvidenceGate(scenario, pack).decide(
        Trace(
            scenario_id=scenario.scenario_id,
            agent_id="synthetic-agent",
            authorization_ids=("authorization:approval",),
            authorization_operation_ids=("operation-001",),
            authorization_action_digests=(wrong_digest,),
            operation_ids=("operation-001", "operation-001"),
            action_digests=(wrong_digest,),
        ),
        action=GateAction.PROTECTED_SIDE_EFFECT,
    )

    assert result.decision is GateDecision.BLOCKED
    assert result.missing_evidence == (
        f"action-digest:{AMBIGUOUS_ACTION_DIGEST}",
    )
