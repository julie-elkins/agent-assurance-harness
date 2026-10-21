import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "refresh_public_sources.py"


def test_refresh_cli_writes_a_metadata_manifest(tmp_path):
    output = tmp_path / "public-sources.json"
    result = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--output",
            str(output),
            "--timeout-seconds",
            "0.001",
        ],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        check=True,
    )

    report = json.loads(output.read_text(encoding="utf-8"))
    assert "sources" in report
    assert "refusals" in report
    assert "private" not in result.stdout.lower()
    assert "response body" not in result.stdout.lower()
