import json
import subprocess
import sys
from pathlib import Path

from agent_reliability_lab.course_doctor import (
    reference_course_doctor_cases,
)


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "course_doctor_report.py"


def test_course_doctor_report_is_metadata_only(tmp_path):
    output = tmp_path / "course-doctor.json"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--workspace",
            str(tmp_path / "workspace"),
            "--output",
            str(output),
            "--markdown",
            "--fail-on-findings",
        ],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["course_doctor_version"] == 1
    assert report["passed"] is True
    assert report["counts"]["requested"] == 5
    assert report["counts"]["packets_emitted"] == 5
    assert report["counts"]["not_reviewed"] == 0
    assert len(reference_course_doctor_cases()) == 5
    assert "Approved technical guidance fixture" not in result.stdout
