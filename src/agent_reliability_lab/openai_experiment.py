"""Local-only OpenAI experiments over the synthetic assurance harness."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

from .live import HttpTransport, LiveProviderPolicy
from .openai_tool_loop import (
    MAX_OPENAI_TOOL_LOOP_TURNS,
    openai_tool_loop_adapter,
)
from .pack_evaluator import evaluate_pack_trace
from .packs import (
    ScenarioPack,
    build_environment_from_pack,
    load_builtin_packs,
    request_from_pack,
)
from .providers import ProviderLimits


OPENAI_PROVIDER_ID = "openai"
OPENAI_DEFAULT_MODEL = "gpt-5.6"
SMOKE_CASE_COUNT = 10
MIN_PILOT_CASE_COUNT = 20
MAX_PILOT_CASE_COUNT = 30
DEFAULT_TOTAL_COST_CEILING_USD = 5.0
DEFAULT_ESTIMATED_COST_PER_REQUEST_USD = 0.05
DEFAULT_OUTPUT_TOKEN_CEILING = 512
DEFAULT_ELAPSED_SECONDS = 60.0


@dataclass(frozen=True)
class OpenAIExperimentPolicy:
    """Explicit controls for one bounded local OpenAI experiment."""

    model: str
    case_count: int
    max_total_cost_usd: float = DEFAULT_TOTAL_COST_CEILING_USD
    estimated_cost_usd_per_request: float = (
        DEFAULT_ESTIMATED_COST_PER_REQUEST_USD
    )
    max_output_tokens: int = DEFAULT_OUTPUT_TOKEN_CEILING
    max_elapsed_seconds: float = DEFAULT_ELAPSED_SECONDS
    allow_network: bool = False
    structured_output: bool = False

    @property
    def mode(self) -> str:
        """Return the selected bounded run mode."""

        return "smoke" if self.case_count == SMOKE_CASE_COUNT else "pilot"

    @property
    def output_condition(self) -> str:
        """Return the controlled response-format condition."""

        return (
            "provider_structured_output"
            if self.structured_output
            else "prompt_and_local_validation"
        )

    def validate(self) -> str | None:
        """Return a refusal message when the experiment is not safely bounded."""

        if not self.model or any(character.isspace() for character in self.model):
            return "model must be a non-empty identifier without whitespace."
        if self.case_count == SMOKE_CASE_COUNT:
            pass
        elif MIN_PILOT_CASE_COUNT <= self.case_count <= MAX_PILOT_CASE_COUNT:
            pass
        else:
            return (
                "case_count must be 10 for smoke or between 20 and 30 for pilot."
            )
        if self.max_total_cost_usd <= 0:
            return "max_total_cost_usd must be greater than zero."
        if self.estimated_cost_usd_per_request <= 0:
            return "estimated_cost_usd_per_request must be greater than zero."
        if (
            self.case_count
            * MAX_OPENAI_TOOL_LOOP_TURNS
            * self.estimated_cost_usd_per_request
            > self.max_total_cost_usd
        ):
            return (
                "The planned case count and three-turn ceiling exceed the aggregate spend ceiling; "
                "lower the per-request estimate or raise the total ceiling deliberately."
            )
        if self.max_output_tokens < 16:
            return "max_output_tokens must be at least 16."
        if self.max_elapsed_seconds <= 0:
            return "max_elapsed_seconds must be greater than zero."
        if not self.allow_network:
            return (
                "Live execution requires explicit local network opt-in; "
                "pass --allow-network for an intentional run."
            )
        return None


@dataclass(frozen=True)
class OpenAICaseResult:
    """Metadata-only result for one synthetic scenario execution."""

    case_id: str
    scenario_id: str
    replicate: int
    status: str
    finding_status: str | None = None
    refusal_error: str | None = None
    refusal_guidance: str | None = None
    refusal_stage: str | None = None
    execution_budget: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a report-safe case record."""

        result: dict[str, object] = {
            "case_id": self.case_id,
            "scenario_id": self.scenario_id,
            "replicate": self.replicate,
            "status": self.status,
        }
        if self.finding_status is not None:
            result["finding_status"] = self.finding_status
        if self.refusal_error is not None:
            result["refusal_error"] = self.refusal_error
        if self.refusal_guidance is not None:
            result["refusal_guidance"] = self.refusal_guidance
        if self.refusal_stage is not None:
            result["refusal_stage"] = self.refusal_stage
        if self.execution_budget is not None:
            result["execution_budget"] = self.execution_budget
        return result


