"""Verify a public-course change plan against a later adapter report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.public_course_post_change import (
    PublicCoursePostChangeVerification,
    build_public_course_post_change_verification,
    post_change_json,
)


def main(argv: list[str] | None = None) -> int:
    """Run bounded post-change verification."""

    parser = argparse.ArgumentParser(
        description=(
            "Compare a metadata-only public-course change plan with a later "
            "adapter report."
        )
    )
    parser.add_argument("--change-plan", type=Path, required=True)
    parser.add_argument("--post-report", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-block", action="store_true")
    args = parser.parse_args(argv)

    change_plan, plan_error = _load_object(args.change_plan)
    post_report, report_error = _load_object(args.post_report)
    if plan_error or report_error:
        verification = PublicCoursePostChangeVerification(
            course_id="unavailable",
            before_revision=None,
            after_revision=None,
            plan_digest=None,
            after_decision="unavailable",
            after_counts={},
            targets=(),
            new_blocking_findings=(),
            refusal_code=plan_error or report_error,
        )
    else:
        verification = build_public_course_post_change_verification(
            change_plan,
            post_report,
        )

    serialized = post_change_json(verification)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(
        verification.to_markdown()
        if args.markdown
        else serialized,
        end="",
    )
    if args.fail_on_block and verification.decision == "blocked":
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
