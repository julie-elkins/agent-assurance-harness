"""Synthetic shadow execution for proposed agent side effects.

Design rules:

1. Shadow execution simulates an action; it never writes to an external system.
2. Action metadata is identifier-only so the receipt cannot become a tool-payload
   transport or a provider transcript store.
3. Missing authority blocks before the simulator runs.
4. A mismatch or ambiguous effect requires human review rather than being read as
   a successful action.
5. The receipt records what was checked and what it does not prove.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Sequence


SHADOW_EXECUTION_VERSION = 1
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
_AUTHORITY_VALUES = frozenset({"granted", "missing", "revoked"})
_OUTCOME_VALUES = frozenset(
    {"matched", "mismatched", "not_observed", "ambiguous"}
)
_DECISION_VALUES = frozenset({"allow", "block", "human_review"})


class ShadowDecision(str, Enum):
    """The bounded decision after one synthetic shadow run."""

    ALLOW = "allow"
    BLOCK = "block"
    HUMAN_REVIEW = "human_review"


class ShadowOutcome(str, Enum):
    """The synthetic observation produced by the shadow simulator."""

    MATCHED = "matched"
    MISMATCHED = "mismatched"
    NOT_OBSERVED = "not_observed"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class ShadowAction:
    """Identifier-only metadata for one proposed side effect."""

    action_id: str
    operation_id: str
    tool_name: str
    effect_class: str
    intended_effect: str
    policy_revision: str
    authority_status: str
    requires_human_approval: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return the safe action contract without arguments or payloads."""

        return {
            "action_id": self.action_id,
            "operation_id": self.operation_id,
            "tool_name": self.tool_name,
            "effect_class": self.effect_class,
            "intended_effect": self.intended_effect,
            "policy_revision": self.policy_revision,
            "authority_status": self.authority_status,
            "requires_human_approval": self.requires_human_approval,
        }


@dataclass(frozen=True)
class ShadowCase:
    """One named synthetic action and its simulator outcome."""

    case_id: str
    action: ShadowAction
    outcome: ShadowOutcome
    expected_decision: ShadowDecision

    def to_dict(self) -> dict[str, object]:
        """Return the fixture shape used by the public demo."""

        return {
            "case_id": self.case_id,
            "action": self.action.to_dict(),
            "simulation": {
                "outcome": self.outcome.value,
                "expected_decision": self.expected_decision.value,
            },
        }


@dataclass(frozen=True)
class ShadowRefusal:
    """A structured refusal for invalid shadow input."""

    error: str
    message: str
    guidance: str
    source: str

    def to_dict(self) -> dict[str, str]:
        """Return a safe refusal without the invalid payload."""

        return {
            "error": self.error,
            "message": self.message,
            "guidance": self.guidance,
            "source": self.source,
        }


