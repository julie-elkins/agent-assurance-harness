import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "release_promotion_report.py"


def test_release_promotion_report_is_metadata_only(tmp_path):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    wheel = artifacts / "agent_reliability_lab-0.48.0-py3-none-any.whl"
    source = artifacts / "agent_reliability_lab-0.48.0.tar.gz"
    wheel.write_bytes(b"synthetic wheel")
    source.write_bytes(b"synthetic source distribution")

    import hashlib

    wheel_digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    commit = "a" * 40
    repository = "julie-elkins/agent-assurance-harness"
    signer = (
        "github.com/julie-elkins/agent-assurance-harness/"
        ".github/workflows/reliability.yml"
    )
    provenance = {
        "provenance_version": 1,
        "passed": True,
        "repository": repository,
        "signer_workflow": signer,
        "source_digest": commit,
        "predicate_type": "https://slsa.dev/provenance/v1",
        "subjects": [
            {"name": source.name, "sha256": source_digest, "verified": True},
            {"name": wheel.name, "sha256": wheel_digest, "verified": True},
        ],
    }
    manifest = {
        "release_artifact_version": 1,
        "passed": True,
        "git_commit": commit,
        "package_version": "0.48.0",
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
        "git_commit": commit,
        "failure_injection": {"applied": True, "detected": True},
        "recovery": {"restored_match": True},
        "side_effects": {
            "external_writes_attempted": False,
            "network_used": False,
        },
    }
    evidence = {}
    for filename, value in (
        ("provenance.json", provenance),
        ("manifest.json", manifest),
        ("rollback.json", rollback),
    ):
        path = tmp_path / filename
        path.write_text(json.dumps(value), encoding="utf-8")
        evidence[filename] = path
    output = tmp_path / "promotion.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--artifact-directory",
            str(artifacts),
            "--provenance-report",
            str(evidence["provenance.json"]),
            "--release-manifest",
            str(evidence["manifest.json"]),
            "--rollback-report",
            str(evidence["rollback.json"]),
            "--repository",
            repository,
            "--signer-workflow",
            signer,
            "--source-digest",
            commit,
            "--approved-by",
            "julie-elkins",
            "--approval-id",
            "release-2026-10-20",
            "--environment",
            "release",
            "--output",
            str(output),
            "--fail-on-block",
        ],
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    data = json.loads(completed.stdout)
    assert data["decision"] == "promote"
    assert data["approval"]["environment"] == "release"
    assert "synthetic wheel" not in completed.stdout
    assert str(tmp_path) not in completed.stdout
    assert json.loads(output.read_text(encoding="utf-8")) == data
