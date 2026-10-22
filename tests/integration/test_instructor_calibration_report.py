import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "instructor_calibration_report.py"


def test_instructor_calibration_report_passes_and_writes_metadata_only(tmp_path):
    output = tmp_path / "instructor-calibration.json"
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
    assert report["instructor_calibration_version"] == 1
    assert report["passed"] is True
    assert report["controls_missed"] == []
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert "learner_confusion" not in result.stdout


def test_instructor_calibration_markdown_explains_coaching_path():
    result = subprocess.run(
        [sys.executable, str(TOOL), "--markdown"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Instructor Calibration Report" in result.stdout
    assert "`instructor-ready`" in result.stdout
    assert "`instructor-missing-adaptation`" in result.stdout
    assert "coach:audience_adaptation" in result.stdout
    assert "ready_for_human_signoff" in result.stdout
