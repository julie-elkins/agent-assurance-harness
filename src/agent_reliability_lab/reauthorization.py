"""Deterministic synthetic pilot for change-aware agent reauthorization.

The pilot compares three decision conditions over the same claim-change cases:

1. pass/fail reporting;
2. revision-aware evidence; and
3. revision-aware evidence plus reauthorization controls.

All records are synthetic and metadata-only. The module deliberately does not model
prompts, tool payloads, provider output, or hidden model state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any


REFERENCE_DECISIONS_PATH = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "reauthorization-pilot"
    / "reference-decisions.json"
)


class PilotCondition(str, Enum):
    """One decision process under comparison."""

    PASS_FAIL = "pass_fail"
    REVISION_AWARE = "revision_aware"
    REAUTHORIZATION = "reauthorization"


class PilotDecision(str, Enum):
    """The bounded decision a condition can make."""

    REAUTHORIZED = "reauthorized"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


class CaseVariant(str, Enum):
    """The pre-specified state of one synthetic claim-change case."""

    CURRENT = "current"
    REEVALUATION_REQUIRED = "reevaluation_required"
    NEGATIVE_CONTROL = "negative_control"


@dataclass(frozen=True)
class ReauthorizationCase:
    """Metadata-only synthetic claim-change case."""

    case_id: str
    change_family: str
    variant: CaseVariant
    changed_component: str
    prior_system_revision: str
    current_system_revision: str
    prior_evidence_revision: str
    current_task_result: str
    accountable_owner_present: bool
    rollback_evidence_present: bool
    required_reevaluation_scope: str

    @property
    def requires_reevaluation(self) -> bool:
        """Whether the change invalidates the prior evidence scope."""

        return self.variant in {
            CaseVariant.REEVALUATION_REQUIRED,
            CaseVariant.NEGATIVE_CONTROL,
        }

    @property
    def expected_decision(self) -> PilotDecision:
        """Return the variant-derived default used for case construction.

        The pilot runner does not use this property as its decision oracle. It loads
        the checked-in reference manifest instead, so the expected decision is not
        derived from the condition evaluator.
        """

        if self.variant is CaseVariant.NEGATIVE_CONTROL:
            return PilotDecision.BLOCKED
        if self.variant is CaseVariant.REEVALUATION_REQUIRED:
            return PilotDecision.REVIEW_REQUIRED
        return PilotDecision.REAUTHORIZED

    def to_metadata(
        self,
        *,
        reference_decision: PilotDecision | None = None,
    ) -> dict[str, Any]:
        """Return a public-safe case record."""

        value = asdict(self)
        value["variant"] = self.variant.value
        value["expected_decision"] = (
            reference_decision or self.expected_decision
        ).value
        value["requires_reevaluation"] = self.requires_reevaluation
        return value


@dataclass(frozen=True)
class PilotResult:
    """One condition's decision over one claim-change case."""

    case_id: str
    change_family: str
    variant: str
    condition: str
    decision: str
    reference_decision: str
    false_ready: bool
    stale_claim_detected: bool
    correct_escalation: bool
    detection_latency_steps: int | None
    evaluation_runs: int
    review_steps: int
    synthetic_time_units: int
    finding_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe result without content-bearing fields."""

        value = asdict(self)
        value["finding_codes"] = list(self.finding_codes)
        return value


def _case(
    family: str,
    variant: CaseVariant,
    component: str,
    *,
    owner: bool = True,
    rollback: bool = True,
) -> ReauthorizationCase:
    suffix = variant.value.replace("_", "-")
    case_id = f"reauth-{family}-{suffix}"
    return ReauthorizationCase(
        case_id=case_id,
        change_family=family,
        variant=variant,
        changed_component=component,
        prior_system_revision=f"system-{family}-r1",
        current_system_revision=f"system-{family}-r2",
        prior_evidence_revision=f"evidence-{family}-r1",
        current_task_result="pass",
        accountable_owner_present=owner,
        rollback_evidence_present=rollback,
        required_reevaluation_scope=(
            "none"
            if variant is CaseVariant.CURRENT
            else f"scenario-family:{family}"
        ),
    )


def synthetic_cases() -> tuple[ReauthorizationCase, ...]:
    """Return the fixed eighteen-case pilot set."""

    families = (
        ("prompt", "instruction"),
        ("tool", "api-contract"),
        ("retrieval", "policy-source"),
        ("authorization", "permission-policy"),
        ("evaluator", "threshold"),
        ("deployment", "dependency"),
    )
    cases: list[ReauthorizationCase] = []
    for family, component in families:
        cases.extend(
            (
                _case(family, CaseVariant.CURRENT, component),
                _case(family, CaseVariant.REEVALUATION_REQUIRED, component),
                _case(
                    family,
                    CaseVariant.NEGATIVE_CONTROL,
                    component,
                    owner=False,
                    rollback=False,
                ),
            )
        )
    return tuple(cases)


def _held_out_case(
    family: str,
    component: str,
    variant: CaseVariant,
    *,
    rollback: bool,
) -> ReauthorizationCase:
    """Build a case absent from the original pilot matrix."""

    suffix = variant.value.replace("_", "-")
    return ReauthorizationCase(
        case_id=f"reauth-heldout-{family}-{suffix}",
        change_family=family,
        variant=variant,
        changed_component=f"{component}+deployment",
        prior_system_revision=f"system-{family}-r1",
        current_system_revision=f"system-{family}-r3-heldout",
        prior_evidence_revision=f"evidence-{family}-r1",
        current_task_result="pass",
        accountable_owner_present=True,
        rollback_evidence_present=rollback,
        required_reevaluation_scope=f"compound-change:{family}+deployment",
    )


def held_out_cases() -> tuple[ReauthorizationCase, ...]:
    """Return twelve cases not used to shape the original pilot logic."""

    families = (
        ("prompt", "instruction"),
        ("tool", "api-contract"),
        ("retrieval", "policy-source"),
        ("authorization", "permission-policy"),
        ("evaluator", "threshold"),
        ("deployment", "dependency"),
    )
    cases: list[ReauthorizationCase] = []
    for family, component in families:
        cases.extend(
            (
                _held_out_case(
                    family,
                    component,
                    CaseVariant.REEVALUATION_REQUIRED,
                    rollback=True,
                ),
                _held_out_case(
                    family,
                    component,
                    CaseVariant.NEGATIVE_CONTROL,
                    rollback=False,
                ),
            )
        )
    return tuple(cases)


def load_reference_decisions(
    path: Path = REFERENCE_DECISIONS_PATH,
) -> dict[str, PilotDecision]:
    """Load the independent metadata-only reference decision manifest."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise ValueError("Reference decision manifest must be a non-empty object.")
    try:
        return {
            case_id: PilotDecision(decision)
            for case_id, decision in raw.items()
        }
    except (TypeError, ValueError) as exc:
        raise ValueError("Reference decisions contain an unsupported decision.") from exc


