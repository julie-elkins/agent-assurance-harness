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
AUDIT_VALUES = {
    "git-commit": "a" * 40,
    "package-version": "0.38.0",
    "scenario-pack-sha256": "b" * 64,
    "golden-trace-sha256": "c" * 64,
    "source-distribution-sha256": "d" * 64,
    "wheel-sha256": "e" * 64,
    "sbom-sha256": "f" * 64,
    "rollback-artifact-sha256": "a" * 64,
    "decision": "ready",
}


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

    report = evaluate_ship_gate(manifest, observations, AUDIT_VALUES)

    assert report.passed is True
    assert report.decision == "ready"
    assert report.blocking_reasons == ()


def test_ship_gate_blocks_missing_observation():
    manifest = load_ship_gate(MANIFEST)

    report = evaluate_ship_gate(manifest, {})

    assert report.passed is False
    assert report.decision == "blocked"
    assert "adapter-regression-positive:missing_observation" in report.blocking_reasons


def test_ship_gate_blocks_missing_audit_evidence():
    manifest = load_ship_gate(MANIFEST)
    observations = {
        check.check_id: CheckObservation(check.check_id, True, "expected-state")
        for check in manifest.required_checks
    }

    report = evaluate_ship_gate(manifest, observations)

    assert report.passed is False
    assert "audit:git-commit:missing" in report.blocking_reasons
    assert report.audit_evidence.complete is False


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

    serialized = json.dumps(
        evaluate_ship_gate(manifest, observations, AUDIT_VALUES).to_dict()
    )

    assert '"prompt":' not in serialized
    assert '"trace":' not in serialized
    assert '"provider_output":' not in serialized
