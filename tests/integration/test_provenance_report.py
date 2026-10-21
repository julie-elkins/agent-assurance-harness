import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "provenance_report.py"


def test_provenance_report_verifies_metadata_only_subjects(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    wheel = artifacts / "agent-reliability-lab-0.48.0-py3-none-any.whl"
    source = artifacts / "agent-reliability-lab-0.48.0.tar.gz"
    wheel.write_bytes(b"synthetic wheel")
    source.write_bytes(b"synthetic source distribution")
    fake_gh = tmp_path / "gh"
    fake_gh.write_text(
        """#!/usr/bin/env python3
import hashlib
import json
import pathlib
import sys

artifact = pathlib.Path(sys.argv[3])
digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
print(json.dumps([{
    "verificationResult": {
        "statement": {
            "predicateType": "https://slsa.dev/provenance/v1",
            "subject": [{"name": artifact.name, "digest": {"sha256": digest}}],
        }
    }
}]))
""",
        encoding="utf-8",
    )
    fake_gh.chmod(
        stat.S_IRUSR
        | stat.S_IWUSR
        | stat.S_IXUSR
        | stat.S_IRGRP
        | stat.S_IXGRP
        | stat.S_IROTH
        | stat.S_IXOTH
    )
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    output = tmp_path / "provenance.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--artifact-directory",
            str(artifacts),
            "--repository",
            "julie-elkins/agent-assurance-harness",
            "--signer-workflow",
            "github.com/julie-elkins/agent-assurance-harness/"
            ".github/workflows/reliability.yml",
            "--source-digest",
            "a" * 40,
            "--output",
            str(output),
            "--fail-on-findings",
        ],
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    data = json.loads(completed.stdout)
    assert data["passed"] is True
    assert data["subject_count"] == 2
    assert all(item["verified"] for item in data["subjects"])
    assert "synthetic wheel" not in completed.stdout
    assert str(tmp_path) not in completed.stdout
    assert json.loads(output.read_text(encoding="utf-8")) == data
