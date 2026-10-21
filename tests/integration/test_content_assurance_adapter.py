import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "custom_pack_report.py"
PACKS = REPOSITORY / "examples" / "content-assurance-packs"
ADAPTER = REPOSITORY / "examples" / "content_assurance_adapter.py"


def test_content_assurance_adapter_passes_all_reference_packs(tmp_path):
    output = tmp_path / "content-conformance.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--pack-directory",
            str(PACKS),
            "--agent-id",
            "content-assurance-reference",
            "--adapter-command",
            sys.executable,
            "--adapter-command",
            str(ADAPTER),
            "--output",
            str(output),
            "--fail-on-findings",
        ],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(completed.stdout)
    assert report["conformance_id"] == "custom-pack-conformance-v2"
    assert report["passed"] is True
    assert report["pack_count"] == 4
    assert report["refusal_count"] == 0
    assert json.loads(output.read_text(encoding="utf-8")) == report
