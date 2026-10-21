import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
CONSUMER_TOOL = REPOSITORY / "tools" / "consumer_validation.py"
VERIFY_TOOL = REPOSITORY / "tools" / "verify_consumer_provenance.py"


def _consumer_report(path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(CONSUMER_TOOL),
            "--output",
            str(path),
            "--fail-on-block",
        ],
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0


def _verify(report: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VERIFY_TOOL),
            "--report",
            str(report),
            "--fail-on-unverified",
        ],
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )


def test_verifier_recomputes_current_consumer_provenance(tmp_path):
    report = tmp_path / "consumer-validation.json"
    _consumer_report(report)

    completed = _verify(report)

    assert completed.returncode == 0
    result = json.loads(completed.stdout)
    assert result["verified"] is True
    assert result["consumer_validation_version"] == 3
    assert result["rollback_restored"] is True
    assert [item["decision"] for item in result["state_sequence"]] == [
        "pass",
        "blocked",
        "pass",
    ]


def test_verifier_blocks_tampered_git_identity(tmp_path):
    report = tmp_path / "consumer-validation.json"
    _consumer_report(report)
    data = json.loads(report.read_text(encoding="utf-8"))
    data["policy_replay_provenance"]["git_commit"] = "0" * 40
    report.write_text(json.dumps(data), encoding="utf-8")

    completed = _verify(report)

    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result["verified"] is False
    assert result["error"] == "consumer_provenance_verification_failed"


def test_verifier_blocks_tampered_manifest_fingerprint(tmp_path):
    report = tmp_path / "consumer-validation.json"
    _consumer_report(report)
    data = json.loads(report.read_text(encoding="utf-8"))
    data["policy_replay_provenance"]["manifest_fingerprints"][
        "approved_sha256"
    ] = "0" * 64
    report.write_text(json.dumps(data), encoding="utf-8")

    completed = _verify(report)

    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result["verified"] is False
    assert "fingerprint" in result["message"]
