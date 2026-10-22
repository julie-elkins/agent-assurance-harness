"""Apply a metadata-only human disposition manifest to a review packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.public_course_adjudication import (
    PublicCourseAdjudication,
    adjudication_json,
    build_public_course_adjudication,
)


def main(argv: list[str] | None = None) -> int:
    """Run bounded packet adjudication."""

    parser = argparse.ArgumentParser(
        description=(
            "Apply a safe human-disposition manifest to a public-course "
            "review packet."
        )
    )
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-open", action="store_true")
    parser.add_argument("--fail-on-review-required", action="store_true")
    args = parser.parse_args(argv)

    packet, packet_error = _load_object(args.packet)
    decisions, decisions_error = _load_object(args.decisions)
    if packet_error or decisions_error:
        record = PublicCourseAdjudication(
            course_id="unavailable",
            course_revision=None,
            packet_digest=None,
            reviewer_id=None,
            findings=(),
            course_evidence_decision="unavailable",
            refusal_code=packet_error or decisions_error,
        )
    else:
        record = build_public_course_adjudication(packet, decisions)

    serialized = adjudication_json(record)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(record.to_markdown() if args.markdown else serialized, end="")
    if record.refusal_code is not None:
        return 1
    if args.fail_on_open and record.open_count:
        return 1
    if args.fail_on_review_required and (
        record.decision != "adjudicated"
        or record.course_evidence_decision != "verified"
    ):
        return 1
    return 0


def _load_object(path: Path) -> tuple[dict[str, object], str | None]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, "input_load_failed"
    if not isinstance(value, dict):
        return {}, "input_object_required"
    return value, None


if __name__ == "__main__":
    raise SystemExit(main())
