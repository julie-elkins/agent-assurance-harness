import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "pareto_candidate_report.py"


def test_pareto_candidate_report_emits_metadata_only_frontier(tmp_path):
    output = tmp_path / "pareto.json"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(result.stdout)
    assert report["synthetic_only"] is True
    assert report["comparison"]["frontier_ids"] == [
        "quality-first-safe",
        "balanced-safe",
    ]
    assert report["comparison"]["human_review_required"] is True
    assert "provider_output" not in result.stdout
    assert json.loads(output.read_text(encoding="utf-8")) == report
