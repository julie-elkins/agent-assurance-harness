"""Run the Muse Ember evidence-gate demonstration.

The default path is offline and deterministic. The optional live path sends one
built-in synthetic scenario to Muse Ember and evaluates the returned identifier-only
events through the same evidence contract as the offline controls.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from agent_reliability_lab.live import LiveProviderPolicy, live_provider_adapter
from agent_reliability_lab.providers import ProviderLimits
from agent_reliability_lab.runner import (
    failed_checks,
    run_adapter_scenario,
    run_comparison,
)


DEFAULT_SCENARIO_ID = "unauthorized-side-effect"
DEFAULT_MODEL = "muse-ember-1.0"


def main(argv: list[str] | None = None) -> int:
    """Run the offline demo and, when requested, one bounded live scenario."""

    parser = argparse.ArgumentParser(
        description="Run the Muse Ember evidence-gate demonstration."
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json",
        action="store_true",
        help="Emit the metadata-only result as JSON.",
    )
    output_group.add_argument(
        "--markdown",
        action="store_true",
        help="Emit a short reviewer-facing Markdown summary.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Opt in to one bounded Muse Ember request after the offline controls.",
    )
    parser.add_argument("--scenario-id", default=DEFAULT_SCENARIO_ID)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="Required with --live; permits the one local synthetic request.",
    )
    parser.add_argument("--max-requests", type=int)
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--max-elapsed-seconds", type=float)
    parser.add_argument("--max-estimated-cost-usd", type=float)
    parser.add_argument("--estimated-cost-usd-per-request", type=float)
    args = parser.parse_args(argv)

    comparison = run_comparison(include_mutations=True)
    summary: dict[str, Any] = {
        "demo_version": 1,
        "offline": _offline_summary(comparison),
        "live": None,
        "controls": {
            "metadata_only": True,
            "synthetic_inputs_only": True,
            "raw_provider_output_retained": False,
            "network_called": False,
        },
    }

    if args.live:
        missing = [
            name
            for name, value in {
                "--max-requests": args.max_requests,
                "--max-output-tokens": args.max_output_tokens,
                "--max-elapsed-seconds": args.max_elapsed_seconds,
                "--max-estimated-cost-usd": args.max_estimated_cost_usd,
                "--estimated-cost-usd-per-request": (
                    args.estimated_cost_usd_per_request
                ),
            }.items()
            if value is None
        ]
        if missing:
            print(
                "--live requires explicit usage ceilings: "
                + ", ".join(missing)
                + ".",
                file=sys.stderr,
            )
            return 2
        policy = LiveProviderPolicy(
            provider_id="muse-ember",
            model=args.model,
            credential_env_var="MODEL_API_KEY",
            limits=ProviderLimits(
                max_requests=args.max_requests,
                max_output_tokens=args.max_output_tokens,
                max_elapsed_seconds=args.max_elapsed_seconds,
                max_estimated_cost_usd=args.max_estimated_cost_usd,
            ),
            estimated_cost_usd_per_request=args.estimated_cost_usd_per_request,
            allow_network=args.allow_network,
        )
        try:
            live_report = run_adapter_scenario(
                live_provider_adapter(policy),
                args.scenario_id,
            )
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 2
        summary["live"] = _live_summary(live_report, args.scenario_id)
        summary["controls"]["network_called"] = True

    if args.markdown:
        print(_markdown(summary), end="")
    else:
        print(json.dumps(summary, indent=2, sort_keys=True))

    return 1 if _has_findings(summary) else 0


def _offline_summary(comparison) -> dict[str, Any]:
    """Reduce the offline comparison to the proof points a reviewer needs."""

    reports = {report.agent_id: report for report in comparison.reports}
    return {
        "scenarios_checked": comparison.scenario_count,
        "guarded_agent_passed": reports["guarded"].passed,
        "unsafe_control_findings": sum(
            finding.status.value != "passed"
            for finding in reports["naive"].findings
        ),
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
    }


def _live_summary(report, scenario_id: str) -> dict[str, Any]:
    """Return live metadata without provider text or raw trace payloads."""

    agent_report = report.reports[0]
    return {
        "provider": "muse-ember",
        "scenario_id": scenario_id,
        "agent_id": agent_report.agent_id,
        "passed": agent_report.passed,
        "finding_statuses": [
            {
                "check_id": finding.check_id,
                "status": finding.status.value,
            }
            for finding in agent_report.findings
        ],
        "finding_messages": [
            finding.message for finding in agent_report.findings
        ],
        "execution_budgets": {
            scenario: budget.to_dict()
            for scenario, budget in agent_report.execution_budgets.items()
        },
        "failed_checks": failed_checks(report),
    }


def _has_findings(summary: dict[str, Any]) -> bool:
    """Return whether the demo found an assurance failure."""

    offline = summary["offline"]
    if not offline["guarded_agent_passed"]:
        return True
    if not offline["evaluator_controls_caught"] or not offline["mutation_controls_caught"]:
        return True
    live = summary["live"]
    return live is not None and live["failed_checks"] > 0


def _markdown(summary: dict[str, Any]) -> str:
    """Render the short judge-facing demonstration summary."""

    offline = summary["offline"]
    lines = [
        "# Muse Ember Evidence Gate",
        "",
        "## Offline proof",
        "",
        f"- Synthetic scenarios checked: `{offline['scenarios_checked']}`",
        f"- Guarded path: `{'PASS' if offline['guarded_agent_passed'] else 'BLOCKED'}`",
        f"- Unsafe-control findings: `{offline['unsafe_control_findings']}`",
        f"- Evaluator negative controls caught: `{len(offline['evaluator_controls_caught'])}`",
        f"- Mutation negative controls caught: `{len(offline['mutation_controls_caught'])}`",
        "",
        "The gate accepts the guarded path because its required evidence is present "
        "and catches deliberately unsafe or weakened evaluator paths.",
        "",
    ]
    live = summary["live"]
    if live is None:
        lines.extend(
            [
                "## Live Muse Ember path",
                "",
                "Not run. Add `--live`, `MODEL_API_KEY`, and explicit usage ceilings "
                "for one local synthetic request.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Live Muse Ember path",
                "",
                f"- Scenario: `{live['scenario_id']}`",
                f"- Adapter result: `{'PASS' if live['passed'] else 'FINDINGS'}`",
                f"- Failed checks: `{live['failed_checks']}`",
                f"- Budget records: `{len(live['execution_budgets'])}`",
                "",
            ]
        )
        for message in live["finding_messages"]:
            lines.insert(
                -1,
                f"- Diagnostic: {message}",
            )
    lines.extend(
        [
            "## Boundary",
            "",
            "- Synthetic inputs only",
            "- One request maximum when live",
            "- No retries",
            "- Metadata-only output; provider text and credentials are not reported",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
