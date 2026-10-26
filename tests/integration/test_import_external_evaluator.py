import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).parents[2]
TOOL = ROOT / "tools" / "import_external_evaluator.py"
MANIFEST = ROOT / "examples" / "run-manifest" / "manifest.json"
CURRENT = ROOT / "examples" / "run-manifest" / "current-revisions.json"


def test_inspect_and_petri_shapes_import_to_the_same_report_contract(tmp_path):
    for source_system in ("inspect", "petri"):
        result_path = (
            ROOT
            / "examples"
            / "external-evaluator"
            / f"{source_system}-result.json"
        )
        output = tmp_path / f"{source_system}-import.json"
        safety_case = tmp_path / f"{source_system}-safety-case.json"
        result = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--input",
                str(result_path),
                "--manifest",
                str(MANIFEST),
                "--current-revisions",
                str(CURRENT),
                "--output",
                str(output),
                "--safety-case-output",
                str(safety_case),
                "--fail-on-review",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        report = json.loads(output.read_text(encoding="utf-8"))
        assert report["source_system"] == source_system
        assert report["import_status"] == "accepted"
        assert report["monitorability_report"]["status"] == (
            "ready_for_human_review"
        )
        assert report["safety_case"]["required_human_review"] is True
        assert "prompts" not in result.stdout
        assert "transcripts" not in result.stdout
        assert "transcript" not in result.stdout
        assert "tool_payload" not in result.stdout


def test_import_cli_refuses_wrong_revision_digest(tmp_path):
    source = json.loads(
        (
            ROOT
            / "examples"
            / "external-evaluator"
            / "inspect-result.json"
        ).read_text(encoding="utf-8")
    )
    source["revision_digest"] = "sha256:" + ("d" * 64)
    input_path = tmp_path / "wrong-revision.json"
    output = tmp_path / "import.json"
    safety_case = tmp_path / "safety-case.json"
    input_path.write_text(json.dumps(source), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--input",
            str(input_path),
            "--manifest",
            str(MANIFEST),
            "--current-revisions",
            str(CURRENT),
            "--output",
            str(output),
            "--safety-case-output",
            str(safety_case),
            "--fail-on-review",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["import_status"] == "blocked"
    assert report["reasons"] == ["external_evaluator_revision_mismatch"]
    assert not safety_case.exists()
    assert "external_evaluator_revision_mismatch" in result.stdout
