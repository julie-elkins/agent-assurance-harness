import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent_reliability_lab.reauthorization_record import canonical_digest


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "reauthorization_record.py"


def test_reauthorization_record_cli_validates_positive_example(tmp_path):
    rerun_result = json.loads(
        (ROOT / "examples" / "reauthorization-record" / "rerun-result.json").read_text()
    )
    record = json.loads(
        (ROOT / "examples" / "reauthorization-record" / "record.json").read_text()
    )
    output_path = tmp_path / "validation.json"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--record",
            str(ROOT / "examples" / "reauthorization-record" / "record.json"),
            "--rerun-result",
            str(ROOT / "examples" / "reauthorization-record" / "rerun-result.json"),
            "--now",
            "2026-11-10T12:00:00Z",
            "--output",
            str(output_path),
            "--fail-on-nonreusable",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert result.returncode == 0
    assert data["status"] == "reauthorized"
    assert data["reusable"] is True
    assert data["rerun_result_digest"] == canonical_digest(rerun_result)
    assert data["validated_at"] == "2026-11-10T12:00:00Z"
    assert "reports" not in data
    assert "prompts" not in result.stdout
    assert record["decision"] == "reauthorized"
