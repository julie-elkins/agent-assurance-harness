import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "public_course_review_packet.py"


def test_review_packet_cli_refuses_missing_course_without_path_leak(tmp_path):
    output = tmp_path / "packet.json"
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
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    packet = json.loads(output.read_text(encoding="utf-8"))
    assert result.returncode == 1
    assert packet["decision"] == "blocked"
    assert packet["refusal_code"] == "course_root_missing"
    assert str(tmp_path) not in result.stdout
    assert "course_root_missing" in result.stdout
