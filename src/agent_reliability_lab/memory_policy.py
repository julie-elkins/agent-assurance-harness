"""Bounded synthetic agent-memory policy assurance.

This module tests a narrow safety contract: a memory policy may discard optional
history, but it must retain evidence required for safe continuation and must not
carry memory across workflow boundaries. The inputs and outputs are identifiers
and numeric observations only; no memory text or tool payloads cross the boundary.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


MEMORY_POLICY_VERSION = 1
MEMORY_POLICY_LANE_ID = "agent_memory_policy"
_PACK_VERSION = 1
_PACK_METADATA = {
    "data_class": "synthetic",
    "owner": "agent-assurance-harness",
    "purpose": "bounded-memory-safety",
}
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACK_DIRECTORY = _REPOSITORY_ROOT / "examples" / "memory-policy-packs"


class MemoryPolicyInputError(ValueError):
    """Raised when a memory-policy pack violates its declarative contract."""


@dataclass(frozen=True)
class MemoryItem:
    """Identifier-only memory metadata."""

    item_id: str
    workflow_id: str
    kind: str
    age_rank: int
    required_for_safe_continuation: bool


@dataclass(frozen=True)
class MemoryPolicyCase:
    """One synthetic memory-retention case."""

    case_id: str
    workflow_id: str
    memory_items: tuple[MemoryItem, ...]
    must_retain: tuple[str, ...]
    must_not_retain: tuple[str, ...]
    max_retained_items: int


@dataclass(frozen=True)
class MemoryCaseResult:
    """Metadata-only result for one policy and case."""

    case_id: str
    retained_item_count: int
    discarded_item_count: int
    required_memory_retained: bool
    workflow_boundary_respected: bool
    bounded_retention_respected: bool
    evidence_status: str
    task_outcome: str
    refusal_status: str
    reason_codes: tuple[str, ...]
    cost_units: int
    latency_units: int

    @property
    def passed(self) -> bool:
        """Return whether this policy met the case safety contract."""

        return not self.reason_codes

    def to_dict(self) -> dict[str, object]:
        """Return identifier-only case metadata."""

        return {
            "case_id": self.case_id,
            "retained_item_count": self.retained_item_count,
            "discarded_item_count": self.discarded_item_count,
            "required_memory_retained": self.required_memory_retained,
            "workflow_boundary_respected": self.workflow_boundary_respected,
            "bounded_retention_respected": self.bounded_retention_respected,
            "evidence_status": self.evidence_status,
            "task_outcome": self.task_outcome,
            "refusal_status": self.refusal_status,
            "reason_codes": list(self.reason_codes),
            "cost_units": self.cost_units,
            "latency_units": self.latency_units,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class MemoryPolicySpec:
    """One deterministic policy used by the synthetic suite."""

    policy_id: str
    recent_window: int | None
    retain_required: bool
    refuse_if_required_missing: bool
    enforce_retention_bound: bool


@dataclass(frozen=True)
class MemoryPolicyEvaluation:
    """Metadata-only result for one policy across the pack."""

    policy_id: str
    passed: bool
    case_results: tuple[MemoryCaseResult, ...]
    controls_caught: tuple[str, ...]
    controls_missed: tuple[str, ...]
    total_cost_units: int
    total_latency_units: int

    def to_dict(self) -> dict[str, object]:
        """Return the safe policy result."""

        return {
            "policy_id": self.policy_id,
            "passed": self.passed,
            "case_results": [result.to_dict() for result in self.case_results],
            "controls_caught": list(self.controls_caught),
            "controls_missed": list(self.controls_missed),
            "total_cost_units": self.total_cost_units,
            "total_latency_units": self.total_latency_units,
        }


@dataclass(frozen=True)
class MemoryPolicySuiteReport:
    """The complete bounded-memory assurance result."""

    pack_fingerprint: str
    case_count: int
    policies: tuple[MemoryPolicyEvaluation, ...]
    controls_caught: tuple[str, ...]
    controls_missed: tuple[str, ...]
    negative_control: dict[str, object]

    @property
    def passed(self) -> bool:
        """Return whether positives pass and the unsafe control is caught."""

        return not self.controls_missed and bool(self.negative_control["caught"])

    def to_dict(self) -> dict[str, object]:
        """Return metadata-only suite evidence."""

        return {
            "memory_policy_version": MEMORY_POLICY_VERSION,
            "lane_id": MEMORY_POLICY_LANE_ID,
            "passed": self.passed,
            "pack_fingerprint": self.pack_fingerprint,
            "case_count": self.case_count,
            "policies": [policy.to_dict() for policy in self.policies],
            "controls_caught": list(self.controls_caught),
            "controls_missed": list(self.controls_missed),
            "negative_control": self.negative_control,
            "diagnostics": {
                "warnings": [
                    "The suite is synthetic, offline, and metadata-only.",
                    "Cost and latency units are relative observations, not provider billing or production timings.",
                ],
                "what_it_does_not_show": (
                    "It does not prove live cache behavior, model quality, "
                    "production performance, or provider-specific savings."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Render a concise reviewer-facing summary."""

        lines = [
            "# Bounded Synthetic Agent Memory Policy",
            "",
            f"Decision: `{'PASS' if self.passed else 'BLOCKED'}`",
            "",
            f"Cases checked: `{self.case_count}`",
            "",
            "| Policy | Result | Cost units | Latency units |",
            "| --- | --- | ---: | ---: |",
        ]
        for policy in self.policies:
            lines.append(
                f"| `{policy.policy_id}` | "
                f"`{'PASS' if policy.passed else 'BLOCKED'}` | "
                f"`{policy.total_cost_units}` | "
                f"`{policy.total_latency_units}` |"
            )
        lines.extend(
            [
                "",
                "Controls caught: "
                + (
                    ", ".join(f"`{item}`" for item in self.controls_caught)
                    or "none"
                ),
                "Controls missed: "
                + (
                    ", ".join(f"`{item}`" for item in self.controls_missed)
                    or "none"
                ),
                "",
                "A blocked required-evidence discard is a safety finding even "
                "when a task could still produce a plausible answer.",
                "",
                "This is synthetic evidence; it does not prove live provider "
                "cache savings or production performance.",
                "",
            ]
        )
        return "\n".join(lines)


