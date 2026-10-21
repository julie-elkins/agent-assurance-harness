import hashlib
import json

from agent_reliability_lab.release_promotion import evaluate_release_promotion


REPOSITORY = "julie-elkins/agent-assurance-harness"
SIGNER_WORKFLOW = (
    "github.com/julie-elkins/agent-assurance-harness/"
    ".github/workflows/reliability.yml"
)
COMMIT = "a" * 40
PACKAGE_VERSION = "0.59.0"


def _write_evidence(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    wheel = artifacts / f"agent_reliability_lab-{PACKAGE_VERSION}-py3-none-any.whl"
    source = artifacts / f"agent_reliability_lab-{PACKAGE_VERSION}.tar.gz"
    wheel.write_bytes(b"synthetic wheel")
    source.write_bytes(b"synthetic source distribution")
    wheel_digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()

    provenance = {
        "provenance_version": 1,
        "passed": True,
        "repository": REPOSITORY,
        "signer_workflow": SIGNER_WORKFLOW,
        "source_digest": COMMIT,
        "predicate_type": "https://slsa.dev/provenance/v1",
        "subjects": [
            {"name": source.name, "sha256": source_digest, "verified": True},
            {"name": wheel.name, "sha256": wheel_digest, "verified": True},
        ],
    }
    release_manifest = {
        "release_artifact_version": 1,
        "passed": True,
        "git_commit": COMMIT,
        "package_version": PACKAGE_VERSION,
        "artifact_output_persisted": True,
        "sbom_persisted": True,
        "artifact_names": [source.name, wheel.name],
        "artifacts": {
            "source_distribution_sha256": source_digest,
            "wheel_sha256": wheel_digest,
        },
    }
    rollback = {
        "rollback_rehearsal_version": 1,
        "passed": True,
        "git_commit": COMMIT,
        "failure_injection": {"applied": True, "detected": True},
        "recovery": {"restored_match": True},
        "side_effects": {
            "external_writes_attempted": False,
            "network_used": False,
        },
    }
    paths = {}
    for name, value in (
        ("provenance.json", provenance),
        ("release-manifest.json", release_manifest),
        ("rollback.json", rollback),
    ):
        path = tmp_path / name
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = path
    return artifacts, paths


def _evaluate(tmp_path, artifacts, paths):
    return evaluate_release_promotion(
        artifact_directory=artifacts,
        provenance_path=paths["provenance.json"],
        release_manifest_path=paths["release-manifest.json"],
        rollback_path=paths["rollback.json"],
        repository=REPOSITORY,
        signer_workflow=SIGNER_WORKFLOW,
        source_digest=COMMIT,
        approved_by="julie-elkins",
        approval_id="release-2026-10-20",
        environment="release",
    )


def test_release_promotion_requires_verified_current_evidence(tmp_path):
    artifacts, paths = _write_evidence(tmp_path)

    report = _evaluate(tmp_path, artifacts, paths)

    assert report.passed is True
    assert report.decision == "promote"
    assert all(item.local_match for item in report.artifacts)
    assert "artifact contents" in report.to_dict()["diagnostics"]["what_it_does_not_show"]


def test_release_promotion_blocks_tampered_artifact(tmp_path):
    artifacts, paths = _write_evidence(tmp_path)
    wheel = next(artifacts.glob("*.whl"))
    wheel.write_bytes(b"tampered wheel")

    report = _evaluate(tmp_path, artifacts, paths)

    assert report.passed is False
    assert any(
        reason.startswith("artifact-hash-mismatch:")
        for reason in report.blocking_reasons
    )


def test_release_promotion_blocks_wrong_source_commit(tmp_path):
    artifacts, paths = _write_evidence(tmp_path)
    data = json.loads(paths["provenance.json"].read_text(encoding="utf-8"))
    data["source_digest"] = "b" * 40
    paths["provenance.json"].write_text(json.dumps(data), encoding="utf-8")

    report = _evaluate(tmp_path, artifacts, paths)

    assert report.passed is False
    assert "provenance-report-invalid" in report.blocking_reasons
