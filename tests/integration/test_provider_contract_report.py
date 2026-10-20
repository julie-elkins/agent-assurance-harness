import json
import subprocess
import sys
from pathlib import Path


REPOSITORY = Path(__file__).parents[2]
TOOL = REPOSITORY / "tools" / "provider_contract_report.py"
MANIFEST = REPOSITORY / "examples" / "provider-contract-manifest.json"
FIXTURE_ROOT = REPOSITORY / "tests" / "fixtures" / "provider_contracts"


def test_provider_contract_report_passes_and_writes_metadata(tmp_path):
    output = tmp_path / "provider-contract.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(TOOL),
            "--manifest",
            str(MANIFEST),
            "--fixture-root",
            str(FIXTURE_ROOT),
            "--output",
            str(output),
            "--fail-on-drift",
        ],
        cwd=REPOSITORY,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0
    data = json.loads(completed.stdout)
    assert data["passed"] is True
    assert all(item["caught"] for item in data["negative_controls"])
    assert "synthetic raw provider text" not in completed.stdout
