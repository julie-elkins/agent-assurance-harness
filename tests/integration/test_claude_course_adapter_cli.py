import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "claude_course_adapter.py"


def test_claude_course_adapter_cli_reports_refusal_without_source_path(tmp_path):
    output = tmp_path / "adapter.json"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--course-root",
            str(tmp_path / "missing-course"),
            "--output",
            str(output),
            "--markdown",
            "--fail-on-findings",
        ],
        cwd=REPOSITORY,
        check=False,
        capture_output=True,
        text=True,
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert result.returncode == 1
    assert report["refusal_code"] == "course_root_missing"
    assert str(tmp_path) not in result.stdout
    assert "course_root_missing" in result.stdout
