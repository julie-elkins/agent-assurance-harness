from pathlib import Path

from agent_reliability_lab.action_parity import (
    REQUIRED_ACTION_MARKERS,
    verify_action_text,
)


def test_current_action_contains_required_contract_markers():
    action = Path(".github/actions/agent-assurance/action.yml").read_text(
        encoding="utf-8"
    )

    result = verify_action_text(action)

    assert result.passed is True
    assert result.missing_markers == ()
    assert result.present_markers == REQUIRED_ACTION_MARKERS


def test_action_parity_blocks_missing_policy_argument():
    action = "\n".join(
        marker
        for marker in REQUIRED_ACTION_MARKERS
        if marker
        != '--consumer-policy-manifest "$ASSURANCE_CONSUMER_POLICY_MANIFEST"'
    )

    result = verify_action_text(action)

    assert result.passed is False
    assert result.failure_reasons == (
        'missing_action_marker:--consumer-policy-manifest "$ASSURANCE_CONSUMER_POLICY_MANIFEST"',
    )