REFERENCE_POLICIES = (
    MemoryPolicySpec(
        policy_id="retain-all-baseline",
        recent_window=None,
        retain_required=True,
        refuse_if_required_missing=True,
        enforce_retention_bound=False,
    ),
    MemoryPolicySpec(
        policy_id="bounded-guarded-memory",
        recent_window=2,
        retain_required=True,
        refuse_if_required_missing=True,
        enforce_retention_bound=True,
    ),
    MemoryPolicySpec(
        policy_id="naive-forget-old-negative-control",
        recent_window=2,
        retain_required=False,
        refuse_if_required_missing=False,
        enforce_retention_bound=True,
    ),
)


def load_memory_policy_pack(path: Path) -> tuple[tuple[MemoryPolicyCase, ...], str]:
    """Load and strictly validate one synthetic memory-policy pack."""

    raw_bytes = path.read_bytes()
    pack_fingerprint = hashlib.sha256(raw_bytes).hexdigest()
    try:
        value = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MemoryPolicyInputError("invalid_pack_json") from exc
    if not isinstance(value, dict):
        raise MemoryPolicyInputError("pack_not_object")
    _require_exact_keys(value, {"pack_version", "metadata", "cases"}, "pack")
    if value["pack_version"] != _PACK_VERSION:
        raise MemoryPolicyInputError("unsupported_pack_version")
    if value["metadata"] != _PACK_METADATA:
        raise MemoryPolicyInputError("invalid_pack_metadata")
    cases = value["cases"]
    if not isinstance(cases, list) or not cases:
        raise MemoryPolicyInputError("empty_pack")
    parsed = tuple(_parse_case(item) for item in cases)
    case_ids = [case.case_id for case in parsed]
    if len(case_ids) != len(set(case_ids)):
        raise MemoryPolicyInputError("duplicate_case_id")
    return parsed, pack_fingerprint


def load_memory_policy_cases(
    pack_directory: Path = DEFAULT_PACK_DIRECTORY,
) -> tuple[tuple[MemoryPolicyCase, ...], str]:
    """Load every checked-in pack and refuse missing or duplicate coverage."""

    paths = sorted(pack_directory.glob("*.json"))
    if not paths:
        raise MemoryPolicyInputError("empty_pack_directory")
    all_cases: list[MemoryPolicyCase] = []
    fingerprints: list[str] = []
    for path in paths:
        cases, fingerprint = load_memory_policy_pack(path)
        all_cases.extend(cases)
        fingerprints.append(fingerprint)
    case_ids = [case.case_id for case in all_cases]
    if len(case_ids) != len(set(case_ids)):
        raise MemoryPolicyInputError("duplicate_case_id")
    digest = hashlib.sha256("".join(fingerprints).encode("ascii")).hexdigest()
    return tuple(all_cases), digest


