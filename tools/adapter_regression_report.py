"""Compare two local adapter commands through the identifier-only regression gate."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tomllib
from pathlib import Path

from agent_reliability_lab.attestation import (
    AssuranceAttestation,
    build_regression_attestation,
)
from agent_reliability_lab.external import (
    DEFAULT_ADAPTER_TIMEOUT_SECONDS,
    DEFAULT_MAX_MEMORY_BYTES,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_MAX_STDERR_BYTES,
    SubprocessAdapter,
)
from agent_reliability_lab.regression import RegressionReport, compare_replays
from agent_reliability_lab.replay import (
    HARNESS_COMPONENTS,
    HarnessChangeManifest,
    ReplayRefusal,
    run_adapter_replay,
)
from agent_reliability_lab.packs import load_builtin_packs


_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
ROOT = Path(__file__).resolve().parents[1]


def _identifier(value: str) -> str:
    if _IDENTIFIER.fullmatch(value) is None:
        raise argparse.ArgumentTypeError(
            "must contain identifier characters only: letters, numbers, _, ., :, /, or -"
        )
    return value


def _components(parser: argparse.ArgumentParser, values: list[str]) -> tuple[str, ...]:
    if not values:
        parser.error("at least one harness component is required")
    return tuple(values)


def _refused_report(error: Exception) -> RegressionReport:
    return RegressionReport(
        baseline_source="baseline-adapter",
        candidate_source="candidate-adapter",
        expected_scenario_count=0,
        refusal=ReplayRefusal(
            error="candidate_regression_refused",
            message="The candidate regression run could not be completed.",
            guidance="Repair the adapter or built-in pack validation issue before retrying.",
            source=type(error).__name__,
        ),
    )


def _package_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]["version"]


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _attestation(
    report: RegressionReport,
) -> AssuranceAttestation:
    return build_regression_attestation(
        report,
        load_builtin_packs(),
        package_version=_package_version(),
        git_commit=_git_commit(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare baseline and candidate adapters through the identifier-only "
            "safety and evidence regression gate."
        )
    )
    parser.add_argument("--agent-id", required=True)
    parser.add_argument(
        "--baseline-adapter-command",
        action="append",
        required=True,
        help="One argument of the approved baseline adapter command; repeat for each argument.",
    )
    parser.add_argument(
        "--candidate-adapter-command",
        action="append",
        required=True,
        help="One argument of the candidate adapter command; repeat for each argument.",
    )
    parser.add_argument("--baseline-change-id", required=True, type=_identifier)
    parser.add_argument(
        "--baseline-component",
        action="append",
        choices=HARNESS_COMPONENTS,
        default=[],
        help="Changed baseline component; repeat for each component.",
    )
    parser.add_argument("--candidate-change-id", required=True, type=_identifier)
    parser.add_argument(
        "--candidate-component",
        action="append",
        choices=HARNESS_COMPONENTS,
        default=[],
        help="Changed candidate component; repeat for each component.",
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
    parser.add_argument(
        "--attestation-output",
        type=Path,
        help="Optional path for the metadata-only assurance attestation.",
    )
    parser.add_argument("--fail-on-findings", action="store_true")
    parser.add_argument(
        "--expect-blocking",
        action="store_true",
        help="Pass only when the comparison catches at least one blocking regression.",
    )
    args = parser.parse_args(argv)

    baseline_components = _components(parser, args.baseline_component)
    candidate_components = _components(parser, args.candidate_component)
    baseline = SubprocessAdapter(
        agent_id=args.agent_id,
        command=tuple(args.baseline_adapter_command),
        timeout_seconds=args.timeout_seconds,
        max_response_bytes=args.max_response_bytes,
        max_stderr_bytes=args.max_stderr_bytes,
        max_memory_bytes=args.max_memory_bytes,
        working_directory=args.adapter_working_directory,
    )
    candidate = SubprocessAdapter(
        agent_id=args.agent_id,
        command=tuple(args.candidate_adapter_command),
        timeout_seconds=args.timeout_seconds,
        max_response_bytes=args.max_response_bytes,
        max_stderr_bytes=args.max_stderr_bytes,
        max_memory_bytes=args.max_memory_bytes,
        working_directory=args.adapter_working_directory,
    )
    try:
        baseline_replay = run_adapter_replay(
            baseline,
            harness_change=HarnessChangeManifest(
                change_id=args.baseline_change_id,
                components=baseline_components,
            ),
        )
        candidate_replay = run_adapter_replay(
            candidate,
            harness_change=HarnessChangeManifest(
                change_id=args.candidate_change_id,
                components=candidate_components,
            ),
        )
        report = compare_replays(
            baseline_replay,
            candidate_replay,
            baseline_source="baseline-adapter",
            candidate_source="candidate-adapter",
        )
    except (OSError, RuntimeError, ValueError) as error:
        report = _refused_report(error)

    attestation = _attestation(report)
    report_data = report.to_dict()
    report_data["assurance_attestation"] = attestation.to_dict()
    serialized = json.dumps(report_data, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    if args.attestation_output is not None:
        args.attestation_output.parent.mkdir(parents=True, exist_ok=True)
        args.attestation_output.write_text(
            json.dumps(attestation.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(serialized, end="")
    if args.expect_blocking:
        return int(
            report.refusal is not None
            or not any(finding.blocking for finding in report.findings)
        )
    if args.fail_on_findings and report.failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
