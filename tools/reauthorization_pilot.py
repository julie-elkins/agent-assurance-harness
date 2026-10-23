"""Run the offline synthetic agent-reauthorization pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.reauthorization import pilot_to_markdown, run_pilot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the metadata-only synthetic pilot for change-aware "
            "agent reauthorization."
        )
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Return non-zero if pilot integrity controls do not pass.",
    )
    args = parser.parse_args(argv)

    report = run_pilot()
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(pilot_to_markdown(report) if args.markdown else serialized, end="")
    return int(args.fail_on_findings and report["decision"] != "pass")


if __name__ == "__main__":
    raise SystemExit(main())
