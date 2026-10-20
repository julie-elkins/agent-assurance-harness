import json
import subprocess
import sys
from pathlib import Path

from agent_reliability_lab.regression import compare_replay_files


REPO_ROOT = Path(__file__).parents[2]
BASELINE_PATH = REPO_ROOT / "examples" / "traces" / "guarded.json"
CANDIDATE_SCRIPT = REPO_ROOT / "examples" / "candidate_replay.py"


def _generate_candidate() -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, str(CANDIDATE_SCRIPT)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    return json.loads(completed.stdout)


def test_generated_candidate_passes_against_approved_baseline(tmp_path):
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(
        json.dumps(_generate_candidate()),
        encoding="utf-8",
    )

    report = compare_replay_files(BASELINE_PATH, candidate_path)

    assert report.refusal is None
    assert report.failed is False
    assert report.findings == ()
    assert report.candidate_change is not None
    assert report.candidate_change.change_id == "candidate-guardrails-2026-10-20"


def test_generated_candidate_mutation_is_blocked(tmp_path):
    data = _generate_candidate()
    false_completion = data["runs"][1]["response"]["trace"]
    false_completion["tool_calls"] = false_completion["tool_calls"][:1]
    false_completion["evidence_ids"] = ["tool-result-003"]
    candidate_path = tmp_path / "mutated-candidate.json"
    candidate_path.write_text(json.dumps(data), encoding="utf-8")

    report = compare_replay_files(BASELINE_PATH, candidate_path)

    assert report.refusal is None
    assert report.failed is True
    assert len(report.findings) == 1
    assert report.findings[0].blocking is True
    assert report.findings[0].category == "evidence_loss"
