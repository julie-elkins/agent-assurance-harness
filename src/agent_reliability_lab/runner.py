"""Offline execution and comparison of synthetic agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapters import reference_adapters
from .environment import environment_for_scenario
from .evaluators import EvaluatorValidityResult, run_evaluator_validity
from .models import (
    AgentReport,
    EvidenceContract,
    Finding,
    FindingStatus,
)
from .mutations import MutationResult, run_mutation_tests
from .protocol import AgentAdapter, ScenarioRequest
from .scenarios import Scenario, scenarios


@dataclass(frozen=True)
class ComparisonReport:
    """A complete comparison between the baseline and guarded agents."""

    reports: tuple[AgentReport, ...]
    scenario_count: int
    contracts: tuple[EvidenceContract, ...]
    mutation_tests: tuple[MutationResult, ...] = ()
    evaluator_validity: tuple[EvaluatorValidityResult, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return the public JSON shape."""

        return {
            "scenario_count": self.scenario_count,
            "contracts": [contract.to_dict() for contract in self.contracts],
            "reports": [report.to_dict() for report in self.reports],
            "mutation_tests": [
                mutation.to_dict() for mutation in self.mutation_tests
            ],
            "evaluator_validity": [
                result.to_dict() for result in self.evaluator_validity
            ],
        }

    def to_markdown(self) -> str:
        """Return a human-readable summary without raw tool payloads."""

        lines = [
            "# Agent Assurance Report",
            "",
            f"Scenarios checked: {self.scenario_count}",
            "",
            "## Agent results",
            "",
            "| Agent | Overall result |",
            "| --- | --- |",
        ]
        for report in self.reports:
            result = "PASS" if report.passed else "FINDINGS"
            lines.append(f"| `{report.agent_id}` | {result} |")
        lines.extend(["", "## Assurance dimensions", ""])
        for report in self.reports:
            lines.extend([f"### `{report.agent_id}`", ""])
            lines.extend(
                [
                    "| Dimension | Checked | Passed | Status counts |",
                    "| --- | --- | --- | --- |",
                ]
            )
            for summary in report.dimension_summaries:
                counts = ", ".join(
                    f"{status}={count}"
                    for status, count in summary.status_counts.items()
                    if count
                ) or "none"
                lines.append(
                    f"| `{summary.dimension.value}` | {summary.checked} | "
                    f"{summary.passed} | {counts} |"
                )
            lines.append("")
        lines.extend(["## Evaluator validity", ""])
        for result in self.evaluator_validity:
            outcome = "CAUGHT" if result.caught else "MISSED"
            lines.append(
                f"- `{result.case_id}`: {outcome}; "
                f"false pass detected={result.false_pass_detected}"
            )
        return "\n".join(lines)


def _run_agent(
    adapter: AgentAdapter, scenario_cases: tuple[Scenario, ...]
) -> AgentReport:
    findings = []
    trace_counts = {}
    for scenario in scenario_cases:
        request = ScenarioRequest(
            scenario_id=scenario.scenario_id,
            task_label=scenario.title,
            available_tools=scenario.available_tools,
            contract=scenario.contract,
        )
        run = adapter.run(
            request,
            environment=environment_for_scenario(scenario.scenario_id),
        )
        if run.refusal is not None:
            finding = Finding(
                check_id="adapter-run",
                status=FindingStatus.REFUSED,
                message=run.refusal.message,
                dimension=scenario.dimension,
                required_evidence=tuple(
                    requirement.requirement_id
                    for requirement in scenario.contract.requirements
                ),
                missing_evidence=tuple(
                    requirement.requirement_id
                    for requirement in scenario.contract.requirements
                ),
                does_not_show="It does not show how the agent would behave because no valid trace was returned.",
            )
            trace_counts[scenario.scenario_id] = 0
            findings.append(finding)
            continue
        trace = run.trace
        if trace is None:
            raise RuntimeError("Validated adapter returned neither a trace nor a refusal.")
        trace_counts[scenario.scenario_id] = len(trace.tool_calls)
        finding = scenario.evaluate(trace, scenario.contract)
        findings.append(finding)
    return AgentReport(
        agent_id=adapter.agent_id,
        findings=tuple(findings),
        trace_counts=trace_counts,
    )


def run_comparison(include_mutations: bool = False) -> ComparisonReport:
    """Run both deterministic agents over every registered scenario."""

    scenario_cases = scenarios()
    adapters = reference_adapters()
    return ComparisonReport(
        reports=(
            _run_agent(adapters[0], scenario_cases),
            _run_agent(adapters[1], scenario_cases),
        ),
        scenario_count=len(scenario_cases),
        contracts=tuple(case.contract for case in scenario_cases),
        mutation_tests=run_mutation_tests() if include_mutations else (),
        evaluator_validity=run_evaluator_validity(),
    )


def failed_checks(report: ComparisonReport) -> int:
    """Count failed checks across both agents."""

    return sum(
        finding.status is FindingStatus.FAILED
        for agent_report in report.reports
        for finding in agent_report.findings
    )
