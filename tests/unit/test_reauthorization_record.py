import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent_reliability_lab.change_impact import build_change_impact_plan
from agent_reliability_lab.evidence_registry import load_evidence_registry
from agent_reliability_lab.reauthorization_record import (
    ReauthorizationRecord,
    canonical_digest,
    validate_reauthorization,
)
from agent_reliability_lab.rerun_executor import run_bounded_rerun
from agent_reliability_lab.run_manifest import REQUIRED_REVISION_KEYS, RunManifest


ROOT = Path(__file__).parents[2]
NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def _revisions(**overrides):
    values = {key: f"{key}-r1" for key in REQUIRED_REVISION_KEYS}
    values.update(overrides)
    return values


def _rerun_result():
    manifest = RunManifest.from_dict(
        json.loads(
            (ROOT / "examples" / "run-manifest" / "manifest.json").read_text()
        )
    )
    registry = load_evidence_registry(
        ROOT / "examples" / "change-impact" / "evidence-registry.json"
    )
    plan = build_change_impact_plan(
        [manifest],
        _revisions(),
        _revisions(policy="policy-r2"),
        registry=registry,
    )
    return run_bounded_rerun(plan).to_dict()


def _record(rerun_result, **overrides):
    value = {
        "reauthorization_record_version": 1,
        "decision_id": "reauth-run-synthetic-001-001",
        "decision": "reauthorized",
        "decision_target": rerun_result["decision_targets"][0],
        "evidence_ids": rerun_result["evidence_ids"],
        "owner_id": "assurance-team",
        "decided_by": "human-reviewer",
        "decided_at": "2026-11-10T11:30:00Z",
        "expires_at": "2026-12-01T00:00:00Z",
        "baseline_revisions_digest": rerun_result["revision_digests"]["baseline"],
        "current_revisions_digest": rerun_result["revision_digests"]["current"],
        "rerun_executor_version": rerun_result["rerun_executor_version"],
        "selected_check_ids": rerun_result["selected_check_ids"],
        "rerun_result_digest": canonical_digest(rerun_result),
        "residual_risk": "Synthetic controls do not establish live model quality.",
        "next_action": "Review again before the expiration time.",
    }
    value.update(overrides)
    return ReauthorizationRecord.from_dict(value)


def test_matching_completed_rerun_is_reauthorized():
    rerun_result = _rerun_result()

    validation = validate_reauthorization(
        _record(rerun_result),
        rerun_result,
        now=NOW,
    )

    assert validation.status == "reauthorized"
    assert validation.reusable is True
    assert validation.reason_codes == ()


def test_reauthorization_cannot_use_blocked_rerun():
    rerun_result = _rerun_result()
    rerun_result["status"] = "blocked"
    rerun_result["reason_codes"] = ["selected_check_failed"]
    record = _record(rerun_result)

    validation = validate_reauthorization(record, rerun_result, now=NOW)

    assert validation.status == "blocked"
    assert validation.reusable is False
    assert "rerun_not_completed" in validation.reason_codes


def test_revision_digest_mismatch_blocks_reuse():
    rerun_result = _rerun_result()
    record = _record(
        rerun_result,
        current_revisions_digest="sha256:" + "a" * 64,
    )

    validation = validate_reauthorization(record, rerun_result, now=NOW)

    assert validation.status == "blocked"
    assert validation.reusable is False
    assert validation.reason_codes == ("current_revision_digest_mismatch",)


def test_expired_reauthorization_is_not_reusable():
    rerun_result = _rerun_result()
    record = _record(
        rerun_result,
        decided_at="2026-11-09T11:30:00Z",
        expires_at="2026-11-10T10:00:00Z",
    )

    validation = validate_reauthorization(record, rerun_result, now=NOW)

    assert validation.status == "expired"
    assert validation.reusable is False
    assert validation.reason_codes == ("reauthorization_expired",)


@pytest.mark.parametrize("decision", ["held", "blocked"])
def test_non_reauthorized_decisions_remain_visible_and_non_reusable(decision):
    rerun_result = _rerun_result()
    record = _record(
        rerun_result,
        decision=decision,
        next_action="Repair the evidence and request a new review.",
    )

    validation = validate_reauthorization(record, rerun_result, now=NOW)

    assert validation.status == decision
    assert validation.reusable is False
    assert validation.required_action == "Repair the evidence and request a new review."


def test_unsupported_or_missing_record_fields_are_rejected():
    rerun_result = _rerun_result()
    value = _record(rerun_result).to_dict()
    del value["owner_id"]

    with pytest.raises(ValueError, match="owner_id"):
        ReauthorizationRecord.from_dict(value)
