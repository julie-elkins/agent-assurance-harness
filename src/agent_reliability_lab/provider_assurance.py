"""Metadata-only assurance for the reviewed provider-shaped adapter lane.

Design rules:

1. The positive lane runs both mocked provider shapes through the shared evaluator.
2. A deliberately over-budget adapter run must be caught as a structured refusal.
3. Credential policy records names and opt-in state, never credential values.
4. The report carries counts and decisions, never provider payloads, prompts, or text.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import FindingStatus
from .providers import ProviderLimits, mock_provider_adapters
from .runner import run_adapters_comparison


PROVIDER_ASSURANCE_VERSION = 1


@dataclass(frozen=True)
class ProviderResult:
    """Metadata about one provider-shaped positive-control run."""

    provider_id: str
    credential_env_var: str
    credential_value_observed: bool
    live_enabled: bool
    scenario_count: int
    passed: bool
    mutation_checks_caught: int
    mutation_checks_total: int
    budgets_within_limits: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "credential_env_var": self.credential_env_var,
            "credential_value_observed": self.credential_value_observed,
            "live_enabled": self.live_enabled,
            "scenario_count": self.scenario_count,
            "passed": self.passed,
            "mutation_checks_caught": self.mutation_checks_caught,
            "mutation_checks_total": self.mutation_checks_total,
            "budgets_within_limits": self.budgets_within_limits,
        }


@dataclass(frozen=True)
class ProviderNegativeControl:
    """The expected result of a provider run whose token ceiling is too small."""

    provider_id: str
    max_output_tokens: int
    caught: bool
    refusal_count: int
    over_budget_scenario_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "max_output_tokens": self.max_output_tokens,
            "caught": self.caught,
            "refusal_count": self.refusal_count,
            "over_budget_scenario_count": self.over_budget_scenario_count,
        }


@dataclass(frozen=True)
class ProviderAssuranceReport:
    """The public, metadata-only provider assurance result."""

    providers: tuple[ProviderResult, ...]
    negative_control: ProviderNegativeControl

    @property
    def passed(self) -> bool:
        return all(item.passed for item in self.providers) and (
            self.negative_control.caught
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_assurance_version": PROVIDER_ASSURANCE_VERSION,
            "passed": self.passed,
            "providers": [item.to_dict() for item in self.providers],
            "negative_control": self.negative_control.to_dict(),
            "diagnostics": {
                "warnings": [
                    "This report proves the reviewed mocked adapter lane and "
                    "its budget refusal control; it does not measure live "
                    "provider quality.",
                    "Credential fields contain environment-variable names only. "
                    "No credential value is read by this assurance lane.",
                ],
                "what_it_does_not_show": (
                    "It does not show prompts, provider requests or responses, "
                    "model text, credentials, or production monitoring."
                ),
            },
        }

    def to_markdown(self) -> str:
        lines = [
            "# Provider adapter assurance",
            "",
            f"- **Decision:** {'PASS' if self.passed else 'BLOCKED'}",
            "- **Network:** disabled; mocked adapters only",
            "",
            "## Provider controls",
            "",
            "| Provider | Result | Credential reference | Value observed | "
            "Live enabled | Budgets within limits |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        lines.extend(
            f"| `{item.provider_id}` | "
            f"{'PASS' if item.passed else 'BLOCKED'} | "
            f"`{item.credential_env_var}` | "
            f"{item.credential_value_observed} | "
            f"{item.live_enabled} | {item.budgets_within_limits} |"
            for item in self.providers
        )
        lines.extend(
            [
                "",
                "## Negative control",
                "",
                "| Control | Result | Refusals | Over-budget scenarios |",
                "| --- | --- | ---: | ---: |",
                f"| `{self.negative_control.provider_id}` token ceiling | "
                f"{'CAUGHT' if self.negative_control.caught else 'MISSED'} | "
                f"{self.negative_control.refusal_count} | "
                f"{self.negative_control.over_budget_scenario_count} |",
                "",
                "Provider output, prompts, credentials, and raw payloads are "
                "excluded from this summary.",
                "",
            ]
        )
        return "\n".join(lines)


def run_provider_assurance() -> ProviderAssuranceReport:
    """Run positive provider controls and the deliberate budget negative control."""

    adapters = mock_provider_adapters("all")
    positive = run_adapters_comparison(adapters, include_mutations=True)
    providers = tuple(
        ProviderResult(
            provider_id=adapter.provider_id,
            credential_env_var=adapter.policy.credential_env_var,
            credential_value_observed=False,
            live_enabled=adapter.policy.live_enabled,
            scenario_count=positive.scenario_count,
            passed=report.passed,
            mutation_checks_caught=sum(
                mutation.caught for mutation in positive.mutation_tests
            ),
            mutation_checks_total=len(positive.mutation_tests),
            budgets_within_limits=all(
                budget.within_limits
                for budget in report.execution_budgets.values()
            ),
        )
        for adapter, report in zip(adapters, positive.reports)
    )
    negative_adapter = mock_provider_adapters(
        "openai",
        limits=ProviderLimits(
            max_requests=1,
            max_output_tokens=1,
            max_elapsed_seconds=5.0,
            max_estimated_cost_usd=0.01,
        ),
    )[0]
    negative = run_adapters_comparison((negative_adapter,))
    negative_report = negative.reports[0]
    refusal_count = sum(
        finding.status is FindingStatus.REFUSED
        for finding in negative_report.findings
    )
    over_budget_scenario_count = sum(
        not budget.within_limits
        for budget in negative_report.execution_budgets.values()
    )
    return ProviderAssuranceReport(
        providers=providers,
        negative_control=ProviderNegativeControl(
            provider_id=negative_adapter.provider_id,
            max_output_tokens=negative_adapter.policy.limits.max_output_tokens,
            caught=(
                refusal_count == negative.scenario_count
                and over_budget_scenario_count == negative.scenario_count
            ),
            refusal_count=refusal_count,
            over_budget_scenario_count=over_budget_scenario_count,
        ),
    )
