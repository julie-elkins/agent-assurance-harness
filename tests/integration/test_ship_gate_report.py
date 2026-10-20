import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "ship_gate_report.py"
MANIFEST = REPOSITORY / "examples" / "ship-gate.json"


def _report(
    *,
    passed: bool,
    findings: list[dict[str, object]] | None = None,
    drifts: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "passed": passed,
        "refusal": None,
        "findings": findings if findings is not None else [],
        "drifts": drifts if drifts is not None else [],
    }


def _run(tmp_path: Path, *, block: bool = False) -> subprocess.CompletedProcess[str]:
    positive_regression = tmp_path / "positive-regression.json"
    positive_golden = tmp_path / "positive-golden.json"
    negative_regression = tmp_path / "negative-regression.json"
    negative_golden = tmp_path / "negative-golden.json"
    output = tmp_path / "ship-gate.json"
    positive_regression.write_text(
        json.dumps(_report(passed=True)),
        encoding="utf-8",
    )
    positive_golden.write_text(
        json.dumps(_report(passed=True)),
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
