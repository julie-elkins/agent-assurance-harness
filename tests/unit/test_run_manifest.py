from datetime import datetime, timezone

import pytest

from agent_reliability_lab.run_manifest import (
    REQUIRED_REVISION_KEYS,
    RUN_MANIFEST_STATUS_BLOCKED,
    RUN_MANIFEST_STATUS_REAUTHORIZED,
    RUN_MANIFEST_STATUS_REAUTHORIZATION_REQUIRED,
    RunManifest,
    RunManifestValidationError,
    evaluate_reauthorization,
)


def _revisions(**overrides):
    values = {key: f"{key}-r1" for key in REQUIRED_REVISION_KEYS}
    values.update(overrides)
    return values


def _manifest(**overrides):
    value = {
        "manifest_version": 1,
        "run_id": "run-001",
        "decision_target": "release-agent-v1",
        "actor_id": "julie",
        "agent_id": "agent-demo",
        "provider": "anthropic",
        "model": "claude-synthetic",
        "revisions": _revisions(),
        "tool_scope": ["lookup_policy", "check_status"],
        "budget": {
            "observed": {
                "requests": 3,
                "output_tokens": 900,
                "elapsed_seconds": 12.5,
                "estimated_cost_usd": 0.12,
            },
            "limits": {
                "max_requests": 5,
                "max_output_tokens": 2000,
                "max_elapsed_seconds": 60,
                "max_estimated_cost_usd": 1.0,
            },
            "stop_condition": "stop after 5 requests or 60 seconds",
        },
        "checkpoint": {
            "checkpoint_id": "checkpoint-001",
            "checkpoint_revision": "checkpoint-r1",
            "resume_supported": True,
        },
        "repeatability": {
            "run_count": 3,
            "successful_run_count": 3,
            "variance": {"task_success_rate": 0.0},
        },
        "grader_version": "grader-r1",
        "evidence": {
            "scope": ["release-agent-v1"],
            "digest": "sha256:" + "a" * 64,
            "expires_at": "2026-12-01T00:00:00Z",
            "observed_outcome": "success",
        },
        "created_at": "2026-10-25T12:00:00Z",
    }
    value.update(overrides)
    return value


def test_current_manifest_is_reauthorized():
    manifest = RunManifest.from_dict(_manifest())

    decision = evaluate_reauthorization(
        manifest,
        _revisions(),
        now=datetime(2026, 10, 25, tzinfo=timezone.utc),
    )

    assert decision.status == RUN_MANIFEST_STATUS_REAUTHORIZED
    assert decision.supports_decision is True
    assert decision.changed_dependencies == ()
    assert decision.reasons == ()
    assert decision.manifest_digest.startswith("sha256:")


def test_changed_prompt_requires_reauthorization():
    manifest = RunManifest.from_dict(_manifest())

    decision = evaluate_reauthorization(
        manifest,
        _revisions(prompt="prompt-r2"),
        now=datetime(2026, 10, 25, tzinfo=timezone.utc),
    )

    assert decision.status == RUN_MANIFEST_STATUS_REAUTHORIZATION_REQUIRED
    assert decision.supports_decision is False
    assert decision.changed_dependencies == ("prompt",)
    assert decision.reasons == ("dependency_revision_changed",)


def test_expired_evidence_requires_reauthorization():
    manifest = RunManifest.from_dict(
        _manifest(
            evidence={
                "scope": ["release-agent-v1"],
                "digest": "sha256:" + "a" * 64,
                "expires_at": "2026-10-24T00:00:00Z",
                "observed_outcome": "success",
            }
        )
    )

    decision = evaluate_reauthorization(
        manifest,
        _revisions(),
        now=datetime(2026, 10, 25, tzinfo=timezone.utc),
    )

    assert decision.status == RUN_MANIFEST_STATUS_REAUTHORIZATION_REQUIRED
    assert decision.reasons == ("evidence_expired",)


@pytest.mark.parametrize(
    "change",
    [
        {"evidence": {
            "scope": ["release-agent-v1"],
            "digest": "sha256:" + "a" * 64,
            "expires_at": "2026-12-01T00:00:00Z",
            "observed_outcome": "failed",
        }},
        {
            "repeatability": {
                "run_count": 1,
                "successful_run_count": 1,
                "variance": {},
            }
        },
    ],
)
def test_unsupported_evidence_is_blocked(change):
    manifest = RunManifest.from_dict(_manifest(**change))

    decision = evaluate_reauthorization(manifest, _revisions())

    assert decision.status == RUN_MANIFEST_STATUS_BLOCKED
    assert decision.supports_decision is False


def test_missing_current_revision_is_blocked():
    manifest = RunManifest.from_dict(_manifest())
    current = _revisions()
    del current["grader"]

    decision = evaluate_reauthorization(manifest, current)

    assert decision.status == RUN_MANIFEST_STATUS_BLOCKED
    assert "current revisions missing: grader" in decision.reasons


def test_raw_payload_like_whitespace_is_rejected_from_revision_ids():
    invalid = _manifest()
    invalid["revisions"] = _revisions(prompt="do not store prompt text")

    with pytest.raises(RunManifestValidationError, match="whitespace"):
        RunManifest.from_dict(invalid)
