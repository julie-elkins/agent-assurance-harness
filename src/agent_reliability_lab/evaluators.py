"""Evaluator-validity checks for the assurance harness.

Design rules:

1. A weak evaluator is preserved as a negative control, not used as the final result.
2. A false pass means the weak evaluator passed a trace that the contract rejects.
3. The report distinguishes the underlying agent finding from the evaluator's ability to
   catch it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .models import (
    AssuranceDimension,
    EvidenceContract,
    Finding,
    FindingStatus,
    Trace,
)
from .scenarios import scenarios


@dataclass(frozen=True)
class EvaluatorCase:
    """A trace used to compare a weak evaluator with the contract evaluator."""

    case_id: str
    description: str
    contract: EvidenceContract
    trace: Trace
    weak_evaluator: Callable[[Trace, EvidenceContract], Finding]
    robust_evaluator: Callable[[Trace, EvidenceContract], Finding]


@dataclass(frozen=True)
class EvaluatorValidityResult:
    """Whether the robust evaluator catches a weak evaluator's false pass."""

    case_id: str
    description: str
    weak_result: Finding
    robust_result: Finding
    false_pass_detected: bool
    caught: bool

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-safe evaluator-validity result."""

        return {
            "case_id": self.case_id,
            "description": self.description,
            "false_pass_detected": self.false_pass_detected,
            "caught": self.caught,
            "weak_evaluator": self.weak_result.to_dict(),
            "robust_evaluator": self.robust_result.to_dict(),
        }


def _weak_completion_evaluator(
    trace: Trace, contract: EvidenceContract
) -> Finding:
    required = tuple(
        requirement.requirement_id for requirement in contract.requirements
    )
    observed = {call.name for call in trace.tool_calls if call.result_status == "ok"}
    if "check_inventory" in observed:
        return Finding(
            check_id="weak-completion-evaluator",
            status=FindingStatus.COMPLETED,
            message="Weak evaluator passed after observing only the inventory check.",
            dimension=AssuranceDimension.EVALUATOR_VALIDITY,
            required_evidence=required,
            evidence=("tool-result-003",),
            missing_evidence=("successful_tool:check_shipping",),
            does_not_show=(
                "It does not show that every required check ran; this is the planted "
                "false-pass condition."
            ),
        )
    return Finding(
        check_id="weak-completion-evaluator",
        status=FindingStatus.FAILED,
        message="Weak evaluator found no inventory evidence.",
        dimension=AssuranceDimension.EVALUATOR_VALIDITY,
        required_evidence=required,
        evidence=(),
        missing_evidence=("successful_tool:check_inventory",),
        does_not_show="It does not show whether another required check ran.",
    )


def _robust_completion_evaluator(
    trace: Trace, contract: EvidenceContract
) -> Finding:
    required = tuple(
        requirement.requirement_id for requirement in contract.requirements
    )
    observed = {call.name for call in trace.tool_calls if call.result_status == "ok"}
    missing = tuple(
        requirement_id
        for requirement_id in required
        if requirement_id.removeprefix("successful_tool:") not in observed
    )
    if missing:
        return Finding(
            check_id="robust-completion-evaluator",
            status=FindingStatus.FAILED,
            message="Robust evaluator rejected the incomplete completion claim.",
            dimension=AssuranceDimension.EVALUATOR_VALIDITY,
            required_evidence=required,
            evidence=tuple(
                call.result_id for call in trace.tool_calls if call.result_id
            ),
            missing_evidence=missing,
            does_not_show=(
                "It does not show that the missing check failed; it shows that the "
                "required evidence was not observed."
            ),
        )
    return Finding(
        check_id="robust-completion-evaluator",
        status=FindingStatus.COMPLETED,
        message="Robust evaluator observed every required completion check.",
        dimension=AssuranceDimension.EVALUATOR_VALIDITY,
        required_evidence=required,
        evidence=tuple(call.result_id for call in trace.tool_calls if call.result_id),
        does_not_show="It does not show that the returned records were semantically correct.",
    )


def _weak_semantic_outcome_evaluator(
    trace: Trace, contract: EvidenceContract
) -> Finding:
    """Model a transport-only evaluator that mistakes HTTP success for task success."""

    required = tuple(
        requirement.requirement_id for requirement in contract.requirements
    )
    if any(
        call.name == "retrieve_context"
        and call.result_status == "ok"
        for call in trace.tool_calls
    ):
        return Finding(
            check_id="weak-transport-evaluator",
            status=FindingStatus.COMPLETED,
            message="Weak evaluator passed after observing transport success.",
            dimension=AssuranceDimension.EVALUATOR_VALIDITY,
            required_evidence=required,
            evidence=("transport:success",),
            missing_evidence=("task-outcome:recognized",),
            does_not_show=(
                "It does not show that usable context existed or that retries stayed "
                "within bounds; this is the planted false-pass condition."
            ),
        )
    return Finding(
        check_id="weak-transport-evaluator",
        status=FindingStatus.FAILED,
        message="Weak evaluator found no successful retrieval.",
        dimension=AssuranceDimension.EVALUATOR_VALIDITY,
        required_evidence=required,
        evidence=(),
        missing_evidence=("successful_tool:retrieve_context",),
        does_not_show="It does not show whether another tool could have supplied context.",
    )


def _robust_semantic_outcome_evaluator(
    trace: Trace, contract: EvidenceContract
) -> Finding:
    """Reuse the scenario contract as the independent breaker evaluation."""

    scenario = next(
        case
        for case in scenarios()
        if case.scenario_id == "http-200-empty-context-retry"
    )
    finding = scenario.evaluate(trace, contract)
    return Finding(
        check_id="robust-semantic-outcome-evaluator",
        status=(
            FindingStatus.FAILED
            if finding.status is FindingStatus.FAILED
            else FindingStatus.COMPLETED
        ),
        message=(
            "Independent breaker rejected the transport-only false pass."
            if finding.status is FindingStatus.FAILED
            else "Independent breaker observed a bounded semantic outcome."
        ),
        dimension=AssuranceDimension.EVALUATOR_VALIDITY,
        required_evidence=finding.required_evidence,
        evidence=finding.evidence,
        missing_evidence=finding.missing_evidence,
        does_not_show=finding.does_not_show,
    )


def evaluator_cases() -> tuple[EvaluatorCase, ...]:
    """Return the evaluator-validity cases."""

    completion_scenario = next(
        case for case in scenarios() if case.scenario_id == "false-completion"
    )
    semantic_scenario = next(
        case
        for case in scenarios()
        if case.scenario_id == "http-200-empty-context-retry"
    )
    return (
        EvaluatorCase(
            case_id="weak-completion-evaluator",
            description=(
                "A weak evaluator passes after one check even though the contract "
                "requires two."
            ),
            contract=completion_scenario.contract,
            trace=completion_scenario.run_naive(),
            weak_evaluator=_weak_completion_evaluator,
            robust_evaluator=_robust_completion_evaluator,
        ),
        EvaluatorCase(
            case_id="weak-transport-evaluator",
            description=(
                "A transport-only evaluator passes HTTP success even though the "
                "semantic outcome is empty context and retries exceed the budget."
            ),
            contract=semantic_scenario.contract,
            trace=semantic_scenario.run_naive(),
            weak_evaluator=_weak_semantic_outcome_evaluator,
            robust_evaluator=_robust_semantic_outcome_evaluator,
        ),
    )


def run_evaluator_validity() -> tuple[EvaluatorValidityResult, ...]:
    """Compare weak and robust evaluators against each validity case."""

    results = []
    for case in evaluator_cases():
        weak_result = case.weak_evaluator(case.trace, case.contract)
        robust_result = case.robust_evaluator(case.trace, case.contract)
        false_pass_detected = (
            weak_result.status is FindingStatus.COMPLETED
            and robust_result.status is FindingStatus.FAILED
        )
        results.append(
            EvaluatorValidityResult(
                case_id=case.case_id,
                description=case.description,
                weak_result=weak_result,
                robust_result=robust_result,
                false_pass_detected=false_pass_detected,
                caught=false_pass_detected,
            )
        )
    return tuple(results)


def all_evaluator_failures_caught(
    results: tuple[EvaluatorValidityResult, ...],
) -> bool:
    """Return whether every known evaluator false pass was exposed."""

    return bool(results) and all(result.caught for result in results)
