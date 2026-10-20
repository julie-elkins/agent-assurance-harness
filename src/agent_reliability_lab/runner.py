"""Offline execution and comparison of synthetic agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import AgentReport, EvidenceContract, FindingStatus
from .mutations import MutationResult, run_mutation_tests
from .scenarios import scenarios


@dataclass(frozen=True)
class ComparisonReport:
    """A complete comparison between the baseline and guarded agents."""

    reports: tuple[AgentReport, ...]
    scenario_count: int
    contracts: tuple[EvidenceContract, ...]
    mutation_tests: tuple[MutationResult, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return the public JSON shape."""

        return {
            "scenario_count": self.scenario_count,
            "contracts": [contract.to_dict() for contract in self.contracts],
            "reports": [report.to_dict() for report in self.reports],
            "mutation_tests": [
                mutation.to_dict() for mutation in self.mutation_tests
            ],
        }


def _run_agent(agent_id: str, scenario_cases: tuple) -> AgentReport:
    findings = []
    trace_counts = {}
    for scenario in scenario_cases:
        trace = scenario.run_naive() if agent_id == "naive" else scenario.run_guarded()
        trace_counts[scenario.scenario_id] = len(trace.tool_calls)
        finding = scenario.evaluate(trace, scenario.contract)
        findings.append(finding)
    return AgentReport(agent_id=agent_id, findings=tuple(findings), trace_counts=trace_counts)


def run_comparison(include_mutations: bool = False) -> ComparisonReport:
    """Run both deterministic agents over every first-milestone scenario."""

    scenario_cases = scenarios()
    return ComparisonReport(
        reports=(
            _run_agent("naive", scenario_cases),
            _run_agent("guarded", scenario_cases),
        ),
        scenario_count=len(scenario_cases),
        contracts=tuple(case.contract for case in scenario_cases),
        mutation_tests=run_mutation_tests() if include_mutations else (),
    )


def failed_checks(report: ComparisonReport) -> int:
    """Count failed checks across both agents."""

    return sum(
        finding.status is FindingStatus.FAILED
        for agent_report in report.reports
        for finding in agent_report.findings
    )
