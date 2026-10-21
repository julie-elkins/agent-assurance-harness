import hashlib
import json
import subprocess

from agent_reliability_lab import provenance


def _verification_payload(name: str, digest: str) -> str:
    return json.dumps(
        [
            {
                "verificationResult": {
                    "statement": {
                        "predicateType": provenance.SLSA_PROVENANCE,
                        "subject": [
                            {
                                "name": name,
                                "digest": {"sha256": digest},
                            }
                        ],
                    }
                }
            }
        ]
    )


def test_provenance_verification_requires_exact_artifact_subjects(
    tmp_path,
    monkeypatch,
):
    artifact = tmp_path / "agent-reliability-lab-0.47.0-py3-none-any.whl"
    artifact.write_bytes(b"synthetic wheel")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            _verification_payload(artifact.name, digest),
            "",
        )

    monkeypatch.setattr(provenance.subprocess, "run", fake_run)

    report = provenance.run_provenance_verification(
        tmp_path,
        repository="julie-elkins/agent-assurance-harness",
        signer_workflow=(
            "github.com/julie-elkins/agent-assurance-harness/"
            ".github/workflows/reliability.yml"
        ),
        source_digest="a" * 40,
    )

    assert report.passed is True
    assert report.subjects[0].verified is True
    assert "--signer-workflow" in commands[0]
    assert "--source-digest" in commands[0]
    serialized = json.dumps(report.to_dict())
    assert "synthetic wheel" not in serialized
    assert str(tmp_path) not in serialized


def test_provenance_verification_blocks_subject_digest_mismatch(
    tmp_path,
    monkeypatch,
):
    artifact = tmp_path / "agent-reliability-lab-0.47.0.tar.gz"
    artifact.write_bytes(b"synthetic source distribution")

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(
            command,
            0,
            _verification_payload(artifact.name, "0" * 64),
            "",
        )

    monkeypatch.setattr(provenance.subprocess, "run", fake_run)

    report = provenance.run_provenance_verification(
        tmp_path,
        repository="julie-elkins/agent-assurance-harness",
        signer_workflow="github.com/julie-elkins/agent-assurance-harness/workflow",
        source_digest="b" * 40,
    )

    assert report.passed is False
    assert report.subjects[0].failure_code == "subject_digest_mismatch"
