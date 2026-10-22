import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "launch_to_field_report.py"


def test_launch_to_field_report_passes_and_writes_metadata_only(tmp_path):
    output = tmp_path / "launch-to-field.json"
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

    report = json.loads(result.stdout)
    assert report["enablement_pack_version"] == 1
    assert report["passed"] is True
    assert report["controls_missed"] == []
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert "Approved launch guidance fixture" not in result.stdout


def test_launch_to_field_markdown_explains_the_scaling_path():
    result = subprocess.run(
        [sys.executable, str(TOOL), "--markdown"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Launch-to-Field Enablement Pack Report" in result.stdout
    assert "`launch-pack-ready`" in result.stdout
    assert "`launch-pack-stale-source`" in result.stdout
    assert "ready_for_human_approval" in result.stdout
    assert "evidence_stale" in result.stdout
