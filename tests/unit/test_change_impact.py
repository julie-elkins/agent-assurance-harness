import json
from pathlib import Path

from agent_reliability_lab.change_impact import (
    IMPACT_BLOCKED,
    IMPACT_READY,
    IMPACT_RERUN_REQUIRED,
    build_change_impact_plan,
    classify_paths,
)
from agent_reliability_lab.evidence_registry import (
    EvidenceRegistration,
)
from agent_reliability_lab.run_manifest import (
    REQUIRED_REVISION_KEYS,
    RunManifest,
)


ROOT = Path(__file__).parents[2]


def _revisions(**overrides):
    values = {key: f"{key}-r1" for key in REQUIRED_REVISION_KEYS}
    values.update(overrides)
    return values


def _manifest(**overrides):
    data = json.loads(
        (ROOT / "examples" / "run-manifest" / "manifest.json").read_text()
    )
    data.update(overrides)
    return RunManifest.from_dict(data)


def test_classify_paths_is_conservative_and_metadata_only():
    result = classify_paths(
        [
            "src/agent_reliability_lab/providers.py",
            "src/agent_reliability_lab/providers.py",
            "policies/release-policy.json",
            "README.md",
        ]
    )

    assert result["src/agent_reliability_lab/providers.py"] == ("model", "harness")
    assert result["policies/release-policy.json"] == ("policy",)
    assert "README.md" not in result


def test_unchanged_evidence_remains_valid():
    plan = build_change_impact_plan(
        [_manifest()],
        _revisions(),
        _revisions(),
    )

    assert plan.status == IMPACT_READY
    assert plan.evidence[0].status == IMPACT_READY
    assert plan.evidence[0].supports_decision is True


def test_revision_change_requires_rerun():
    plan = build_change_impact_plan(
        [_manifest()],
        _revisions(),
        _revisions(policy="policy-r2"),
    )

    assert plan.status == IMPACT_RERUN_REQUIRED
    assert plan.evidence[0].changed_dependencies == ("policy",)
    assert plan.evidence[0].reasons == ("changed_dependency:policy",)


def test_path_change_requires_rerun_even_when_revision_map_has_not_changed():
    plan = build_change_impact_plan(
        [_manifest()],
        _revisions(),
        _revisions(),
        ["policies/release-policy.json"],
    )

    assert plan.status == IMPACT_RERUN_REQUIRED
    assert plan.evidence[0].changed_paths == ("policies/release-policy.json",)


def test_existing_blocked_evidence_stays_blocked():
    manifest = _manifest(
        evidence={
            "scope": ["release-agent-v1"],
            "digest": "sha256:" + "a" * 64,
            "expires_at": "2026-12-01T00:00:00Z",
            "observed_outcome": "failed",
        }
    )
    plan = build_change_impact_plan([manifest], _revisions(), _revisions())

    assert plan.status == IMPACT_BLOCKED
    assert plan.evidence[0].status == IMPACT_BLOCKED


def test_registry_scopes_rerun_to_registered_dependencies():
    registry = {
        "run-synthetic-001": EvidenceRegistration(
            evidence_id="run-synthetic-001",
            decision_target="release-agent-v1",
            dependency_scope=("policy",),
            check_ids=("authorization-negative-controls",),
            owner_id="assurance-team",
        )
    }
    plan = build_change_impact_plan(
        [_manifest()],
        _revisions(),
        _revisions(tools="tools-r2"),
        registry=registry,
    )

    assert plan.status == IMPACT_READY
    assert plan.evidence[0].rerun_checks == ()


def test_registry_adds_named_checks_for_affected_evidence():
    registry = {
        "run-synthetic-001": EvidenceRegistration(
            evidence_id="run-synthetic-001",
            decision_target="release-agent-v1",
            dependency_scope=("policy", "tools"),
            check_ids=("authorization-negative-controls", "tool-safety-regression"),
            owner_id="assurance-team",
        )
    }
    plan = build_change_impact_plan(
        [_manifest()],
        _revisions(),
        _revisions(policy="policy-r2"),
        registry=registry,
    )

    assert plan.status == IMPACT_RERUN_REQUIRED
    assert plan.evidence[0].rerun_checks == (
        "authorization-negative-controls",
        "tool-safety-regression",
    )
    assert plan.evidence[0].owner_id == "assurance-team"


def test_affected_evidence_without_registry_entry_is_blocked():
    plan = build_change_impact_plan(
        [_manifest()],
        _revisions(),
        _revisions(policy="policy-r2"),
        registry={},
    )

    assert plan.status == IMPACT_BLOCKED
    assert plan.evidence[0].reasons == ("evidence_registry_missing",)
