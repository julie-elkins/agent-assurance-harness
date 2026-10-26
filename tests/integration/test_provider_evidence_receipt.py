import json
from pathlib import Path
import subprocess

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
            "--revisions",
            str(ROOT / "examples" / "change-impact" / "baseline-revisions.json"),
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

    impact_result = subprocess.run(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            str(ROOT / "tools" / "agent_impact_plan.py"),
            "--baseline-revisions",
            str(ROOT / "examples" / "change-impact" / "baseline-revisions.json"),
            "--current-revisions",
            str(ROOT / "examples" / "change-impact" / "current-revisions.json"),
            "--manifest",
            str(ROOT / "examples" / "run-manifest" / "manifest.json"),
            "--registry",
            str(ROOT / "examples" / "change-impact" / "evidence-registry.json"),
            "--receipt",
            str(output),
            "--json",
            "--fail-on-rerun",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    impact = json.loads(impact_result.stdout)
    assert impact_result.returncode == 1
    assert impact["status"] == "rerun_required"
    assert impact["evidence"][0]["receipt_status"] == "accepted"
    assert impact["evidence"][0]["receipt_providers"] == ["anthropic", "openai"]
