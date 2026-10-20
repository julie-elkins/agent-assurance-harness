"""Compare a candidate adapter with the checked-in synthetic Golden Trace."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from agent_reliability_lab.golden_trace import (
    build_golden_manifest,
    compare_golden_trace,
    load_golden_manifest,
    load_replay_for_golden,
)
from agent_reliability_lab.external import (
    DEFAULT_ADAPTER_TIMEOUT_SECONDS,
    DEFAULT_MAX_MEMORY_BYTES,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_MAX_STDERR_BYTES,
    SubprocessAdapter,
)
from agent_reliability_lab.packs import load_builtin_packs
from agent_reliability_lab.replay import (
    HARNESS_COMPONENTS,
    HarnessChangeManifest,
    ReplayRefusal,
    run_adapter_replay,
)


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")


def _identifier(value: str) -> str:
    if _IDENTIFIER.fullmatch(value) is None:
        raise argparse.ArgumentTypeError(
            "must contain identifier characters only: letters, numbers, _, ., :, /, or -"
        )
    return value


def _components(parser: argparse.ArgumentParser, values: list[str]) -> tuple[str, ...]:
    if not values:
        parser.error("at least one candidate component is required")
    return tuple(values)


def _write_manifest(golden_replay: Path, output: Path) -> int:
    replay = load_replay_for_golden(golden_replay)
    manifest = build_golden_manifest(replay, load_builtin_packs())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest.to_dict(), indent=2, sort_keys=True))
    return 0


def _refused_report(
    golden_source: str,
    candidate_source: str,
    error: Exception,
) -> dict[str, object]:
    refusal = ReplayRefusal(
        error="golden_trace_refused",
        message="The Golden Trace comparison could not be completed.",
        guidance="Repair the replay, manifest, or candidate adapter before retrying.",
        source=type(error).__name__,
    )
    return {
        "golden_source": golden_source,
        "candidate_source": candidate_source,
        "passed": False,
        "drifts": [],
        "refusal": refusal.to_dict(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare a candidate adapter with a synthetic Golden Trace baseline "
            "without exporting trace content."
        )
    )
    parser.add_argument("--golden-replay", required=True, type=Path)
    parser.add_argument("--golden-manifest", type=Path)
    parser.add_argument(
        "--manifest-output",
        type=Path,
        help="Write a new manifest from --golden-replay.",
    )
    parser.add_argument("--candidate-adapter-command", action="append")
    parser.add_argument("--agent-id")
    parser.add_argument("--candidate-change-id", type=_identifier)
    parser.add_argument(
        "--candidate-component",
        action="append",
        choices=HARNESS_COMPONENTS,
        default=[],
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_ADAPTER_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--max-response-bytes",
        type=int,
        default=DEFAULT_MAX_RESPONSE_BYTES,
    )
    parser.add_argument(
        "--max-stderr-bytes",
        type=int,
        default=DEFAULT_MAX_STDERR_BYTES,
    )
    parser.add_argument(
        "--max-memory-bytes",
        type=int,
        default=DEFAULT_MAX_MEMORY_BYTES,
    )
    parser.add_argument("--adapter-working-directory", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-drift", action="store_true")
    parser.add_argument(
        "--expect-drift",
        action="store_true",
        help="Pass only when at least one Golden Trace drift is detected.",
    )
    args = parser.parse_args(argv)

    if args.manifest_output is not None:
        if any(
            value is not None
            for value in (
                args.golden_manifest,
                args.candidate_adapter_command,
                args.agent_id,
                args.candidate_change_id,
            )
        ):
            parser.error("--manifest-output cannot be combined with comparison options")
        return _write_manifest(args.golden_replay, args.manifest_output)

    if (
        args.golden_manifest is None
        or not args.candidate_adapter_command
        or args.agent_id is None
        or args.candidate_change_id is None
    ):
        parser.error(
            "--golden-manifest, --agent-id, --candidate-change-id, and "
            "--candidate-adapter-command are required for comparison"
        )
    candidate_components = _components(parser, args.candidate_component)
    golden_source = str(args.golden_replay)
    candidate_source = "candidate-adapter"
    try:
        golden = load_replay_for_golden(args.golden_replay)
        manifest = load_golden_manifest(args.golden_manifest)
        adapter = SubprocessAdapter(
            agent_id=args.agent_id,
            command=tuple(args.candidate_adapter_command),
            timeout_seconds=args.timeout_seconds,
            max_response_bytes=args.max_response_bytes,
            max_stderr_bytes=args.max_stderr_bytes,
            max_memory_bytes=args.max_memory_bytes,
            working_directory=args.adapter_working_directory,
        )
        candidate = run_adapter_replay(
            adapter,
            harness_change=HarnessChangeManifest(
                change_id=args.candidate_change_id,
                components=candidate_components,
            ),
        )
        report = compare_golden_trace(
            golden,
            candidate,
            manifest=manifest,
            packs=load_builtin_packs(),
            golden_source=golden_source,
            candidate_source=candidate_source,
        )
        data = report.to_dict()
        exit_code = 0
        if args.expect_drift:
            exit_code = int(report.refusal is not None or not report.drifts)
        elif args.fail_on_drift and not report.passed:
            exit_code = 1
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        data = _refused_report(golden_source, candidate_source, error)
        exit_code = 1
    serialized = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
