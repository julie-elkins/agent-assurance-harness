"""Validate a metadata-only human reauthorization record."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent_reliability_lab.reauthorization_record import (
    ReauthorizationRecord,
    canonical_digest,
    load_reauthorization_record,
    validate_reauthorization,
)


def _now(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--now must include a timezone")
    return parsed.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate whether a human reauthorization decision is reusable for "
            "one exact bounded rerun result."
        )
    )
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--rerun-result", type=Path, required=True)
    parser.add_argument(
        "--now",
        help="Validation time as an ISO-8601 timestamp; defaults to current UTC.",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument(
        "--fail-on-nonreusable",
        action="store_true",
        help="Return non-zero unless the validated status is reauthorized.",
    )
    args = parser.parse_args(argv)

    try:
        record = load_reauthorization_record(args.record)
        with open(args.rerun_result, encoding="utf-8") as handle:
            rerun_result = json.load(handle)
        validation = validate_reauthorization(
            record,
            rerun_result,
            now=_now(args.now),
        )
        data = validation.to_dict()
        serialized = (
            validation.to_markdown()
            if args.markdown
            else json.dumps(data, indent=2, sort_keys=True) + "\n"
        )
        exit_code = int(args.fail_on_nonreusable and not validation.reusable)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        data = {
            "reauthorization_validation_version": 1,
            "status": "refused",
            "decision": "unknown",
            "reusable": False,
            "decision_target": "unknown",
            "evidence_ids": [],
            "rerun_result_digest": (
                canonical_digest({"input_error": type(error).__name__})
            ),
            "reason_codes": ["reauthorization_input_invalid", type(error).__name__],
            "required_action": "Repair the record or rerun-result artifact before retrying.",
            "claim_boundary": (
                "This validation did not accept the input artifacts and does not "
                "authorize deployment."
            ),
        }
        serialized = (
            "# Reauthorization validation\n\n"
            "- **Status:** `refused`\n"
            "- **Required action:** Repair the record or rerun-result artifact before retrying.\n"
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
