"""Metadata-only synthetic benchmark for the shared assurance contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import AgentReport
from .providers import mock_provider_adapters
from .runner import run_adapters_comparison, run_comparison


@dataclass(frozen=True)
class BenchmarkAgentResult:
    """Public benchmark summary for one synthetic adapter."""

    agent_id: str
    adapter_kind: str
    passed: bool
    scenario_count: int
    trace_count: int
    dimensions: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        """Return status counts without findings, traces, or payloads."""

        return {
            "agent_id": self.agent_id,
            "adapter_kind": self.adapter_kind,
            "passed": self.passed,
            "scenario_count": self.scenario_count,
            "trace_count": self.trace_count,
            "dimensions": [dict(dimension) for dimension in self.dimensions],
        }


@dataclass(frozen=True)
class SyntheticBenchmarkReport:
    """A public, deterministic summary of the synthetic assurance benchmark."""

    benchmark_id: str
    scenario_ids: tuple[str, ...]
    agents: tuple[BenchmarkAgentResult, ...]
    mutation_count: int
    mutations_caught: int
    evaluator_case_count: int
    evaluator_failures_caught: int

    @property
    def gate_passed(self) -> bool:
        """Return whether guarded paths and evaluator controls remain healthy."""

        guarded_results = tuple(
            result.passed
            for result in self.agents
            if result.adapter_kind in {"guarded", "mock-provider"}
        )
        guarded_passed = bool(guarded_results) and all(guarded_results)
        return (
            guarded_passed
            and self.mutation_count == self.mutations_caught
            and self.evaluator_case_count == self.evaluator_failures_caught
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the public report without raw findings or event content."""

        return {
            "benchmark_id": self.benchmark_id,
            "synthetic_only": True,
            "scenario_ids": list(self.scenario_ids),
            "agents": [agent.to_dict() for agent in self.agents],
            "evaluator_controls": {
                "mutation_count": self.mutation_count,
                "mutations_caught": self.mutations_caught,
                "evaluator_case_count": self.evaluator_case_count,
                "evaluator_failures_caught": self.evaluator_failures_caught,
            },
            "gate_passed": self.gate_passed,
        }


def run_synthetic_benchmark() -> SyntheticBenchmarkReport:
    """Run all public synthetic adapters through the shared evaluator."""

    reference = run_comparison(include_mutations=True)
    mocked = run_adapters_comparison(
        mock_provider_adapters("all"),
        include_mutations=False,
    )
    reports = (
        tuple(("reference", report) for report in reference.reports)
        + tuple(("mock-provider", report) for report in mocked.reports)
    )
    return SyntheticBenchmarkReport(
        benchmark_id="synthetic-assurance-v1",
        scenario_ids=tuple(contract.scenario_id for contract in reference.contracts),
        agents=tuple(
            _agent_result(kind, report, reference.scenario_count)
            for kind, report in reports
        ),
        mutation_count=len(reference.mutation_tests),
        mutations_caught=sum(
            mutation.caught and mutation.applied
            for mutation in reference.mutation_tests
        ),
        evaluator_case_count=len(reference.evaluator_validity),
        evaluator_failures_caught=sum(
            result.caught for result in reference.evaluator_validity
        ),
    )


def _agent_result(
    adapter_kind: str,
    report: AgentReport,
    scenario_count: int,
) -> BenchmarkAgentResult:
    return BenchmarkAgentResult(
        agent_id=report.agent_id,
        adapter_kind=adapter_kind,
        passed=report.passed,
        scenario_count=scenario_count,
        trace_count=sum(report.trace_counts.values()),
        dimensions=tuple(
            {
                "dimension": summary.dimension.value,
                "checked": summary.checked,
                "passed": summary.passed,
                "status_counts": dict(summary.status_counts),
            }
            for summary in report.dimension_summaries
        ),
    )
