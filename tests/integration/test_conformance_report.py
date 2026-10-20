import json
import sys
from pathlib import Path

from agent_reliability_lab.conformance import run_adapter_conformance
from agent_reliability_lab.external import SubprocessAdapter


def test_external_example_passes_public_conformance_contract():
    adapter = SubprocessAdapter(
        agent_id="external",
        command=(
            sys.executable,
            str(Path(__file__).parents[2] / "examples" / "guarded_adapter.py"),
        ),
    )

    report = run_adapter_conformance(adapter)
    data = report.to_dict()

    assert report.conformance_passed
    assert data["scenario_count"] == 5
    assert data["refusal_count"] == 0
    assert data["mutation_controls"] == {
        "mutation_count": 3,
        "mutations_caught": 3,
    }
    serialized = json.dumps(data)
    assert "findings" not in serialized
    assert '"trace":' not in serialized
