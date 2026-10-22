"""Create a metadata-only public-course change plan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.public_course_change_plan import (
    PublicCourseChangePlan,
    build_public_course_change_plan,
    change_plan_json,
)


def main(argv: list[str] | None = None) -> int:
    """Run the bounded change-plan generator."""

    parser = argparse.ArgumentParser(
        description=(
            "Create a metadata-only change proposal from an adjudicated "
            "public-course review."
        )
    )
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--adjudication", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-block", action="store_true")
    args = parser.parse_args(argv)

    packet, packet_error = _load_object(args.packet)
    adjudication, adjudication_error = _load_object(args.adjudication)
    if packet_error or adjudication_error:
        plan = PublicCourseChangePlan(
            course_id="unavailable",
            course_revision=None,
            packet_digest=None,
            adjudication_decision="unavailable",
            course_evidence_decision="unavailable",
            items=(),
            refusal_code=packet_error or adjudication_error,
        )
    else:
        plan = build_public_course_change_plan(packet, adjudication)

    serialized = change_plan_json(plan)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(plan.to_markdown() if args.markdown else serialized, end="")
    if args.fail_on_block and plan.decision == "blocked":
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
