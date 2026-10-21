import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "content_assurance_pipeline_report.py"


def test_content_pipeline_report_passes_and_writes_metadata_only(tmp_path):
    output = tmp_path / "content-pipeline.json"
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
    assert report["content_pipeline_version"] == 2
    assert report["passed"] is True
    assert report["controls_missed"] == []
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8")) == report
