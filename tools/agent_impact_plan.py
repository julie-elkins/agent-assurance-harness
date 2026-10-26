"""Generate a metadata-only agent change-impact plan."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from agent_reliability_lab.change_impact import (
    IMPACT_READY,
    build_change_impact_plan,
)
from agent_reliability_lab.evidence_registry import load_evidence_registry
from agent_reliability_lab.provider_receipt import (
    ProviderEvidenceReceipt,
    load_provider_evidence_receipt_report,
)
from agent_reliability_lab.run_manifest import (
    RunManifestValidationError,
    load_current_revisions,
    load_manifest,
)


def _git_paths(repo: Path, base: str, head: str) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "-C", str(repo), "diff", "--name-only", base, head],
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Plan the smallest evidence rerun after agent code or revision changes."
        )
    )
    parser.add_argument("--baseline-revisions", type=Path, required=True)
    parser.add_argument("--current-revisions", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument(
        "--registry",
        type=Path,
        help="Optional metadata-only evidence registry for selective rerun checks.",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        action="append",
        default=[],
        help="Optional provider evidence receipt report; repeat for more reports.",
    )
    parser.add_argument("--changed-path", action="append", default=[])
    parser.add_argument("--git-diff-base")
    parser.add_argument("--git-diff-head", default="HEAD")
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the structured plan as JSON (the default output format).",
    )
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--fail-on-rerun", action="store_true")
    args = parser.parse_args(argv)

    try:
        paths = list(args.changed_path)
        if args.git_diff_base:
            paths.extend(_git_paths(args.repo, args.git_diff_base, args.git_diff_head))
        receipts: dict[str, list[ProviderEvidenceReceipt]] | None = None
        if args.receipt:
            receipts = {}
            for receipt_path in args.receipt:
                report = load_provider_evidence_receipt_report(str(receipt_path))
                for receipt in report.receipts:
                    receipts.setdefault(receipt.evidence_id, []).append(receipt)
        plan = build_change_impact_plan(
            [load_manifest(str(path)) for path in args.manifest],
            load_current_revisions(str(args.baseline_revisions)),
            load_current_revisions(str(args.current_revisions)),
            paths,
            load_evidence_registry(args.registry) if args.registry else None,
            receipts,
        )
        data = plan.to_dict()
        serialized = (
            plan.to_markdown()
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        exit_code = int(args.fail_on_rerun and plan.status != IMPACT_READY)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        data = {
            "change_impact_version": 1,
            "status": "blocked",
            "failed": True,
            "changed_paths": [],
            "path_classifications": {},
            "changed_dependencies": [],
            "evidence": [],
            "required_action": "Repair the impact-plan inputs before retrying.",
            "refusal": {
                "error": "change_impact_input_invalid",
                "message": "The change-impact plan could not be completed.",
                "source": type(error).__name__,
            },
        }
        serialized = (
            json.dumps(data, indent=2, sort_keys=True) + "\n"
            if not args.markdown
            else "## Agent change-impact plan\n\n- **Decision:** `BLOCKED`\n"
            "- **Required action:** Repair the impact-plan inputs before retrying.\n"
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
    sys.exit(main())
