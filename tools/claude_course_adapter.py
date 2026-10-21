"""Run the metadata-only adapter for an explicitly supplied Claude course checkout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.claude_course_adapter import (
    DEFAULT_MAX_REQUESTS,
    DEFAULT_MAX_ROWS,
    run_claude_course_adapter,
)


def main(argv: list[str] | None = None) -> int:
    """Run the local public-course adapter and render its safe report."""

    parser = argparse.ArgumentParser(
        description=(
            "Adapt a checked-out public Claude course verifier into a "
            "metadata-only Agent Assurance Harness report."
        )
    )
    parser.add_argument("--course-root", type=Path, required=True)
    parser.add_argument("--course-id", default="claude-architect-lab")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)
    parser.add_argument("--max-requests", type=int, default=DEFAULT_MAX_REQUESTS)
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args(argv)

    report = run_claude_course_adapter(
        args.course_root,
        course_id=args.course_id,
        offline=args.offline,
        max_rows=args.max_rows,
        max_requests=args.max_requests,
    )
    value = report.to_dict()
    rendered = report.to_markdown() if args.markdown else _json(value)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(_json(value), encoding="utf-8")
    print(rendered, end="")
    return int(args.fail_on_findings and not report.passed)


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
