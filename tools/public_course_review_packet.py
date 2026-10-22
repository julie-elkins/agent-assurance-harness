"""Create a metadata-only public-course review packet."""

from __future__ import annotations

import argparse
from pathlib import Path

from agent_reliability_lab.claude_course_adapter import (
    DEFAULT_MAX_REQUESTS,
    DEFAULT_MAX_ROWS,
    run_claude_course_adapter,
)
from agent_reliability_lab.public_course_review import (
    DEFAULT_MAX_FINDINGS,
    build_public_course_review_packet,
    packet_json,
)


def main(argv: list[str] | None = None) -> int:
    """Run the bounded public-course review queue."""

    parser = argparse.ArgumentParser(
        description=(
            "Create a metadata-only worklist from a checked-out public "
            "Claude course."
        )
    )
    parser.add_argument("--course-root", type=Path, required=True)
    parser.add_argument("--course-id", default="claude-architect-lab")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS)
    parser.add_argument(
        "--max-requests",
        type=int,
        default=DEFAULT_MAX_REQUESTS,
    )
    parser.add_argument(
        "--max-findings",
        type=int,
        default=DEFAULT_MAX_FINDINGS,
    )
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args(argv)

    report = run_claude_course_adapter(
        args.course_root,
        course_id=args.course_id,
        offline=args.offline,
        max_rows=args.max_rows,
        max_requests=args.max_requests,
    )
    packet = build_public_course_review_packet(
        report,
        max_findings=args.max_findings,
    )
    serialized = packet_json(packet)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(packet.to_markdown() if args.markdown else serialized, end="")
    return int(args.fail_on_findings and not packet.passed)


if __name__ == "__main__":
    raise SystemExit(main())