@dataclass(frozen=True)
class OpenAIExperimentReport:
    """Metadata-only report for a bounded local OpenAI experiment."""

    provider_id: str
    model: str
    mode: str
    output_condition: str
    requested_case_count: int
    attempted_case_count: int
    completed_case_count: int
    refused_case_count: int
    total_estimated_cost_usd: float
    max_total_cost_usd: float
    cases: tuple[OpenAICaseResult, ...] = ()
    refusal_error: str | None = None
    refusal_message: str | None = None

    @property
    def within_total_cost_limit(self) -> bool:
        """Return whether the metadata-only estimate stayed within the cap."""

        return self.total_estimated_cost_usd <= self.max_total_cost_usd

    @property
    def decision(self) -> str:
        """Return the bounded experiment outcome."""

        if self.refusal_error is not None:
            return "refused"
        if not self.within_total_cost_limit:
            return "refused"
        if self.refused_case_count:
            return "incomplete"
        return "complete"

    def to_dict(self) -> dict[str, object]:
        """Return JSON-safe metadata without prompts or provider responses."""

        result: dict[str, object] = {
            "provider_id": self.provider_id,
            "model": self.model,
            "mode": self.mode,
            "output_condition": self.output_condition,
            "requested_case_count": self.requested_case_count,
            "attempted_case_count": self.attempted_case_count,
            "completed_case_count": self.completed_case_count,
            "refused_case_count": self.refused_case_count,
            "estimated_cost": {
                "total_usd": round(self.total_estimated_cost_usd, 6),
                "max_total_usd": self.max_total_cost_usd,
                "within_limit": self.within_total_cost_limit,
                "note": (
                    "Planning estimate only; provider billing is not asserted "
                    "by this report."
                ),
            },
            "decision": self.decision,
            "cases": [case.to_dict() for case in self.cases],
        }
        if self.refusal_error is not None:
            result["refusal"] = {
                "error": self.refusal_error,
                "message": self.refusal_message,
            }
        return result

    def to_markdown(self) -> str:
        """Return a reviewer-readable metadata summary."""

        lines = [
            "# Local OpenAI Synthetic Experiment",
            "",
            f"- Provider: `{self.provider_id}`",
            f"- Model: `{self.model}`",
            f"- Mode: `{self.mode}`",
            f"- Output condition: `{self.output_condition}`",
            f"- Decision: **{self.decision.upper()}**",
            f"- Cases attempted: `{self.attempted_case_count}` / "
            f"`{self.requested_case_count}`",
            f"- Cases completed: `{self.completed_case_count}`",
            f"- Cases refused: `{self.refused_case_count}`",
            f"- Estimated spend: `${self.total_estimated_cost_usd:.4f}` / "
            f"`${self.max_total_cost_usd:.2f}`",
            "",
            "The run sends built-in synthetic identifiers only and retains "
            "metadata, statuses, and usage ceilings—not prompts or model responses.",
            "",
            "## Cases",
            "",
            "| Case | Scenario | Replicate | Status | Finding | Refusal | Stage | Guidance |",
            "| --- | --- | ---: | --- | --- | --- | --- | --- |",
        ]
        for case in self.cases:
            lines.append(
                f"| `{case.case_id}` | `{case.scenario_id}` | {case.replicate} | "
                f"{case.status} | {case.finding_status or '—'} | "
                f"{case.refusal_error or '—'} | {case.refusal_stage or '—'} | "
                f"{case.refusal_guidance or '—'} |"
            )
        if self.refusal_error is not None:
            lines.extend(
                [
                    "",
                    "## Refusal",
                    "",
                    f"- `{self.refusal_error}`: {self.refusal_message}",
                ]
            )
        return "\n".join(lines)


