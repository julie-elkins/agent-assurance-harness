import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_showcase_demo_is_offline_and_passes():
    result = subprocess.run(
        [sys.executable, "tools/showcase_demo.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["offline"] is True
    assert report["synthetic_assurance"]["guarded_agent_passed"] is True
    assert report["synthetic_assurance"]["evaluator_controls_caught"]
    assert report["synthetic_assurance"]["mutation_controls_caught"]
    assert report["course_doctor"]["passed"] is True
    assert report["launch_to_field"]["passed"] is True
    assert len(report["launch_to_field"]["degraded_controls_caught"]) == 4
    assert report["memory_policy"]["passed"] is True
    assert report["memory_policy"]["negative_control"]["caught"] is True
    assert report["synthetic_finding_example"]["reason_code"] == "evidence_stale"
    assert (
        report["synthetic_finding_example"]["claim_id"]
        == "claim-pipeline-supported"
    )
    assert "lesson-001.md" not in result.stdout
    assert "Synthetic agent lesson" not in result.stdout


def test_showcase_markdown_explains_where_review_starts():
    result = subprocess.run(
        [sys.executable, "tools/showcase_demo.py", "--markdown"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Example blocked finding (synthetic)" in result.stdout
    assert "Source is older than the allowed freshness window." in result.stdout
    assert "Claim: `claim-pipeline-supported`" in result.stdout
    assert "Section: `section-synthetic-guidance`" in result.stdout
    assert "Launch-to-field enablement" in result.stdout
    assert "Degraded controls caught: `4`" in result.stdout
    assert "Bounded synthetic agent memory policy" in result.stdout
    assert "Required evidence is retained" in result.stdout
    assert "lesson-001.md" not in result.stdout


def test_muse_ember_evidence_gate_demo_is_offline_by_default():
    result = subprocess.run(
        [sys.executable, "tools/muse_ember_evidence_gate_demo.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["offline"]["guarded_agent_passed"] is True
    assert report["offline"]["evaluator_controls_caught"]
    assert report["offline"]["mutation_controls_caught"]
    assert report["live"] is None
    assert report["controls"]["metadata_only"] is True
    assert report["controls"]["synthetic_inputs_only"] is True
    assert report["controls"]["raw_provider_output_retained"] is False
    assert report["controls"]["network_called"] is False


def test_muse_ember_evidence_gate_demo_requires_explicit_live_ceilings():
    result = subprocess.run(
        [
            sys.executable,
            "tools/muse_ember_evidence_gate_demo.py",
            "--live",
            "--allow-network",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--max-requests" in result.stderr
    assert "MODEL_API_KEY" not in result.stderr
