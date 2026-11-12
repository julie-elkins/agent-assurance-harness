import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "atif_conformance_report.py"
FIXTURES = ROOT / "examples" / "atif-conformance"


def _run(fixture: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--summary",
            str(FIXTURES / fixture),
            "--fail-on-findings",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_positive_fixture_emits_metadata_only_report():
    result = _run("positive.json")

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["conformance_passed"]
    assert "trajectory_digest" not in result.stdout
    assert "provider_response" not in result.stdout


def test_harbor_adapter_fixture_emits_accepted_report():
    result = _run("harbor-adapter-v1.2.json")

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["conformance_passed"]
    assert report["schema_version"] == "ATIF-v1.2"


def test_negative_fixture_returns_nonzero_and_only_reports_refusal_metadata():
    result = _run("missing-artifact.json")

    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["refusal_code"] == "trajectory_artifact_not_observed"
    assert "step_count" not in result.stdout
    assert "trajectory_digest" not in result.stdout
