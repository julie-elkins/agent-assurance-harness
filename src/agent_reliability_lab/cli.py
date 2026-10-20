"""Command-line interface for the offline reliability comparison."""

from __future__ import annotations

import argparse
import json
import sys

from .external import (
    DEFAULT_ADAPTER_TIMEOUT_SECONDS,
    DEFAULT_MAX_RESPONSE_BYTES,
    SubprocessAdapter,
)
from .runner import failed_checks, run_adapter_comparison, run_comparison


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
    parser.add_argument(
        "--adapter-check",
        action="store_true",
        help="Run a local subprocess adapter through the assurance harness.",
    )
    parser.add_argument(
        "--adapter-command",
        action="append",
        help="One argument of the adapter command; repeat for each argument.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_ADAPTER_TIMEOUT_SECONDS,
        help="Maximum time for one adapter scenario run.",
    )
    parser.add_argument(
        "--max-response-bytes",
        type=int,
        default=DEFAULT_MAX_RESPONSE_BYTES,
        help="Maximum stdout bytes accepted from one adapter scenario run.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    args = build_parser().parse_args(argv)
    if args.adapter_check:
        if not args.adapter_command:
            print(
                "--adapter-check requires at least one --adapter-command argument.",
                file=sys.stderr,
            )
            return 2
        adapter = SubprocessAdapter(
            agent_id="external",
            command=tuple(args.adapter_command),
            timeout_seconds=args.timeout_seconds,
            max_response_bytes=args.max_response_bytes,
        )
        report = run_adapter_comparison(
            adapter,
            include_mutations=args.mutations,
        )
    else:
        if args.adapter_command:
            print(
                "--adapter-command is only valid with --adapter-check.",
                file=sys.stderr,
            )
            return 2
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
