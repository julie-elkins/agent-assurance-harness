"""Import one external evaluator result through the metadata-only contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_reliability_lab.external_evaluator import (
    EXTERNAL_IMPORT_ACCEPTED,
    ExternalEvaluatorImportReport,
    import_external_evaluator_files,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Import an Inspect-, Petri-, or local-shaped evaluator result "
            "without importing content-bearing evidence."
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--current-revisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--safety-case-output", type=Path, required=True)
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument(
        "--fail-on-review",
        action="store_true",
        help="Return non-zero unless the external result is accepted.",
    )
    args = parser.parse_args(argv)

    try:
        report = import_external_evaluator_files(
            args.input,
            args.manifest,
            args.current_revisions,
        )
        _write_json(args.output, report.to_dict())
        if report.safety_case is not None:
            _write_json(args.safety_case_output, report.safety_case.to_dict())
        if args.markdown:
            print(report.to_markdown(), end="")
        else:
            print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return int(
            args.fail_on_review
            and report.import_status != EXTERNAL_IMPORT_ACCEPTED
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        payload = {
            "error": "external_evaluator_import_refused",
            "message": str(error),
            "guidance": (
                "Use the strict synthetic result contract and bind it to the "
                "manifest revision."
            ),
        }
        print(json.dumps(payload, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
