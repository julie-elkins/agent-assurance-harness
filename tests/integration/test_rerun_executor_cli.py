import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "rerun_executor.py"


def test_rerun_executor_emits_metadata_only_success(tmp_path):
    output_path = tmp_path / "rerun.json"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--baseline-revisions",
            "examples/change-impact/baseline-revisions.json",
            "--current-revisions",
            "examples/change-impact/current-revisions.json",
            "--manifest",
            "examples/run-manifest/manifest.json",
            "--registry",
            "examples/change-impact/evidence-registry.json",
            "--changed-path",
            "policies/release-policy.json",
            "--output",
            str(output_path),
            "--fail-on-noncompleted",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert result.returncode == 0
    assert data["status"] == "rerun_completed"
    assert data["summary"]["checks_selected"] == 3
    assert data["summary"]["negative_controls_caught"] == 3
    assert data["revision_digests"]["baseline"].startswith("sha256:")
    assert data["revision_digests"]["current"].startswith("sha256:")
    assert data["limits"] == {"max_checks": 8, "max_elapsed_seconds": 30.0}
    assert "reports" not in data
    assert "prompts" not in result.stdout
    assert "tool_calls" not in result.stdout
