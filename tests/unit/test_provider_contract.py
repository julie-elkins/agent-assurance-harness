import json
from pathlib import Path

from agent_reliability_lab.provider_contract import (
    run_provider_contract_assurance,
)


REPOSITORY = Path(__file__).parents[2]
MANIFEST = REPOSITORY / "examples" / "provider-contract-manifest.json"
FIXTURE_ROOT = REPOSITORY / "tests" / "fixtures" / "provider_contracts"


def test_provider_contract_assurance_accepts_reviewed_shapes_and_catches_negatives():
    report = run_provider_contract_assurance(MANIFEST, FIXTURE_ROOT)

    assert report.passed is True
    assert {item.provider_id for item in report.contracts} == {
        "openai",
        "anthropic",
    }
    assert all(item.passed for item in report.contracts)
    assert all(item.caught for item in report.negative_controls)


def test_provider_contract_assurance_detects_fixture_drift(tmp_path):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["contracts"][0]["fixture_sha256"] = "0" * 64
    mutated_manifest = tmp_path / "provider-contract-manifest.json"
    mutated_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    report = run_provider_contract_assurance(mutated_manifest, FIXTURE_ROOT)

    openai = next(item for item in report.contracts if item.provider_id == "openai")
    assert report.passed is False
    assert openai.passed is False
    assert "fixture-sha256-mismatch" in openai.drift_reasons


def test_provider_contract_report_is_metadata_only():
    report = run_provider_contract_assurance(MANIFEST, FIXTURE_ROOT)
    serialized = json.dumps(report.to_dict())

    assert "synthetic raw provider text" not in serialized
    assert '"text":' not in serialized
    assert '"provider_output":' not in serialized
