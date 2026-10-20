import json
import subprocess
import sys
import tomllib
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "ship_gate_report.py"
MANIFEST = REPOSITORY / "examples" / "ship-gate.json"
GOLDEN_MANIFEST = REPOSITORY / "examples" / "traces" / "golden-manifest.json"


def _current_identity() -> tuple[str, str]:
    package_data = tomllib.loads(
        (REPOSITORY / "pyproject.toml").read_text(encoding="utf-8")
    )
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return git_commit, package_data["project"]["version"]


def _report(
    *,
    passed: bool,
    findings: list[dict[str, object]] | None = None,
    drifts: list[dict[str, object]] | None = None,
    **extra: object,
) -> dict[str, object]:
    report = {
        "passed": passed,
        "refusal": None,
        "findings": findings if findings is not None else [],
        "drifts": drifts if drifts is not None else [],
    }
    report.update(extra)
    return report


def _run(tmp_path: Path, *, block: bool = False) -> subprocess.CompletedProcess[str]:
    positive_regression = tmp_path / "positive-regression.json"
    positive_golden = tmp_path / "positive-golden.json"
    negative_regression = tmp_path / "negative-regression.json"
    negative_golden = tmp_path / "negative-golden.json"
    provider_assurance = tmp_path / "provider-assurance.json"
    provider_contract = tmp_path / "provider-contract.json"
    rollback_rehearsal = tmp_path / "rollback-rehearsal.json"
    output = tmp_path / "ship-gate.json"
    git_commit, package_version = _current_identity()
    golden_manifest = json.loads(GOLDEN_MANIFEST.read_text(encoding="utf-8"))
    positive_regression.write_text(
        json.dumps(
            _report(
                passed=True,
                assurance_attestation={
                    "git_commit": git_commit,
                    "package_version": package_version,
                    "pack_set_sha256": golden_manifest["pack_set_sha256"],
                },
            )
        ),
        encoding="utf-8",
    )
    positive_golden.write_text(
        json.dumps(
            _report(
                passed=True,
                manifest=golden_manifest,
                candidate_trace_sha256=golden_manifest["trace_sha256"],
            )
        ),
        encoding="utf-8",
    )
    negative_regression.write_text(
        json.dumps(
            _report(
                passed=False,
                findings=[{"blocking": True, "finding": "synthetic"}],
            )
        ),
        encoding="utf-8",
    )
    negative_golden.write_text(
        json.dumps(
            _report(
                passed=False,
                drifts=[{"scenario_id": "synthetic"}],
            )
        ),
        encoding="utf-8",
    )
    provider_assurance.write_text(
        json.dumps(
            {
                "provider_assurance_version": 1,
                "passed": True,
                "providers": [
                    {"provider_id": "openai"},
                    {"provider_id": "anthropic"},
                ],
                "negative_control": {"caught": True},
            }
        ),
        encoding="utf-8",
    )
    provider_contract.write_text(
        json.dumps(
            {
                "provider_contract_version": 1,
                "passed": True,
                "contracts": [
                    {"provider_id": "openai"},
                    {"provider_id": "anthropic"},
                ],
                "negative_controls": [{"caught": True}],
            }
        ),
        encoding="utf-8",
    )
    rollback_rehearsal.write_text(
        json.dumps(
            {
                "rollback_rehearsal_version": 1,
                "passed": True,
                "failure_injection": {
                    "type": "synthetic-release-marker",
                    "applied": True,
                    "detected": True,
                },
                "recovery": {
                    "method": "git-archive-restore-rehearsal",
                    "target": "last-known-good-commit",
                    "original_tree_sha256": "d" * 64,
                    "failed_tree_sha256": "e" * 64,
                    "restored_tree_sha256": "d" * 64,
                    "restored_match": True,
                },
                "side_effects": {
                    "external_writes_attempted": False,
                    "network_used": False,
                },
                "verification": {"passed": True},
            }
        ),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        str(TOOL),
        "--gate",
        str(MANIFEST),
        "--adapter-regression-positive",
        str(positive_regression),
        "--golden-trace-positive",
        str(positive_golden),
        "--adapter-regression-negative-control",
        str(negative_regression),
        "--golden-trace-negative-control",
        str(negative_golden),
        "--provider-assurance",
        str(provider_assurance),
        "--provider-contract",
        str(provider_contract),
        "--rollback-rehearsal",
        str(rollback_rehearsal),
        "--output",
        str(output),
        "--fail-on-block",
    ]
    if block:
        negative_golden.write_text(
            json.dumps(_report(passed=False, drifts=[])),
            encoding="utf-8",
        )
    return subprocess.run(
        command,
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )


def test_ship_gate_report_returns_ready_for_expected_controls(tmp_path):
    completed = _run(tmp_path)

    assert completed.returncode == 0
    data = json.loads(completed.stdout)
    assert data["decision"] == "ready"
    assert data["blocking_reasons"] == []
    assert '"prompt"' not in completed.stdout


def test_ship_gate_report_blocks_when_negative_control_is_not_caught(tmp_path):
    completed = _run(tmp_path, block=True)

    assert completed.returncode == 1
    data = json.loads(completed.stdout)
    assert data["decision"] == "blocked"
    assert "golden-trace-negative-control:negative-control-not-caught" in data[
        "blocking_reasons"
    ]
