"""Constrained, metadata-only comparison of synthetic agent candidates."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable


_PASS = "passed"
_HELD_OUT_PASS = "passed"


@dataclass(frozen=True)
class CandidateEvaluation:
    """Synthetic candidate metrics used for a bounded comparison.

    The scores are metadata, not model output. ``total_cost_units`` must include
    the repeated runs and retries represented by the candidate record.
    """

    candidate_id: str
    safety_status: str
    evidence_status: str
    held_out_status: str
    quality_scores: tuple[float, ...]
    total_cost_units: float
    latency_units: float

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("candidate_id must not be empty")
        if not self.quality_scores:
            raise ValueError("quality_scores must not be empty")
        numeric_values = (
            *self.quality_scores,
            self.total_cost_units,
            self.latency_units,
        )
        if any(not isfinite(value) for value in numeric_values):
            raise ValueError("candidate metrics must be finite")
        if any(value < 0 for value in self.quality_scores):
            raise ValueError("quality_scores must be non-negative")
        if not 0 <= self.quality_mean <= 1:
            raise ValueError("quality_scores must be between 0 and 1")
        if self.total_cost_units < 0 or self.latency_units < 0:
            raise ValueError("cost and latency must be non-negative")

    @property
    def quality_mean(self) -> float:
        """Return the mean repeated-run quality score."""

        return sum(self.quality_scores) / len(self.quality_scores)

    @property
    def quality_spread(self) -> float:
        """Return the observed max-minus-min repeated-run variation."""

        return max(self.quality_scores) - min(self.quality_scores)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CandidateEvaluation":
        """Load one bounded candidate record from JSON-compatible metadata."""

        try:
            return cls(
                candidate_id=str(value["candidate_id"]),
                safety_status=str(value["safety_status"]),
                evidence_status=str(value["evidence_status"]),
                held_out_status=str(value["held_out_status"]),
                quality_scores=tuple(
                    float(item) for item in value["quality_scores"]
                ),
                total_cost_units=float(value["total_cost_units"]),
                latency_units=float(value["latency_units"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("invalid candidate metadata") from error

    def metrics(self) -> dict[str, object]:
        """Return only bounded numeric metadata."""

        return {
            "quality_mean": round(self.quality_mean, 6),
            "quality_spread": round(self.quality_spread, 6),
            "repeat_count": len(self.quality_scores),
            "total_cost_units": self.total_cost_units,
            "latency_units": self.latency_units,
        }


@dataclass(frozen=True)
class ParetoConstraints:
    """Hard gates applied before quality/cost/latency comparison."""

    max_quality_spread: float = 0.10
    require_safety_pass: bool = True
    require_evidence_pass: bool = True
    require_held_out_pass: bool = True

    def __post_init__(self) -> None:
        if self.max_quality_spread < 0 or not isfinite(self.max_quality_spread):
            raise ValueError("max_quality_spread must be finite and non-negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "max_quality_spread": self.max_quality_spread,
            "require_safety_pass": self.require_safety_pass,
            "require_evidence_pass": self.require_evidence_pass,
            "require_held_out_pass": self.require_held_out_pass,
        }


@dataclass(frozen=True)
class CandidateDecision:
    """The safe disposition of one candidate identifier."""

    candidate_id: str
    status: str
    reasons: tuple[str, ...]
    metrics: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "status": self.status,
            "reasons": list(self.reasons),
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True)
class ParetoComparison:
    """A human-review frontier without an automatic final selection."""

    candidates: tuple[CandidateDecision, ...]
    frontier_ids: tuple[str, ...]
    constraints: ParetoConstraints

    @property
    def decision(self) -> str:
        return "review_frontier"

    def to_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision,
            "frontier_ids": list(self.frontier_ids),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "constraints": self.constraints.to_dict(),
            "objectives": {
                "quality_mean": "maximize",
                "total_cost_units": "minimize",
                "latency_units": "minimize",
            },
            "human_review_required": True,
            "diagnostics": {
                "warnings": [
                    "All values are synthetic metadata; no provider call was made.",
                    "Total cost includes the repeated runs and retries represented by each candidate.",
                    "A frontier is not a release approval or an automatic winner.",
                ],
                "what_it_does_not_prove": (
                    "It does not prove live model quality, production safety, "
                    "global optimality, or that the tested candidates generalize."
                ),
            },
        }


def _constraint_reasons(
    candidate: CandidateEvaluation,
    constraints: ParetoConstraints,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if constraints.require_safety_pass and candidate.safety_status != _PASS:
        reasons.append("safety_not_passed")
    if constraints.require_evidence_pass and candidate.evidence_status != _PASS:
        reasons.append("evidence_not_complete")
    if (
        constraints.require_held_out_pass
        and candidate.held_out_status != _HELD_OUT_PASS
    ):
        reasons.append("held_out_not_passed")
    if candidate.quality_spread > constraints.max_quality_spread:
        reasons.append("repeated_run_variation_above_limit")
    return tuple(reasons)


def _dominates(left: CandidateEvaluation, right: CandidateEvaluation) -> bool:
    """Return whether left is at least as good on every objective and better on one."""

    left_values = (
        left.quality_mean,
        -left.total_cost_units,
        -left.latency_units,
    )
    right_values = (
        right.quality_mean,
        -right.total_cost_units,
        -right.latency_units,
    )
    return (
        all(
            left_value >= right_value
            for left_value, right_value in zip(left_values, right_values)
        )
        and any(
            left_value > right_value
            for left_value, right_value in zip(left_values, right_values)
        )
    )


def compare_candidates(
    candidates: Iterable[CandidateEvaluation],
    *,
    constraints: ParetoConstraints | None = None,
) -> ParetoComparison:
    """Apply hard gates, then calculate the non-dominated candidate frontier."""

    selected_constraints = constraints or ParetoConstraints()
    candidate_list = tuple(candidates)
    if not candidate_list:
        raise ValueError("at least one candidate is required")
    identifiers = [candidate.candidate_id for candidate in candidate_list]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("candidate_id values must be unique")

    eligible = [
        candidate
        for candidate in candidate_list
        if not _constraint_reasons(candidate, selected_constraints)
    ]
    frontier = tuple(
        candidate
        for candidate in eligible
        if not any(
            _dominates(other, candidate)
            for other in eligible
            if other.candidate_id != candidate.candidate_id
        )
    )
    frontier_ids = tuple(candidate.candidate_id for candidate in frontier)
    decisions: list[CandidateDecision] = []
    for candidate in candidate_list:
        reasons = _constraint_reasons(candidate, selected_constraints)
        if reasons:
            status = "excluded"
        elif candidate.candidate_id in frontier_ids:
            status = "frontier"
        else:
            status = "dominated"
            reasons = ("dominated_by_eligible_candidate",)
        decisions.append(
            CandidateDecision(
                candidate_id=candidate.candidate_id,
                status=status,
                reasons=reasons,
                metrics=candidate.metrics(),
            )
        )
    return ParetoComparison(
        candidates=tuple(decisions),
        frontier_ids=frontier_ids,
        constraints=selected_constraints,
    )
