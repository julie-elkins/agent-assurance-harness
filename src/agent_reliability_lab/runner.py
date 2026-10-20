"""Offline execution and comparison of synthetic agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .adapters import reference_adapters
from .evaluators import EvaluatorValidityResult, run_evaluator_validity
from .models import (
    AgentReport,
    EvidenceContract,
    Finding,
    FindingStatus,
)
from .mutations import MutationResult, run_mutation_tests
from .packs import ScenarioPack, build_environment_from_pack, load_builtin_packs
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
    adapter: AgentAdapter,
    scenario_cases: tuple[Scenario, ...],
    scenario_packs: dict[str, ScenarioPack],
) -> AgentReport:
    findings = []
    trace_counts = {}
    for scenario in scenario_cases:
        pack = scenario_packs[scenario.scenario_id]
        request = ScenarioRequest(
            scenario_id=pack.scenario_id,
            task_label=pack.title,
            available_tools=pack.available_tools,
            contract=pack.contract,
        )
        run = adapter.run(
            request,
            environment=build_environment_from_pack(pack),
        )
        if run.refusal is not None:
            finding = Finding(
                check_id="adapter-run",
                status=FindingStatus.REFUSED,
                message=run.refusal.message,
                dimension=scenario.dimension,
                required_evidence=tuple(
                    requirement.requirement_id
                    for requirement in pack.requirements
                ),
                missing_evidence=tuple(
                    requirement.requirement_id
                    for requirement in pack.requirements
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
        finding = scenario.evaluate(trace, pack.contract)
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
    scenario_packs = load_builtin_packs()
    return _build_comparison(
        adapters,
        scenario_cases,
        scenario_packs,
        include_mutations=include_mutations,
    )


def run_adapter_comparison(
    adapter: AgentAdapter,
    *,
    include_mutations: bool = False,
) -> ComparisonReport:
    """Run one external adapter through the same assurance report shape."""

    return _build_comparison(
        (adapter,),
        scenarios(),
        load_builtin_packs(),
        include_mutations=include_mutations,
    )


def run_adapters_comparison(
    adapters: tuple[AgentAdapter, ...],
    *,
    include_mutations: bool = False,
) -> ComparisonReport:
    """Run several provider adapters through one shared assurance report."""

    return _build_comparison(
        adapters,
        scenarios(),
        load_builtin_packs(),
        include_mutations=include_mutations,
    )


def _build_comparison(
    adapters: tuple[AgentAdapter, ...],
    scenario_cases: tuple[Scenario, ...],
    scenario_packs: tuple[ScenarioPack, ...],
    *,
    include_mutations: bool,
) -> ComparisonReport:
    packs_by_id = {pack.scenario_id: pack for pack in scenario_packs}
    if set(packs_by_id) != {scenario.scenario_id for scenario in scenario_cases}:
        raise RuntimeError("Scenario packs and reference scenarios are out of sync.")
    return ComparisonReport(
        reports=tuple(
            _run_agent(adapter, scenario_cases, packs_by_id)
            for adapter in adapters
        ),
        scenario_count=len(scenario_cases),
        contracts=tuple(
            packs_by_id[case.scenario_id].contract for case in scenario_cases
        ),
        mutation_tests=run_mutation_tests() if include_mutations else (),
        evaluator_validity=run_evaluator_validity(),
    )


def failed_checks(report: ComparisonReport) -> int:
    """Count failed checks across both agents."""

    return sum(
        finding.status in {FindingStatus.FAILED, FindingStatus.REFUSED}
        for agent_report in report.reports
        for finding in agent_report.findings
    )
