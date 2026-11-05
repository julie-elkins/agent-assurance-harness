import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "shadow_reauthorization_demo.py"


def test_shadow_reauthorization_demo_compares_provider_lanes() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--fail-on-findings",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    data = json.loads(result.stdout)
    assert data["passed"] is True
    assert data["provider_count"] == 2
    assert data["decision_counts"]["current"]["reauthorized"] == 2
    assert data["decision_counts"]["changed"]["reauthorization_required"] == 2
    assert all(
        item["shadow_decision"] == "allow" for item in data["results"]
    )
    assert all(
        item["current"]["supports_decision"] is True
        for item in data["results"]
    )
    assert all(
        item["changed"]["supports_decision"] is False
        for item in data["results"]
    )


def test_shadow_reauthorization_demo_markdown_is_reviewable() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--markdown",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "# Shadow reauthorization" in result.stdout
    assert "`reauthorized`" in result.stdout
    assert "`reauthorization_required`" in result.stdout
    assert "real tool action" in result.stdout
