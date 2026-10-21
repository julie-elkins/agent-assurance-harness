"""Run the bounded synthetic course-freshness coordinator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.course_freshness import (
    DEFAULT_MAX_COURSES,
    DEFAULT_MAX_ELAPSED_SECONDS,
    DEFAULT_MAX_WORKERS,
    run_reference_course_freshness_suite,
)


def main(argv: list[str] | None = None) -> int:
    """Run the reference inventory through independent freshness workers."""

    parser = argparse.ArgumentParser(
        description=(
            "Run a bounded synthetic course-freshness sweep with metadata-only "
            "worker checkpoints."
        )
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    parser.add_argument("--max-courses", type=int, default=DEFAULT_MAX_COURSES)
    parser.add_argument(
        "--max-elapsed-seconds",
        type=float,
        default=DEFAULT_MAX_ELAPSED_SECONDS,
    )
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args(argv)

    report = run_reference_course_freshness_suite(
        workspace=args.workspace,
        max_workers=args.max_workers,
        max_courses=args.max_courses,
        max_elapsed_seconds=args.max_elapsed_seconds,
    )
    serialized = json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(report.to_markdown() if args.markdown else serialized, end="")
    return int(args.fail_on_findings and not report.passed)


if __name__ == "__main__":
    raise SystemExit(main())
