"""Records shared by scenarios, agents, and the report.

Design rules:

1. A trace records observable events, not an imagined internal chain of thought.
2. An evidence contract names what must be observed before a claim can pass.
3. A finding states required evidence, observed evidence, missing evidence, and the
   limit of what that evidence proves.
4. Status values distinguish a check that did not run from a check that passed.
5. Records are frozen so later report stages cannot silently rewrite the evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FindingStatus(str, Enum):
    """The outcome of one reliability check."""

    COMPLETED = "completed"
    SKIPPED = "skipped"
    REFUSED = "refused"
    FAILED = "failed"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class EvidenceRequirement:
    """One observable condition required by an evidence contract."""

    requirement_id: str
    description: str
    evidence_type: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-safe contract entry."""

        return {
            "requirement_id": self.requirement_id,
            "description": self.description,
            "evidence_type": self.evidence_type,
        }


@dataclass(frozen=True)
class EvidenceContract:
    """The evidence a scenario requires before its agent claim can pass."""

    scenario_id: str
    requirements: tuple[EvidenceRequirement, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe contract without raw scenario payloads."""

        return {
            "scenario_id": self.scenario_id,
            "requirements": [
                requirement.to_dict() for requirement in self.requirements
            ],
        }


@dataclass(frozen=True)
class ToolCall:
    """An observed tool invocation with synthetic identifiers only."""

    name: str
    arguments: dict[str, str]
    result_status: str
    result_id: str | None = None


@dataclass(frozen=True)
class Trace:
    """The observable record produced by one synthetic agent run."""

    scenario_id: str
    agent_id: str
    tool_calls: tuple[ToolCall, ...] = ()
    claim: str | None = None
    answer: str | None = None
    abstained: bool = False
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Finding:
    """One check result, including what the result cannot establish."""

    check_id: str
    status: FindingStatus
    message: str
    required_evidence: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    does_not_show: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation without raw payloads."""

        return {
            "check_id": self.check_id,
            "status": self.status.value,
            "message": self.message,
            "required_evidence": list(self.required_evidence),
            "evidence": list(self.evidence),
            "missing_evidence": list(self.missing_evidence),
            "what_it_does_not_show": self.does_not_show,
        }


@dataclass(frozen=True)
class AgentReport:
    """The findings for one agent across the selected scenarios."""

    agent_id: str
    findings: tuple[Finding, ...]
    trace_counts: dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Whether no check failed."""

        return not any(finding.status is FindingStatus.FAILED for finding in self.findings)

    def to_dict(self) -> dict[str, Any]:
        """Return a stable report shape suitable for stdout JSON."""

        return {
            "agent_id": self.agent_id,
            "passed": self.passed,
            "trace_counts": dict(self.trace_counts),
            "findings": [finding.to_dict() for finding in self.findings],
        }
