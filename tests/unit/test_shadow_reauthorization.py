from dataclasses import replace
from pathlib import Path

from agent_reliability_lab.run_manifest import load_current_revisions
from agent_reliability_lab.shadow_execution import (
    ShadowAction,
    ShadowCase,
    ShadowDecision,
    ShadowOutcome,
)
from agent_reliability_lab.shadow_reauthorization import (
    SHADOW_STATUS_BLOCKED,
    SHADOW_STATUS_HUMAN_REVIEW,
    SHADOW_STATUS_REAUTHORIZED,
    SHADOW_STATUS_REAUTHORIZATION_REQUIRED,
    load_shadow_reauthorization_fixture,
    run_shadow_reauthorization,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "examples" / "shadow-reauthorization" / "fixture.json"
CURRENT = ROOT / "examples" / "run-manifest" / "current-revisions.json"
CHANGED = ROOT / "examples" / "run-manifest" / "changed-revisions.json"


def test_provider_lanes_share_shadow_and_reauthorization_contract() -> None:
    report = run_shadow_reauthorization(
        load_shadow_reauthorization_fixture(FIXTURE, repository_root=ROOT),
        load_current_revisions(str(CURRENT)),
        load_current_revisions(str(CHANGED)),
    )

    assert report.passed is True
    assert {result.provider_id for result in report.results} == {
        "openai",
        "anthropic",
    }
    assert all(
        result.current.final_status == SHADOW_STATUS_REAUTHORIZED
        for result in report.results
    )
    assert all(
        result.changed.final_status == SHADOW_STATUS_REAUTHORIZATION_REQUIRED
        for result in report.results
    )


def test_missing_authority_blocks_both_revision_lanes() -> None:
    proposal = load_shadow_reauthorization_fixture(
        FIXTURE,
        repository_root=ROOT,
    )[0]
    action = replace(proposal.case.action, authority_status="missing")
    case = replace(
        proposal.case,
        action=action,
        expected_decision=ShadowDecision.BLOCK,
    )
    result = run_shadow_reauthorization(
        (replace(proposal, case=case),),
        load_current_revisions(str(CURRENT)),
        load_current_revisions(str(CHANGED)),
    ).results[0]

    assert result.shadow_decision == ShadowDecision.BLOCK.value
    assert result.current.final_status == SHADOW_STATUS_BLOCKED
    assert result.changed.final_status == SHADOW_STATUS_BLOCKED
    assert result.current.reasons == (
        "shadow:execution_authority_missing",
    )


def test_unlisted_tool_blocks_before_shadow_simulation() -> None:
    proposal = load_shadow_reauthorization_fixture(
        FIXTURE,
        repository_root=ROOT,
    )[0]
    action = replace(proposal.case.action, tool_name="unlisted_tool")
    case = replace(proposal.case, action=action)
    result = run_shadow_reauthorization(
        (replace(proposal, case=case),),
        load_current_revisions(str(CURRENT)),
        load_current_revisions(str(CHANGED)),
    ).results[0]

    assert result.shadow_decision is None
    assert result.binding_reasons == ("action_tool_outside_manifest_scope",)
    assert result.current.final_status == SHADOW_STATUS_BLOCKED


def test_human_review_shadow_result_overrides_current_reauthorization() -> None:
    proposal = load_shadow_reauthorization_fixture(
        FIXTURE,
        repository_root=ROOT,
    )[0]
    action = replace(proposal.case.action, requires_human_approval=True)
    case = replace(
        proposal.case,
        action=action,
        expected_decision=ShadowDecision.HUMAN_REVIEW,
        outcome=ShadowOutcome.MATCHED,
    )
    result = run_shadow_reauthorization(
        (replace(proposal, case=case),),
        load_current_revisions(str(CURRENT)),
        load_current_revisions(str(CURRENT)),
    ).results[0]

    assert result.current.final_status == SHADOW_STATUS_HUMAN_REVIEW
    assert result.current.reauthorization_status == SHADOW_STATUS_REAUTHORIZED
