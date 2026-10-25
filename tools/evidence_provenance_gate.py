"""Verify metadata-only provenance for one run-manifest evidence record."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_reliability_lab.evidence_provenance import (
    EVIDENCE_PROVENANCE_OBSERVED,
    evaluate_evidence_provenance,
)
from agent_reliability_lab.run_manifest import load_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check whether a producer recorded an observed metadata-only "
            "evidence artifact for one run manifest."
        )
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Return non-zero unless an observed artifact is bound to the manifest.",
    )
    args = parser.parse_args(argv)
    write_output = True

    try:
        manifest = load_manifest(str(args.manifest))
        provenance = _read_object(args.provenance)
        decision = evaluate_evidence_provenance(manifest, provenance)
        data = decision.to_dict()
        serialized = (
            _markdown(data)
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        exit_code = int(
            decision.status == "blocked"
            or (
                args.fail_on_missing
                and decision.status != EVIDENCE_PROVENANCE_OBSERVED
            )
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        data = {
            "status": "blocked",
            "supports_evidence": False,
            "reasons": ["provenance_input_invalid"],
            "required_action": "Repair the manifest and provenance inputs before retrying.",
            "refusal": {
                "error": "evidence_provenance_refused",
                "message": "The evidence provenance gate could not be completed.",
                "source": type(error).__name__,
            },
        }
        serialized = (
            _markdown(data)
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        exit_code = 1
        write_output = False

    if args.output is not None and write_output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(serialized, end="")
    return exit_code


def _read_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return value


def _markdown(data: dict[str, object]) -> str:
    lines = [
        "## Evidence provenance gate",
        "",
        f"- **Decision:** `{str(data.get('status', 'blocked')).upper()}`",
        f"- **Supports evidence:** `{str(data.get('supports_evidence', False)).lower()}`",
        f"- **Reasons:** {', '.join(data.get('reasons', [])) or 'none'}",
        f"- **Required action:** {data.get('required_action', 'Repair the inputs before retrying.')}",
        "",
        "This gate checks metadata-only producer provenance; it does not inspect the evidence artifact.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
