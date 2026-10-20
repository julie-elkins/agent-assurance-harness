"""Command-line interface for the offline reliability comparison."""

from __future__ import annotations

import argparse
import json
import sys

from .runner import failed_checks, run_comparison


def build_parser() -> argparse.ArgumentParser:
    """Build the parser without reading files or making network calls."""

    parser = argparse.ArgumentParser(
        description="Run the offline Agent Assurance Harness scenarios."
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json",
        action="store_true",
        help="Emit the structured report as JSON to stdout.",
    )
    output_group.add_argument(
        "--markdown",
        action="store_true",
        help="Emit a Markdown summary to stdout.",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit 1 when any agent produces a failed reliability check.",
    )
    parser.add_argument(
        "--mutations",
        action="store_true",
        help="Run controlled evidence mutations against the evaluator.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    args = build_parser().parse_args(argv)
    report = run_comparison(include_mutations=args.mutations)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    elif args.markdown:
        print(report.to_markdown())
    else:
        for agent_report in report.reports:
            outcome = "PASS" if agent_report.passed else "FINDINGS"
            print(f"{agent_report.agent_id}: {outcome}")
            for finding in agent_report.findings:
                print(f"  [{finding.status.value}] {finding.check_id}: {finding.message}")
        if args.mutations:
            print("mutation tests:")
            for mutation in report.mutation_tests:
                outcome = "CAUGHT" if mutation.caught else "MISSED"
                print(f"  [{outcome}] {mutation.mutation_id}: {mutation.description}")
    if args.fail_on_findings and failed_checks(report):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
