from pathlib import Path

from agent_reliability_lab.shadow_execution import (
    ShadowAction,
    ShadowCase,
    ShadowDecision,
    ShadowOutcome,
    load_shadow_cases,
    run_shadow_case,
    run_shadow_cases,
)


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "examples" / "shadow-execution" / "manifest.json"


def _action(**overrides: object) -> ShadowAction:
    values = {
        "action_id": "action-test-001",
        "operation_id": "operation-test-001",
        "tool_name": "file-update",
        "effect_class": "repository-change",
        "intended_effect": "update-readme",
        "policy_revision": "policy-r1",
        "authority_status": "granted",
        "requires_human_approval": False,
    }
    values.update(overrides)
    return ShadowAction(**values)


def _case(
    outcome: ShadowOutcome,
    *,
    action: ShadowAction | None = None,
    expected: ShadowDecision = ShadowDecision.HUMAN_REVIEW,
) -> ShadowCase:
    return ShadowCase(
        case_id="case-test-001",
        action=action or _action(),
        outcome=outcome,
        expected_decision=expected,
    )


def test_matched_effect_is_allowed_without_real_side_effect() -> None:
    result = run_shadow_case(
        _case(
            ShadowOutcome.MATCHED,
            expected=ShadowDecision.ALLOW,
        )
    )

    assert result.refusal is None
    assert result.receipt is not None
    assert result.receipt.decision is ShadowDecision.ALLOW
    assert result.receipt.simulation_ran is True
    assert result.receipt.real_side_effects_attempted is False
    assert result.receipt.tool_name == "file-update"
    assert result.receipt.effect_class == "repository-change"
    assert result.receipt.policy_revision == "policy-r1"
    assert (
        result.receipt.intended_effect_digest
        == result.receipt.observed_effect_digest
    )


def test_missing_authority_blocks_before_simulation() -> None:
    result = run_shadow_case(
        _case(
            ShadowOutcome.MATCHED,
            action=_action(authority_status="missing"),
            expected=ShadowDecision.BLOCK,
        )
    )

    assert result.refusal is None
    assert result.receipt is not None
    assert result.receipt.decision is ShadowDecision.BLOCK
    assert result.receipt.simulation_ran is False
    assert result.receipt.observed_effect_digest is None
    assert result.receipt.reason_codes == ("execution_authority_missing",)


def test_mismatched_effect_requires_human_review() -> None:
    result = run_shadow_case(_case(ShadowOutcome.MISMATCHED))

    assert result.receipt is not None
    assert result.receipt.decision is ShadowDecision.HUMAN_REVIEW
    assert result.receipt.reason_codes == ("shadow_effect_mismatch",)
    assert (
        result.receipt.intended_effect_digest
        != result.receipt.observed_effect_digest
    )


def test_approval_and_ambiguous_state_require_human_review() -> None:
    approval = run_shadow_case(
        _case(
            ShadowOutcome.MATCHED,
            action=_action(requires_human_approval=True),
        )
    )
    ambiguous = run_shadow_case(_case(ShadowOutcome.AMBIGUOUS))

    assert approval.receipt is not None
    assert approval.receipt.reason_codes == ("human_approval_required",)
    assert ambiguous.receipt is not None
    assert ambiguous.receipt.reason_codes == ("effect_state_ambiguous",)


def test_public_fixture_matches_all_expected_decisions() -> None:
    report = run_shadow_cases(load_shadow_cases(MANIFEST))

    assert report.passed is True
    assert report.to_dict()["decision_counts"] == {
        "allow": 1,
        "block": 1,
        "human_review": 3,
    }


def test_loader_rejects_content_bearing_action_field(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        """
        {
          "shadow_execution_version": 1,
          "data_class": "synthetic",
          "purpose": "reject-content",
          "cases": [
            {
              "case_id": "case-1",
              "action": {
                "action_id": "action-1",
                "operation_id": "operation-1",
                "tool_name": "file-update",
                "effect_class": "repository-change",
                "intended_effect": "update-readme",
                "policy_revision": "policy-r1",
                "authority_status": "granted",
                "requires_human_approval": false,
                "arguments": "forbidden"
              },
              "simulation": {
                "outcome": "matched",
                "expected_decision": "allow"
              }
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    try:
        load_shadow_cases(manifest)
    except ValueError as error:
        assert "unknown fields" in str(error)
    else:
        raise AssertionError("content-bearing action field was accepted")
