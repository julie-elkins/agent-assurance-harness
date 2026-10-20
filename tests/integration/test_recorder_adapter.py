import subprocess
import sys
from pathlib import Path

from agent_reliability_lab.external import SubprocessAdapter
from agent_reliability_lab.replay import run_replay_file
from agent_reliability_lab.runner import run_adapter_comparison


EXAMPLE = Path(__file__).parents[2] / "examples" / "recorder_adapter.py"


def test_recorder_example_generates_a_passing_complete_replay(tmp_path):
    completed = subprocess.run(
        [sys.executable, str(EXAMPLE), "--replay"],
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    assert "payload" not in completed.stdout
    replay_path = tmp_path / "recorder-replay.json"
    replay_path.write_text(completed.stdout, encoding="utf-8")

    report = run_replay_file(replay_path)

    assert report.refusal is None
    assert report.agent_report is not None
    assert report.agent_report.passed is True
    assert len(report.agent_report.findings) == 5


def test_recorder_example_passes_the_subprocess_adapter_boundary():
    adapter = SubprocessAdapter(
        agent_id="external",
        command=(sys.executable, str(EXAMPLE)),
    )

    report = run_adapter_comparison(adapter, include_mutations=True)

    assert report.reports[0].passed is True
    assert report.mutation_tests
    assert all(mutation.caught for mutation in report.mutation_tests)
