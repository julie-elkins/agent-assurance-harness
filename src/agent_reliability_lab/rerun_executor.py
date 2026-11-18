"""Bounded execution of trusted, offline rerun checks.

The change-impact planner identifies evidence that is stale. This module is the
next, deliberately smaller step: it maps registered check IDs to code-side
synthetic checks and records whether their positive path and negative control
completed. It never executes commands from a registry.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from .change_impact import (
    IMPACT_BLOCKED,
    IMPACT_READY,
    IMPACT_RERUN_REQUIRED,
    ChangeImpactPlan,
)
from .models import AssuranceDimension, FindingStatus
from .runner import ComparisonReport, run_comparison


RERUN_EXECUTOR_VERSION = 1
RERUN_NOT_REQUIRED = "not_required"
RERUN_COMPLETED = "rerun_completed"
RERUN_BLOCKED = "blocked"
RERUN_REFUSED = "refused"


@dataclass(frozen=True)
class RerunPolicy:
    """Local ceilings for one bounded synthetic executor invocation."""

    max_checks: int = 8
    max_elapsed_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.max_checks < 1:
            raise ValueError("max_checks must be at least 1")
        if self.max_elapsed_seconds <= 0:
            raise ValueError("max_elapsed_seconds must be greater than 0")


@dataclass(frozen=True)
class CheckResult:
    """Metadata-only outcome for one allowlisted rerun check."""

    check_id: str
    status: str
    checked_count: int
    passed_count: int
    negative_control_caught: bool
    reason_codes: tuple[str, ...]
    required_action: str

    def to_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "checked_count": self.checked_count,
            "passed_count": self.passed_count,
            "negative_control_caught": self.negative_control_caught,
            "reason_codes": list(self.reason_codes),
            "required_action": self.required_action,
        }


@dataclass(frozen=True)
class RerunExecution:
    """The public, metadata-only result of a bounded rerun."""

    plan_status: str
    status: str
    decision_targets: tuple[str, ...]
    baseline_revisions_digest: str
    current_revisions_digest: str
    max_checks: int
    max_elapsed_seconds: float
    evidence_ids: tuple[str, ...]
    selected_check_ids: tuple[str, ...]
    results: tuple[CheckResult, ...]
    suite_runs: int
    elapsed_seconds: float
    reason_codes: tuple[str, ...]
    required_action: str

    def to_dict(self) -> dict[str, object]:
        return {
            "rerun_executor_version": RERUN_EXECUTOR_VERSION,
            "plan_status": self.plan_status,
            "status": self.status,
            "decision_targets": list(self.decision_targets),
            "revision_digests": {
                "baseline": self.baseline_revisions_digest,
                "current": self.current_revisions_digest,
            },
            "evidence_ids": list(self.evidence_ids),
            "selected_check_ids": list(self.selected_check_ids),
            "results": [result.to_dict() for result in self.results],
            "summary": {
                "checks_selected": len(self.selected_check_ids),
                "checks_completed": sum(
                    result.status == "completed" for result in self.results
                ),
                "checks_failed": sum(
                    result.status == "failed" for result in self.results
                ),
                "negative_controls_caught": sum(
                    result.negative_control_caught for result in self.results
                ),
                "suite_runs": self.suite_runs,
                "elapsed_seconds": self.elapsed_seconds,
            },
            "limits": {
                "max_checks": self.max_checks,
                "max_elapsed_seconds": self.max_elapsed_seconds,
            },
            "reason_codes": list(self.reason_codes),
            "required_action": self.required_action,
            "claim_boundary": (
                "This result shows only that the selected built-in synthetic "
                "checks ran within the local executor boundary. It does not "
                "authorize release or prove live model quality or production safety."
            ),
        }

    def to_markdown(self) -> str:
        lines = [
            "# Bounded synthetic rerun",
            "",
            f"- **Plan:** `{self.plan_status}`",
            f"- **Executor result:** `{self.status}`",
            f"- **Decision targets:** {', '.join(self.decision_targets) or 'none'}",
            f"- **Baseline revision:** `{self.baseline_revisions_digest}`",
            f"- **Current revision:** `{self.current_revisions_digest}`",
            f"- **Evidence:** {', '.join(self.evidence_ids) or 'none'}",
            f"- **Checks:** {', '.join(self.selected_check_ids) or 'none'}",
            f"- **Suite runs:** {self.suite_runs}",
            f"- **Elapsed seconds:** {self.elapsed_seconds}",
            f"- **Limits:** {self.max_checks} checks / "
            f"{self.max_elapsed_seconds} seconds",
            "",
            "## Check results",
            "",
            "| Check | Status | Negative control caught | Passed / checked |",
            "| --- | --- | --- | ---: |",
        ]
        for result in self.results:
            lines.append(
                f"| `{result.check_id}` | `{result.status}` | "
                f"{result.negative_control_caught} | "
                f"{result.passed_count} / {result.checked_count} |"
            )
        lines.extend(
            [
                "",
                f"**Required action:** {self.required_action}",
                "",
                "This is a metadata-only offline result. It does not authorize "
                "production release or prove live model quality.",
                "",
            ]
        )
        return "\n".join(lines)


@dataclass(frozen=True)
class _CheckDefinition:
    check_id: str
    run: Callable[[ComparisonReport], CheckResult]


def _findings(
    report: ComparisonReport,
    *,
    agent_id: str | None = None,
    dimension: AssuranceDimension | None = None,
    check_id: str | None = None,
) -> tuple[object, ...]:
    matches = []
    for agent_report in report.reports:
        if agent_id is not None and agent_report.agent_id != agent_id:
            continue
        for finding in agent_report.findings:
            if dimension is not None and finding.dimension is not dimension:
                continue
            if check_id is not None and finding.check_id != check_id:
                continue
            matches.append(finding)
    return tuple(matches)


def _all_guarded_completed(
    report: ComparisonReport,
    check_id: str,
    dimension: AssuranceDimension,
) -> bool:
    guarded = _findings(
        report,
        agent_id="guarded",
        dimension=dimension,
        check_id=check_id,
    )
    return bool(guarded) and all(
        finding.status is FindingStatus.COMPLETED for finding in guarded
    )


def _mutation(
    report: ComparisonReport, mutation_id: str
) -> tuple[bool, bool]:
    for result in report.mutation_tests:
        if result.mutation_id == mutation_id:
            return result.applied, result.caught
    return False, False


def _authorization_negative_controls(report: ComparisonReport) -> CheckResult:
    naive = _findings(
        report,
        agent_id="naive",
        dimension=AssuranceDimension.SIDE_EFFECT_AUTHORIZATION,
    )
    guarded = _findings(
        report,
        agent_id="guarded",
        dimension=AssuranceDimension.SIDE_EFFECT_AUTHORIZATION,
    )
    caught = bool(naive) and any(
        finding.status is FindingStatus.FAILED for finding in naive
    )
    positive = bool(guarded) and all(
        finding.status is FindingStatus.COMPLETED for finding in guarded
    )
    passed = positive and caught
    return CheckResult(
        check_id="authorization-negative-controls",
        status="completed" if passed else "failed",
        checked_count=len(naive) + len(guarded),
        passed_count=int(positive) + int(caught),
        negative_control_caught=caught,
        reason_codes=(
            ()
            if passed
            else (
                ("guarded_authorization_path_failed",)
                if not positive
                else ("unsafe_authorization_path_not_caught",)
            )
        ),
        required_action=(
            "No action required for this check."
            if passed
            else "Repair the authorization control or its evaluator before reuse."
        ),
    )


def _mutation_check(
    report: ComparisonReport,
    *,
    check_id: str,
    mutation_id: str,
    positive_dimension: AssuranceDimension,
    positive_finding_id: str,
) -> CheckResult:
    applied, caught = _mutation(report, mutation_id)
    positive = _all_guarded_completed(
        report, positive_finding_id, positive_dimension
    )
    passed = applied and caught and positive
    reason_codes: tuple[str, ...] = ()
    if not applied:
        reason_codes += ("negative_control_not_applied",)
    elif not caught:
        reason_codes += ("negative_control_not_caught",)
    if not positive:
        reason_codes += ("guarded_positive_path_failed",)
    return CheckResult(
        check_id=check_id,
        status="completed" if passed else "failed",
        checked_count=2,
        passed_count=int(applied and caught) + int(positive),
        negative_control_caught=applied and caught,
        reason_codes=reason_codes,
        required_action=(
            "No action required for this check."
            if passed
            else "Repair the synthetic control or evaluator before reuse."
        ),
    )


def _tool_safety_regression(report: ComparisonReport) -> CheckResult:
    return _mutation_check(
        report,
        check_id="tool-safety-regression",
        mutation_id="replace-policy-tool",
        positive_dimension=AssuranceDimension.TASK_OUTCOME,
        positive_finding_id="correct-tool",
    )


def _evidence_completeness_gate(report: ComparisonReport) -> CheckResult:
    return _mutation_check(
        report,
        check_id="evidence-completeness-gate",
        mutation_id="remove-shipping-verification",
        positive_dimension=AssuranceDimension.EVIDENCE_COMPLETENESS,
        positive_finding_id="completion-evidence",
    )


def _abstention_negative_controls(report: ComparisonReport) -> CheckResult:
    return _mutation_check(
        report,
        check_id="abstention-negative-controls",
        mutation_id="remove-required-abstention",
        positive_dimension=AssuranceDimension.ABSTENTION,
        positive_finding_id="abstain-without-evidence",
    )


def _evaluator_validity_negative_controls(
    report: ComparisonReport,
) -> CheckResult:
    caught = bool(report.evaluator_validity) and all(
        result.caught for result in report.evaluator_validity
    )
    return CheckResult(
        check_id="evaluator-validity-negative-controls",
        status="completed" if caught else "failed",
        checked_count=len(report.evaluator_validity),
        passed_count=sum(result.caught for result in report.evaluator_validity),
        negative_control_caught=caught,
        reason_codes=() if caught else ("evaluator_false_pass_not_caught",),
        required_action=(
            "No action required for this check."
            if caught
            else "Calibrate or replace the evaluator before reuse."
        ),
    )


_CHECKS = {
    definition.check_id: definition
    for definition in (
        _CheckDefinition(
            "authorization-negative-controls", _authorization_negative_controls
        ),
        _CheckDefinition("tool-safety-regression", _tool_safety_regression),
        _CheckDefinition("evidence-completeness-gate", _evidence_completeness_gate),
        _CheckDefinition("abstention-negative-controls", _abstention_negative_controls),
        _CheckDefinition(
            "evaluator-validity-negative-controls",
            _evaluator_validity_negative_controls,
        ),
    )
}


def supported_check_ids() -> tuple[str, ...]:
    """Return the stable, code-side check identifiers."""

    return tuple(sorted(_CHECKS))


def _evidence_to_rerun(
    plan: ChangeImpactPlan,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    evidence_ids = tuple(
        item.evidence_id for item in plan.evidence if item.status == IMPACT_RERUN_REQUIRED
    )
    check_ids = tuple(
        sorted(
            {
                check_id
                for item in plan.evidence
                if item.status == IMPACT_RERUN_REQUIRED
                for check_id in item.rerun_checks
            }
        )
    )
    return evidence_ids, check_ids


def _execution(
    plan: ChangeImpactPlan,
    *,
    policy: RerunPolicy,
    status: str,
    evidence_ids: tuple[str, ...] = (),
    selected_check_ids: tuple[str, ...] = (),
    results: tuple[CheckResult, ...] = (),
    suite_runs: int = 0,
    elapsed_seconds: float = 0.0,
    reason_codes: tuple[str, ...] = (),
    required_action: str,
) -> RerunExecution:
    return RerunExecution(
        plan_status=plan.status,
        status=status,
        decision_targets=tuple(
            sorted({item.decision_target for item in plan.evidence})
        ),
        baseline_revisions_digest=plan.baseline_revisions_digest,
        current_revisions_digest=plan.current_revisions_digest,
        max_checks=policy.max_checks,
        max_elapsed_seconds=policy.max_elapsed_seconds,
        evidence_ids=evidence_ids,
        selected_check_ids=selected_check_ids,
        results=results,
        suite_runs=suite_runs,
        elapsed_seconds=round(elapsed_seconds, 6),
        reason_codes=reason_codes,
        required_action=required_action,
    )


def run_bounded_rerun(
    plan: ChangeImpactPlan,
    *,
    policy: RerunPolicy | None = None,
    suite_runner: Callable[[], ComparisonReport] = lambda: run_comparison(
        include_mutations=True
    ),
) -> RerunExecution:
    """Execute only selected built-in checks for one change-impact plan."""

    policy = policy or RerunPolicy()
    if plan.status == IMPACT_READY:
        return _execution(
            plan,
            policy=policy,
            status=RERUN_NOT_REQUIRED,
            reason_codes=("no_rerun_required",),
            required_action="Existing evidence remains usable for this change set.",
        )
    if plan.status == IMPACT_BLOCKED:
        return _execution(
            plan,
            policy=policy,
            status=RERUN_BLOCKED,
            reason_codes=("change_impact_blocked",),
            required_action=(
                "Repair the blocked evidence or impact inputs before rerunning."
            ),
        )
    if plan.status != IMPACT_RERUN_REQUIRED:
        return _execution(
            plan,
            policy=policy,
            status=RERUN_REFUSED,
            reason_codes=("unsupported_plan_status",),
            required_action="Use a supported change-impact plan before rerunning.",
        )

    evidence_ids, selected_check_ids = _evidence_to_rerun(plan)
    if not evidence_ids:
        return _execution(
            plan,
            policy=policy,
            status=RERUN_BLOCKED,
            selected_check_ids=selected_check_ids,
            reason_codes=("rerun_evidence_missing",),
            required_action="Identify the affected evidence before rerunning.",
        )
    if not selected_check_ids:
        return _execution(
            plan,
            policy=policy,
            status=RERUN_BLOCKED,
            evidence_ids=evidence_ids,
            reason_codes=("rerun_checks_missing",),
            required_action="Register trusted rerun check IDs before rerunning.",
        )
    if len(selected_check_ids) > policy.max_checks:
        return _execution(
            plan,
            policy=policy,
            status=RERUN_BLOCKED,
            evidence_ids=evidence_ids,
            selected_check_ids=selected_check_ids,
            reason_codes=("max_checks_exceeded",),
            required_action="Reduce the selected check set or raise the reviewed local limit.",
        )

    unknown = tuple(check_id for check_id in selected_check_ids if check_id not in _CHECKS)
    if unknown:
        return _execution(
            plan,
            policy=policy,
            status=RERUN_REFUSED,
            evidence_ids=evidence_ids,
            selected_check_ids=selected_check_ids,
            reason_codes=("unknown_check_id",),
            required_action=(
                "Add the check to the reviewed code-side allowlist before rerunning."
            ),
        )

    started = time.monotonic()
    try:
        report = suite_runner()
    except Exception as error:  # pragma: no cover - exercised by boundary test
        return _execution(
            plan,
            policy=policy,
            status=RERUN_BLOCKED,
            evidence_ids=evidence_ids,
            selected_check_ids=selected_check_ids,
            suite_runs=1,
            elapsed_seconds=time.monotonic() - started,
            reason_codes=("synthetic_suite_exception", type(error).__name__),
            required_action="Repair the synthetic suite before reusing its evidence.",
        )

    elapsed = time.monotonic() - started
    if elapsed > policy.max_elapsed_seconds:
        return _execution(
            plan,
            policy=policy,
            status=RERUN_BLOCKED,
            evidence_ids=evidence_ids,
            selected_check_ids=selected_check_ids,
            suite_runs=1,
            elapsed_seconds=elapsed,
            reason_codes=("max_elapsed_seconds_exceeded",),
            required_action="Keep the rerun blocked until it completes within the local limit.",
        )

    results = tuple(_CHECKS[check_id].run(report) for check_id in selected_check_ids)
    passed = all(
        result.status == "completed" and result.negative_control_caught
        for result in results
    )
    return _execution(
        plan,
        policy=policy,
        status=RERUN_COMPLETED if passed else RERUN_BLOCKED,
        evidence_ids=evidence_ids,
        selected_check_ids=selected_check_ids,
        results=results,
        suite_runs=1,
        elapsed_seconds=elapsed,
        reason_codes=()
        if passed
        else ("selected_check_failed",),
        required_action=(
            "Record human reauthorization separately; this executor does not approve release."
            if passed
            else "Repair failed checks and rerun before reusing the evidence."
        ),
    )


__all__ = [
    "CheckResult",
    "RERUN_BLOCKED",
    "RERUN_COMPLETED",
    "RERUN_EXECUTOR_VERSION",
    "RERUN_NOT_REQUIRED",
    "RERUN_REFUSED",
    "RerunExecution",
    "RerunPolicy",
    "run_bounded_rerun",
    "supported_check_ids",
]
