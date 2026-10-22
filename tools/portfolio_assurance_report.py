"""Run the reviewer-facing public portfolio assurance report."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from agent_reliability_lab.portfolio_report import (
    run_reference_portfolio_report,
)


def main(argv: list[str] | None = None) -> int:
    """Run the bounded portfolio orchestrator."""

    parser = argparse.ArgumentParser(
        description=(
            "Join the public assurance lanes into one metadata-only "
            "reviewer report."
        )
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help="Optional workspace for inspectable intermediate lane reports.",
    )
    parser.add_argument(
        "--course-root",
        type=Path,
        help=(
            "Optional checked-out public Claude course. When supplied, "
            "add its metadata-only verification as a local review lane."
        ),
    )
    parser.add_argument("--course-id", default="claude-architect-lab")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--max-rows", type=int, default=1000)
    parser.add_argument("--max-requests", type=int, default=50)
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Return non-zero when a lane or orchestration control is missed.",
    )
    args = parser.parse_args(argv)

    if args.workspace is None:
        with tempfile.TemporaryDirectory(
            prefix="agent-assurance-portfolio-"
        ) as directory:
            report = run_reference_portfolio_report(
                workspace=Path(directory),
                course_root=args.course_root,
                course_id=args.course_id,
                offline=args.offline,
                max_rows=args.max_rows,
                max_requests=args.max_requests,
            )
    else:
        report = run_reference_portfolio_report(
            workspace=args.workspace,
            course_root=args.course_root,
            course_id=args.course_id,
            offline=args.offline,
            max_rows=args.max_rows,
            max_requests=args.max_requests,
        )

    output_value = report.to_dict()
    serialized = json.dumps(output_value, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(report.to_markdown() if args.markdown else serialized, end="")
    return int(args.fail_on_findings and not report.passed)


if __name__ == "__main__":
    raise SystemExit(main())