def evaluate_memory_policy(
    policy: MemoryPolicySpec,
    cases: Iterable[MemoryPolicyCase],
) -> MemoryPolicyEvaluation:
    """Evaluate one deterministic policy without retaining memory content."""

    case_results = tuple(_evaluate_case(policy, case) for case in cases)
    controls_caught: list[str] = []
    controls_missed: list[str] = []
    if all(result.workflow_boundary_respected for result in case_results):
        controls_caught.append("memory-policy-workflow-boundary")
    else:
        controls_missed.append("memory-policy-workflow-boundary")
    if policy.retain_required:
        if all(result.required_memory_retained for result in case_results):
            controls_caught.append("memory-policy-required-evidence")
        else:
            controls_missed.append("memory-policy-required-evidence")
    if not policy.enforce_retention_bound or all(
        result.bounded_retention_respected for result in case_results
    ):
        controls_caught.append("memory-policy-bounded-retention")
    else:
        controls_missed.append("memory-policy-bounded-retention")
    passed = not controls_missed and all(result.passed for result in case_results)
    return MemoryPolicyEvaluation(
        policy_id=policy.policy_id,
        passed=passed,
        case_results=case_results,
        controls_caught=tuple(controls_caught),
        controls_missed=tuple(controls_missed),
        total_cost_units=sum(result.cost_units for result in case_results),
        total_latency_units=sum(result.latency_units for result in case_results),
    )


def run_reference_memory_policy_suite(
    pack_directory: Path = DEFAULT_PACK_DIRECTORY,
) -> MemoryPolicySuiteReport:
    """Run the offline positive and negative memory-policy controls."""

    cases, pack_fingerprint = load_memory_policy_cases(pack_directory)
    evaluations = tuple(
        evaluate_memory_policy(policy, cases) for policy in REFERENCE_POLICIES
    )
    baseline, guarded, negative = evaluations
    controls_caught: list[str] = []
    controls_missed: list[str] = []
    if baseline.passed:
        controls_caught.append("memory-policy-baseline-complete")
    else:
        controls_missed.append("memory-policy-baseline-complete")
    if guarded.passed:
        controls_caught.append("memory-policy-guarded-safe")
    else:
        controls_missed.append("memory-policy-guarded-safe")
    negative_findings = tuple(
        sorted(
            {
                reason_code
                for result in negative.case_results
                for reason_code in result.reason_codes
            }
        )
    )
    negative_caught = (
        not negative.passed
        and "required_memory_discarded" in negative_findings
        and "unsafe_continue_without_required_evidence" in negative_findings
    )
    if negative_caught:
        controls_caught.append("memory-policy-negative-control")
    else:
        controls_missed.append("memory-policy-negative-control")
    return MemoryPolicySuiteReport(
        pack_fingerprint=pack_fingerprint,
        case_count=len(cases),
        policies=evaluations,
        controls_caught=tuple(controls_caught),
        controls_missed=tuple(controls_missed),
        negative_control={
            "control_id": "memory-policy-naive-forget-old",
            "policy_id": negative.policy_id,
            "caught": negative_caught,
            "reason_codes": list(negative_findings),
        },
    )


def _evaluate_case(
    policy: MemoryPolicySpec,
    case: MemoryPolicyCase,
) -> MemoryCaseResult:
    eligible = tuple(
        item for item in case.memory_items if item.workflow_id == case.workflow_id
    )
    retained = tuple(
        item
        for item in eligible
        if (
            (policy.retain_required and item.required_for_safe_continuation)
            or (
                policy.recent_window is not None
                and item.age_rank <= policy.recent_window
            )
            or policy.recent_window is None
        )
    )
    retained_ids = {item.item_id for item in retained}
    required_memory_retained = set(case.must_retain) <= retained_ids
    workflow_boundary_respected = not (
        set(case.must_not_retain) & retained_ids
    )
    bounded_retention_respected = len(retained) <= case.max_retained_items
    reason_codes: list[str] = []
    if not required_memory_retained:
        reason_codes.append("required_memory_discarded")
    if not workflow_boundary_respected:
        reason_codes.append("workflow_boundary_violation")
    if policy.enforce_retention_bound and not bounded_retention_respected:
        reason_codes.append("retention_bound_exceeded")
    evidence_status = "complete" if required_memory_retained else "incomplete"
    refusal_status = "not_required"
    task_outcome = "completed"
    if not required_memory_retained and policy.refuse_if_required_missing:
        refusal_status = "refused"
        task_outcome = "not_completed"
    elif not required_memory_retained:
        reason_codes.append("unsafe_continue_without_required_evidence")
    cost_units = 100 + len(retained) * 10
    latency_units = 20 + len(retained) * 3
    return MemoryCaseResult(
        case_id=case.case_id,
        retained_item_count=len(retained),
        discarded_item_count=len(case.memory_items) - len(retained),
        required_memory_retained=required_memory_retained,
        workflow_boundary_respected=workflow_boundary_respected,
        bounded_retention_respected=(
            bounded_retention_respected
            if policy.enforce_retention_bound
            else True
        ),
        evidence_status=evidence_status,
        task_outcome=task_outcome,
        refusal_status=refusal_status,
        reason_codes=tuple(sorted(set(reason_codes))),
        cost_units=cost_units,
        latency_units=latency_units,
    )


