"""Validate the reusable action from a separate synthetic consumer fixture."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONSUMER = ROOT / "examples" / "consumer-repository"
RUNNER = ROOT / "tools" / "reusable_action_runner.py"
WORKFLOW = CONSUMER / ".github" / "workflows" / "assurance.yml"
ACTION_REF = (
    "0c84a8c442a4229206a05fee9eb9e07982a4f0c3"
)
ACTION_USE = (
    "julie-elkins/agent-assurance-harness/.github/actions/agent-assurance@"
    + ACTION_REF
)


def _workflow_contract() -> dict[str, object]:
    text = WORKFLOW.read_text(encoding="utf-8")
    return {
        "pinned_to_reviewed_commit": text.count(ACTION_USE) == 2,
        "no_moving_action_reference": "@main" not in text,
        "read_only_permissions": "permissions:\n  contents: read" in text,
        "positive_and_negative_jobs": (
            "id: positive" in text
            and "id: negative" in text
            and "continue-on-error: true" in text
        ),
    }


def _run_consumer(adapter: str, *, fail_on_findings: bool) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="agent-assurance-consumer-") as directory:
        output = Path(directory) / "report.json"
        github_output = Path(directory) / "github-output"
        environment = os.environ.copy()
        environment["GITHUB_OUTPUT"] = str(github_output)
        command = [
            sys.executable,
            str(RUNNER),
            "--agent-id",
            "consumer-agent",
            "--adapter-command-json",
            json.dumps(["python", adapter]),
            "--adapter-working-directory",
            str(CONSUMER),
            "--output",
            str(output),
            "--mutations",
            "true",
            "--fail-on-findings",
            str(fail_on_findings).lower(),
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            check=False,
            text=True,
        )
        try:
            report = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "return_code": completed.returncode,
                "decision": "blocked",
                "passed": False,
                "report_version": None,
                "github_outputs_present": False,
            }
        output_text = (
            github_output.read_text(encoding="utf-8")
            if github_output.exists()
            else ""
        )
        return {
            "return_code": completed.returncode,
            "decision": report.get("decision"),
            "passed": report.get("passed"),
            "report_version": report.get("reusable_action_version"),
            "github_outputs_present": (
                "decision=" in output_text and "passed=" in output_text
            ),
        }


def build_report() -> dict[str, object]:
    workflow = _workflow_contract()
    positive = _run_consumer("guarded_adapter.py", fail_on_findings=True)
    negative = _run_consumer("regressed_adapter.py", fail_on_findings=True)
    negative_caught = (
        negative["return_code"] != 0
        and negative["decision"] == "blocked"
        and negative["passed"] is False
    )
    passed = all(workflow.values()) and (
        positive["return_code"] == 0
        and positive["decision"] == "pass"
        and positive["passed"] is True
        and positive["github_outputs_present"] is True
        and negative_caught
    )
    return {
        "consumer_validation_version": 1,
        "consumer_fixture": "synthetic-consumer-repository",
        "action_ref": ACTION_REF,
        "workflow_contract": workflow,
        "positive_run": positive,
        "negative_control": {
            **negative,
            "caught": negative_caught,
        },
        "passed": passed,
        "diagnostics": {
            "warnings": [
                "The fixture runs locally through the same bounded subprocess "
                "runner used by the composite action.",
                "The fixture contains synthetic identifiers only.",
            ],
            "what_it_does_not_show": (
                "It does not prove GitHub-hosted runner availability, live provider "
                "quality, or consumer-specific deployment behaviour."
            ),
        },
    }


def _markdown(data: dict[str, object]) -> str:
    positive = data["positive_run"]
    negative = data["negative_control"]
    status = "PASS" if data["passed"] else "BLOCKED"
    return "\n".join(
        [
            "## Reusable action consumer validation",
            "",
            f"- **Decision:** {status}",
            f"- **Action commit:** `{data['action_ref']}`",
            f"- **Positive consumer run:** `{positive['decision']}`",
            f"- **Negative control caught:** `{negative['caught']}`",
            "",
            "The fixture is synthetic and metadata-only; credentials, prompts, "
            "payloads, and provider output are not exported.",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the reusable action from a synthetic consumer fixture."
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-block", action="store_true")
    args = parser.parse_args(argv)
    data = build_report()
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.markdown:
        print(_markdown(data), end="")
    else:
        print(json.dumps(data, indent=2, sort_keys=True))
    return int(args.fail_on_block and not data["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
