import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "developer_workflow_report.py"


def test_developer_workflow_lane_passes_and_catches_green_negative_control(tmp_path):
    output = tmp_path / "developer-workflow.json"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--output",
            str(output),
            "--fail-on-findings",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert json.loads(result.stdout) == report
    assert report["report_kind"] == "developer-workflow-assurance-v1"
    assert report["decision"] == "pass"
    assert report["offline"] is True
    assert report["synthetic_only"] is True
    assert report["raw_payloads_included"] is False
    assert report["provider_output_included"] is False
    assert report["live_repository_execution"] is False
    assert report["pack_count"] == 6
    assert report["guarded_reference"]["passed"] is True
    assert report["degraded_negative_control"]["caught"] is True
    assert report["negative_control"]["scenario_id"] == (
        "developer-green-but-unaudited"
    )
    assert all(
        manifest["data_class"] == "synthetic"
        for manifest in report["guarded_reference"]["pack_manifests"]
    )


def test_developer_workflow_markdown_is_reviewer_safe():
    result = subprocess.run(
        [sys.executable, str(TOOL), "--markdown"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "**Decision:** `PASS`" in result.stdout
    assert "**Green-but-unaudited negative control caught:** `YES`" in result.stdout
    assert "source-code correctness" in result.stdout
    assert "synthetic" in result.stdout.lower()
