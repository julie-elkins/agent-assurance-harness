"""Evaluate a metadata-only, provenance-aware release promotion decision."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.release_promotion import (
    ReleasePromotionReport,
    evaluate_release_promotion,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify an approved release evidence bundle before promotion "
            "without publishing or deploying it."
        )
    )
    parser.add_argument("--artifact-directory", type=Path, required=True)
    parser.add_argument("--provenance-report", type=Path, required=True)
    parser.add_argument("--release-manifest", type=Path, required=True)
    parser.add_argument("--rollback-report", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--signer-workflow", required=True)
    parser.add_argument("--source-digest", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--approval-id", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-block", action="store_true")
    args = parser.parse_args(argv)

    try:
        report: ReleasePromotionReport = evaluate_release_promotion(
            artifact_directory=args.artifact_directory,
            provenance_path=args.provenance_report,
            release_manifest_path=args.release_manifest,
            rollback_path=args.rollback_report,
            repository=args.repository,
            signer_workflow=args.signer_workflow,
            source_digest=args.source_digest,
            approved_by=args.approved_by,
            approval_id=args.approval_id,
            environment=args.environment,
        )
        data = report.to_dict()
        serialized = (
            report.to_markdown()
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        exit_code = int(args.fail_on_block and not report.passed)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        data = {
            "promotion_version": 1,
            "passed": False,
            "decision": "blocked",
            "refusal": {
                "error": "release_promotion_refused",
                "message": "The release promotion decision could not be evaluated.",
                "guidance": (
                    "Repair the evidence bundle or approval policy before retrying."
                ),
                "source": type(error).__name__,
            },
            "diagnostics": {
                "warnings": [
                    "A refusal is a blocked result, not a passing empty result."
                ],
                "what_it_does_not_show": (
                    "It does not show paths, artifact contents, credentials, "
                    "or deployment state."
                ),
            },
        }
        serialized = (
            "# Release promotion decision\n\n"
            "- **Decision:** BLOCKED\n"
            "- **Reason:** `release-promotion-refused`\n"
        )
        exit_code = 1

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(serialized, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
