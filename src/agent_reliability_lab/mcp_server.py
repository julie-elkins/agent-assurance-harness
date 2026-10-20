"""Read-only MCP surface for the synthetic assurance contract.

Design rules:

1. Tools expose the evidence contract, not arbitrary code execution or live data access.
2. Inputs and outputs use strict Pydantic models so the served schema is discoverable.
3. Every successful result carries diagnostics and every unsafe or unavailable result
   carries a structured refusal.
4. The server has no write surface, credentials, network calls, or provider dependency.
5. stdio is the only transport in this phase; stdout remains reserved for MCP messages.
"""

from __future__ import annotations

from typing import Annotated

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from .models import (
    AgentReport,
    AssuranceDimension,
    Finding,
    FindingStatus,
    ToolCall,
    Trace,
)
from .packs import (
    ScenarioPack,
    load_builtin_pack_results,
    load_builtin_packs,
)
from .runner import run_comparison
from .scenarios import scenarios


SERVER_VERSION = "0.4.0"
SERVER_INSTRUCTIONS = (
    "Use list_scenario_packs before evaluate_agent_trace when the scenario is unknown. "
    "Submit identifier-only synthetic traces; tool arguments and raw payloads are not "
    "accepted. Read diagnostics and what_it_does_not_show before treating a result as "
    "evidence. This server is read-only, local, credential-free, and synthetic-only."
)

_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    openWorldHint=False,
    title="Read-only synthetic assurance operation",
)


class StrictModel(BaseModel):
    """Reject undeclared fields at the MCP boundary."""

    model_config = ConfigDict(extra="forbid")


class RefusalOutput(StrictModel):
    """A recoverable refusal returned as normal tool data."""

    error: str = Field(description="Stable refusal code; it is not evidence of a clean run.")
    message: str = Field(description="What could not be established and why there is no safe default.")
    guidance: str = Field(description="The cheapest correction the caller should make before retrying.")
    source: str = Field(description="The synthetic or caller-supplied source that was refused.")


class DiagnosticsOutput(StrictModel):
    """Caveats attached to every tool result."""

    source: str = Field(description="Where the result came from.")
    freshness: str = Field(description="How current the result is; static packs are loaded at call time.")
    warnings: list[str] = Field(
        description="Warnings the caller must carry with the result; an empty list is not proof that no caveat exists."
    )
    what_it_does_not_show: str = Field(
        description="The strongest claim this result does not establish."
    )


class EvidenceRequirementOutput(StrictModel):
    """One requirement in a scenario's evidence contract."""

    requirement_id: str
    description: str
    evidence_type: str


class FaultOutput(StrictModel):
    """One named synthetic simulator fault."""

    fault_id: str
    tool_name: str
    mode: str


class ScenarioPackOutput(StrictModel):
    """Public metadata for one validated scenario pack."""

    pack_version: int
    scenario_id: str
    title: str
    description: str
    dimension: str
    available_tools: list[str]
    requirements: list[EvidenceRequirementOutput]
    faults: list[FaultOutput]


class ListScenarioPacksOutput(StrictModel):
    """Result of listing and validating built-in scenario packs."""

    packs: list[ScenarioPackOutput]
    refusals: list[RefusalOutput]
    diagnostics: DiagnosticsOutput


class ToolCallInput(StrictModel):
    """Identifier-only observation of one tool call."""

    name: str = Field(
        min_length=1,
        max_length=128,
        description="Tool name only; raw arguments are deliberately not accepted.",
    )
    result_status: str = Field(
        min_length=1,
        max_length=64,
        description="Short classification such as 'ok' or 'not_found', never a raw tool payload.",
    )
    result_id: str | None = Field(
        default=None,
        max_length=128,
        description="Synthetic result identifier, or null when no identifier was observed.",
    )


