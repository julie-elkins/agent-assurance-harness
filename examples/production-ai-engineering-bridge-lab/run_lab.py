"""Run the synthetic production AI engineering bridge lab.

The lab is intentionally provider-neutral. It emits bounded metadata only.
"""

from __future__ import annotations

import json
import sys


EXPECTED = {
    "data_contract": "observed",
    "access_check": "passed",
    "transport_status": "ok",
    "semantic_outcome": "empty_context",
    "tool_scope": "draft_only",
    "execution_authority": "missing_for_external_write",
    "guardrail_coverage": "complete_for_synthetic_boundaries",
    "privacy": "identifier_only",
    "operating_targets": "within_synthetic_targets",
    "evaluation": "blocked_by_known_negative_control",
    "incident_state": "contained",
    "recovery": "staged_for_human_review",
}


def build_result() -> dict[str, object]:
    """Return the deterministic learner-facing result."""

    return {
        "lab_version": 1,
        "scenario_id": "bounded-production-agent-rollback",
        "offline": True,
        "metadata_only": True,
        "data_contract": "observed",
        "access_check": "passed",
        "model_revision": "synthetic-model-rev-01",
        "retrieval_revision": "synthetic-kb-rev-03",
        "transport_status": "ok",
        "semantic_outcome": "empty_context",
        "tool_scope": "draft_only",
        "execution_authority": "missing_for_external_write",
        "guardrail_coverage": "complete_for_synthetic_boundaries",
        "privacy": "identifier_only",
        "operating_targets": "within_synthetic_targets",
        "retry_count": 0,
        "estimated_cost_usd": 0.0,
        "latency_ms": 120,
        "telemetry": {
            "workflow_id": "workflow-bridge-001",
            "evidence_ids": [
                "data-contract-observed",
                "access-check-passed",
                "transport-ok",
                "semantic-empty-context",
                "tool-scope-draft-only",
            ],
        },
        "evaluation": "blocked_by_known_negative_control",
        "incident_response": {
            "incident_state": "contained",
            "evidence_preserved": True,
            "external_action": "blocked_pending_approval",
            "notification": "human_review_required",
        },
        "incident_state": "contained",
        "recovery": "staged_for_human_review",
        "what_it_does_not_prove": [
            "live model quality",
            "production observability",
            "security approval",
            "rollback capability",
            "business impact",
        ],
    }


def main() -> int:
    """Print the result and fail if the teaching contract drifts."""

    result = build_result()
    mismatches = [
        key
        for key, expected in EXPECTED.items()
        if result.get(key) != expected
    ]
    result["contract_status"] = "pass" if not mismatches else "fail"
    if mismatches:
        result["contract_mismatches"] = mismatches
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not mismatches else 1


if __name__ == "__main__":
    sys.exit(main())
