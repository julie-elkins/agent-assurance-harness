"""Run the short, offline Agent Assurance Harness showcase.

The showcase combines the core synthetic assurance comparison with one
metadata-only Course Doctor review packet. It is intentionally offline and
does not read credentials, call a provider, or fetch documentation.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from agent_reliability_lab.course_doctor import (
    CourseDoctorCoordinator,
    describe_finding_reason,
    load_local_course_manifest,
    run_reference_course_doctor_suite,
)
from agent_reliability_lab.enablement_pack import (
    run_reference_launch_to_field_suite,
)
from agent_reliability_lab.runner import run_comparison


ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = ROOT / "examples" / "course-doctor-demo"


def main(argv: list[str] | None = None) -> int:
    """Run the offline showcase and return a process status."""

    parser = argparse.ArgumentParser(
        description="Run the offline Agent Assurance Harness showcase."
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Render a short reviewer-facing Markdown summary.",
    )
    args = parser.parse_args(argv)

    comparison = run_comparison(include_mutations=True)
    enablement_report = run_reference_launch_to_field_suite()
    with tempfile.TemporaryDirectory(prefix="agent-assurance-showcase-") as path:
        requests = load_local_course_manifest(
            DEMO_ROOT / "manifest.json",
            source_root=DEMO_ROOT,
        )
        course_report = CourseDoctorCoordinator().review(
            requests,
            workspace=Path(path),
            max_courses=1,
            max_workers=1,
            max_elapsed_seconds=10.0,
        )
        control_suite = run_reference_course_doctor_suite(
            workspace=Path(path) / "synthetic-controls",
        )

    guarded = next(
        report for report in comparison.reports if report.agent_id == "guarded"
    )
    example_packet = next(
        packet
        for packet in control_suite.report.packets
        if packet.course_id == "course-pipeline-stale-source"
    )
    example_finding = example_packet.findings[0]
    example_locator = example_finding.locators[0]
    summary = {
        "showcase_version": 3,
        "offline": True,
        "synthetic_assurance": {
            "scenario_count": comparison.scenario_count,
            "guarded_agent_passed": guarded.passed,
            "evaluator_controls_caught": [
                result.case_id
                for result in comparison.evaluator_validity
                if result.caught
            ],
            "mutation_controls_caught": [
                result.mutation_id
                for result in comparison.mutation_tests
                if result.caught
            ],
        },
        "course_doctor": {
            "passed": course_report.passed,
            "counts": course_report.counts,
            "packets": [
                {
                    "course_id": packet.course_id,
                    "course_revision": packet.course_revision,
                    "worker_status": packet.worker_status.value,
                    "recommended_disposition": packet.recommended_disposition.value,
                    "finding_count": len(packet.findings),
                }
                for packet in course_report.packets
            ],
        },
        "launch_to_field": {
            "passed": enablement_report.passed,
            "controls_caught": list(enablement_report.controls_caught),
            "degraded_controls_caught": [
                case_id
                for case_id in enablement_report.controls_caught
                if case_id != "launch-pack-ready"
            ],
            "controls_missed": list(enablement_report.controls_missed),
            "ready_case": next(
                report.to_dict()
                for case_id, report in enablement_report.reports
                if case_id == "launch-pack-ready"
            ),
        },
        "synthetic_finding_example": {
            "course_id": example_packet.course_id,
            "what_needs_attention": describe_finding_reason(
                example_finding.reason_code
            ),
            "reason_code": example_finding.reason_code,
            "claim_id": example_locator.claim_id,
            "section_id": example_locator.section_id,
            "evidence_id": example_locator.evidence_id,
            "source_id": example_locator.source_id,
            "observed_age_seconds": example_locator.age_seconds,
            "allowed_age_seconds": example_locator.max_age_seconds,
        },
        "diagnostics": {
            "warnings": [
                "The showcase uses synthetic source bytes and no provider credentials.",
                "Course Doctor recommendations are not human approval or publication authority.",
            ],
            "what_it_does_not_show": (
                "It does not establish live-model quality, semantic truth, "
                "deployment health, or production monitoring."
            ),
        },
    }
    if args.markdown:
        print(_markdown(summary), end="")
    else:
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if _passed(summary) else 1


def _passed(summary: dict[str, object]) -> bool:
    """Return whether both showcase paths completed and controls were caught."""

    synthetic = summary["synthetic_assurance"]
    course = summary["course_doctor"]
    enablement = summary["launch_to_field"]
    if (
        not isinstance(synthetic, dict)
        or not isinstance(course, dict)
        or not isinstance(enablement, dict)
    ):
        return False
    return (
        synthetic["guarded_agent_passed"] is True
        and bool(synthetic["evaluator_controls_caught"])
        and bool(synthetic["mutation_controls_caught"])
        and course["passed"] is True
        and enablement["passed"] is True
        and bool(enablement["controls_caught"])
        and enablement["controls_missed"] == []
    )


def _markdown(summary: dict[str, object]) -> str:
    """Render only the safe showcase summary."""

    synthetic = summary["synthetic_assurance"]
    course = summary["course_doctor"]
    enablement = summary["launch_to_field"]
    example = summary["synthetic_finding_example"]
    if (
        not isinstance(synthetic, dict)
        or not isinstance(course, dict)
        or not isinstance(enablement, dict)
        or not isinstance(example, dict)
    ):
        raise ValueError("showcase summary has an invalid internal shape")
    lines = [
        "# Agent Assurance Harness Showcase",
        "",
        "## Offline assurance",
        "",
        f"- Scenarios checked: `{synthetic['scenario_count']}`",
        f"- Guarded agent: `{'PASS' if synthetic['guarded_agent_passed'] else 'BLOCKED'}`",
        f"- Evaluator controls caught: `{len(synthetic['evaluator_controls_caught'])}`",
        f"- Mutation controls caught: `{len(synthetic['mutation_controls_caught'])}`",
        "",
        "## Course Doctor",
        "",
        f"- Review packets passed: `{'PASS' if course['passed'] else 'BLOCKED'}`",
        f"- Packet counts: `{json.dumps(course['counts'], sort_keys=True)}`",
        "",
        "## Example blocked finding (synthetic)",
        "",
        f"- Course: `{example['course_id']}`",
        f"- What needs attention: {example['what_needs_attention']}",
        f"- Claim: `{example['claim_id']}`",
        f"- Section: `{example['section_id']}`",
        f"- Evidence: `{example['evidence_id']}`",
        f"- Source: `{example['source_id']}`",
        f"- Freshness: `{example['observed_age_seconds']}` seconds observed; "
        f"`{example['allowed_age_seconds']}` seconds allowed",
        "",
        "This example is deliberately blocked to prove the harness can identify "
        "where a review must start. It contains no lesson text or source path.",
        "",
        "## Launch-to-field enablement",
        "",
        f"- Ready pack: `{'PASS' if enablement['passed'] else 'BLOCKED'}`",
        f"- Degraded controls caught: `{len(enablement['degraded_controls_caught'])}`",
        "- Pack includes: `demo`, `lab`, `quick_reference`, and synthetic feedback signals",
        "",
        "The ready pack still requires human approval before publication. Its degraded "
        "controls demonstrate stale, wrong-source, unsupported-claim, and incomplete-pack "
        "behavior.",
        "",
        "This demo is synthetic, offline, and metadata-only.",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