class AgentTraceInput(StrictModel):
    """Safe, identifier-only trace submitted for evaluation."""

    scenario_id: str = Field(
        min_length=1,
        max_length=128,
        description="Scenario pack identifier, for example 'tool-misuse'.",
    )
    agent_id: str = Field(
        min_length=1,
        max_length=128,
        description="Caller-assigned agent identifier, not a credential or person identifier.",
    )
    tool_calls: list[ToolCallInput] = Field(
        default_factory=list,
        description=(
            "Identifier-only tool observations, for example "
            '[{"name":"lookup_policy","result_status":"not_found","result_id":"tool-result-001"}]. '
            "Raw arguments and result payloads are not accepted."
        ),
    )
    claim: str | None = Field(
        default=None,
        max_length=512,
        description="Short synthetic claim made by the agent, or null when none was made.",
    )
    answer: str | None = Field(
        default=None,
        max_length=512,
        description="Short synthetic answer, or null when the agent did not answer.",
    )
    abstained: bool = Field(
        description="Whether the agent deliberately refused because evidence was insufficient."
    )
    evidence_ids: list[str] = Field(
        default_factory=list,
        description="Identifier-only evidence references; do not include payload text.",
    )
    side_effects: list[str] = Field(
        default_factory=list,
        description="Synthetic side-effect identifiers observed in the trace.",
    )
    authorization_ids: list[str] = Field(
        default_factory=list,
        description="Synthetic authorization identifiers observed in the trace.",
    )
    tool_output_flags: list[str] = Field(
        default_factory=list,
        description="Classifications such as 'instruction_like', not the output itself.",
    )


class FindingOutput(StrictModel):
    """One evidence-contract finding."""

    check_id: str
    status: str
    message: str
    dimension: str
    required_evidence: list[str]
    evidence: list[str]
    missing_evidence: list[str]
    what_it_does_not_show: str


class EvaluateAgentTraceOutput(StrictModel):
    """Result of evaluating one submitted trace."""

    scenario_id: str
    agent_id: str
    finding: FindingOutput | None = Field(
        default=None,
        description="Finding when the trace was evaluated; null when the request was refused.",
    )
    refusal: RefusalOutput | None = Field(
        default=None,
        description="Structured refusal; null when the trace was evaluated.",
    )
    diagnostics: DiagnosticsOutput


class StatusCountsOutput(StrictModel):
    """Counts for every possible finding status."""

    completed: int
    skipped: int
    refused: int
    failed: int
    not_applicable: int


class DimensionSummaryOutput(StrictModel):
    """One dimension's checked and passed state."""

    dimension: str
    checked: bool
    passed: bool | None = Field(
        description="Null means this dimension was not checked; absence is not a pass."
    )
    status_counts: StatusCountsOutput


class TraceCountOutput(StrictModel):
    """Observed tool-call count for one scenario."""

    scenario_id: str
    count: int


class AgentReportOutput(StrictModel):
    """One agent's complete typed report."""

    agent_id: str
    passed: bool
    trace_counts: list[TraceCountOutput]
    dimensions: list[DimensionSummaryOutput]
    findings: list[FindingOutput]


class EvidenceContractOutput(StrictModel):
    """One scenario contract in a comparison response."""

    scenario_id: str
    requirements: list[EvidenceRequirementOutput]


class MutationOutput(StrictModel):
    """One controlled evidence mutation result."""

    mutation_id: str
    scenario_id: str
    description: str
    applied: bool
    caught: bool
    finding: FindingOutput


class EvaluatorValidityOutput(StrictModel):
    """One weak-versus-robust evaluator validity result."""

    case_id: str
    description: str
    false_pass_detected: bool
    caught: bool
    weak_evaluator: FindingOutput
    robust_evaluator: FindingOutput


class ReferenceComparisonOutput(StrictModel):
    """Typed result of the deterministic reference comparison."""

    scenario_count: int
    contracts: list[EvidenceContractOutput]
    reports: list[AgentReportOutput]
    mutation_tests: list[MutationOutput]
    evaluator_validity: list[EvaluatorValidityOutput]
    refusal: RefusalOutput | None = Field(
        default=None,
        description="Structured refusal; null when the comparison completed.",
    )
    diagnostics: DiagnosticsOutput


