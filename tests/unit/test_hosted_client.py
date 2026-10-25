import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent_reliability_lab.hosted_client import (
    AwsCredentials,
    HostedControlPlaneClient,
    HostedResponse,
    build_local_run,
    decision_view,
    load_aws_cli_credentials,
    load_safe_submission,
    sign_request,
    validate_endpoint,
)


ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "examples/run-manifest/manifest.json"
CURRENT = ROOT / "examples/run-manifest/current-revisions.json"


def _credentials() -> AwsCredentials:
    return AwsCredentials(
        "ASIAEXAMPLE",
        "secret-value-must-not-leak",
        "session-token",
    )


def test_endpoint_requires_https_api_gateway_url_in_selected_region():
    endpoint = "https://abc123.execute-api.us-east-2.amazonaws.com/v1"

    assert validate_endpoint(endpoint, "us-east-2") == endpoint

    with pytest.raises(ValueError, match="HTTPS API Gateway"):
        validate_endpoint(
            "http://abc123.execute-api.us-east-2.amazonaws.com/v1",
            "us-east-2",
        )
    with pytest.raises(ValueError, match="HTTPS API Gateway"):
        validate_endpoint(
            "https://abc123.execute-api.us-west-2.amazonaws.com/v1",
            "us-east-2",
        )
    with pytest.raises(ValueError, match="HTTPS API Gateway"):
        validate_endpoint(
            "https://abc123.execute-api.us-east-2.amazonaws.com/v1?redirect=1",
            "us-east-2",
        )


def test_sigv4_request_contains_authentication_metadata_without_secret():
    request = sign_request(
        "POST",
        "https://abc123.execute-api.us-east-2.amazonaws.com/v1/reauthorizations",
        b'{"metadata":"synthetic"}',
        _credentials(),
        "us-east-2",
        now=datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc),
    )

    assert request.headers["x-amz-date"] == "20261025T120000Z"
    assert "AWS4-HMAC-SHA256" in request.headers["authorization"]
    assert "secret-value-must-not-leak" not in json.dumps(dict(request.headers))


def test_aws_credential_refusal_does_not_echo_cli_output():
    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0],
            1,
            stdout="",
            stderr="secret-value-must-not-leak",
        )

    credentials, refusal = load_aws_cli_credentials(
        "agent-assurance-admin",
        "us-east-2",
        runner=runner,
    )

    assert credentials is None
    assert refusal is not None
    assert "secret-value-must-not-leak" not in json.dumps(refusal)


def test_provider_bridge_reuses_one_safe_manifest_shape_for_both_providers():
    openai_payload = load_safe_submission(MANIFEST, CURRENT, provider="openai")
    anthropic_payload = load_safe_submission(
        MANIFEST,
        CURRENT,
        provider="anthropic",
    )

    assert set(openai_payload) == {"manifest", "current_revisions"}
    assert set(openai_payload["manifest"]) == set(anthropic_payload["manifest"])
    assert openai_payload["manifest"]["provider"] == "openai"
    assert anthropic_payload["manifest"]["provider"] == "anthropic"
    assert openai_payload["manifest"]["model"] == "openai-synthetic"
    assert anthropic_payload["manifest"]["model"] == "anthropic-synthetic"
    assert "within_limits" not in openai_payload["manifest"]["budget"]
    assert "prompt" not in openai_payload["manifest"]
    assert "provider_output" not in openai_payload["manifest"]


def test_provider_bridge_rejects_unknown_provider():
    with pytest.raises(ValueError, match="openai or anthropic"):
        load_safe_submission(MANIFEST, CURRENT, provider="unknown")


def test_decision_view_drops_submitter_identity_and_unknown_fields():
    view = decision_view(
        {
            "run_id": "run-001",
            "status": "reauthorized",
            "supports_decision": True,
            "submitted_by": "arn:aws:sts::private",
            "unexpected": "must not pass through",
        }
    )

    assert view == {
        "run_id": "run-001",
        "status": "reauthorized",
        "supports_decision": True,
    }


def test_build_local_run_submits_then_retrieves_bounded_decision():
    calls = []

    def credentials_loader(profile, region):
        assert profile == "agent-assurance-admin"
        assert region == "us-east-2"
        return _credentials(), None

    def transport(request):
        calls.append(request)
        if request.method == "POST":
            return HostedResponse(
                200,
                {
                    "run_id": "run-synthetic-001",
                    "audit_id": "audit-001",
                    "status": "reauthorized",
                    "supports_decision": True,
                },
            )
        return HostedResponse(
            200,
            {
                "run_id": "run-synthetic-001",
                "status": "reauthorized",
                "supports_decision": True,
                "submitted_by": "arn:aws:sts::private",
                "expires_at_epoch": 1795524049,
            },
        )

    client = HostedControlPlaneClient(
        "https://abc123.execute-api.us-east-2.amazonaws.com/v1",
        "agent-assurance-admin",
        "us-east-2",
        credentials_loader=credentials_loader,
        transport=transport,
    )
    result = build_local_run(client, MANIFEST, CURRENT, provider="openai")

    assert result["provider"] == "openai"
    assert result["latest"] == {
        "expires_at_epoch": 1795524049,
        "run_id": "run-synthetic-001",
        "status": "reauthorized",
        "supports_decision": True,
    }
    assert [request.method for request in calls] == ["POST", "GET"]
    assert all(request.url.startswith("https://") for request in calls)
