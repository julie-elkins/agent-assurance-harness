"""Run the metadata-only rollback rehearsal."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.rollback_rehearsal import (
    RollbackRehearsalReport,
    run_rollback_rehearsal,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLAN = ROOT / "examples" / "rollback-plan.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Rehearse restoring a synthetic last-known-good release artifact "
            "without deployment writes or network access."
        )
    )
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args(argv)

    try:
        report: RollbackRehearsalReport = run_rollback_rehearsal(
            args.plan,
            ROOT,
        )
        data = report.to_dict()
        serialized = (
            report.to_markdown()
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        exit_code = int(args.fail_on_findings and not report.passed)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        data = {
            "rollback_rehearsal_version": 1,
            "passed": False,
            "refusal": {
                "error": "rollback_rehearsal_refused",
                "message": "The rollback rehearsal could not be completed.",
                "guidance": (
                    "Repair the rollback plan or repository checkout before retrying."
                ),
                "source": type(error).__name__,
            },
            "diagnostics": {
                "warnings": [
                    "A refusal is a blocked result, not a passing empty result."
                ],
                "what_it_does_not_show": (
                    "It does not show temporary paths, raw files, or failure-marker content."
                ),
            },
        }
        serialized = (
            "## Rollback rehearsal\n\n"
            "- **Decision:** BLOCKED\n"
            "- **Reason:** `rollback-rehearsal-refused`\n"
        )
        exit_code = 1

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(serialized, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
