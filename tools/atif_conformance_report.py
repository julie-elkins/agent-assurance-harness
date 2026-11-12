"""Run the metadata-only ATIF evidence conformance check."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.atif_conformance import run_atif_conformance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check an identifier-only ATIF evidence summary."
    )
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Return non-zero unless the evidence summary conforms.",
    )
    args = parser.parse_args(argv)

    try:
        value = json.loads(args.summary.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        report = run_atif_conformance(None)
    else:
        report = run_atif_conformance(value)

    serialized = (
        report.to_markdown()
        if args.markdown
        else json.dumps(report.to_dict(), indent=2, sort_keys=True)
    ) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    if args.fail_on_findings and not report.conformance_passed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
