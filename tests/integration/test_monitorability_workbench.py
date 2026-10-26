import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "monitorability_workbench.py"
CASES = ROOT / "examples" / "monitorability" / "cases.json"
MANIFEST = ROOT / "examples" / "run-manifest" / "manifest.json"
CURRENT = ROOT / "examples" / "run-manifest" / "current-revisions.json"


def test_workbench_emits_report_safety_case_and_negative_control(tmp_path):
    report = tmp_path / "report.json"
    safety_case = tmp_path / "safety-case.json"
    negative_control = tmp_path / "negative-control.json"

    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--cases",
            str(CASES),
            "--manifest",
            str(MANIFEST),
            "--current-revisions",
            str(CURRENT),
            "--decision-target",
            "release-agent-v1",
            "--output",
            str(report),
            "--safety-case-output",
            str(safety_case),
            "--negative-control-output",
            str(negative_control),
            "--fail-on-review",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    report_data = json.loads(report.read_text(encoding="utf-8"))
    safety_case_data = json.loads(safety_case.read_text(encoding="utf-8"))
    negative_data = json.loads(negative_control.read_text(encoding="utf-8"))
    stdout_data = json.loads(result.stdout)

    assert report_data["status"] == "ready_for_human_review"
    assert safety_case_data["status"] == "supports_human_review"
    assert negative_data["status"] == "review_required"
    assert (
        "held_out_monitor_recall_below_threshold"
        in negative_data["reasons"]
    )
    assert stdout_data["safety_case"]["required_human_review"] is True
    assert "tool payload" not in result.stdout
    assert "provider output" not in result.stdout


def test_workbench_refuses_unknown_fixture_field(tmp_path):
    cases = tmp_path / "cases.json"
    output = tmp_path / "report.json"
    safety_case = tmp_path / "safety-case.json"
    value = json.loads(CASES.read_text(encoding="utf-8"))
    value["unexpected"] = "refuse"
    cases.write_text(json.dumps(value), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--cases",
            str(cases),
            "--manifest",
            str(MANIFEST),
            "--current-revisions",
            str(CURRENT),
            "--decision-target",
            "release-agent-v1",
            "--output",
            str(output),
            "--safety-case-output",
            str(safety_case),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "monitorability_workbench_refused" in result.stdout
    assert not output.exists()
