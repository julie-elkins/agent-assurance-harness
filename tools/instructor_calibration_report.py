"""Run the synthetic instructor-calibration controls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.instructor_calibration import (
    run_reference_instructor_calibration_suite,
)


def main(argv: list[str] | None = None) -> int:
    """Run the deterministic observer-rubric suite."""

    parser = argparse.ArgumentParser(
        description=(
            "Verify synthetic instructor observations and coaching controls."
        )
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Return non-zero when a declared control is missed.",
    )
    args = parser.parse_args(argv)

    report = run_reference_instructor_calibration_suite()
    serialized = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(report.to_markdown() if args.markdown else serialized, end="")
    return int(args.fail_on_findings and not report.passed)


if __name__ == "__main__":
    raise SystemExit(main())
