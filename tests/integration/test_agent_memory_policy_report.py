import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "agent_memory_policy_report.py"


def test_memory_policy_report_is_metadata_only_and_passes(tmp_path):
    output = tmp_path / "memory-policy.json"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--output",
            str(output),
            "--fail-on-findings",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(result.stdout)
    assert report["passed"] is True
    assert report["lane_id"] == "agent_memory_policy"
    assert report["case_count"] == 4
    assert report["negative_control"]["caught"] is True
    serialized = output.read_text(encoding="utf-8")
    assert "memory-authorization" not in serialized
    assert "raw_tool_result" not in serialized
    assert json.loads(serialized) == report


def test_memory_policy_markdown_names_the_safety_boundary():
    result = subprocess.run(
        [sys.executable, str(TOOL), "--markdown"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Bounded Synthetic Agent Memory Policy" in result.stdout
    assert "required-evidence discard" in result.stdout
    assert "live provider cache savings" in result.stdout
