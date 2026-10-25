import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "run_manifest_gate.py"
MANIFEST = ROOT / "examples" / "run-manifest" / "manifest.json"
CURRENT = ROOT / "examples" / "run-manifest" / "current-revisions.json"
CHANGED = ROOT / "examples" / "run-manifest" / "changed-revisions.json"


def _run(*arguments):
    return subprocess.run(
        [sys.executable, str(TOOL), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_gate_accepts_current_revisions():
    result = _run(
        "--manifest",
        str(MANIFEST),
        "--current-revisions",
        str(CURRENT),
        "--fail-on-non-reauthorized",
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "reauthorized"


def test_gate_blocks_changed_revisions_and_reports_scope():
    result = _run(
        "--manifest",
        str(MANIFEST),
        "--current-revisions",
        str(CHANGED),
        "--fail-on-non-reauthorized",
    )

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == "reauthorization_required"
    assert data["changed_dependencies"] == ["prompt", "tools"]