def _evaluate(
    case: ReauthorizationCase,
    condition: PilotCondition,
    reference_decision: PilotDecision,
) -> PilotResult:
    """Evaluate one case under one pre-specified decision condition."""

    if condition is PilotCondition.PASS_FAIL:
        decision = PilotDecision.REAUTHORIZED
        finding_codes = ("pass_fail_reported",)
        detection_latency = None if case.requires_reevaluation else 0
        evaluation_runs = 1
        review_steps = 0
        time_units = 1
    elif condition is PilotCondition.REVISION_AWARE:
        if case.requires_reevaluation:
            decision = PilotDecision.REVIEW_REQUIRED
            finding_codes = ("affected_evidence_stale",)
            detection_latency = 1
            evaluation_runs = 2
            review_steps = 1
            time_units = 3
        else:
            decision = PilotDecision.REAUTHORIZED
            finding_codes = ("revision_matches_evidence",)
            detection_latency = 0
            evaluation_runs = 1
            review_steps = 0
            time_units = 1
    else:
        if case.variant is CaseVariant.NEGATIVE_CONTROL:
            decision = PilotDecision.BLOCKED
            missing_controls = []
            if not case.accountable_owner_present:
                missing_controls.append("missing_accountable_owner")
            if not case.rollback_evidence_present:
                missing_controls.append("missing_rollback_evidence")
            finding_codes = tuple(missing_controls) or ("negative_control_blocked",)
            detection_latency = 2
            evaluation_runs = 1
            review_steps = 2
            time_units = 4
        elif case.variant is CaseVariant.REEVALUATION_REQUIRED:
            decision = PilotDecision.REVIEW_REQUIRED
            finding_codes = ("reevaluation_required",)
            detection_latency = 1
            evaluation_runs = 2
            review_steps = 1
            time_units = 4
        else:
            decision = PilotDecision.REAUTHORIZED
            finding_codes = ("reauthorization_complete",)
            detection_latency = 0
            evaluation_runs = 1
            review_steps = 1
            time_units = 2

    reference = reference_decision
    false_ready = (
        decision is PilotDecision.REAUTHORIZED
        and reference is not PilotDecision.REAUTHORIZED
    )
    stale_claim_detected = (
        case.requires_reevaluation and decision is not PilotDecision.REAUTHORIZED
    )
    correct_escalation = decision is reference
    return PilotResult(
        case_id=case.case_id,
        change_family=case.change_family,
        variant=case.variant.value,
        condition=condition.value,
        decision=decision.value,
        reference_decision=reference.value,
        false_ready=false_ready,
        stale_claim_detected=stale_claim_detected,
        correct_escalation=correct_escalation,
        detection_latency_steps=detection_latency,
        evaluation_runs=evaluation_runs,
        review_steps=review_steps,
        synthetic_time_units=time_units,
        finding_codes=finding_codes,
    )


