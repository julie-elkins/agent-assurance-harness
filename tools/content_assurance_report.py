"""Run the public synthetic technical-content assurance reference agent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.content_assurance import (
    run_reference_content_assurance_suite,
)


def main(argv: list[str] | None = None) -> int:
    """Run the metadata-only reference suite."""

    parser = argparse.ArgumentParser(
        description="Run synthetic technical-content assurance controls."
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Return non-zero when a positive or negative control is incorrect.",
    )
    args = parser.parse_args(argv)

    report = run_reference_content_assurance_suite()
    if args.markdown:
        rendered = report.to_markdown() + "\n"
    else:
        rendered = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(rendered, end="")
    return int(args.fail_on_findings and not report.passed)


if __name__ == "__main__":
    raise SystemExit(main())
