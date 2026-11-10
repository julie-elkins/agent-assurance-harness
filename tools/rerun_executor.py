"""Execute a bounded, metadata-only synthetic rerun from a change-impact plan."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from agent_reliability_lab.change_impact import build_change_impact_plan
from agent_reliability_lab.evidence_registry import load_evidence_registry
from agent_reliability_lab.rerun_executor import (
    RERUN_COMPLETED,
    RERUN_NOT_REQUIRED,
    RerunPolicy,
    run_bounded_rerun,
)
from agent_reliability_lab.run_manifest import load_current_revisions, load_manifest


def _git_paths(repo: Path, base: str, head: str) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-only", base, head],
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run only code-side allowlisted synthetic checks for affected evidence."
        )
    )
    parser.add_argument("--baseline-revisions", type=Path, required=True)
    parser.add_argument("--current-revisions", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--changed-path", action="append", default=[])
    parser.add_argument("--git-diff-base")
    parser.add_argument("--git-diff-head", default="HEAD")
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--max-checks", type=int, default=8)
    parser.add_argument("--max-elapsed-seconds", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument(
        "--fail-on-noncompleted",
        action="store_true",
        help="Return non-zero unless no rerun was needed or the rerun completed.",
    )
    args = parser.parse_args(argv)

    try:
        paths = list(args.changed_path)
        if args.git_diff_base:
            paths.extend(_git_paths(args.repo, args.git_diff_base, args.git_diff_head))
        plan = build_change_impact_plan(
            [load_manifest(str(path)) for path in args.manifest],
            load_current_revisions(str(args.baseline_revisions)),
            load_current_revisions(str(args.current_revisions)),
            paths,
            load_evidence_registry(args.registry),
        )
        execution = run_bounded_rerun(
            plan,
            policy=RerunPolicy(
                max_checks=args.max_checks,
                max_elapsed_seconds=args.max_elapsed_seconds,
            ),
        )
        data = execution.to_dict()
        serialized = (
            execution.to_markdown()
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        exit_code = int(
            args.fail_on_noncompleted
            and execution.status not in {RERUN_NOT_REQUIRED, RERUN_COMPLETED}
        )
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        data = {
            "rerun_executor_version": 1,
            "plan_status": "input_invalid",
            "status": "refused",
            "evidence_ids": [],
            "selected_check_ids": [],
            "results": [],
            "summary": {
                "checks_selected": 0,
                "checks_completed": 0,
                "checks_failed": 0,
                "negative_controls_caught": 0,
                "suite_runs": 0,
                "elapsed_seconds": 0.0,
            },
            "reason_codes": ["rerun_input_invalid", type(error).__name__],
            "required_action": "Repair the rerun inputs before retrying.",
        }
        serialized = (
            json.dumps(data, indent=2, sort_keys=True) + "\n"
            if not args.markdown
            else "# Bounded synthetic rerun\n\n- **Executor result:** `refused`\n"
            "- **Required action:** Repair the rerun inputs before retrying.\n"
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
    sys.exit(main())
