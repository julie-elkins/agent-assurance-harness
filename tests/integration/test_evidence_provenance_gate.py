import json
import subprocess
import sys
from pathlib import Path

from agent_reliability_lab.evidence_provenance import (
    EVIDENCE_PROVENANCE_BLOCKED,
    EVIDENCE_PROVENANCE_MISSING,
    EVIDENCE_PROVENANCE_OBSERVED,
)


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "evidence_provenance_gate.py"
MANIFEST = ROOT / "examples" / "run-manifest" / "manifest.json"
OBSERVED = ROOT / "examples" / "run-manifest" / "evidence-provenance.json"
MISSING = ROOT / "examples" / "run-manifest" / "evidence-provenance-missing.json"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_gate_accepts_observed_metadata_only_evidence():
    result = _run(
        "--manifest",
        str(MANIFEST),
        "--provenance",
        str(OBSERVED),
        "--fail-on-missing",
    )

    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["status"] == EVIDENCE_PROVENANCE_OBSERVED
    assert data["supports_evidence"] is True
    assert "provider" not in result.stdout
    assert "credentials" not in result.stdout


def test_gate_blocks_missing_evidence_negative_control():
    result = _run(
        "--manifest",
        str(MANIFEST),
        "--provenance",
        str(MISSING),
        "--fail-on-missing",
    )

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == EVIDENCE_PROVENANCE_MISSING
    assert data["supports_evidence"] is False
    assert data["reasons"] == ["evidence_artifact_not_observed"]


def test_gate_blocks_mismatched_manifest_digest(tmp_path):
    provenance = tmp_path / "provenance.json"
    data = json.loads(OBSERVED.read_text(encoding="utf-8"))
    data["manifest_digest"] = "sha256:" + "c" * 64
    provenance.write_text(json.dumps(data), encoding="utf-8")

    result = _run(
        "--manifest",
        str(MANIFEST),
        "--provenance",
        str(provenance),
        "--fail-on-missing",
    )

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["status"] == EVIDENCE_PROVENANCE_BLOCKED
    assert data["reasons"] == ["manifest_digest_mismatch"]


def test_gate_refuses_invalid_provenance_without_writing_output(tmp_path):
    provenance = tmp_path / "provenance.json"
    output = tmp_path / "decision.json"
    provenance.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    result = _run(
        "--manifest",
        str(MANIFEST),
        "--provenance",
        str(provenance),
        "--output",
        str(output),
    )

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["refusal"]["error"] == "evidence_provenance_refused"
    assert data["status"] == EVIDENCE_PROVENANCE_BLOCKED
    assert not output.exists()
