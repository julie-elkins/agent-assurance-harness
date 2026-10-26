"""Run the bounded synthetic agent-memory policy assurance lane."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.memory_policy import (
    DEFAULT_PACK_DIRECTORY,
    run_reference_memory_policy_suite,
)


def main(argv: list[str] | None = None) -> int:
    """Run the synthetic memory-policy suite."""

    parser = argparse.ArgumentParser(
        description="Run bounded synthetic agent-memory policy assurance."
    )
    parser.add_argument(
        "--pack-directory",
        type=Path,
        default=DEFAULT_PACK_DIRECTORY,
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Return non-zero when a positive control or negative control fails.",
    )
    args = parser.parse_args(argv)
    report = run_reference_memory_policy_suite(args.pack_directory)
    serialized = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(report.to_markdown() if args.markdown else serialized, end="")
    return int(args.fail_on_findings and not report.passed)


if __name__ == "__main__":
    raise SystemExit(main())
