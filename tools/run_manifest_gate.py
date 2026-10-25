"""Evaluate a portable run manifest against current dependency revisions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_reliability_lab.run_manifest import (
    RUN_MANIFEST_STATUS_REAUTHORIZED,
    evaluate_reauthorization,
    load_current_revisions,
    load_manifest,
)


def _markdown(data: dict[str, object]) -> str:
    status = str(data["status"]).upper()
    lines = [
        "## Run manifest gate",
        "",
        f"- **Decision:** `{status}`",
        f"- **Supports target decision:** `{str(data['supports_decision']).lower()}`",
        f"- **Changed dependencies:** {', '.join(data['changed_dependencies']) or 'none'}",
        f"- **Reasons:** {', '.join(data['reasons']) or 'none'}",
        f"- **Required action:** {data['required_action']}",
        "",
        "The manifest contains metadata and digests only; it does not prove live model quality.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check whether an agent run's evidence remains valid against "
            "current model, harness, tool, policy, data, and grader revisions."
        )
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--current-revisions", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument(
        "--fail-on-non-reauthorized",
        action="store_true",
        help="Return exit code 1 unless the evidence remains reauthorized.",
    )
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(str(args.manifest))
        current_revisions = load_current_revisions(str(args.current_revisions))
        decision = evaluate_reauthorization(manifest, current_revisions)
        data = decision.to_dict()
        serialized = (
            _markdown(data)
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        exit_code = int(
            args.fail_on_non_reauthorized
            and decision.status != RUN_MANIFEST_STATUS_REAUTHORIZED
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        data = {
            "status": "blocked",
            "supports_decision": False,
            "changed_dependencies": [],
            "reasons": ["manifest_input_invalid"],
            "required_action": "Repair the manifest inputs before retrying.",
            "refusal": {
                "error": "run_manifest_refused",
                "message": "The run manifest gate could not be completed.",
                "guidance": (
                    "Provide a versioned metadata-only manifest and a complete "
                    "current revision map."
                ),
                "source": type(error).__name__,
            },
        }
        serialized = (
            _markdown(data)
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
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
