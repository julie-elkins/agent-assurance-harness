import json
import os
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "reusable_action_runner.py"


def test_reusable_action_runner_emits_metadata_only_outputs(tmp_path):
    output = tmp_path / "report.json"
    github_output = tmp_path / "github-output"
    summary = tmp_path / "summary.md"
    environment = os.environ.copy()
    environment["GITHUB_OUTPUT"] = str(github_output)
    environment["GITHUB_STEP_SUMMARY"] = str(summary)

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--agent-id",
            "consumer-agent",
            "--adapter-command-json",
            json.dumps(
                [
                    "python",
                    "guarded_adapter.py",
                ]
            ),
            "--adapter-working-directory",
            str(REPOSITORY / "examples" / "consumer-repository"),
            "--output",
            str(output),
            "--consumer-policy-manifest",
            "policy-manifest.json",
            "--mutations",
            "true",
            "--fail-on-findings",
            "true",
        ],
        cwd=REPOSITORY,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["reusable_action_version"] == 1
    assert data["decision"] == "pass"
    assert data["passed"] is True
    assert data["consumer_contract"]["passed"] is True
    assert data["custom_packs"] is False
    assert "guarded_adapter.py" not in output.read_text(encoding="utf-8")
    assert str(REPOSITORY) not in output.read_text(encoding="utf-8")
    assert "decision=pass" in github_output.read_text(encoding="utf-8")
    summary_text = summary.read_text(encoding="utf-8")
    assert "# Reusable Agent Assurance" in summary_text
    assert "guarded_adapter.py" not in summary_text


def test_reusable_action_runner_refuses_shell_command_strings(tmp_path):
    output = tmp_path / "report.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--agent-id",
            "consumer-agent",
            "--adapter-command-json",
            "python examples/guarded_adapter.py",
            "--adapter-working-directory",
            str(REPOSITORY),
            "--output",
            str(output),
        ],
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 1
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["decision"] == "blocked"
    assert data["refusal"]["error"] == "reusable_assurance_refused"
    assert "python examples/guarded_adapter.py" not in output.read_text(
        encoding="utf-8"
    )
