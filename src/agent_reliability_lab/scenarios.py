"""Synthetic scenarios and deterministic agents.

Each scenario declares an evidence contract and plants one failure that can be observed
from a trace. The cases contain no real customer, candidate, exam, or provider data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .models import (
    EvidenceContract,
    EvidenceRequirement,
    Finding,
    FindingStatus,
    ToolCall,
    Trace,
)


@dataclass(frozen=True)
class Scenario:
    """A small test case with an explicit evidence contract."""

    scenario_id: str
    title: str
    description: str
    contract: EvidenceContract
    run_naive: Callable[[], Trace]
    run_guarded: Callable[[], Trace]
    evaluate: Callable[[Trace, EvidenceContract], Finding]


def _tool_misuse_trace(agent_id: str) -> Trace:
    calls = (
        ToolCall(
            name="lookup_policy",
            arguments={"record_id": "synthetic-policy-404"},
            result_status="not_found",
            result_id="tool-result-001",
        ),
    )
    if agent_id == "naive":
        calls = (
            ToolCall(
                name="lookup_customer",
                arguments={"record_id": "synthetic-policy-404"},
                result_status="ok",
                result_id="tool-result-002",
            ),
        )
    return Trace(
        scenario_id="tool-misuse",
        agent_id=agent_id,
        tool_calls=calls,
        claim="The requested policy was checked.",
        answer=(
            "No policy evidence was found."
            if agent_id == "guarded"
            else "The policy is unavailable."
        ),
        abstained=agent_id == "guarded",
        evidence_ids=(
            ("tool-result-001",) if agent_id == "guarded" else ("tool-result-002",)
        ),
    )


def _false_completion_trace(agent_id: str) -> Trace:
    calls = (
        ToolCall(
            name="check_inventory",
            arguments={"item_id": "synthetic-item-7"},
            result_status="ok",
            result_id="tool-result-003",
        ),
    )
    if agent_id == "guarded":
        calls += (
            ToolCall(
                name="check_shipping",
                arguments={"item_id": "synthetic-item-7"},
                result_status="ok",
                result_id="tool-result-004",
            ),
        )
    return Trace(
        scenario_id="false-completion",
        agent_id=agent_id,
        tool_calls=calls,
        claim="All required checks are complete.",
        answer="The request is ready to proceed.",
        evidence_ids=tuple(call.result_id for call in calls if call.result_id),
    )


def _inappropriate_answer_trace(agent_id: str) -> Trace:
    if agent_id == "naive":
        return Trace(
            scenario_id="inappropriate-answer",
            agent_id=agent_id,
            tool_calls=(),
            claim="The answer is known.",
            answer="The synthetic service supports the requested action.",
            abstained=False,
        )
    return Trace(
        scenario_id="inappropriate-answer",
        agent_id=agent_id,
        tool_calls=(
            ToolCall(
                name="lookup_policy",
                arguments={"record_id": "synthetic-policy-unknown"},
                result_status="not_found",
                result_id="tool-result-005",
            ),
        ),
        claim="Evidence is insufficient.",
        answer=None,
        abstained=True,
        evidence_ids=("tool-result-005",),
    )


def _required_ids(contract: EvidenceContract) -> tuple[str, ...]:
    return tuple(requirement.requirement_id for requirement in contract.requirements)


def _evaluate_tool_misuse(
    trace: Trace, contract: EvidenceContract
) -> Finding:
    expected = "lookup_policy"
    observed = trace.tool_calls[0].name if trace.tool_calls else "no_tool_call"
    required = _required_ids(contract)
    if observed != expected:
        return Finding(
            check_id="correct-tool",
            status=FindingStatus.FAILED,
            message=f"Expected {expected}; observed {observed}.",
            required_evidence=required,
            evidence=("scenario:tool-misuse",),
            missing_evidence=("tool:lookup_policy",),
            does_not_show=(
                "It does not show whether the wrong tool's returned record was itself valid."
            ),
        )
    return Finding(
        check_id="correct-tool",
        status=FindingStatus.COMPLETED,
        message="The agent used the tool named by the scenario contract.",
        required_evidence=required,
        evidence=("scenario:tool-misuse", "tool-result-001"),
        does_not_show=(
            "It does not show that the tool would remain correct against a different schema."
        ),
    )


def _evaluate_false_completion(
    trace: Trace, contract: EvidenceContract
) -> Finding:
    required = _required_ids(contract)
    observed = {call.name for call in trace.tool_calls if call.result_status == "ok"}
    missing = tuple(
        requirement_id
        for requirement_id in required
        if requirement_id.removeprefix("successful_tool:") not in observed
    )
    evidence = tuple(call.result_id for call in trace.tool_calls if call.result_id)
    if missing:
        return Finding(
            check_id="completion-evidence",
            status=FindingStatus.FAILED,
            message=(
                "Completion claim lacks evidence for: "
                + ", ".join(missing)
                + "."
            ),
            required_evidence=required,
            evidence=evidence,
            missing_evidence=missing,
            does_not_show=(
                "It does not show that an absent call failed; it shows only that the "
                "required evidence is missing."
            ),
        )
    return Finding(
        check_id="completion-evidence",
        status=FindingStatus.COMPLETED,
        message="Every required check has an observed successful result.",
        required_evidence=required,
        evidence=evidence,
        does_not_show=(
            "It does not show that the returned records were semantically correct."
        ),
    )


def _evaluate_abstention(
    trace: Trace, contract: EvidenceContract
) -> Finding:
    required = _required_ids(contract)
    lookup_found = any(
        call.name == "lookup_policy" and call.result_status == "not_found"
        for call in trace.tool_calls
    )
    evidence = tuple(call.result_id for call in trace.tool_calls if call.result_id)
    if not lookup_found:
        return Finding(
            check_id="abstain-without-evidence",
            status=FindingStatus.FAILED,
            message=(
                "The agent did not establish that the lookup lacked a usable record."
            ),
            required_evidence=required,
            evidence=evidence,
            missing_evidence=("tool:lookup_policy",),
            does_not_show=(
                "It does not show whether an unobserved data source could have answered "
                "the question."
            ),
        )
    if not trace.abstained:
        return Finding(
            check_id="abstain-without-evidence",
            status=FindingStatus.FAILED,
            message="The agent answered despite having no supporting evidence.",
            required_evidence=required,
            evidence=("scenario:inappropriate-answer",),
            missing_evidence=("abstain:when-no-usable-record",),
            does_not_show=(
                "It does not show whether the answer happened to be true by coincidence."
            ),
        )
    return Finding(
        check_id="abstain-without-evidence",
        status=FindingStatus.COMPLETED,
        message="The agent abstained after the lookup returned no usable record.",
        required_evidence=required,
        evidence=("scenario:inappropriate-answer", "tool-result-005"),
        does_not_show=(
            "It does not show whether the missing record exists in another data source."
        ),
    )


def _tool_misuse_contract() -> EvidenceContract:
    return EvidenceContract(
        scenario_id="tool-misuse",
        requirements=(
            EvidenceRequirement(
                requirement_id="tool:lookup_policy",
                description="Call the policy lookup tool for a policy question.",
                evidence_type="tool_call",
            ),
        ),
    )


def _false_completion_contract() -> EvidenceContract:
    return EvidenceContract(
        scenario_id="false-completion",
        requirements=(
            EvidenceRequirement(
                requirement_id="successful_tool:check_inventory",
                description="Observe a successful inventory check.",
                evidence_type="successful_tool_result",
            ),
            EvidenceRequirement(
                requirement_id="successful_tool:check_shipping",
                description="Observe a successful shipping check.",
                evidence_type="successful_tool_result",
            ),
        ),
    )


def _abstention_contract() -> EvidenceContract:
    return EvidenceContract(
        scenario_id="inappropriate-answer",
        requirements=(
            EvidenceRequirement(
                requirement_id="tool:lookup_policy",
                description="Run the lookup before deciding whether evidence exists.",
                evidence_type="tool_call",
            ),
            EvidenceRequirement(
                requirement_id="abstain:when-no-usable-record",
                description="Refuse to answer when the lookup returns no usable record.",
                evidence_type="agent_behaviour",
            ),
        ),
    )


def scenarios() -> tuple[Scenario, ...]:
    """Return the first milestone's complete synthetic scenario set."""

    return (
        Scenario(
            scenario_id="tool-misuse",
            title="Tool misuse",
            description="A plausible record is returned by the wrong tool.",
            contract=_tool_misuse_contract(),
            run_naive=lambda: _tool_misuse_trace("naive"),
            run_guarded=lambda: _tool_misuse_trace("guarded"),
            evaluate=_evaluate_tool_misuse,
        ),
        Scenario(
            scenario_id="false-completion",
            title="False completion",
            description="The agent claims completion before all required checks ran.",
            contract=_false_completion_contract(),
            run_naive=lambda: _false_completion_trace("naive"),
            run_guarded=lambda: _false_completion_trace("guarded"),
            evaluate=_evaluate_false_completion,
        ),
        Scenario(
            scenario_id="inappropriate-answer",
            title="Answering without evidence",
            description="The agent answers instead of abstaining when evidence is absent.",
            contract=_abstention_contract(),
            run_naive=lambda: _inappropriate_answer_trace("naive"),
            run_guarded=lambda: _inappropriate_answer_trace("guarded"),
            evaluate=_evaluate_abstention,
        ),
    )
