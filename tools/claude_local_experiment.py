"""Run a bounded local-only Claude experiment over synthetic scenarios."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.claude_experiment import (
    CLAUDE_HAIKU_MODEL,
    CLAUDE_SONNET_MODEL,
    DEFAULT_ELAPSED_SECONDS,
    DEFAULT_ESTIMATED_COST_PER_REQUEST_USD,
    DEFAULT_OUTPUT_TOKEN_CEILING,
    DEFAULT_TOTAL_COST_CEILING_USD,
    MAX_PILOT_CASE_COUNT,
    MIN_PILOT_CASE_COUNT,
    SMOKE_CASE_COUNT,
    ClaudeExperimentPolicy,
    run_claude_experiment,
)


def main(argv: list[str] | None = None) -> int:
    """Parse bounded local-run controls and emit metadata-only output."""

    parser = argparse.ArgumentParser(
        description=(
            "Run a local-only Claude experiment over built-in synthetic "
            "Agent Assurance Harness scenarios."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--smoke",
        action="store_true",
        help="Run one pass over the ten built-in scenarios.",
    )
    mode.add_argument(
        "--pilot",
        action="store_true",
        help="Run 20–30 deterministic replicates over the built-in scenarios.",
    )
    parser.add_argument(
        "--case-count",
        type=int,
        help="Pilot case count; defaults to 30. Smoke always runs 10 cases.",
    )
    parser.add_argument(
        "--model",
        default=CLAUDE_SONNET_MODEL,
        help=(
            "Anthropic model identifier. The default is the approved Sonnet "
            "5.5 first pass."
        ),
    )
    parser.add_argument(
        "--max-total-cost-usd",
        type=float,
        default=DEFAULT_TOTAL_COST_CEILING_USD,
        help="Hard aggregate planning ceiling for the whole run.",
    )
    parser.add_argument(
        "--estimated-cost-usd-per-request",
        type=float,
        default=DEFAULT_ESTIMATED_COST_PER_REQUEST_USD,
        help="Conservative planning estimate used before each request.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=DEFAULT_OUTPUT_TOKEN_CEILING,
    )
    parser.add_argument(
        "--max-elapsed-seconds",
        type=float,
        default=DEFAULT_ELAPSED_SECONDS,
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Required explicit opt-in for the local provider request.",
    )
    parser.add_argument(
        "--structured-output",
        action="store_true",
        help=(
            "Enable the separate provider-enforced JSON Schema comparison "
            "condition; the default baseline remains prompt_and_local_validation."
        ),
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true")
    output.add_argument("--markdown", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    case_count = (
        SMOKE_CASE_COUNT
        if args.smoke
        else args.case_count
        if args.case_count is not None
        else MAX_PILOT_CASE_COUNT
    )
    if args.pilot and not (
        MIN_PILOT_CASE_COUNT <= case_count <= MAX_PILOT_CASE_COUNT
    ):
        parser.error("--case-count must be between 20 and 30 for --pilot.")
    if args.smoke and args.case_count is not None:
        parser.error("--case-count cannot be combined with --smoke.")

    report = run_claude_experiment(
        ClaudeExperimentPolicy(
            model=args.model,
            case_count=case_count,
            max_total_cost_usd=args.max_total_cost_usd,
            estimated_cost_usd_per_request=args.estimated_cost_usd_per_request,
            max_output_tokens=args.max_output_tokens,
            max_elapsed_seconds=args.max_elapsed_seconds,
            allow_network=args.allow_network,
            structured_output=args.structured_output,
        )
    )
    serialized = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    if args.markdown:
        print(report.to_markdown())
    elif args.json or args.output is None:
        print(serialized, end="")
    if report.decision != "complete":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