@dataclass(frozen=True)
class ShadowReceipt:
    """Metadata-only evidence from one simulated action."""

    case_id: str
    action_id: str
    operation_id: str
    tool_name: str
    effect_class: str
    policy_revision: str
    decision: ShadowDecision
    reason_codes: tuple[str, ...]
    intended_effect_digest: str
    observed_effect_digest: str | None
    authority_checked_before_simulation: bool
    simulation_ran: bool
    real_side_effects_attempted: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return the portable receipt shape."""

        return {
            "shadow_execution_version": SHADOW_EXECUTION_VERSION,
            "case_id": self.case_id,
            "action_id": self.action_id,
            "operation_id": self.operation_id,
            "tool_name": self.tool_name,
            "effect_class": self.effect_class,
            "policy_revision": self.policy_revision,
            "decision": self.decision.value,
            "reason_codes": list(self.reason_codes),
            "intended_effect_digest": self.intended_effect_digest,
            "observed_effect_digest": self.observed_effect_digest,
            "controls": {
                "authority_checked_before_simulation": (
                    self.authority_checked_before_simulation
                ),
                "simulation_ran": self.simulation_ran,
                "real_side_effects_attempted": self.real_side_effects_attempted,
            },
            "diagnostics": {
                "warnings": [
                    "This receipt records a deterministic synthetic simulation, "
                    "not a real tool execution."
                ],
                "what_it_does_not_show": (
                    "It does not prove operating-system isolation, rollback, "
                    "live-tool compatibility, provider quality, or production safety."
                ),
            },
        }


@dataclass(frozen=True)
class ShadowCaseResult:
    """One checked case or one structured refusal."""

    case_id: str
    receipt: ShadowReceipt | None = None
    refusal: ShadowRefusal | None = None

    @property
    def passed(self) -> bool:
        """Return whether the case produced a receipt without refusal."""

        return self.receipt is not None and self.refusal is None

    def to_dict(self) -> dict[str, object]:
        """Return a safe case result."""

        return {
            "case_id": self.case_id,
            "receipt": self.receipt.to_dict() if self.receipt else None,
            "refusal": self.refusal.to_dict() if self.refusal else None,
        }


@dataclass(frozen=True)
class ShadowExecutionReport:
    """Metadata-only result for the complete synthetic shadow fixture."""

    cases: tuple[ShadowCaseResult, ...]
    expected_decisions: dict[str, str]

    @property
    def passed(self) -> bool:
        """Return whether every case matched its declared expected decision."""

        for result in self.cases:
            expected = self.expected_decisions.get(result.case_id)
            if result.refusal is not None or result.receipt is None:
                return False
            if result.receipt.decision.value != expected:
                return False
        return bool(self.cases)

    def to_dict(self) -> dict[str, object]:
        """Return a public-safe report with counts and decisions."""

        decision_counts = {decision: 0 for decision in sorted(_DECISION_VALUES)}
        refusal_count = 0
        for result in self.cases:
            if result.receipt is not None:
                decision_counts[result.receipt.decision.value] += 1
            if result.refusal is not None:
                refusal_count += 1
        return {
            "shadow_execution_version": SHADOW_EXECUTION_VERSION,
            "passed": self.passed,
            "case_count": len(self.cases),
            "decision_counts": decision_counts,
            "refusal_count": refusal_count,
            "cases": [case.to_dict() for case in self.cases],
            "diagnostics": {
                "warnings": [
                    "The report uses synthetic action metadata and simulator "
                    "outcomes only."
                ],
                "what_it_does_not_show": (
                    "It does not show that a real external side effect would be "
                    "safe, reversible, or correctly recorded."
                ),
            },
        }

    def to_markdown(self) -> str:
        """Return a concise reviewer-facing summary."""

        lines = [
            "# Shadow execution",
            "",
            f"- **Decision:** {'PASS' if self.passed else 'BLOCKED'}",
            f"- **Cases checked:** {len(self.cases)}",
            "- **Real side effects:** none",
            "",
            "## Case decisions",
            "",
            "| Case | Decision | Reason codes |",
            "| --- | --- | --- |",
        ]
        for result in self.cases:
            if result.receipt is None:
                decision = "BLOCKED"
                reasons = "structured_refusal"
            else:
                decision = result.receipt.decision.value
                reasons = ", ".join(result.receipt.reason_codes)
            lines.append(f"| `{result.case_id}` | `{decision}` | {reasons} |")
        lines.extend(
            [
                "",
                "The simulator compares identifier-only intended and observed "
                "effects. It does not execute tools or prove production isolation.",
                "",
            ]
        )
        return "\n".join(lines)


def run_shadow_case(case: ShadowCase) -> ShadowCaseResult:
    """Run one case without invoking a real tool or external system."""

    try:
        _validate_case(case)
    except ValueError as error:
        return ShadowCaseResult(
            case_id=case.case_id,
            refusal=ShadowRefusal(
                error="shadow_input_refused",
                message="The shadow action could not be evaluated.",
                guidance=(
                    "Use identifier-only action metadata and a supported "
                    "synthetic simulator outcome."
                ),
                source=type(error).__name__,
            ),
        )

    intended_digest = _effect_digest(case.action, case.action.intended_effect)
    if case.action.authority_status != "granted":
        return ShadowCaseResult(
            case_id=case.case_id,
            receipt=ShadowReceipt(
                case_id=case.case_id,
                action_id=case.action.action_id,
                operation_id=case.action.operation_id,
                tool_name=case.action.tool_name,
                effect_class=case.action.effect_class,
                policy_revision=case.action.policy_revision,
                decision=ShadowDecision.BLOCK,
                reason_codes=("execution_authority_missing",),
                intended_effect_digest=intended_digest,
                observed_effect_digest=None,
                authority_checked_before_simulation=True,
                simulation_ran=False,
            ),
        )

    observed_digest = _observed_digest(case.action, case.outcome)
    decision, reason_codes = _decision_for(case)
    return ShadowCaseResult(
        case_id=case.case_id,
        receipt=ShadowReceipt(
            case_id=case.case_id,
            action_id=case.action.action_id,
            operation_id=case.action.operation_id,
            tool_name=case.action.tool_name,
            effect_class=case.action.effect_class,
            policy_revision=case.action.policy_revision,
            decision=decision,
            reason_codes=reason_codes,
            intended_effect_digest=intended_digest,
            observed_effect_digest=observed_digest,
            authority_checked_before_simulation=True,
            simulation_ran=True,
        ),
    )


def run_shadow_cases(cases: Sequence[ShadowCase]) -> ShadowExecutionReport:
    """Evaluate the supplied synthetic cases in declaration order."""

    results = tuple(run_shadow_case(case) for case in cases)
    return ShadowExecutionReport(
        cases=results,
        expected_decisions={
            case.case_id: case.expected_decision.value for case in cases
        },
    )


def load_shadow_cases(path: Path) -> tuple[ShadowCase, ...]:
    """Load and strictly validate a public shadow fixture."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Shadow fixture must be an object.")
    _keys(
        data,
        {"shadow_execution_version", "data_class", "purpose", "cases"},
        "shadow fixture",
    )
    if data.get("shadow_execution_version") != SHADOW_EXECUTION_VERSION:
        raise ValueError("shadow_execution_version is not supported.")
    if data.get("data_class") != "synthetic":
        raise ValueError("data_class must be synthetic.")
    _identifier(data.get("purpose"), "purpose")
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("cases must be a non-empty list.")

    cases: list[ShadowCase] = []
    seen: set[str] = set()
    for index, raw_case in enumerate(raw_cases):
        case = _parse_case(raw_case, f"cases[{index}]")
        if case.case_id in seen:
            raise ValueError("cases contains a duplicate case_id.")
        seen.add(case.case_id)
        cases.append(case)
    return tuple(cases)