def run_openai_experiment(
    policy: OpenAIExperimentPolicy,
    *,
    transport: HttpTransport | None = None,
) -> OpenAIExperimentReport:
    """Run a bounded OpenAI experiment over built-in synthetic packs."""

    refusal = policy.validate()
    if refusal is not None:
        return OpenAIExperimentReport(
            provider_id=OPENAI_PROVIDER_ID,
            model=policy.model,
            mode=policy.mode,
            output_condition=policy.output_condition,
            requested_case_count=policy.case_count,
            attempted_case_count=0,
            completed_case_count=0,
            refused_case_count=0,
            total_estimated_cost_usd=0.0,
            max_total_cost_usd=policy.max_total_cost_usd,
            refusal_error="experiment_policy_refused",
            refusal_message=refusal,
        )

    selected = _repeat_packs(load_builtin_packs(), policy.case_count)
    adapter = openai_tool_loop_adapter(
        LiveProviderPolicy(
            provider_id=OPENAI_PROVIDER_ID,
            model=policy.model,
            credential_env_var="OPENAI_API_KEY",
            limits=ProviderLimits(
                max_requests=1,
                max_output_tokens=policy.max_output_tokens,
                max_elapsed_seconds=policy.max_elapsed_seconds,
                max_estimated_cost_usd=policy.estimated_cost_usd_per_request,
            ),
            estimated_cost_usd_per_request=policy.estimated_cost_usd_per_request,
            allow_network=policy.allow_network,
        ),
        transport=transport,
        max_turns=MAX_OPENAI_TOOL_LOOP_TURNS,
        structured_output=policy.structured_output,
    )

    case_results: list[OpenAICaseResult] = []
    total_estimated_cost = 0.0
    completed = 0
    refused = 0
    for pack, replicate in selected:
        case_id = f"{pack.scenario_id}--replicate-{replicate}"
        run = adapter.run(
            request_from_pack(pack),
            environment=build_environment_from_pack(pack),
        )
        observed_cost = (
            run.execution_budget.estimated_cost_usd
            if run.execution_budget is not None
            else policy.estimated_cost_usd_per_request
        )
        total_estimated_cost += observed_cost
        if run.refusal is not None:
            refused += 1
            case_results.append(
                OpenAICaseResult(
                    case_id=case_id,
                    scenario_id=pack.scenario_id,
                    replicate=replicate,
                    status="refused",
                    refusal_error=run.refusal.error,
                    refusal_guidance=run.refusal.guidance,
                    refusal_stage=run.refusal.stage,
                    execution_budget=(
                        run.execution_budget.to_dict()
                        if run.execution_budget is not None
                        else None
                    ),
                )
            )
            continue
        if run.trace is None:
            refused += 1
            case_results.append(
                OpenAICaseResult(
                    case_id=case_id,
                    scenario_id=pack.scenario_id,
                    replicate=replicate,
                    status="refused",
                    refusal_error="invalid_adapter_run",
                )
            )
            continue
        finding = evaluate_pack_trace(run.trace, pack)
        completed += 1
        case_results.append(
            OpenAICaseResult(
                case_id=case_id,
                scenario_id=pack.scenario_id,
                replicate=replicate,
                status="completed",
                finding_status=finding.status.value,
                execution_budget=(
                    run.execution_budget.to_dict()
                    if run.execution_budget is not None
                    else None
                ),
            )
        )

    return OpenAIExperimentReport(
        provider_id=OPENAI_PROVIDER_ID,
        model=policy.model,
        mode=policy.mode,
        output_condition=policy.output_condition,
        requested_case_count=policy.case_count,
        attempted_case_count=len(case_results),
        completed_case_count=completed,
        refused_case_count=refused,
        total_estimated_cost_usd=round(total_estimated_cost, 6),
        max_total_cost_usd=policy.max_total_cost_usd,
        cases=tuple(case_results),
    )


def _repeat_packs(
    packs: tuple[ScenarioPack, ...],
    case_count: int,
) -> tuple[tuple[ScenarioPack, int], ...]:
    """Repeat the fixed pack order to create bounded variance replicates."""

    if not packs:
        raise ValueError("Built-in scenario packs must not be empty.")
    repetitions = ceil(case_count / len(packs))
    selected = [
        (pack, replicate)
        for replicate in range(1, repetitions + 1)
        for pack in packs
    ]
    return tuple(selected[:case_count])
