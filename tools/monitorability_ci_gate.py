"""Run the blocking CI contract for the monitorability workbench.

The gate proves three things in one offline run:

1. the checked-in synthetic report is ready for human review;
2. the deliberate held-out monitor miss is detected; and
3. a changed revision requires reauthorization.

It writes only the bounded reports and safety case to the caller-selected directory.
It never runs a model, calls a provider, or exports content-bearing evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_reliability_lab.monitorability import (
    MONITORABILITY_READY,
    MONITORABILITY_REVIEW,
    build_monitorability_report,
    force_monitor_miss,
    load_monitorability_fixture,
)
from agent_reliability_lab.run_manifest import (
    load_current_revisions,
    load_manifest,
)
from agent_reliability_lab.safety_case import build_safety_case


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _markdown(summary: dict[str, object]) -> str:
    reasons = summary["reasons"]
    lines = [
        "## Monitorability CI gate",
        "",
        f"- **Decision:** `{summary['status']}`",
        f"- **Positive report:** `{summary['positive_status']}`",
        f"- **Negative control:** `{summary['negative_control_status']}`",
        f"- **Changed revision:** `{summary['changed_revision_status']}`",
        f"- **Safety case:** `{summary['safety_case_status']}`",
        "",
        "### Reasons",
        "",
    ]
    lines.extend(f"- `{reason}`" for reason in reasons or ["none"])
    lines.extend(
        [
            "",
            "This gate uses synthetic identifiers, labels, counts, rates, and revision "
            "metadata only. It does not prove live-provider safety.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the offline monitorability positive path and its "
            "negative/revision controls."
        )
    )
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--current-revisions", type=Path, required=True)
    parser.add_argument("--changed-revisions", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)

    try:
        fixture = load_monitorability_fixture(args.cases)
        manifest = load_manifest(str(args.manifest))
        current_revisions = load_current_revisions(
            str(args.current_revisions)
        )
        changed_revisions = load_current_revisions(
            str(args.changed_revisions)
        )
        positive = build_monitorability_report(
            fixture,
            manifest,
            current_revisions,
        )
        negative = build_monitorability_report(
            force_monitor_miss(fixture),
            manifest,
            current_revisions,
        )
        changed = build_monitorability_report(
            fixture,
            manifest,
            changed_revisions,
        )
        safety_case = build_safety_case(
            positive,
            decision_target=manifest.decision_target,
        )
        reasons: list[str] = []
        if positive.status != MONITORABILITY_READY:
            reasons.append("positive_report_not_ready")
        if negative.status != MONITORABILITY_REVIEW:
            reasons.append("negative_control_not_detected")
        if "held_out_monitor_recall_below_threshold" not in negative.reasons:
            reasons.append("negative_control_reason_missing")
        if changed.status != MONITORABILITY_REVIEW:
            reasons.append("changed_revision_not_review_required")
        if "reauthorization:reauthorization_required" not in changed.reasons:
            reasons.append("changed_revision_reason_missing")
        if safety_case.required_human_review is not True:
            reasons.append("human_review_boundary_missing")
        status = "passed" if not reasons else "blocked"
        summary = {
            "monitorability_ci_gate_version": 1,
            "status": status,
            "positive_status": positive.status,
            "negative_control_status": negative.status,
            "changed_revision_status": changed.status,
            "safety_case_status": safety_case.status,
            "reasons": reasons,
        }
        args.output_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            args.output_dir / "monitorability-positive.json",
            positive.to_dict(),
        )
        _write_json(
            args.output_dir / "monitorability-negative-control.json",
            negative.to_dict(),
        )
        _write_json(
            args.output_dir / "monitorability-changed-revisions.json",
            changed.to_dict(),
        )
        _write_json(
            args.output_dir / "monitorability-safety-case.json",
            safety_case.to_dict(),
        )
        _write_json(args.output_dir / "monitorability-ci-summary.json", summary)
        if args.markdown:
            print(_markdown(summary), end="")
        else:
            print(json.dumps(summary, indent=2, sort_keys=True))
        return int(status != "passed")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        payload = {
            "monitorability_ci_gate_version": 1,
            "status": "blocked",
            "reasons": ["input_refused"],
            "message": str(error),
        }
        print(
            _markdown(payload)
            if args.markdown
            else json.dumps(payload, indent=2, sort_keys=True)
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
