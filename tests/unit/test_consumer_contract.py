import json
from dataclasses import replace

from agent_reliability_lab.consumer_contract import (
    ConsumerPolicyManifest,
    evaluate_consumer_contract,
    load_consumer_policy_manifest,
    policy_digest,
)


def _manifest() -> ConsumerPolicyManifest:
    manifest = ConsumerPolicyManifest(
        manifest_version=1,
        policy_version="consumer-policy-v1",
        policy_sha256="",
        required_authorization_scope="orders:write",
        authorization_scenario_id="ambiguous-side-effect-retry",
        required_escalation_status="escalated",
        escalation_scenario_id="inappropriate-answer",
    )
    return replace(manifest, policy_sha256=policy_digest(manifest))


def _metadata() -> dict[str, dict[str, object]]:
    manifest = _manifest()
    return {
        scenario_id: {
            "policy_version": manifest.policy_version,
            "policy_digest": manifest.policy_sha256,
            "authorization_scopes": (
                ["orders:write"]
                if scenario_id == "ambiguous-side-effect-retry"
                else []
            ),
            "escalation_status": (
                "escalated" if scenario_id == "inappropriate-answer" else None
            ),
            "escalation_id": (
                "escalation-001" if scenario_id == "inappropriate-answer" else None
            ),
        }
        for scenario_id in (
            "tool-misuse",
            "false-completion",
            "inappropriate-answer",
            "unauthorized-side-effect",
            "misleading-tool-output",
            "ambiguous-side-effect-retry",
            "evidence-freshness-source",
            "evidence-stale-approved-source",
            "evidence-fresh-wrong-source",
        )
    }


def test_policy_manifest_round_trips_and_checks_canonical_digest(tmp_path):
    manifest = _manifest()
    path = tmp_path / "policy-manifest.json"
    path.write_text(json.dumps(manifest.to_dict()), encoding="utf-8")

    assert load_consumer_policy_manifest(path) == manifest


def test_consumer_contract_passes_metadata_only_positive_path():
    report = evaluate_consumer_contract(
        _metadata(),
        _manifest(),
        tuple(_metadata()),
    )

    assert report.passed is True
    assert report.failure_reasons == ()


def test_consumer_contract_separates_scope_and_escalation_failures():
    metadata = _metadata()
    metadata["ambiguous-side-effect-retry"]["authorization_scopes"] = ["orders:read"]
    metadata["inappropriate-answer"]["escalation_status"] = "not_escalated"
    metadata["inappropriate-answer"]["escalation_id"] = None

    report = evaluate_consumer_contract(
        metadata,
        _manifest(),
        tuple(metadata),
    )

    assert report.passed is False
    assert "authorization_scope_missing" in report.failure_reasons
    assert "escalation_missing" in report.failure_reasons
