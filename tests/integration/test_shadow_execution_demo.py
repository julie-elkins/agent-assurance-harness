import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "shadow_execution_demo.py"
MANIFEST = ROOT / "examples" / "shadow-execution" / "manifest.json"


def test_shadow_demo_emits_expected_metadata_only_report() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--manifest",
            str(MANIFEST),
            "--fail-on-block",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    data = json.loads(result.stdout)
    assert data["passed"] is True
    assert data["case_count"] == 5
    assert data["decision_counts"] == {
        "allow": 1,
        "block": 1,
        "human_review": 3,
    }
    assert all(
        case["receipt"]["controls"]["real_side_effects_attempted"] is False
        for case in data["cases"]
    )
    assert "diagnostics" in data
    assert "what_it_does_not_show" in data["diagnostics"]


def test_shadow_demo_writes_markdown_summary(tmp_path: Path) -> None:
    output = tmp_path / "shadow.json"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--manifest",
            str(MANIFEST),
            "--output",
            str(output),
            "--markdown",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "# Shadow execution" in result.stdout
    assert "| `missing-authority` | `block` |" in result.stdout
    assert json.loads(output.read_text(encoding="utf-8"))["passed"] is True
