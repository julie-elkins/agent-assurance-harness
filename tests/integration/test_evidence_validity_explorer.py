import json
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
EXPLORER_TOOL = ROOT / "tools" / "evidence_validity_explorer.py"
MANIFEST = ROOT / "examples" / "run-manifest" / "manifest.json"
CURRENT = ROOT / "examples" / "run-manifest" / "current-revisions.json"
CHANGED = ROOT / "examples" / "run-manifest" / "changed-revisions.json"
POLICY_CHANGED = ROOT / "examples" / "change-impact" / "current-revisions.json"
REGISTRY = ROOT / "examples" / "change-impact" / "evidence-registry.json"
MONITORABILITY_CASES = ROOT / "examples" / "monitorability" / "cases.json"
PROVENANCE = ROOT / "examples" / "run-manifest" / "evidence-provenance.json"
MISSING_PROVENANCE = (
    ROOT / "examples" / "run-manifest" / "evidence-provenance-missing.json"
)
_SPEC = importlib.util.spec_from_file_location(
    "evidence_validity_explorer",
    EXPLORER_TOOL,
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
ExplorerData = _MODULE.ExplorerData
render_explorer = _MODULE.render_explorer


def test_explorer_renders_current_and_changed_decisions(tmp_path):
    output = tmp_path / "evidence-validity-explorer.html"

    result = subprocess.run(
        [
            sys.executable,
            str(EXPLORER_TOOL),
            "--manifest",
            str(MANIFEST),
            "--current-revisions",
            str(CURRENT),
            "--changed-revisions",
            str(CHANGED),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    rendered = output.read_text(encoding="utf-8")
    assert "Evidence Validity Explorer" in rendered
    assert "reauthorized" in rendered
    assert "reauthorization required" in rendered
    assert "prompt" in rendered
    assert "tools" in rendered
    assert "provider_output" not in rendered
    assert "credentials" not in rendered
    assert "explorer written" in result.stderr


def test_explorer_renders_four_step_assurance_story(tmp_path):
    output = tmp_path / "assurance-story.html"

    result = subprocess.run(
        [
            sys.executable,
            str(EXPLORER_TOOL),
            "--manifest",
            str(MANIFEST),
            "--current-revisions",
            str(CURRENT),
            "--changed-revisions",
            str(CHANGED),
            "--provenance",
            str(PROVENANCE),
            "--missing-provenance",
            str(MISSING_PROVENANCE),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    rendered = output.read_text(encoding="utf-8")
    assert "The five-minute assurance story" in rendered
    assert "evidence observed" in rendered
    assert "reauthorization required" in rendered
    assert "evidence missing" in rendered
    assert "Reuse is blocked until a producer records evidence." in rendered
    assert "grader_calibration_status" not in rendered
    assert "provider_output" not in rendered
    assert "explorer written" in result.stderr


def test_explorer_renders_provider_receipts_and_stale_negative_control(tmp_path):
    receipt = tmp_path / "provider-receipt.json"
    output = tmp_path / "provider-story.html"

    receipt_result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "provider_evidence_receipt.py"),
            "--provider",
            "all",
            "--evidence-id",
            "run-synthetic-001",
            "--registry",
            str(REGISTRY),
            "--revisions",
            str(CURRENT),
            "--output",
            str(receipt),
            "--fail-on-refusal",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert '"passed": true' in receipt.read_text(encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(EXPLORER_TOOL),
            "--manifest",
            str(MANIFEST),
            "--current-revisions",
            str(CURRENT),
            "--changed-revisions",
            str(POLICY_CHANGED),
            "--registry",
            str(REGISTRY),
            "--receipt",
            str(receipt),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    rendered = output.read_text(encoding="utf-8")
    assert "Provider receipts become a rerun plan" in rendered
    assert "anthropic" in rendered
    assert "openai" in rendered
    assert "rerun_required" in rendered
    assert "authorization-negative-controls" in rendered
    assert "Stale receipt negative control: blocked" in rendered
    assert "provider_receipt_revision_mismatch" in rendered
    assert "provider requests or responses" not in rendered
    assert "explorer written" in result.stderr
    assert receipt_result.stdout


def test_explorer_renders_monitorability_and_safety_case(tmp_path):
    monitorability_report = tmp_path / "monitorability-report.json"
    safety_case = tmp_path / "safety-case.json"
    negative_control = tmp_path / "negative-control.json"
    output = tmp_path / "monitorability-explorer.html"

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "monitorability_workbench.py"),
            "--cases",
            str(MONITORABILITY_CASES),
            "--manifest",
            str(MANIFEST),
            "--current-revisions",
            str(CURRENT),
            "--decision-target",
            "release-agent-v1",
            "--output",
            str(monitorability_report),
            "--safety-case-output",
            str(safety_case),
            "--negative-control-output",
            str(negative_control),
            "--fail-on-review",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [
            sys.executable,
            str(EXPLORER_TOOL),
            "--manifest",
            str(MANIFEST),
            "--current-revisions",
            str(CURRENT),
            "--changed-revisions",
            str(CHANGED),
            "--monitorability-report",
            str(monitorability_report),
            "--monitorability-negative-control",
            str(negative_control),
            "--safety-case",
            str(safety_case),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    rendered = output.read_text(encoding="utf-8")
    assert "Can the safety measurement system be trusted?" in rendered
    assert "Held-out recall" in rendered
    assert "Benign false positives" in rendered
    assert "Evaluator accuracy" in rendered
    assert "Awareness gap" in rendered
    assert "Held-out miss negative control:" in rendered
    assert "review_required" in rendered
    assert "supports_human_review" in rendered
    assert "tool-misuse" not in rendered
    assert "explorer written" in result.stderr


def test_explorer_escapes_revision_identifiers():
    from agent_reliability_lab.run_manifest import (
        load_current_revisions,
        load_manifest,
    )

    manifest = load_manifest(str(MANIFEST))
    current = load_current_revisions(str(CURRENT))
    changed = load_current_revisions(str(CHANGED))
    changed["prompt"] = "<script>alert(1)</script>"
    rendered = render_explorer(
        ExplorerData.from_inputs(manifest, current, changed),
        manifest_name="manifest.json",
        current_name="current.json",
        changed_name="changed.json",
    )

    assert "<script>" not in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


def test_explorer_refuses_incomplete_manifest(tmp_path):
    manifest = tmp_path / "manifest.json"
    current = tmp_path / "current.json"
    changed = tmp_path / "changed.json"
    output = tmp_path / "explorer.html"
    manifest.write_text(json.dumps({"manifest_version": 1}), encoding="utf-8")
    current.write_text("{}", encoding="utf-8")
    changed.write_text("{}", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(EXPLORER_TOOL),
            "--manifest",
            str(manifest),
            "--current-revisions",
            str(current),
            "--changed-revisions",
            str(changed),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "evidence_validity_explorer_refused" in result.stderr
    assert not output.exists()
