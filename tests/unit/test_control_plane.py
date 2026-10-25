from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent_reliability_lab import control_plane_handler
from agent_reliability_lab.control_plane import (
    AUDIT_RETENTION_DAYS,
    ControlPlaneValidationError,
    InMemoryAuditStore,
    get_latest,
    submit,
)


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "examples" / "run-manifest" / "manifest.json"
CURRENT_REVISIONS_PATH = (
    ROOT / "examples" / "run-manifest" / "current-revisions.json"
)
CHANGED_REVISIONS_PATH = (
    ROOT / "examples" / "run-manifest" / "changed-revisions.json"
)
NOW = datetime(2026, 10, 25, 15, 0, tzinfo=timezone.utc)


def _payload(revisions_path: Path) -> dict[str, object]:
    return {
        "manifest": json.loads(MANIFEST_PATH.read_text(encoding="utf-8")),
        "current_revisions": json.loads(revisions_path.read_text(encoding="utf-8")),
    }


def test_submit_reuses_local_decision_and_appends_metadata_only_record():
    store = InMemoryAuditStore()

    result = submit(
        _payload(CURRENT_REVISIONS_PATH),
        principal_id="arn:aws:iam::123456789012:user/tester",
        store=store,
        now=NOW,
    )

    assert result["status"] == "reauthorized"
    assert result["supports_decision"] is True
    record = get_latest("run-synthetic-001", store=store)
    assert record is not None
    assert record["expires_at_epoch"] > int(NOW.timestamp())
    assert record["expires_at_epoch"] == int(
        NOW.timestamp() + AUDIT_RETENTION_DAYS * 24 * 60 * 60
    )
    assert "prompt" not in record
    assert "tool_arguments" not in record
    assert "provider_output" not in record


def test_submit_blocks_stale_evidence_and_records_changed_dependencies():
    store = InMemoryAuditStore()

    result = submit(
        _payload(CHANGED_REVISIONS_PATH),
        principal_id="arn:aws:iam::123456789012:user/tester",
        store=store,
        now=NOW,
    )

    assert result["status"] == "reauthorization_required"
    assert result["supports_decision"] is False
    assert result["changed_dependencies"] == ["prompt", "tools"]
    assert get_latest("run-synthetic-001", store=store)["status"] == (
        "reauthorization_required"
    )


def test_unknown_manifest_field_is_refused_before_evaluation():
    payload = _payload(CURRENT_REVISIONS_PATH)
    payload["manifest"]["unexpected_payload"] = "must not be accepted"

    with pytest.raises(ControlPlaneValidationError, match="unsupported fields"):
        submit(
            payload,
            principal_id="arn:aws:iam::123456789012:user/tester",
            store=InMemoryAuditStore(),
            now=NOW,
        )


def test_missing_record_does_not_read_as_approved():
    assert get_latest("never-submitted", store=InMemoryAuditStore()) is None


def test_handler_rejects_unauthenticated_request_before_storage():
    response = control_plane_handler.lambda_handler(
        {
            "httpMethod": "POST",
            "resource": "/v1/reauthorizations",
            "body": "{}",
        },
        None,
    )

    assert response["statusCode"] == 401
    assert "authentication_required" in response["body"]


def test_handler_returns_structured_refusal_for_invalid_manifest(monkeypatch):
    monkeypatch.setattr(
        control_plane_handler,
        "_STORE",
        InMemoryAuditStore(),
    )
    payload = _payload(CURRENT_REVISIONS_PATH)
    payload["manifest"]["budget"]["observed"]["requests"] = -1
    response = control_plane_handler.lambda_handler(
        {
            "httpMethod": "POST",
            "resource": "/v1/reauthorizations",
            "body": json.dumps(payload),
            "requestContext": {
                "identity": {
                    "userArn": "arn:aws:iam::123456789012:user/tester",
                }
            },
        },
        None,
    )

    assert response["statusCode"] == 400
    assert "metadata_submission_invalid" in response["body"]
