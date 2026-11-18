"""Validate a private domain-review workflow's metadata-only manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_reliability_lab.workflow_assurance import (
    evaluate_manifest,
    load_manifest,
)


def _markdown(report: dict[str, object]) -> str:
    lines = [
        "## Review workflow assurance",
        "",
        f"- **Decision:** `{report['decision']}`",
        f"- **Supports human review:** `{str(report['supports_human_review']).lower()}`",
        f"- **Release authorized:** `{str(report['release_authorized']).lower()}`",
        f"- **Blocking reasons:** "
        f"{', '.join(report['blocking_reasons']) or 'none'}",
        f"- **Required action:** {report['required_action']}",
        "",
        "The manifest and result contain metadata only. The harness does not "
        "judge subject-matter correctness or authorize release.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check a metadata-only private review workflow manifest for "
            "completeness and evidence integrity."
        )
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument(
        "--fail-on-blocked",
        action="store_true",
        help="Return exit code 1 when the workflow is blocked.",
    )
    args = parser.parse_args(argv)

    try:
        report = evaluate_manifest(load_manifest(args.manifest))
    except Exception as error:  # noqa: BLE001 - bounded CLI refusal
        report = {
            "decision": "blocked",
            "supports_human_review": False,
            "release_authorized": False,
            "blocking_reasons": ["manifest_input_invalid"],
            "required_action": "Repair the manifest input before retrying.",
            "refusal": {
                "error": "review_workflow_manifest_refused",
                "message": "The manifest could not be loaded.",
                "guidance": type(error).__name__,
            },
        }

    serialized = (
        _markdown(report)
        if args.markdown
        else json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    if args.output is not None:
        args.output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(serialized, end="")
    return int(args.fail_on_blocked and report["decision"] == "blocked")


if __name__ == "__main__":
    sys.exit(main())
