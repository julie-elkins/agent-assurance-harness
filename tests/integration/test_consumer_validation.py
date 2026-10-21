import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "consumer_validation.py"


def test_consumer_fixture_passes_and_catches_negative_control(tmp_path):
    output = tmp_path / "consumer-validation.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
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
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["passed"] is True
    assert data["action_ref"] == "5141cf58695a4ed4f45bfbcf106ce559340c61aa"
    assert all(data["workflow_contract"].values())
    assert data["positive_run"]["decision"] == "pass"
    assert data["positive_run"]["passed"] is True
    assert data["positive_run"]["consumer_contract_passed"] is True
    assert data["negative_control"]["decision"] == "blocked"
    assert data["negative_control"]["passed"] is False
    assert data["negative_control"]["consumer_contract_passed"] is False
    assert "authorization_scope_missing" in (
        data["negative_control"]["consumer_contract_failure_reasons"]
    )
    assert "escalation_missing" in (
        data["negative_control"]["consumer_contract_failure_reasons"]
    )
    assert data["negative_control"]["caught"] is True
    replay = data["policy_drift_replay"]
    assert replay["drifted"]["decision"] == "blocked"
    assert replay["drifted"]["caught"] is True
    assert replay["drifted"]["consumer_contract_failure_reasons"] == [
        "policy_version_mismatch",
        "policy_digest_mismatch",
    ]
    assert replay["approved_after"]["decision"] == "pass"
    assert replay["approved_after"]["restored"] is True
    assert replay["rollback_restored"] is True
    provenance = data["policy_replay_provenance"]
    assert provenance["passed"] is True
    assert provenance["git_commit"] == subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY,
        text=True,
    ).strip()
    assert provenance["action_ref"] == data["action_ref"]
    assert (
        provenance["manifest_fingerprints"]["approved_sha256"]
        != provenance["manifest_fingerprints"]["drifted_sha256"]
    )
    assert len(provenance["manifest_fingerprints"]["approved_sha256"]) == 64
    assert len(provenance["manifest_fingerprints"]["drifted_sha256"]) == 64
    assert [item["decision"] for item in provenance["state_sequence"]] == [
        "pass",
        "blocked",
        "pass",
    ]
    assert str(REPOSITORY) not in output.read_text(encoding="utf-8")
    assert "guarded_adapter.py" not in output.read_text(encoding="utf-8")


def test_consumer_workflow_uses_fixed_action_revision():
    workflow = (
        REPOSITORY
        / "examples"
        / "consumer-repository"
        / ".github"
        / "workflows"
        / "assurance.yml"
    ).read_text(encoding="utf-8")

    assert "@main" not in workflow
    assert workflow.count(
        "@5141cf58695a4ed4f45bfbcf106ce559340c61aa"
    ) == 2
