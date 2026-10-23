"""Run the provider-neutral agent workflow teaching lab.

The lab is intentionally small: one bounded executor, one independent breaker
evaluation, and one human-approval boundary. It emits metadata only.
"""

from __future__ import annotations

import json

from agent_reliability_lab.adapters import trace_to_events
from agent_reliability_lab.scenarios import scenarios


SCENARIO_ID = "http-200-empty-context-retry"


def _summary(scenario, profile: str) -> dict[str, object]:
    trace = scenario.run_naive() if profile == "naive" else scenario.run_guarded()
    finding = scenario.evaluate(trace, scenario.contract)
    return {
        "profile": profile,
        "transport_status": trace.transport_status,
        "semantic_outcome": trace.semantic_outcome,
        "workflow_id": trace.workflow_id,
        "retry_count": trace.retry_count,
        "estimated_cost_usd": trace.estimated_cost_usd,
        "finding_status": finding.status.value,
        "missing_evidence": list(finding.missing_evidence),
        "event_count": len(trace_to_events(trace)),
    }


def main() -> int:
    """Run the lab and return success only when both controls behave as expected."""

    scenario = next(
        item for item in scenarios() if item.scenario_id == SCENARIO_ID
    )
    result = {
        "lab_version": 1,
        "scenario_id": SCENARIO_ID,
        "roles": ["bounded_executor", "independent_breaker", "human_approver"],
        "naive": _summary(scenario, "naive"),
        "guarded": _summary(scenario, "guarded"),
        "human_approval_required": True,
        "offline": True,
        "metadata_only": True,
        "what_it_does_not_prove": [
            "live model quality",
            "production observability",
            "learner reach or adoption",
        ],
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return int(
        result["naive"]["finding_status"] != "failed"
        or result["guarded"]["finding_status"] != "completed"
    )


if __name__ == "__main__":
    raise SystemExit(main())