def _parse_case(value: object, context: str) -> ShadowCase:
    data = _object(value, context)
    _keys(data, {"case_id", "action", "simulation"}, context)
    case_id = _identifier(data.get("case_id"), f"{context}.case_id")
    action = _parse_action(data.get("action"), f"{context}.action")
    simulation = _object(data.get("simulation"), f"{context}.simulation")
    _keys(simulation, {"outcome", "expected_decision"}, f"{context}.simulation")
    outcome = _enum_value(
        simulation.get("outcome"),
        ShadowOutcome,
        f"{context}.simulation.outcome",
    )
    expected = _enum_value(
        simulation.get("expected_decision"),
        ShadowDecision,
        f"{context}.simulation.expected_decision",
    )
    return ShadowCase(
        case_id=case_id,
        action=action,
        outcome=outcome,
        expected_decision=expected,
    )


def _parse_action(value: object, context: str) -> ShadowAction:
    data = _object(value, context)
    _keys(
        data,
        {
            "action_id",
            "operation_id",
            "tool_name",
            "effect_class",
            "intended_effect",
            "policy_revision",
            "authority_status",
            "requires_human_approval",
        },
        context,
    )
    approval = data.get("requires_human_approval")
    if not isinstance(approval, bool):
        raise ValueError(f"{context}.requires_human_approval must be boolean.")
    authority = _identifier(
        data.get("authority_status"),
        f"{context}.authority_status",
    )
    if authority not in _AUTHORITY_VALUES:
        raise ValueError(f"{context}.authority_status is unsupported.")
    return ShadowAction(
        action_id=_identifier(data.get("action_id"), f"{context}.action_id"),
        operation_id=_identifier(
            data.get("operation_id"), f"{context}.operation_id"
        ),
        tool_name=_identifier(data.get("tool_name"), f"{context}.tool_name"),
        effect_class=_identifier(
            data.get("effect_class"), f"{context}.effect_class"
        ),
        intended_effect=_identifier(
            data.get("intended_effect"), f"{context}.intended_effect"
        ),
        policy_revision=_identifier(
            data.get("policy_revision"), f"{context}.policy_revision"
        ),
        authority_status=authority,
        requires_human_approval=approval,
    )


