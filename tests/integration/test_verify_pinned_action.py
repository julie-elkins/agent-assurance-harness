import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "verify_pinned_action.py"


def test_pinned_action_content_parity_passes():
    completed = subprocess.run(
        [sys.executable, str(TOOL), "--fail-on-unverified"],
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    result = json.loads(completed.stdout)
    assert result["verified"] is True
    assert result["passed"] is True
    assert result["missing_markers"] == []
    assert result["action_ref"] == (
        "5141cf58695a4ed4f45bfbcf106ce559340c61aa"
    )
    assert "action.yml" not in completed.stdout
