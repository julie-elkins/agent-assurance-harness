import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "monitorability_ci_gate.py"
CASES = ROOT / "examples" / "monitorability" / "cases.json"
MANIFEST = ROOT / "examples" / "run-manifest" / "manifest.json"
CURRENT = ROOT / "examples" / "run-manifest" / "current-revisions.json"
CHANGED = ROOT / "examples" / "change-impact" / "current-revisions.json"


def test_ci_gate_passes_and_writes_all_control_reports(tmp_path):
    output_dir = tmp_path / "monitorability"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--cases",
            str(CASES),
            "--manifest",
            str(MANIFEST),
            "--current-revisions",
            str(CURRENT),
            "--changed-revisions",
            str(CHANGED),
            "--output-dir",
            str(output_dir),
            "--markdown",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(
        (output_dir / "monitorability-ci-summary.json").read_text(
            encoding="utf-8"
        )
    )
    changed = json.loads(
        (output_dir / "monitorability-changed-revisions.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["status"] == "passed"
    assert summary["positive_status"] == "ready_for_human_review"
    assert summary["negative_control_status"] == "review_required"
    assert summary["changed_revision_status"] == "review_required"
    assert changed["reasons"] == ["reauthorization:reauthorization_required"]
    assert "Monitorability CI gate" in result.stdout
    assert len(list(output_dir.glob("*.json"))) == 5


def test_ci_gate_blocks_when_changed_revision_does_not_require_review(tmp_path):
    output_dir = tmp_path / "monitorability"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--cases",
            str(CASES),
            "--manifest",
            str(MANIFEST),
            "--current-revisions",
            str(CURRENT),
            "--changed-revisions",
            str(CURRENT),
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    summary = json.loads(
        (output_dir / "monitorability-ci-summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["status"] == "blocked"
    assert "changed_revision_not_review_required" in summary["reasons"]
