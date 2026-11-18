from __future__ import annotations

import hashlib

from agent_reliability_lab.workflow_assurance import (
    evaluate_manifest,
    validate_manifest,
)


def digest(seed: str) -> str:
    return "sha256:" + hashlib.sha256(seed.encode()).hexdigest()


def manifest(**overrides):
    value = {
        "workflow_assurance_version": 1,
        "run_id": "review-run-001",
        "workflow_version": "item-triage-v1",
        "source_revision": digest("private-source"),
        "stages_expected": ["technical_accuracy", "cueing"],
        "stage_statuses": {
            "technical_accuracy": "completed",
            "cueing": "completed",
        },
        "counts": {"items": 12, "routed": 12, "incomplete": 0},
        "refusals": [],
        "evidence": {
            "status": "complete",
            "required": 4,
            "observed": 4,
            "missing": 0,
        },
        "artifact_hashes": {"review_report": digest("private-report")},
        "resources": {
            "observed": {
                "tool_calls": 24,
                "elapsed_seconds": 15.5,
                "output_bytes": 4096,
            },
            "limits": {
                "tool_calls": 100,
                "elapsed_seconds": 60,
                "output_bytes": 100000,
            },
            "within_limits": True,
        },
        "content_boundary": "metadata_only",
        "human_decision": "required",
    }
    value.update(overrides)
    return value


def test_complete_manifest_supports_human_review_without_authorizing_release():
    report = evaluate_manifest(manifest())

    assert report["decision"] == "pass_for_human_review"
    assert report["supports_human_review"] is True
    assert report["release_authorized"] is False


def test_refused_stage_blocks_human_review():
    value = manifest(
        stage_statuses={
            "technical_accuracy": "completed",
            "cueing": "refused",
        },
        refusals=["stage_refused"],
        evidence={
            "status": "incomplete",
            "required": 4,
            "observed": 3,
            "missing": 1,
        },
        counts={"items": 12, "routed": 12, "incomplete": 1},
    )

    report = evaluate_manifest(value)

    assert report["decision"] == "blocked"
    assert "expected_stage_not_completed" in report["blocking_reasons"]
    assert "workflow_refusal_present" in report["blocking_reasons"]
    assert report["release_authorized"] is False


def test_content_bearing_field_is_refused():
    value = manifest()
    value["answer_key"] = "must never cross the boundary"

    report = evaluate_manifest(value)

    assert report["decision"] == "blocked"
    assert report["refusal"]["error"] == "review_workflow_manifest_refused"


def test_inconsistent_resource_flag_is_refused():
    value = manifest()
    value["resources"]["within_limits"] = False

    report = evaluate_manifest(value)

    assert report["decision"] == "blocked"
    assert report["refusal"]["error"] == "review_workflow_manifest_refused"


def test_validation_normalizes_only_metadata():
    normalized = validate_manifest(manifest())

    assert normalized["counts"] == {"items": 12, "routed": 12, "incomplete": 0}
    assert "items" not in normalized
    assert normalized["content_boundary"] == "metadata_only"