def _diagnostics(*, what_it_does_not_show: str) -> DiagnosticsOutput:
    return DiagnosticsOutput(
        source="agent-reliability-lab synthetic scenario packs",
        freshness="Built-in JSON packs were loaded at call time; no external data was read.",
        warnings=[
            "Synthetic contracts distinguish planted failures; they do not establish live-provider reliability."
        ],
        what_it_does_not_show=what_it_does_not_show,
    )


def _refusal(error: str, message: str, guidance: str, source: str) -> RefusalOutput:
    return RefusalOutput(
        error=error,
        message=message,
        guidance=guidance,
        source=source,
    )


def _pack_output(pack: ScenarioPack) -> ScenarioPackOutput:
    return ScenarioPackOutput(
        pack_version=pack.pack_version,
        scenario_id=pack.scenario_id,
        title=pack.title,
        description=pack.description,
        dimension=pack.dimension.value,
        available_tools=list(pack.available_tools),
        requirements=[
            EvidenceRequirementOutput(
                requirement_id=item.requirement_id,
                description=item.description,
                evidence_type=item.evidence_type,
            )
            for item in pack.requirements
        ],
        faults=[
            FaultOutput(
                fault_id=fault.fault_id,
                tool_name=fault.tool_name,
                mode=fault.mode.value,
            )
            for fault in pack.faults
        ],
    )


def _trace_from_input(trace: AgentTraceInput) -> Trace:
    return Trace(
        scenario_id=trace.scenario_id,
        agent_id=trace.agent_id,
        tool_calls=tuple(
            ToolCall(
                name=call.name,
                arguments={},
                result_status=call.result_status,
                result_id=call.result_id,
            )
            for call in trace.tool_calls
        ),
        claim=trace.claim,
        answer=trace.answer,
        abstained=trace.abstained,
        evidence_ids=tuple(trace.evidence_ids),
        side_effects=tuple(trace.side_effects),
        authorization_ids=tuple(trace.authorization_ids),
        tool_output_flags=tuple(trace.tool_output_flags),
    )


def _finding_output(finding: Finding) -> FindingOutput:
    return FindingOutput(
        check_id=finding.check_id,
        status=finding.status.value,
        message=finding.message,
        dimension=finding.dimension.value,
        required_evidence=list(finding.required_evidence),
        evidence=list(finding.evidence),
        missing_evidence=list(finding.missing_evidence),
        what_it_does_not_show=finding.does_not_show,
    )


def _status_counts(report: AgentReport, dimension: AssuranceDimension) -> StatusCountsOutput:
    summary = next(item for item in report.dimension_summaries if item.dimension is dimension)
    return StatusCountsOutput(
        completed=summary.status_counts[FindingStatus.COMPLETED.value],
        skipped=summary.status_counts[FindingStatus.SKIPPED.value],
        refused=summary.status_counts[FindingStatus.REFUSED.value],
        failed=summary.status_counts[FindingStatus.FAILED.value],
        not_applicable=summary.status_counts[FindingStatus.NOT_APPLICABLE.value],
    )


def _agent_report_output(report: AgentReport) -> AgentReportOutput:
    return AgentReportOutput(
        agent_id=report.agent_id,
        passed=report.passed,
        trace_counts=[
            TraceCountOutput(scenario_id=scenario_id, count=count)
            for scenario_id, count in sorted(report.trace_counts.items())
        ],
        dimensions=[
            DimensionSummaryOutput(
                dimension=dimension.value,
                checked=next(
                    item for item in report.dimension_summaries if item.dimension is dimension
                ).checked,
                passed=next(
                    item for item in report.dimension_summaries if item.dimension is dimension
                ).passed,
                status_counts=_status_counts(report, dimension),
            )
            for dimension in AssuranceDimension
        ],
        findings=[_finding_output(finding) for finding in report.findings],
    )


