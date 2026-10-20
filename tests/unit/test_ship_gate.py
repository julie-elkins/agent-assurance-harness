import json
from pathlib import Path

import pytest

from agent_reliability_lab.ship_gate import (
    CheckObservation,
    evaluate_ship_gate,
    load_ship_gate,
)


REPOSITORY = Path(__file__).parents[2]
MANIFEST = REPOSITORY / "examples" / "ship-gate.json"


def test_ship_gate_manifest_declares_recovery_and_stop_condition():
    manifest = load_ship_gate(MANIFEST)

    assert manifest.gate_id == "agent-assurance-ship-gate"
    assert manifest.rollback.target == "last-known-good-commit"
    assert manifest.audit.required is True
    assert manifest.stop_condition.unattended_allowed is False


def test_ship_gate_is_ready_only_when_all_required_checks_pass():
    manifest = load_ship_gate(MANIFEST)
    observations = {
        check.check_id: CheckObservation(check.check_id, True, "expected-state")
        for check in manifest.required_checks
    }

    report = evaluate_ship_gate(manifest, observations)

    assert report.passed is True
    assert report.decision == "ready"
    assert report.blocking_reasons == ()


def test_ship_gate_blocks_missing_observation():
    manifest = load_ship_gate(MANIFEST)

    report = evaluate_ship_gate(manifest, {})

    assert report.passed is False
    assert report.decision == "blocked"
    assert report.blocking_reasons[0].endswith(":missing_observation")


def test_ship_gate_rejects_missing_rollback_contract(tmp_path):
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    del data["rollback"]
    path = tmp_path / "invalid-ship-gate.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="rollback"):
        load_ship_gate(path)


def test_ship_gate_report_is_metadata_only():
    manifest = load_ship_gate(MANIFEST)
    observations = {
        check.check_id: CheckObservation(check.check_id, True, "expected-state")
        for check in manifest.required_checks
    }

    serialized = json.dumps(evaluate_ship_gate(manifest, observations).to_dict())

    assert '"prompt":' not in serialized
    assert '"trace":' not in serialized
    assert '"provider_output":' not in serialized
