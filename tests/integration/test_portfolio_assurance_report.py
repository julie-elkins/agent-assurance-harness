import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "portfolio_assurance_report.py"


def test_portfolio_report_passes_and_writes_json(tmp_path):
    output = tmp_path / "portfolio.json"
    workspace = tmp_path / "workspace"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--workspace",
            str(workspace),
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
    assert report["portfolio_assurance_version"] == 1
    assert report["passed"] is True
    assert report["decision"] == "ready_for_human_review"
    assert report["controls_missed"] == []
    assert report["negative_control"]["caught"] is True
    assert len(report["lanes"]) == 5
    assert json.loads(output.read_text(encoding="utf-8")) == report


def test_portfolio_markdown_explains_the_human_boundary():
    result = subprocess.run(
        [sys.executable, str(TOOL), "--markdown"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Portfolio Assurance Report" in result.stdout
    assert "`agent_assurance`" in result.stdout
    assert "`instructor_calibration`" in result.stdout
    assert "does not replace human review" in result.stdout