def _validate_case(case: ShadowCase) -> None:
    _identifier(case.case_id, "case_id")
    _validate_action(case.action)
    if case.outcome.value not in _OUTCOME_VALUES:
        raise ValueError("outcome is unsupported.")
    if case.expected_decision.value not in _DECISION_VALUES:
        raise ValueError("expected_decision is unsupported.")


def _validate_action(action: ShadowAction) -> None:
    for field, value in action.to_dict().items():
        if field == "requires_human_approval":
            continue
        _identifier(value, f"action.{field}")
    if action.authority_status not in _AUTHORITY_VALUES:
        raise ValueError("action.authority_status is unsupported.")


def _decision_for(
    case: ShadowCase,
) -> tuple[ShadowDecision, tuple[str, ...]]:
    if case.action.requires_human_approval:
        return ShadowDecision.HUMAN_REVIEW, ("human_approval_required",)
    if case.outcome is ShadowOutcome.MATCHED:
        return ShadowDecision.ALLOW, ("shadow_effect_matched",)
    if case.outcome is ShadowOutcome.MISMATCHED:
        return ShadowDecision.HUMAN_REVIEW, ("shadow_effect_mismatch",)
    if case.outcome is ShadowOutcome.NOT_OBSERVED:
        return ShadowDecision.HUMAN_REVIEW, ("effect_not_observed",)
    return ShadowDecision.HUMAN_REVIEW, ("effect_state_ambiguous",)


def _effect_digest(action: ShadowAction, effect: str) -> str:
    value = {
        "action_id": action.action_id,
        "operation_id": action.operation_id,
        "effect_class": action.effect_class,
        "effect": effect,
        "policy_revision": action.policy_revision,
    }
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _observed_digest(
    action: ShadowAction,
    outcome: ShadowOutcome,
) -> str | None:
    if outcome is ShadowOutcome.NOT_OBSERVED:
        return None
    observed_effect = (
        action.intended_effect
        if outcome is ShadowOutcome.MATCHED
        else f"{action.intended_effect}:observed-difference"
    )
    return _effect_digest(action, observed_effect)


def _enum_value(
    value: object,
    enum_type: type[Enum],
    context: str,
) -> Any:
    if not isinstance(value, str):
        raise ValueError(f"{context} must be a string.")
    try:
        return enum_type(value)
    except ValueError as error:
        raise ValueError(f"{context} is unsupported.") from error


def _object(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be an object.")
    return value


def _keys(value: dict[str, Any], allowed: set[str], context: str) -> None:
    if set(value) - allowed:
        raise ValueError(f"{context} contains unknown fields.")


def _identifier(value: object, context: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{context} must be an identifier.")
    return value