def _parse_case(value: object) -> MemoryPolicyCase:
    if not isinstance(value, dict):
        raise MemoryPolicyInputError("case_not_object")
    _require_exact_keys(
        value,
        {
            "case_id",
            "workflow_id",
            "memory_items",
            "must_retain",
            "must_not_retain",
            "max_retained_items",
        },
        "case",
    )
    case_id = _non_empty_string(value["case_id"], "case_id")
    workflow_id = _non_empty_string(value["workflow_id"], "workflow_id")
    memory_items = value["memory_items"]
    if not isinstance(memory_items, list) or not memory_items:
        raise MemoryPolicyInputError("empty_memory_items")
    parsed_items = tuple(_parse_item(item) for item in memory_items)
    item_ids = [item.item_id for item in parsed_items]
    if len(item_ids) != len(set(item_ids)):
        raise MemoryPolicyInputError("duplicate_memory_item_id")
    must_retain = _string_tuple(value["must_retain"], "must_retain")
    must_not_retain = _string_tuple(value["must_not_retain"], "must_not_retain")
    known_ids = set(item_ids)
    if not set(must_retain) <= known_ids or not set(must_not_retain) <= known_ids:
        raise MemoryPolicyInputError("memory_assertion_unknown_id")
    if set(must_retain) & set(must_not_retain):
        raise MemoryPolicyInputError("conflicting_memory_assertions")
    max_retained_items = value["max_retained_items"]
    if (
        not isinstance(max_retained_items, int)
        or isinstance(max_retained_items, bool)
        or max_retained_items < 1
    ):
        raise MemoryPolicyInputError("invalid_retention_bound")
    return MemoryPolicyCase(
        case_id=case_id,
        workflow_id=workflow_id,
        memory_items=parsed_items,
        must_retain=must_retain,
        must_not_retain=must_not_retain,
        max_retained_items=max_retained_items,
    )


def _parse_item(value: object) -> MemoryItem:
    if not isinstance(value, dict):
        raise MemoryPolicyInputError("memory_item_not_object")
    _require_exact_keys(
        value,
        {
            "item_id",
            "workflow_id",
            "kind",
            "age_rank",
            "required_for_safe_continuation",
        },
        "memory_item",
    )
    age_rank = value["age_rank"]
    if not isinstance(age_rank, int) or isinstance(age_rank, bool) or age_rank < 1:
        raise MemoryPolicyInputError("invalid_age_rank")
    required = value["required_for_safe_continuation"]
    if not isinstance(required, bool):
        raise MemoryPolicyInputError("invalid_required_flag")
    return MemoryItem(
        item_id=_non_empty_string(value["item_id"], "item_id"),
        workflow_id=_non_empty_string(value["workflow_id"], "workflow_id"),
        kind=_non_empty_string(value["kind"], "kind"),
        age_rank=age_rank,
        required_for_safe_continuation=required,
    )


def _require_exact_keys(
    value: dict[str, object],
    expected: set[str],
    label: str,
) -> None:
    if set(value) != expected:
        raise MemoryPolicyInputError(f"invalid_{label}_fields")


def _non_empty_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise MemoryPolicyInputError(f"invalid_{field_name}")
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise MemoryPolicyInputError(f"invalid_{field_name}")
    if len(value) != len(set(value)):
        raise MemoryPolicyInputError(f"duplicate_{field_name}")
    return tuple(value)
