import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "rollback_rehearsal.py"
PLAN = REPOSITORY / "examples" / "rollback-plan.json"


def test_rollback_rehearsal_tool_passes_without_exporting_paths_or_marker(
    tmp_path,
):
    output = tmp_path / "rollback.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--plan",
            str(PLAN),
            "--output",
            str(output),
            "--fail-on-findings",
        ],
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    data = json.loads(completed.stdout)
    assert data["passed"] is True
    assert data["recovery"]["restored_match"] is True
    assert "synthetic release failure" not in completed.stdout
    assert str(tmp_path) not in completed.stdout
    assert json.loads(output.read_text(encoding="utf-8")) == data
