"""Run the synthetic monitorability and evaluator-validity workbench.

The tool accepts only identifier-only case metadata and emits bounded metrics,
reauthorization state, and a human-review safety case. It never runs a model or
publishes a provider trace.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_reliability_lab.monitorability import (
    MONITORABILITY_READY,
    MonitorabilityInputError,
    build_monitorability_report,
    force_monitor_miss,
    load_monitorability_fixture,
)
from agent_reliability_lab.run_manifest import (
    RunManifestValidationError,
    load_current_revisions,
    load_manifest,
)
from agent_reliability_lab.safety_case import build_safety_case


def _write_json(path: Path | None, value: object) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate synthetic monitorability and evaluator validity, then "
            "emit a metadata-only safety case."
        )
    )
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--current-revisions", type=Path, required=True)
    parser.add_argument("--decision-target", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--safety-case-output", type=Path, required=True)
    parser.add_argument(
        "--negative-control-output",
        type=Path,
        help="Optional output for a synthetic held-out monitor-miss report.",
    )
    parser.add_argument(
        "--fail-on-review",
        action="store_true",
        help="Return non-zero unless the main report is ready for human review.",
    )
    args = parser.parse_args(argv)

    try:
        fixture = load_monitorability_fixture(args.cases)
        manifest = load_manifest(str(args.manifest))
        current_revisions = load_current_revisions(
            str(args.current_revisions)
        )
        report = build_monitorability_report(
            fixture,
            manifest,
            current_revisions,
        )
        safety_case = build_safety_case(
            report,
            decision_target=args.decision_target,
        )
        negative_report = None
        if args.negative_control_output is not None:
            negative_fixture = force_monitor_miss(fixture)
            negative_report = build_monitorability_report(
                negative_fixture,
                manifest,
                current_revisions,
            )
            _write_json(
                args.negative_control_output,
                negative_report.to_dict(),
            )
        _write_json(args.output, report.to_dict())
        _write_json(args.safety_case_output, safety_case.to_dict())
        payload = {
            "monitorability_report": report.to_dict(),
            "safety_case": safety_case.to_dict(),
        }
        if negative_report is not None:
            payload["negative_control"] = negative_report.to_dict()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return int(args.fail_on_review and report.status != MONITORABILITY_READY)
    except (
        OSError,
        json.JSONDecodeError,
        MonitorabilityInputError,
        RunManifestValidationError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {
                    "error": "monitorability_workbench_refused",
                    "message": str(error),
                    "guidance": (
                        "Use the checked-in synthetic case pack, complete manifest, "
                        "and revision map."
                    ),
                },
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
