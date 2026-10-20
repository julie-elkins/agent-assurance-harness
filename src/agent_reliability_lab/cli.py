"""Command-line interface for the offline reliability comparison."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .external import (
    DEFAULT_ADAPTER_TIMEOUT_SECONDS,
    DEFAULT_MAX_RESPONSE_BYTES,
    SubprocessAdapter,
)
from .live import LiveProviderPolicy, live_provider_adapter
from .packs import load_builtin_pack_results, load_pack_directory
from .otlp import load_otlp_file
from .providers import ProviderLimits, mock_provider_adapters
from .replay import REPLAY_VERSION, ReplayReport, run_replay, run_replay_file
from .regression import RegressionReport, compare_replay_files
from .runner import (
    failed_checks,
    run_adapter_comparison,
    run_adapters_comparison,
    run_adapter_scenario,
    run_comparison,
)


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
    parser.add_argument(
        "--list-packs",
        action="store_true",
        help="Validate and list built-in or explicitly supplied scenario packs.",
    )
    parser.add_argument(
        "--pack-directory",
        type=Path,
        help="Directory of JSON scenario packs used with --list-packs.",
    )
    parser.add_argument(
        "--replay-file",
        type=Path,
        help="Replay one complete identifier-only adapter response file.",
    )
    parser.add_argument(
        "--otlp-file",
        type=Path,
        help="Import and evaluate one local identifier-only OTLP/JSON trace export.",
    )
    parser.add_argument(
        "--mock-provider",
        choices=("openai", "anthropic", "all"),
        help="Run the credential-free mocked provider adapter(s).",
    )
    parser.add_argument(
        "--live-provider",
        choices=("openai", "anthropic"),
        help="Run one explicitly bounded live provider scenario.",
    )
    parser.add_argument(
        "--scenario-id",
        help="Built-in synthetic scenario to run with --live-provider.",
    )
    parser.add_argument(
        "--model",
        help="Provider model identifier for --live-provider.",
    )
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Explicitly permit the one local synthetic provider request.",
    )
    parser.add_argument("--max-requests", type=int)
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--max-elapsed-seconds", type=float)
    parser.add_argument("--max-estimated-cost-usd", type=float)
    parser.add_argument("--estimated-cost-usd-per-request", type=float)
    parser.add_argument(
        "--compare-replay",
        nargs=2,
        metavar=("BASELINE", "CANDIDATE"),
        type=Path,
        help="Compare a baseline replay with a candidate harness replay.",
    )
    return parser


def _print_replay_report(report: ReplayReport, args: argparse.Namespace) -> None:
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    elif args.markdown:
        print(report.to_markdown())
    elif report.refusal is not None:
        print(
            f"[{report.refusal.error}] {report.refusal.source}: "
            f"{report.refusal.message}"
        )
    else:
        assert report.agent_report is not None
        outcome = "PASS" if report.agent_report.passed else "FINDINGS"
        print(f"replay {report.agent_report.agent_id}: {outcome}")
        for finding in report.agent_report.findings:
            print(
                f"  [{finding.status.value}] {finding.check_id}: "
                f"{finding.message}"
            )


def _print_regression_report(
    report: RegressionReport,
    args: argparse.Namespace,
) -> None:
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    elif args.markdown:
        print(report.to_markdown())
    elif report.refusal is not None:
        print(
            f"[{report.refusal.error}] {report.refusal.source}: "
            f"{report.refusal.message}"
        )
    else:
        outcome = "PASS" if not report.failed else "BLOCKED"
        print(f"harness regression: {outcome}")
        for finding in report.findings:
            gate = "blocking" if finding.blocking else "observation"
            print(
                f"  [{gate}] {finding.scenario_id}/{finding.check_id}: "
                f"{finding.message}"
            )


def _print_comparison_report(report, args: argparse.Namespace) -> None:
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    elif args.markdown:
        print(report.to_markdown())
    else:
        for agent_report in report.reports:
            outcome = "PASS" if agent_report.passed else "FINDINGS"
            print(f"{agent_report.agent_id}: {outcome}")
            for finding in agent_report.findings:
                print(
                    f"  [{finding.status.value}] {finding.check_id}: "
                    f"{finding.message}"
                )
        if args.mutations:
            print("mutation tests:")
            for mutation in report.mutation_tests:
                outcome = "CAUGHT" if mutation.caught else "MISSED"
                print(
                    f"  [{outcome}] {mutation.mutation_id}: "
                    f"{mutation.description}"
                )


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    args = build_parser().parse_args(argv)
    if args.compare_replay is not None:
        if (
            args.replay_file is not None
            or args.otlp_file is not None
            or args.list_packs
            or args.pack_directory is not None
            or args.adapter_check
            or args.adapter_command
            or args.mutations
            or args.mock_provider is not None
            or args.live_provider is not None
        ):
            print(
                "--compare-replay cannot be combined with another trace input, "
                "pack listing, adapter, or mutation options.",
                file=sys.stderr,
            )
            return 2
        report = compare_replay_files(*args.compare_replay)
        _print_regression_report(report, args)
        if report.refusal is not None:
            return 1
        if args.fail_on_findings and report.failed:
            return 1
        return 0
    if args.replay_file is not None or args.otlp_file is not None:
        if (
            args.replay_file is not None
            and args.otlp_file is not None
        ) or (
            args.list_packs
            or args.pack_directory is not None
            or args.adapter_check
            or args.adapter_command
            or args.mutations
            or args.mock_provider is not None
            or args.live_provider is not None
        ):
            print(
                "Trace input cannot be combined with another trace input, pack listing, "
                "adapter, or mutation options.",
                file=sys.stderr,
            )
            return 2
        if args.otlp_file is not None:
            loaded = load_otlp_file(args.otlp_file)
            if loaded.refusal is not None:
                report = ReplayReport(
                    source=str(args.otlp_file),
                    replay_version=REPLAY_VERSION,
                    expected_scenario_count=0,
                    refusal=loaded.refusal,
                )
            else:
                assert loaded.replay is not None
                report = run_replay(
                    loaded.replay,
                    source=str(args.otlp_file),
                )
        else:
            assert args.replay_file is not None
            report = run_replay_file(args.replay_file)
        _print_replay_report(report, args)
        if report.refusal is not None:
            return 1
        if args.fail_on_findings and report.failed:
            return 1
        return 0
    if args.live_provider is not None:
        required = {
            "--scenario-id": args.scenario_id,
            "--model": args.model,
            "--max-requests": args.max_requests,
            "--max-output-tokens": args.max_output_tokens,
            "--max-elapsed-seconds": args.max_elapsed_seconds,
            "--max-estimated-cost-usd": args.max_estimated_cost_usd,
            "--estimated-cost-usd-per-request": (
                args.estimated_cost_usd_per_request
            ),
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            print(
                "--live-provider requires: " + ", ".join(missing) + ".",
                file=sys.stderr,
            )
            return 2
        if (
            args.list_packs
            or args.pack_directory is not None
            or args.adapter_check
            or args.adapter_command
            or args.mutations
            or args.mock_provider is not None
        ):
            print(
                "--live-provider cannot be combined with pack listing, adapter, "
                "mutation, or mocked-provider options.",
                file=sys.stderr,
            )
            return 2
        credential_env_var = (
            "OPENAI_API_KEY"
            if args.live_provider == "openai"
            else "ANTHROPIC_API_KEY"
        )
        policy = LiveProviderPolicy(
            provider_id=args.live_provider,
            model=args.model,
            credential_env_var=credential_env_var,
            limits=ProviderLimits(
                max_requests=args.max_requests,
                max_output_tokens=args.max_output_tokens,
                max_elapsed_seconds=args.max_elapsed_seconds,
                max_estimated_cost_usd=args.max_estimated_cost_usd,
            ),
            estimated_cost_usd_per_request=args.estimated_cost_usd_per_request,
            allow_network=args.allow_network,
        )
        try:
            report = run_adapter_scenario(
                live_provider_adapter(policy),
                args.scenario_id,
            )
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 2
        _print_comparison_report(report, args)
        if failed_checks(report):
            return 1
        return 0
    if args.mock_provider is not None:
        if (
            args.list_packs
            or args.pack_directory is not None
            or args.adapter_check
            or args.adapter_command
            or args.live_provider is not None
        ):
            print(
                "--mock-provider cannot be combined with pack listing or adapter options.",
                file=sys.stderr,
            )
            return 2
        report = run_adapters_comparison(
            mock_provider_adapters(args.mock_provider),
            include_mutations=args.mutations,
        )
        _print_comparison_report(report, args)
        if args.fail_on_findings and failed_checks(report):
            return 1
        return 0
    if args.list_packs:
        if args.adapter_check or args.adapter_command:
            print("--list-packs cannot be combined with --adapter-check.", file=sys.stderr)
            return 2
        results = (
            load_pack_directory(args.pack_directory)
            if args.pack_directory is not None
            else load_builtin_pack_results()
        )
        packs = [result.pack.to_dict() for result in results if result.pack is not None]
        refusals = [
            result.refusal.to_dict()
            for result in results
            if result.refusal is not None
        ]
        if args.json:
            print(json.dumps({"packs": packs, "refusals": refusals}, indent=2))
        elif args.markdown:
            print("# Scenario Packs")
            print("")
            for pack in packs:
                print(f"- `{pack['scenario_id']}` — {pack['title']}")
            if refusals:
                print("")
                print("## Refusals")
                print("")
                for refusal in refusals:
                    print(f"- `{refusal['source']}`: {refusal['message']}")
        else:
            for pack in packs:
                print(f"{pack['scenario_id']}: {pack['title']}")
            for refusal in refusals:
                print(f"[{refusal['error']}] {refusal['source']}: {refusal['message']}")
        return 1 if refusals else 0
    if args.pack_directory is not None:
        print("--pack-directory requires --list-packs.", file=sys.stderr)
        return 2
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
    _print_comparison_report(report, args)
    if args.fail_on_findings and failed_checks(report):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
