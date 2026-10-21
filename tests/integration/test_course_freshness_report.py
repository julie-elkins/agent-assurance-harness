import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "course_freshness_report.py"


def test_course_freshness_report_is_metadata_only(tmp_path):
    workspace = tmp_path / "workspace"
    output = tmp_path / "course-freshness.json"
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
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(result.stdout)
    assert report["course_freshness_version"] == 1
    assert report["passed"] is True
    assert report["counts"] == {
        "completed": 5,
        "requested": 5,
        "unavailable": 0,
    }
    assert json.loads(output.read_text(encoding="utf-8")) == report
