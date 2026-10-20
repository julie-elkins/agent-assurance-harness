import json
from pathlib import Path

import pytest

from agent_reliability_lab.rollback_rehearsal import (
    load_rollback_plan,
    run_rollback_rehearsal,
)


REPOSITORY = Path(__file__).parents[2]
PLAN = REPOSITORY / "examples" / "rollback-plan.json"


def test_rollback_rehearsal_detects_failure_and_restores_artifact():
    report = run_rollback_rehearsal(PLAN, REPOSITORY)

    assert report.passed is True
    assert report.failure_injection_applied is True
    assert report.failure_injection_detected is True
    assert report.failed_tree_sha256 != report.original_tree_sha256
    assert report.restored_tree_sha256 == report.original_tree_sha256
    assert report.restored_match is True
    data = report.to_dict()
    assert data["side_effects"] == {
        "external_writes_attempted": False,
        "network_used": False,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target", None),
        ("external_writes_allowed", True),
        ("network_allowed", True),
    ],
)
def test_rollback_plan_refuses_unsafe_or_incomplete_policy(
    tmp_path,
    field,
    value,
):
    data = json.loads(PLAN.read_text(encoding="utf-8"))
    if value is None:
        del data[field]
    else:
        data[field] = value
    path = tmp_path / "rollback-plan.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError):
        load_rollback_plan(path)


def test_rollback_rehearsal_report_is_metadata_only():
    report = run_rollback_rehearsal(PLAN, REPOSITORY)
    serialized = json.dumps(report.to_dict())

    assert "synthetic release failure" not in serialized
    assert "TemporaryDirectory" not in serialized
    assert '"path":' not in serialized
    assert '"prompt":' not in serialized
