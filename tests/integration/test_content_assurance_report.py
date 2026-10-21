import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "content_assurance_report.py"


def test_content_assurance_report_has_positive_and_negative_controls(tmp_path):
    output = tmp_path / "content-assurance.json"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--output",
            str(output),
            "--fail-on-findings",
        ],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(result.stdout)
    assert report["passed"] is True
    assert report["controls_missed"] == []
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["cases"][1]["abstention_reasons"] == ["evidence_stale"]
    assert report["cases"][2]["abstention_reasons"] == ["evidence_wrong_source"]
    assert "lesson text" in report["cases"][0]["diagnostics"]["warnings"][0]
