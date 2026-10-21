"""Run the metadata-only Course Doctor review workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.course_doctor import (
    DEFAULT_MAX_REVIEW_COURSES,
    CourseDoctorCoordinator,
    load_local_course_manifest,
    run_reference_course_doctor_suite,
)


def main(argv: list[str] | None = None) -> int:
    """Run synthetic reference cases or an explicitly supplied local manifest."""

    parser = argparse.ArgumentParser(
        description=(
            "Generate bounded metadata-only course review packets. "
            "Without --manifest, run the public synthetic suite."
        )
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument(
        "--max-courses",
        type=int,
        default=DEFAULT_MAX_REVIEW_COURSES,
    )
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--max-elapsed-seconds", type=float, default=30.0)
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args(argv)

    if args.manifest is None:
        suite = run_reference_course_doctor_suite(
            workspace=args.workspace,
            max_courses=args.max_courses,
            max_workers=args.max_workers,
            max_elapsed_seconds=args.max_elapsed_seconds,
        )
        output_value = suite.to_dict()
        rendered = suite.to_markdown() if args.markdown else _json(output_value)
        passed = suite.passed
    else:
        if args.source_root is None:
            parser.error("--source-root is required with --manifest")
        try:
            requests = load_local_course_manifest(
                args.manifest,
                source_root=args.source_root,
            )
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            output_value = {
                "course_doctor_version": 1,
                "passed": False,
                "packets": [],
                "counts": {
                    "requested": 0,
                    "packets_emitted": 0,
                    "completed": 0,
                    "failed": 0,
                    "timed_out": 0,
                    "not_reviewed": 0,
                    "truncated": False,
                    "counts_reconcile": True,
                },
                "refusal_code": "manifest_invalid",
                "diagnostics": {
                    "warnings": [
                        "The manifest was refused before source review; "
                        "source content was not included in the error."
                    ],
                    "what_it_does_not_show": (
                        "It does not identify which source record failed."
                    ),
                },
            }
            rendered = _json(output_value)
            passed = False
        else:
            report = CourseDoctorCoordinator().review(
                requests,
                workspace=args.workspace,
                max_courses=args.max_courses,
                max_workers=args.max_workers,
                max_elapsed_seconds=args.max_elapsed_seconds,
            )
            output_value = report.to_dict()
            rendered = report.to_markdown() if args.markdown else _json(output_value)
            passed = report.passed

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(_json(output_value), encoding="utf-8")
    print(rendered, end="")
    return int(args.fail_on_findings and not passed)


def _json(value: dict[str, object]) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
