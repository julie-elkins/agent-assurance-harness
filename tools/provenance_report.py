"""Verify signed GitHub Actions release provenance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_lab.provenance import (
    ProvenanceReport,
    run_provenance_verification,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify signed SLSA provenance for release artifacts and emit "
            "metadata-only evidence."
        )
    )
    parser.add_argument("--artifact-directory", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--signer-workflow", required=True)
    parser.add_argument("--source-digest", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args(argv)

    try:
        report: ProvenanceReport = run_provenance_verification(
            args.artifact_directory,
            repository=args.repository,
            signer_workflow=args.signer_workflow,
            source_digest=args.source_digest,
        )
        data = report.to_dict()
        serialized = (
            report.to_markdown()
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        exit_code = int(args.fail_on_findings and not report.passed)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        data = {
            "provenance_version": 1,
            "passed": False,
            "refusal": {
                "error": "provenance_verification_refused",
                "message": "Release provenance could not be verified.",
                "guidance": (
                    "Repair the artifact set or attestation policy before retrying."
                ),
                "source": type(error).__name__,
            },
            "diagnostics": {
                "warnings": [
                    "A refusal is a blocked result, not a passing empty result."
                ],
                "what_it_does_not_show": (
                    "It does not show artifact paths, contents, credentials, "
                    "or attestation bundles."
                ),
            },
        }
        serialized = (
            "## Release provenance verification\n\n"
            "- **Decision:** BLOCKED\n"
            "- **Reason:** `provenance-verification-refused`\n"
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
