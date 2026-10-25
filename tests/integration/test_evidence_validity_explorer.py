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