def _comparison_output(include_mutations: bool) -> ReferenceComparisonOutput:
    report = run_comparison(include_mutations=include_mutations)
    return ReferenceComparisonOutput(
        scenario_count=report.scenario_count,
        contracts=[
            EvidenceContractOutput(
                scenario_id=contract.scenario_id,
                requirements=[
                    EvidenceRequirementOutput(
                        requirement_id=item.requirement_id,
                        description=item.description,
                        evidence_type=item.evidence_type,
                    )
                    for item in contract.requirements
                ],
            )
            for contract in report.contracts
        ],
        reports=[_agent_report_output(item) for item in report.reports],
        mutation_tests=[
            MutationOutput(
                mutation_id=item.mutation_id,
                scenario_id=item.scenario_id,
                description=item.description,
                applied=item.applied,
                caught=item.caught,
                finding=_finding_output(item.finding),
            )
            for item in report.mutation_tests
        ],
        evaluator_validity=[
            EvaluatorValidityOutput(
                case_id=item.case_id,
                description=item.description,
                false_pass_detected=item.false_pass_detected,
                caught=item.caught,
                weak_evaluator=_finding_output(item.weak_result),
                robust_evaluator=_finding_output(item.robust_result),
            )
            for item in report.evaluator_validity
        ],
        diagnostics=_diagnostics(
            what_it_does_not_show=(
                "It does not show live-provider behaviour, latency, cost, or reliability "
                "outside the five synthetic scenarios."
            )
        ),
    )


server = MCPServer(
    name="agent-reliability-lab",
    title="Agent Reliability Lab",
    description="Read-only tools for evaluating synthetic agent evidence contracts.",
    version=SERVER_VERSION,
    instructions=SERVER_INSTRUCTIONS,
)


@server.tool(
    name="list_scenario_packs",
    title="List synthetic scenario packs",
    description=(
        "Validate and list the five built-in synthetic scenario packs. Use this first "
        "when you need a scenario_id. The result includes refusals and diagnostics; "
        "an empty pack list is not evidence that all packs are valid."
    ),
    annotations=_READ_ONLY,
    structured_output=True,
)
def list_scenario_packs() -> ListScenarioPacksOutput:
    """List the validated built-in scenario packs."""

    results = load_builtin_pack_results()
    return ListScenarioPacksOutput(
        packs=[_pack_output(result.pack) for result in results if result.pack is not None],
        refusals=[
            RefusalOutput(**result.refusal.to_dict())
            for result in results
            if result.refusal is not None
        ],
        diagnostics=_diagnostics(
            what_it_does_not_show="It does not show that a pack's evaluator is valid against live agent behaviour."
        ),
    )