def _sha256(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _condition_summary(
    results: tuple[PilotResult, ...],
    condition: PilotCondition,
) -> dict[str, Any]:
    selected = tuple(result for result in results if result.condition == condition.value)
    latencies = [
        result.detection_latency_steps
        for result in selected
        if result.detection_latency_steps is not None
    ]
    return {
        "condition": condition.value,
        "case_count": len(selected),
        "false_ready_count": sum(result.false_ready for result in selected),
        "stale_claims_requiring_detection": sum(
            result.variant != CaseVariant.CURRENT.value for result in selected
        ),
        "stale_claim_detection_count": sum(
            result.stale_claim_detected for result in selected
        ),
        "correct_escalation_count": sum(
            result.correct_escalation for result in selected
        ),
        "detection_latency_steps_total": sum(latencies),
        "detection_latency_steps_observed": len(latencies),
        "evaluation_runs_total": sum(result.evaluation_runs for result in selected),
        "review_steps_total": sum(result.review_steps for result in selected),
        "synthetic_time_units_total": sum(
            result.synthetic_time_units for result in selected
        ),
    }


def run_pilot(*, include_held_out: bool = False) -> dict[str, Any]:
    """Run the pilot or its held-out robustness extension."""

    cases = synthetic_cases()
    if include_held_out:
        cases += held_out_cases()
    reference_decisions = load_reference_decisions()
    case_ids = {case.case_id for case in cases}
    manifest_ids = set(reference_decisions)
    missing = sorted(case_ids - manifest_ids)
    if missing:
        extra = sorted(manifest_ids - case_ids)
        raise ValueError(
            f"Reference manifest mismatch; missing={missing}, extra={extra}."
        )
    if include_held_out and case_ids != manifest_ids:
        missing = sorted(case_ids - manifest_ids)
        extra = sorted(manifest_ids - case_ids)
        raise ValueError(
            f"Reference manifest mismatch; missing={missing}, extra={extra}."
        )
    results = tuple(
        _evaluate(case, condition, reference_decisions[case.case_id])
        for case in cases
        for condition in PilotCondition
    )
    expected_case_count = 30 if include_held_out else 18
    controls = {
        "case_count_is_expected": len(cases) == expected_case_count,
        "reference_manifest_is_complete": (
            case_ids == manifest_ids if include_held_out else case_ids <= manifest_ids
        ),
        "each_family_has_base_variants": all(
            {
                case.variant for case in cases if case.change_family == family
            }
            == {
                CaseVariant.CURRENT,
                CaseVariant.REEVALUATION_REQUIRED,
                CaseVariant.NEGATIVE_CONTROL,
            }
            for family in {case.change_family for case in cases}
        ),
        "each_condition_has_full_coverage": all(
            sum(result.condition == condition.value for result in results) == len(cases)
            for condition in PilotCondition
        ),
        "revision_condition_detects_all_affected_cases": all(
            result.stale_claim_detected
            for result in results
            if result.condition == PilotCondition.REVISION_AWARE.value
            and result.variant != CaseVariant.CURRENT.value
        ),
        "reauthorization_blocks_all_negative_controls": all(
            result.decision == PilotDecision.BLOCKED.value
            for result in results
            if result.condition == PilotCondition.REAUTHORIZATION.value
            and result.variant == CaseVariant.NEGATIVE_CONTROL.value
        ),
    }
    report_kind = (
        "agent-reauthorization-robustness-v1"
        if include_held_out
        else "agent-reauthorization-pilot-v1"
    )
    report = {
        "report_version": 1,
        "report_kind": report_kind,
        "decision": "pass" if all(controls.values()) else "blocked",
        "offline": True,
        "synthetic_only": True,
        "metadata_only": True,
        "raw_payloads_included": False,
        "provider_output_included": False,
        "case_count": len(cases),
        "condition_count": len(PilotCondition),
        "case_set_sha256": _sha256(
            [
                case.to_metadata(
                    reference_decision=reference_decisions[case.case_id]
                )
                for case in cases
            ]
        ),
        "controls": controls,
        "conditions": [
            _condition_summary(results, condition) for condition in PilotCondition
        ],
        "cases": [
            case.to_metadata(
                reference_decision=reference_decisions[case.case_id]
            )
            for case in cases
        ],
        "results": [result.to_dict() for result in results],
        "limits": [
            "The cases and outcomes are synthetic and deterministic.",
            "The decision oracle is a pilot reference, not a universal organizational authority.",
            "The pilot does not establish production safety, model quality, or general agent capability.",
            "Synthetic time units and evaluation runs are relative cost proxies, not financial estimates.",
        ],
    }
    return report


def pilot_to_markdown(report: dict[str, Any]) -> str:
    """Render a reviewer-facing summary without content-bearing fields."""

    lines = [
        (
            "# Agent reauthorization robustness study"
            if report["report_kind"] == "agent-reauthorization-robustness-v1"
            else "# Agent reauthorization pilot"
        ),
        "",
        f"- **Decision:** `{str(report['decision']).upper()}`",
        f"- **Synthetic cases:** `{report['case_count']}`",
        f"- **Conditions:** `{report['condition_count']}`",
        f"- **Case-set SHA-256:** `{report['case_set_sha256']}`",
        "",
        "| condition | false-ready | stale detected | correct escalation | eval runs | review steps | time units |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for summary in report["conditions"]:
        lines.append(
            "| `{condition}` | {false_ready_count} | "
            "{stale_claim_detection_count}/{stale_claims_requiring_detection} | "
            "{correct_escalation_count}/{case_count} | {evaluation_runs_total} | "
            "{review_steps_total} | {synthetic_time_units_total} |".format(**summary)
        )
    lines.extend(
        [
            "",
            "The study compares decision conditions over identical synthetic cases.",
            "It emits identifiers, statuses, counts, and hashes only.",
            "",
            "## Limits",
            "",
        ]
    )
    lines.extend(f"- {limit}" for limit in report["limits"])
    lines.append("")
    return "\n".join(lines)
