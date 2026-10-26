import json
from pathlib import Path

from jsonschema import validate

from agent_reliability_lab.provider_receipt import PROVIDER_RECEIPT_VERSION


ROOT = Path(__file__).parents[2]


def test_provider_evidence_receipt_demo_matches_schema(tmp_path):
    output = tmp_path / "receipt.json"
    tool = ROOT / "tools" / "provider_evidence_receipt.py"
    result = __import__("subprocess").run(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            str(tool),
            "--provider",
            "all",
            "--scenario-id",
            "tool-misuse",
            "--evidence-id",
            "run-synthetic-001",
            "--registry",
            str(ROOT / "examples" / "change-impact" / "evidence-registry.json"),
            "--output",
            str(output),
            "--fail-on-refusal",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    data = json.loads(result.stdout)
    schema = json.loads(
        (ROOT / "schemas" / "provider-evidence-receipt-v1.json").read_text()
    )
    validate(data, schema)
    assert data["provider_receipt_version"] == PROVIDER_RECEIPT_VERSION
    assert data["passed"] is True
    assert len(data["receipts"]) == 2
