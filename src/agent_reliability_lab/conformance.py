"""Conformance summaries for external JSONL adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import AgentReport, FindingStatus
from .protocol import AgentAdapter
from .packs import ScenarioPack
from .pack_provenance import pack_manifest
from .runner import run_adapter_comparison, run_pack_comparison


@dataclass(frozen=True)
class AdapterConformanceReport:
    """A metadata-only result for one external adapter."""

    agent_id: str
    scenario_count: int
    passed: bool
    trace_count: int
    refusal_count: int
    dimensions: tuple[dict[str, Any], ...]
    mutation_count: int
    mutations_caught: int

    @property
    def conformance_passed(self) -> bool:
        """Return whether the adapter and evaluator controls both passed."""

        return (
            self.passed
            and self.mutation_count > 0
            and self.mutation_count == self.mutations_caught
        )

    def to_dict(self) -> dict[str, object]:
        """Return counts without findings, messages, commands, or traces."""

        return {
            "report_version": 1,
            "conformance_id": "adapter-conformance-v1",
            "agent_id": self.agent_id,
            "scenario_count": self.scenario_count,
            "passed": self.passed,
            "conformance_passed": self.conformance_passed,
            "trace_count": self.trace_count,
            "refusal_count": self.refusal_count,
            "dimensions": [dict(dimension) for dimension in self.dimensions],
            "mutation_controls": {
                "mutation_count": self.mutation_count,
                "mutations_caught": self.mutations_caught,
            },
        }


@dataclass(frozen=True)
class CustomPackConformanceReport:
    """A metadata-only conformance result for caller-supplied packs."""

    agent_id: str
    pack_ids: tuple[str, ...]
    passed: bool
    trace_count: int
    refusal_count: int
    dimensions: tuple[dict[str, Any], ...]
    pack_manifests: tuple[dict[str, object], ...]

    def to_dict(self) -> dict[str, object]:
        """Return counts without custom pack text, findings, or traces."""

        return {
            "report_version": 2,
            "conformance_id": "custom-pack-conformance-v2",
            "agent_id": self.agent_id,
            "pack_ids": list(self.pack_ids),
            "pack_count": len(self.pack_ids),
            "passed": self.passed,
            "trace_count": self.trace_count,
            "refusal_count": self.refusal_count,
            "dimensions": [dict(dimension) for dimension in self.dimensions],
            "pack_manifests": [dict(manifest) for manifest in self.pack_manifests],
        }


def run_adapter_conformance(adapter: AgentAdapter) -> AdapterConformanceReport:
    """Run one external adapter through all scenarios and mutation controls."""

    comparison = run_adapter_comparison(adapter, include_mutations=True)
    if len(comparison.reports) != 1:
        raise RuntimeError("Conformance requires exactly one adapter report.")
    report = comparison.reports[0]
    return _summary(
        report,
        scenario_count=comparison.scenario_count,
        mutation_count=len(comparison.mutation_tests),
        mutations_caught=sum(
            mutation.applied and mutation.caught
            for mutation in comparison.mutation_tests
        ),
    )


def run_custom_pack_conformance(
    adapter: AgentAdapter,
    packs: tuple[ScenarioPack, ...],
) -> CustomPackConformanceReport:
    """Run one adapter against validated caller-supplied declarative packs."""

    if not packs:
        raise ValueError("Custom pack conformance requires at least one pack.")
    report = run_pack_comparison(adapter, packs)
    return CustomPackConformanceReport(
        agent_id=report.agent_id,
        pack_ids=tuple(pack.scenario_id for pack in packs),
        passed=report.passed,
        trace_count=sum(report.trace_counts.values()),
        refusal_count=sum(
            finding.status is FindingStatus.REFUSED for finding in report.findings
        ),
        dimensions=tuple(
            {
                "dimension": summary.dimension.value,
                "checked": summary.checked,
                "passed": summary.passed,
                "status_counts": dict(summary.status_counts),
            }
            for summary in report.dimension_summaries
        ),
        pack_manifests=tuple(
            pack_manifest(pack).to_dict()
            for pack in packs
        ),
    )


def _summary(
    report: AgentReport,
    *,
    scenario_count: int,
    mutation_count: int,
    mutations_caught: int,
) -> AdapterConformanceReport:
    return AdapterConformanceReport(
        agent_id=report.agent_id,
        scenario_count=scenario_count,
        passed=report.passed,
        trace_count=sum(report.trace_counts.values()),
        refusal_count=sum(
            finding.status is FindingStatus.REFUSED
            for finding in report.findings
        ),
        dimensions=tuple(
            {
                "dimension": summary.dimension.value,
                "checked": summary.checked,
                "passed": summary.passed,
                "status_counts": dict(summary.status_counts),
            }
            for summary in report.dimension_summaries
        ),
        mutation_count=mutation_count,
        mutations_caught=mutations_caught,
    )