@server.tool(
    name="evaluate_agent_trace",
    title="Evaluate one synthetic agent trace",
    description=(
        "Evaluate one identifier-only synthetic trace against its named scenario pack. "
        "The trace must contain no raw tool arguments or result payloads; use a shape such "
        "as {'scenario_id':'tool-misuse','agent_id':'candidate','tool_calls':["
        "{'name':'lookup_policy','result_status':'not_found','result_id':'tool-result-001'}],"
        "'abstained':true}. Unknown scenarios and contract mismatches return structured refusals."
    ),
    annotations=_READ_ONLY,
    structured_output=True,
)
def evaluate_agent_trace(
    scenario_id: Annotated[
        str,
        Field(
            min_length=1,
            max_length=128,
            description="Scenario pack identifier, for example 'tool-misuse'.",
        ),
    ],
    trace: Annotated[
        AgentTraceInput,
        Field(
            description=(
                "Identifier-only trace to evaluate; example "
                '{"scenario_id":"tool-misuse","agent_id":"candidate","tool_calls":[],'
                '"abstained":true}. Raw payloads are rejected.'
            )
        ),
    ],
) -> EvaluateAgentTraceOutput:
    """Evaluate one submitted trace without reading external data."""

    if scenario_id != trace.scenario_id:
        return EvaluateAgentTraceOutput(
            scenario_id=scenario_id,
            agent_id=trace.agent_id,
            refusal=_refusal(
                "scenario_id_mismatch",
                "The tool argument and trace scenario_id identify different packs.",
                "Use the same scenario_id in both places before retrying.",
                "caller-supplied trace",
            ),
            diagnostics=_diagnostics(
                what_it_does_not_show="It does not show agent behaviour because the trace was not evaluated."
            ),
        )
    try:
        pack = next(
            (pack for pack in load_builtin_packs() if pack.scenario_id == scenario_id),
            None,
        )
    except RuntimeError as error:
        return EvaluateAgentTraceOutput(
            scenario_id=scenario_id,
            agent_id=trace.agent_id,
            refusal=_refusal(
                "scenario_registry_refused",
                "The built-in scenario registry is invalid, so the trace was not evaluated.",
                "Repair the named pack validation defect before retrying the evaluation.",
                str(error),
            ),
            diagnostics=_diagnostics(
                what_it_does_not_show="It does not show agent behaviour because the scenario registry was unavailable."
            ),
        )
    if pack is None:
        return EvaluateAgentTraceOutput(
            scenario_id=scenario_id,
            agent_id=trace.agent_id,
            refusal=_refusal(
                "unknown_scenario",
                f"No built-in scenario pack is registered for {scenario_id}.",
                "Call list_scenario_packs and use one of its scenario_id values.",
                "caller-supplied trace",
            ),
            diagnostics=_diagnostics(
                what_it_does_not_show="It does not show agent behaviour because no matching contract exists."
            ),
        )
    scenario = next(
        (case for case in scenarios() if case.scenario_id == scenario_id),
        None,
    )
    if scenario is None:
        return EvaluateAgentTraceOutput(
            scenario_id=scenario_id,
            agent_id=trace.agent_id,
            refusal=_refusal(
                "reference_scenario_missing",
                "The pack exists but its Python parity control is missing.",
                "Restore the matching reference scenario before retrying the evaluation.",
                scenario_id,
            ),
            diagnostics=_diagnostics(
                what_it_does_not_show="It does not show agent behaviour because the parity control was unavailable."
            ),
        )
    finding = scenario.evaluate(_trace_from_input(trace), pack.contract)
    return EvaluateAgentTraceOutput(
        scenario_id=scenario_id,
        agent_id=trace.agent_id,
        finding=_finding_output(finding),
        diagnostics=_diagnostics(
            what_it_does_not_show=finding.does_not_show,
        ),
    )


@server.tool(
    name="run_reference_comparison",
    title="Run deterministic reference comparison",
    description=(
        "Run the built-in naive and guarded agents against all five synthetic scenario "
        "packs. Set include_mutations=true to run deliberate evidence-removal checks. "
        "This never launches a caller command, reads a file path, uses credentials, or "
        "contacts a provider."
    ),
    annotations=_READ_ONLY,
    structured_output=True,
)
def run_reference_comparison(
    include_mutations: Annotated[
        bool,
        Field(
            description="Whether to run controlled synthetic evidence mutations in addition to the comparison."
        ),
    ] = False,
) -> ReferenceComparisonOutput:
    """Run the deterministic in-process comparison."""

    try:
        return _comparison_output(include_mutations)
    except RuntimeError as error:
        return ReferenceComparisonOutput(
            scenario_count=0,
            contracts=[],
            reports=[],
            mutation_tests=[],
            evaluator_validity=[],
            refusal=_refusal(
                "reference_comparison_refused",
                "The built-in synthetic scenario packs are not currently valid.",
                "Repair the named pack validation defect before retrying the comparison.",
                str(error),
            ),
            diagnostics=_diagnostics(
                what_it_does_not_show="It does not show any agent behaviour because the comparison did not run."
            ),
        )


def main() -> None:
    """Run the MCP server over stdio."""

    server.run("stdio")


if __name__ == "__main__":
    main()
