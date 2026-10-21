import json
from pathlib import Path

from agent_reliability_lab.consumer_compatibility import (
    ConsumerCompatibilityManifest,
    evaluate_consumer_compatibility,
    load_consumer_compatibility_manifest,
)


def _manifest() -> ConsumerCompatibilityManifest:
    return ConsumerCompatibilityManifest(
        compatibility_version=1,
        required_action_ref="a" * 40,
        required_reusable_action_version=1,
        required_consumer_validation_version=3,
        required_policy_manifest_version=1,
    )


def _runs() -> dict[str, dict[str, object]]:
    return {
        name: {
            "report_version": 1,
            "policy_manifest_version": 1,
        }
        for name in ("positive", "negative", "policy-drift", "policy-restored")
    }


def test_compatibility_manifest_round_trips(tmp_path: Path):
    manifest = _manifest()
    path = tmp_path / "compatibility.json"
    path.write_text(json.dumps(manifest.to_dict()), encoding="utf-8")

    assert load_consumer_compatibility_manifest(path) == manifest


def test_compatibility_checks_every_run():
    report = evaluate_consumer_compatibility(
        _manifest(),
        action_ref="a" * 40,
        consumer_validation_version=3,
        runs=_runs(),
    )

    assert report.passed is True
    assert report.failure_reasons == ()


def test_compatibility_blocks_old_action_pin_and_report_version():
    runs = _runs()
    runs["policy-drift"]["report_version"] = 2
    report = evaluate_consumer_compatibility(
        _manifest(),
        action_ref="b" * 40,
        consumer_validation_version=2,
        runs=runs,
    )

    assert report.passed is False
    assert "action_pin_mismatch" in report.failure_reasons
    assert "consumer_validation_version_mismatch" in report.failure_reasons
    assert "reusable_action_version_mismatch" in report.failure_reasons
