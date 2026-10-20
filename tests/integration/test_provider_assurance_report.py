import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "provider_assurance_report.py"


def test_provider_assurance_report_passes_and_writes_safe_metadata(tmp_path):
    output = tmp_path / "provider-assurance.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--output",
            str(output),
            "--fail-on-findings",
        ],
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    data = json.loads(completed.stdout)
    assert data["passed"] is True
    assert data["negative_control"]["caught"] is True
    assert output.exists()
    assert '"private"' not in completed.stdout
    assert '"prompt":' not in completed.stdout
